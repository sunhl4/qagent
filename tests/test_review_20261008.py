"""Current review regressions use synthetic data and never call science or devices."""

from __future__ import annotations

import json

import pytest

from company_agent import knowledge
from company_agent.catalog import load_presets, load_tools
from company_agent.invoke import _validate_handles, _validate_output, invoke, validate_invocation
from company_agent.sanitize import validate_output_content
from company_agent.workflow import validate

RUN = {"algorithm": "fixture", "catalog_version": "cat_fixture", "component_version": "1.0"}


@pytest.mark.parametrize("field", ["catalog_version", "component_version"])
def test_exact_version_missing_stops_before_dispatch(field, monkeypatch, capsys):
    import importlib

    module = importlib.import_module("company_agent.invoke")

    calls = []
    monkeypatch.setattr(module, "client_by_provider", lambda *_: calls.append(1))
    result = invoke(
        "quantum_algorithm_run", "lab", {key: value for key, value in RUN.items() if key != field}
    )
    assert result.status == "error" and field in result.error
    assert calls == []
    events = [json.loads(line.split(":", 1)[1]) for line in capsys.readouterr().err.splitlines()]
    assert len(events) == 1 and events[0]["event"] == "invocation"
    assert events[0]["request_id"] == "" and events[0]["error_category"] == "validation"


@pytest.mark.parametrize("value", [2**53, -(2**53), float(2**53), {"nested": [2**53]}])
def test_unsafe_integer_arguments_fail_closed(value):
    assert "unsafe integer" in validate_invocation(
        "quantum_algorithm_run", {**RUN, "parameters": {"seed": value}}
    )
    assert validate_invocation("quantum_algorithm_run", {**RUN, "parameters": {"seed": str(2**53)}}) is None


@pytest.mark.parametrize("body", ["-----BEGIN PRIVATE KEY-----\nsynthetic", "OPENQASM 3.0; qubit q;"])
def test_knowledge_entire_source_content_is_checked(tmp_path, monkeypatch, body):
    (tmp_path / "source.md").write_text("needle allowed prose\n" + "safe prose\n" * 400 + body)
    monkeypatch.setattr(knowledge, "roots", lambda: (("builtin", tmp_path),))
    result = invoke("company_knowledge_search", "boot", {"query": "needle"})
    assert result.status == "error" and result.payload is None
    assert body not in result.error


@pytest.mark.parametrize("location", ["title", "source", "snippet", "status", "description"])
def test_known_credential_values_are_forbidden_in_any_text(monkeypatch, location):
    secret = "synthetic-credential-review-not-a-real-secret"
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", secret)
    with pytest.raises(ValueError, match="forbidden content"):
        validate_output_content({location: "prefix " + secret + " suffix"}, reference=True)


def test_catalog_identity_is_component_and_version():
    rows = [{"id": "fixture", "version": version} for version in ["1.0", "2.0"]]
    result = {"provider": "uniqon", "algorithms": rows, "complete": True}
    _validate_handles("quantum_algorithm_catalog", result)
    with pytest.raises(RuntimeError, match="duplicate"):
        _validate_handles("quantum_algorithm_catalog", {**result, "algorithms": [rows[0], rows[0]]})


def workflow(inputs, binding=None):
    step = {
        "id": "simulate",
        "capability": "quantum.simulation",
        "tool": "quantum_simulate",
        "needs": ["circuit_id"],
        "arguments": {"shots": 10},
    }
    if binding is not None:
        step["bindings"] = {"circuit_id": binding}
    return {"inputs": inputs, "steps": [step]}


def test_external_handle_inference_and_multiple_explicit_inputs():
    source = {"id": "existing", "handle": "circuit_id", "value": "circ_existing"}
    result = validate(workflow([source]))
    assert result["steps"][0]["bindings"] == {"circuit_id": {"input": "existing", "output": "circuit_id"}}
    assert result["produces"] == []
    sources = [source, {**source, "id": "other", "value": "circ_other"}]
    with pytest.raises(ValueError, match="ambiguous"):
        validate(workflow(sources))
    assert validate(workflow(sources, {"input": "other", "output": "circuit_id"}))["valid"]
    assert (
        invoke(
            "company_workflow_validate", "lab", workflow(sources, {"input": "other", "output": "circuit_id"})
        ).status
        == "ok"
    )


@pytest.mark.parametrize(
    "binding",
    [
        {"input": "missing", "output": "circuit_id"},
        {"input": "existing", "step": "simulate", "output": "circuit_id"},
        {"input": "existing", "output": "asset_id"},
    ],
)
def test_external_handle_invalid_bindings(binding):
    with pytest.raises(ValueError):
        validate(workflow([{"id": "existing", "handle": "circuit_id", "value": "circ_x"}], binding))


@pytest.mark.parametrize(
    "inputs",
    [
        [{"id": "simulate", "handle": "circuit_id", "value": "circ_x"}],
        [{"id": "existing", "handle": "circuit_id", "value": "asset_x"}],
        [{"id": "existing", "handle": "circuit_id", "value": "circ_x"}] * 2,
    ],
)
def test_external_handle_collision_and_type_checks(inputs):
    with pytest.raises(ValueError):
        validate(workflow(inputs))


def test_metrics_are_typed_bounded_and_unit_checked():
    item = {"name": "objective", "kind": "objective", "value": -1.0, "unit": "hartree"}
    result = {"summary": {"metrics": {"schema_version": "scientific-metrics/1.0", "items": [item]}}}
    _validate_output("quantum_asset_get", result)
    for bad in [
        {**item, "kind": "probability"},
        {**item, "kind": "uncertainty"},
        {**item, "kind": "count", "unit": "count", "value": 0.5},
        {**item, "unit": "arbitrary"},
        {**item, "value": float("inf")},
    ]:
        with pytest.raises((ValueError, RuntimeError)):
            _validate_output(
                "quantum_asset_get",
                {"summary": {"metrics": {"schema_version": "scientific-metrics/1.0", "items": [bad]}}},
            )
    result["summary"]["metrics"]["items"] = [item, item]
    with pytest.raises(RuntimeError, match="unique"):
        _validate_output("quantum_asset_get", result)


@pytest.mark.parametrize("preset", ["boot", "lab", "algo", "sign"])
def test_capability_visibility_is_exact_current_preset(preset):
    result = invoke("company_capabilities", preset)
    assert result.status == "ok"
    assert result.payload["preset"] == preset
    rows = result.payload["capabilities"]
    assert {name for row in rows for name in row["visible_tools"]} == set(
        load_presets()["presets"][preset]["visible_tools"]
    )
    assert {name for row in rows for name in row["tools"]} == set(load_tools())
    assert all(row["provider_state"] in {"local", "unconfigured", "configured_unverified"} for row in rows)


def test_unknown_tool_final_event_does_not_echo_name(capsys):
    result = invoke("malicious_name", "lab")
    assert result.status == "denied"
    event = json.loads(capsys.readouterr().err.split(":", 1)[1])
    assert event["tool"] == "unknown" and event["request_id"] == ""


def test_long_document_selects_matching_passage_and_marks_untrusted(tmp_path, monkeypatch):
    (tmp_path / "long.md").write_text(
        "irrelevant prefix. " * 1000 + "distinctive_answer specific_query" + " suffix" * 1000
    )
    monkeypatch.setattr(knowledge, "roots", lambda: (("builtin", tmp_path),))
    result = knowledge.search({"query": "specific_query"})
    assert result["trust"] == "untrusted_reference_data"
    assert "distinctive_answer" in result["hits"][0]["snippet"]
    assert len(result["hits"][0]["snippet"]) <= 600
