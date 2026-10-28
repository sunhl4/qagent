from __future__ import annotations

import importlib

from company_agent.invoke import invoke

invoke_module = importlib.import_module("company_agent.invoke")


def test_missing_provider_is_honest(monkeypatch) -> None:
    monkeypatch.delenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", raising=False)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert "not configured" in str(result.error)
    assert result.payload is None


def test_algorithm_catalog_missing_provider_is_honest(monkeypatch) -> None:
    monkeypatch.delenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", raising=False)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert "not configured" in str(result.error)
    assert result.payload is None


def test_algorithm_run_rejects_discovery_sentinel() -> None:
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "__list_algorithms__"},
    )
    assert result.status == "error"
    assert "quantum_algorithm_catalog" in str(result.error)
    assert result.payload is None


def test_arguments_are_validated_before_provider() -> None:
    result = invoke("quantum_simulate", "lab", {"circuit_id": "circ_x", "shots": 0})
    assert result.status == "error"
    assert "shots must be >= 1" in str(result.error)


def test_argument_upper_bounds_are_enforced() -> None:
    result = invoke("quantum_simulate", "lab", {"circuit_id": "circ_x", "shots": 1000001})
    assert result.status == "error"
    assert "shots must be <= 1000000" in str(result.error)


def test_string_length_limits_are_enforced() -> None:
    result = invoke("company_knowledge_search", "lab", {"query": "x" * 1001})
    assert result.status == "error"
    assert "query must have at most 1000 characters" in str(result.error)


def test_workflow_tool_invocation_uses_nested_step_contract() -> None:
    result = invoke(
        "company_workflow_validate",
        "lab",
        {
            "steps": [
                {
                    "id": "algorithm",
                    "capability": "company.algorithm",
                    "tool": "quantum_algorithm_run",
                    "produces": ["asset_id"],
                    "arguments": {
                        "catalog_version": "cat_fixture",
                        "component_version": "1.0",
                        "algorithm": "vqe",
                    },
                    "legacy": True,
                }
            ]
        },
    )
    assert result.status == "error"
    assert "unknown fields" in str(result.error)


def test_workflow_with_static_arguments_executes_through_invocation() -> None:
    result = invoke(
        "company_workflow_validate",
        "lab",
        {
            "steps": [
                {
                    "id": "algorithm",
                    "capability": "company.algorithm",
                    "tool": "quantum_algorithm_run",
                    "produces": ["asset_id"],
                    "arguments": {
                        "catalog_version": "cat_fixture",
                        "component_version": "1.0",
                        "algorithm": "vqe",
                        "parameters": {"iterations": 2},
                    },
                },
                {
                    "id": "export",
                    "capability": "company.asset",
                    "tool": "quantum_circuit_export",
                    "needs": ["asset_id"],
                    "produces": ["circuit_id"],
                },
                {
                    "id": "device",
                    "capability": "quantum.device",
                    "tool": "quantum_device_run",
                    "needs": ["circuit_id"],
                    "produces": ["twin_id"],
                    "arguments": {"shots": 8},
                },
            ]
        },
    )
    assert result.status == "ok", result.error
    assert result.payload["valid"] is True
    assert result.payload["steps"][-1]["approval"] == "human"
    assert result.payload["produces"] == ["asset_id", "circuit_id", "twin_id"]


def test_workflow_step_count_is_bounded() -> None:
    steps = [
        {"id": f"step-{index}", "capability": "company.workflow", "tool": "company_capabilities"}
        for index in range(65)
    ]
    result = invoke("company_workflow_validate", "lab", {"steps": steps})
    assert result.status == "error"
    assert "steps must contain at most 64 items" in str(result.error)


def test_nested_argument_size_is_bounded_before_provider() -> None:
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {
            "catalog_version": "cat_fixture",
            "component_version": "1.0",
            "algorithm": "vqe",
            "parameters": {"blob": "x" * 256_000},
        },
    )
    assert result.status == "error"
    assert result.error in {
        "arguments exceed maximum encoded size",
        "arguments contain an oversized string",
    }


def test_oversized_nested_argument_key_fails_closed() -> None:
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {
            "catalog_version": "cat_fixture",
            "component_version": "1.0",
            "algorithm": "vqe",
            "parameters": {"x" * 513: 1},
        },
    )
    assert result.status == "error"
    assert result.error == "arguments contain an oversized object key"


def test_negative_zero_argument_fails_closed() -> None:
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {
            "catalog_version": "cat_fixture",
            "component_version": "1.0",
            "algorithm": "vqe",
            "parameters": {"value": -0.0},
        },
    )
    assert result.status == "error"
    assert result.error == "arguments contain negative zero"


def test_non_json_argument_values_fail_closed() -> None:
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {
            "catalog_version": "cat_fixture",
            "component_version": "1.0",
            "algorithm": "vqe",
            "parameters": {"bad": object()},
        },
    )
    assert result.status == "error"
    assert "unsupported type" in str(result.error)


def test_unknown_arguments_fail_closed() -> None:
    result = invoke("quantum_simulate", "lab", {"circuit_id": "circ_x", "shots": 8, "claim_twin_id": True})
    assert result.status == "error"
    assert "unknown arguments" in str(result.error)


def test_local_tools_reject_unknown_arguments() -> None:
    result = invoke("company_capabilities", "lab", {"unexpected": True})
    assert result.status == "error"
    assert "unknown arguments" in str(result.error)


def test_args_must_be_an_object() -> None:
    result = invoke("quantum_algorithm_run", "lab", ["vqe"])  # type: ignore[arg-type]
    assert result.status == "error"
    assert result.decision == "deny"
    assert result.error == "args must be an object"


def test_unexpected_local_failure_is_sanitized(monkeypatch) -> None:
    def fail(_arguments):
        raise RuntimeError("authorization secret leaked-value")

    monkeypatch.setitem(invoke_module._LOCAL_TOOLS, "company_capabilities", fail)
    result = invoke("company_capabilities", "lab", {})
    assert result.status == "error"
    assert result.error == "internal tool failure"
    assert "leaked-value" not in str(result.error)


def test_invalid_contract_is_returned_as_safe_error(monkeypatch) -> None:
    monkeypatch.setattr(invoke_module, "load_tools", lambda: (_ for _ in ()).throw(RuntimeError("bad")))
    result = invoke("company_capabilities", "lab", {})
    assert result.status == "error"
    assert result.decision == "deny"
    assert result.error == "invalid tool contract"


def test_invalid_policy_contract_is_returned_as_safe_error(monkeypatch) -> None:
    monkeypatch.setattr(
        invoke_module,
        "decide",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("policy broken")),
    )
    result = invoke("company_capabilities", "lab", {})
    assert result.status == "error"
    assert result.decision == "deny"
    assert result.error == "invalid policy contract"


def test_error_sanitizer_rejects_urls_and_absolute_paths() -> None:
    assert invoke_module._safe_error_message("failed at https://private.example", "safe") == "safe"
    assert invoke_module._safe_error_message("failed at /mnt/private/data", "safe") == "safe"
    assert invoke_module._safe_error_message("ordinary error", "safe") == "ordinary error"


def test_input_handle_prefixes_are_validated_before_provider() -> None:
    result = invoke("quantum_simulate", "lab", {"circuit_id": "asset_wrong", "shots": 8})
    assert result.status == "error"
    assert result.decision == "deny"
    assert result.error == "circuit_id has an invalid format"


def test_input_handle_error_precedes_unrelated_schema_error() -> None:
    result = invoke("quantum_simulate", "lab", {"circuit_id": "asset_wrong", "shots": 0})
    assert result.status == "error"
    assert result.error == "circuit_id has an invalid format"


def test_input_handles_reject_whitespace_and_unicode() -> None:
    for circuit_id in ("circ_bad value", "circ_量子"):
        result = invoke("quantum_simulate", "lab", {"circuit_id": circuit_id, "shots": 8})
        assert result.status == "error"
        assert result.error == "circuit_id has an invalid format"


def test_device_handle_is_validated_before_ask() -> None:
    result = invoke("quantum_device_run", "lab", {"circuit_id": "asset_wrong", "shots": 8})
    assert result.status == "error"
    assert result.decision == "deny"
    assert result.error == "circuit_id has an invalid format"


def test_device_stops_at_ask() -> None:
    result = invoke("quantum_device_run", "lab", {"circuit_id": "circ_x", "shots": 16})
    assert result.status == "needs_ask"
    assert result.payload is None


def test_device_policy_stays_denied_when_approved_outside_device_presets() -> None:
    for preset in ("boot", "algo"):
        result = invoke(
            "quantum_device_run",
            preset,
            {"circuit_id": "circ_x", "shots": 8},
            approved=True,
        )
        assert result.status == "denied"
        assert result.decision == "deny"
        assert result.payload is None


def test_device_arguments_are_validated_before_ask() -> None:
    result = invoke("quantum_device_run", "lab", {"circuit_id": "circ_x", "shots": 0})
    assert result.status == "error"
    assert result.decision == "deny"
    assert result.error == "shots must be >= 1"
