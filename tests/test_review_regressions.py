from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from company_agent import catalog
from company_agent.capabilities import _parse_capabilities
from company_agent.cli import main
from company_agent.invoke import invoke
from company_agent.jsonutil import StrictJsonError, loads
from company_agent.knowledge import search
from company_agent.sanitize import has_forbidden_output, validate_result_size
from company_agent.schema import SchemaError, validate_json_schema

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "child",
    [42, None, True, {"type": "string", "format": "uuid"}, {"type": "array", "items": None}],
)
@pytest.mark.parametrize("value", [{}, {"optional": "ignored-before-fix"}])
def test_schema_checks_absent_and_present_optional_branches(child, value) -> None:
    with pytest.raises(SchemaError):
        validate_json_schema(
            value,
            {
                "type": "object",
                "properties": {"optional": child},
                "additionalProperties": False,
            },
        )


@pytest.mark.parametrize("value", [1, [1], {"nested": 1}])
def test_schema_constants_distinguish_boolean_from_number(value) -> None:
    constant = True if value == 1 else [True] if isinstance(value, list) else {"nested": True}
    with pytest.raises(SchemaError, match="must equal"):
        validate_json_schema(value, {"const": constant})


def test_schema_uses_json_numeric_equality_and_pattern_search() -> None:
    with pytest.raises(SchemaError, match="unique items"):
        validate_json_schema([1, 1.0], {"type": "array", "items": {"type": "number"}, "uniqueItems": True})
    with pytest.raises(SchemaError, match="unique JSON values"):
        validate_json_schema(1, {"type": "number", "enum": [1, 1.0]})
    validate_json_schema(True, {"enum": [True, 1]})
    validate_json_schema("prefix_needle_suffix", {"type": "string", "pattern": "needle"})


@pytest.mark.parametrize("flag", [0, 1, [], {}, None])
def test_unique_items_requires_boolean(flag) -> None:
    with pytest.raises(SchemaError, match="uniqueItems must be a boolean"):
        validate_json_schema([], {"type": "array", "items": {}, "uniqueItems": flag})


def test_catalog_rejects_broken_output_before_provider_call(monkeypatch) -> None:
    original = catalog._load_object
    tools = original("tools.json")
    run = next(row for row in tools["tools"] if row["name"] == "quantum_algorithm_run")
    run["output"]["properties"]["optional"] = {"type": "string", "format": "uuid"}
    monkeypatch.setattr(
        catalog, "_load_object", lambda name: tools if name == "tools.json" else original(name)
    )
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "fixture"},
    )
    assert result.status == "error"
    assert result.error == "invalid tool contract"


def test_unknown_capability_is_a_sanitized_contract_error() -> None:
    with pytest.raises(RuntimeError, match="capability contract is invalid"):
        _parse_capabilities(
            [
                {
                    "id": "unknown",
                    "kind": "workflow",
                    "provider": "company-agent",
                    "contract_version": "1",
                    "tools": [],
                }
            ]
        )


@pytest.mark.parametrize("raw", ["1e999", "-1e999", '"\\ud800"', '{"\\udfff":0}', "[" * 2000 + "]" * 2000])
def test_strict_json_rejects_overflow_unicode_and_excessive_depth(raw) -> None:
    with pytest.raises(StrictJsonError):
        loads(raw)


def test_strict_json_preserves_valid_surrogate_pair() -> None:
    assert loads('"\\ud83d\\ude00"') == "\U0001f600"


@pytest.mark.parametrize("raw", ["[" * 2000 + "]" * 2000, '{"query":"\\ud800"}'])
def test_cli_bad_json_fails_without_traceback(raw, capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["validate", "--tool", "company_knowledge_search", "--args", raw])
    assert caught.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_cli_applies_size_limit_to_direct_arguments(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["decide", "--tool", "company_capabilities", "--args", " " * 256_001 + "{}"])
    assert caught.value.code == 2
    assert "maximum size" in capsys.readouterr().err


@pytest.mark.parametrize(
    "key",
    [
        "apiKey",
        "APIKey",
        "accessToken",
        "clientSecret",
        "circuitBody",
        "CALData",
        "ＡＰＩＫｅｙ",
        "twinId",
        "circuitId",
        "assetId",
    ],
)
def test_output_key_normalization_closes_common_aliases(key) -> None:
    assert has_forbidden_output({"summary": {key: "private-fixture"}})


@pytest.mark.parametrize("text", ["qccd-twin", "OPENQASM 3.0; qubit q;", "-----BEGIN PRIVATE KEY-----"])
def test_summary_cannot_hide_forbidden_content(text) -> None:
    assert has_forbidden_output({"summary": {"text": text}})


def test_twin_provenance_is_only_allowed_at_authorized_top_level() -> None:
    assert not has_forbidden_output({"twin_id": "twin_x", "provenance": "qccd-twin"}, allow_twin_id=True)
    assert has_forbidden_output({"summary": {"provenance": "qccd-twin"}}, allow_twin_id=True)


def test_result_policy_bounds_aggregate_bytes_and_dsh_render_limit() -> None:
    result = {"summary": {f"metric{i}": "x" * 4000 for i in range(32)}}
    assert has_forbidden_output(result)
    with pytest.raises(ValueError, match="maximum encoded size"):
        validate_result_size(result)
    limit = catalog.load_result_policy()["max_result_bytes"]
    assert limit == 64_000
    source = (ROOT / "packages/company-agent-core/src/runtime.js").read_text()
    assert f"const MAX_TOOL_RESULT_BYTES = {limit:_};" in source


def test_missing_result_contract_fails_before_local_execution(monkeypatch) -> None:
    module = importlib.import_module("company_agent.invoke")
    monkeypatch.setattr(module, "load_result_policy", lambda: (_ for _ in ()).throw(RuntimeError("bad")))
    monkeypatch.setitem(module._LOCAL_TOOLS, "company_capabilities", lambda _: pytest.fail("executed"))
    assert invoke("company_capabilities", "lab", {}).status == "error"


def test_knowledge_versions_track_content(monkeypatch, tmp_path) -> None:
    path = tmp_path / "note.md"
    path.write_text("needle first", encoding="utf-8")
    monkeypatch.setattr("company_agent.knowledge.roots", lambda: (("builtin", tmp_path),))
    first = search({"query": "needle"})["hits"][0]["version"]
    assert first.startswith("sha256:")
    assert search({"query": "needle"})["hits"][0]["version"] == first
    path.write_text("needle second", encoding="utf-8")
    assert search({"query": "needle"})["hits"][0]["version"] != first


def test_knowledge_directory_enumeration_is_bounded(monkeypatch, tmp_path) -> None:
    for index in range(10):
        (tmp_path / f"note{index}.md").write_text("needle", encoding="utf-8")
    monkeypatch.setattr("company_agent.knowledge.roots", lambda: (("builtin", tmp_path),))
    monkeypatch.setattr("company_agent.knowledge._MAX_KNOWLEDGE_ENTRIES", 3)
    assert len(search({"query": "needle"})["hits"]) == 3


def test_knowledge_total_read_bytes_are_bounded(monkeypatch, tmp_path) -> None:
    for index in range(3):
        (tmp_path / f"note{index}.md").write_text("needle " + "x" * 10, encoding="utf-8")
    monkeypatch.setattr("company_agent.knowledge.roots", lambda: (("builtin", tmp_path),))
    monkeypatch.setattr("company_agent.knowledge._MAX_KNOWLEDGE_TOTAL_BYTES", 20)
    assert len(search({"query": "needle"})["hits"]) == 1


def test_handle_schema_matches_adapter_restrictions() -> None:
    for row in catalog.load_tools().values():
        for key in row["input_handles"]:
            schema = row["parameters"]["properties"][key]
            with pytest.raises(SchemaError):
                validate_json_schema("circ_bad value" if key == "circuit_id" else "asset_中文", schema)


def test_bridge_python_ignores_shadow_package_in_launch_directory(tmp_path) -> None:
    shadow = tmp_path / "company_agent"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('shadow-package-imported')")
    runtime = (ROOT / "packages/company-agent-core/src/runtime.js").as_uri()
    # Windows node aborts at process init (ncrypto::CSPRNG) without SystemRoot;
    # POSIX keeps the bare hermetic PATH used by the review fixtures.
    child_env: dict[str, str] = {}
    if os.name == "nt":
        child_env.update({
            "PATH": os.environ.get("PATH", ""),
            "SystemRoot": os.environ.get("SystemRoot", ""),
            "windir": os.environ.get("windir", ""),
        })
    else:
        child_env["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"import {{ validate }} from {json.dumps(runtime)}; "
            "console.log(JSON.stringify(await validate('company_capabilities', {})));",
        ],
        cwd=tmp_path,
        env={
            **child_env,
            "COMPANY_AGENT_PYTHON": sys.executable,
            "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
            "COMPANY_AGENT_PROFILE": "company-agent-minimal",
            "COMPANY_AGENT_PRESET": "boot",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"valid": True, "error": None}
