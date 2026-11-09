from __future__ import annotations

import json
from pathlib import Path

import pytest

from company_agent import catalog


def _contract_dir(tmp_path: Path, tools: object) -> Path:
    root = tmp_path / "contracts"
    root.mkdir()
    (root / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    return root


def test_contract_override_must_be_absolute(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", "relative/contracts")
    with pytest.raises(RuntimeError, match="must be an absolute path"):
        catalog.contract_root()


def test_missing_contract_override_fails_without_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="configured Company Agent contracts are unavailable"):
        catalog.contract_root()


def test_tool_catalog_rejects_duplicate_names(monkeypatch, tmp_path: Path) -> None:
    root = _contract_dir(
        tmp_path,
        {"tools": [{"name": "duplicate"}, {"name": "duplicate"}]},
    )
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(root))
    with pytest.raises(RuntimeError, match="invalid Company Agent contract: tools.json"):
        catalog.load_tools()


def test_tool_catalog_rejects_non_object_shape(monkeypatch, tmp_path: Path) -> None:
    root = _contract_dir(tmp_path, [])
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(root))
    with pytest.raises(RuntimeError, match="invalid Company Agent contract: tools.json"):
        catalog.load_tools()


def _real_tools_contract(tmp_path: Path) -> Path:
    """Copy the shipped tools.json so managed-builtins mutations stay isolated."""
    root = tmp_path / "contracts"
    root.mkdir()
    source = json.loads(catalog.contract_root().joinpath("tools.json").read_text(encoding="utf-8"))
    (root / "tools.json").write_text(json.dumps(source), encoding="utf-8")
    return root


def test_managed_builtins_shape_and_preset_coverage() -> None:
    builtins = catalog.load_managed_builtins()
    assert set(builtins) == {
        "read", "read_image", "write", "edit", "glob", "grep", "web_search",
        "todo_write", "present",
    }
    for preset in ("boot", "lab", "algo", "sign"):
        assert catalog.builtin_tools_for_preset(preset) == (
            "read", "read_image", "write", "edit", "glob", "grep", "web_search",
            "todo_write", "present",
        )
    tools = catalog.load_tools()
    assert not set(builtins) & set(tools)
    contract = json.loads(catalog.contract_root().joinpath("tools.json").read_text(encoding="utf-8"))
    packages = {row["name"]: row["package"] for row in contract["managed_builtins"]["tools"]}
    for name in ("read", "read_image", "write", "edit"):
        assert packages[name] == "@deepseek-ai/dsh-tool-fs"
    for name in ("glob", "grep"):
        assert packages[name] == "@deepseek-ai/dsh-tool-fs-search"
    assert packages["web_search"] == "@deepseek-ai/dsh-tool-web"
    assert packages["todo_write"] == "@deepseek-ai/dsh-tool-todo"
    assert packages["present"] == "@deepseek-ai/dsh-tool-present"


def test_managed_builtins_fail_closed_on_mutated_contracts(monkeypatch, tmp_path: Path) -> None:
    import copy

    base = json.loads(catalog.contract_root().joinpath("tools.json").read_text(encoding="utf-8"))
    mutations = {
        "unknown row key": lambda d: d["managed_builtins"]["tools"][0].update({"extra": 1}),
        "standard source": lambda d: d["managed_builtins"]["tools"][0].update({"source": "shipped"}),
        "unknown preset": lambda d: d["managed_builtins"]["tools"][0].update({"presets": ["root"]}),
        "bad package": lambda d: d["managed_builtins"]["tools"][0].update({"package": "bun/widget"}),
        "name collision": lambda d: d["managed_builtins"]["tools"][0].update(
            {"name": "quantum_asset_list"}
        ),
    }
    for label, mutate in mutations.items():
        broken = copy.deepcopy(base)
        mutate(broken)
        root = tmp_path / label.replace(" ", "-")
        root.mkdir()
        (root / "tools.json").write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(root))
        with pytest.raises(RuntimeError, match="managed_builtins"):
            catalog.load_managed_builtins()


def test_builtin_tools_for_preset_rejects_unknown_preset() -> None:
    with pytest.raises(KeyError):
        catalog.builtin_tools_for_preset("standard")
    catalog.load_managed_builtins()


def test_other_catalogs_reject_wrong_shapes(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "contracts"
    root.mkdir()
    (root / "tools.json").write_text('{"tools": []}', encoding="utf-8")
    (root / "capabilities.json").write_text('{"capabilities": {}}', encoding="utf-8")
    (root / "presets.json").write_text('{"presets": []}', encoding="utf-8")
    (root / "providers.json").write_text('{"providers": [{"id": "same"}, {"id": "same"}]}', encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(root))
    with pytest.raises(RuntimeError, match="capabilities.json"):
        catalog.load_capabilities()
    with pytest.raises(RuntimeError, match="presets.json"):
        catalog.load_presets()
    with pytest.raises(RuntimeError, match="providers.json"):
        catalog.load_providers()


def test_contract_parse_errors_are_sanitized(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "contracts"
    root.mkdir()
    (root / "tools.json").write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(root))
    with pytest.raises(RuntimeError, match="invalid Company Agent contract: tools.json"):
        catalog.load_tools()
