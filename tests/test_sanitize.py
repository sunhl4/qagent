from __future__ import annotations

import math

import pytest

from company_agent.sanitize import has_forbidden_output, short_result


def test_short_result_removes_large_science_fields() -> None:
    raw = {"qasm3": "OPENQASM", "circuit": {"body": [1]}, "pauli_terms": ["X"], "summary": "ok"}
    assert short_result(raw) == {"summary": "ok"}


def test_short_result_caps_collections() -> None:
    raw = {str(i): i for i in range(100)}
    assert len(short_result(raw)) == 64
    assert len(short_result(list(range(100)))) == 32


def test_short_result_removes_credential_shaped_keys_recursively() -> None:
    raw = {
        "summary": {
            "authorization_token": "bearer-value",
            "provider_secret": "secret-value",
            "service_api_key": "key-value",
            "admin_password": "password-value",
            "token_metadata": "must-not-pass",
            "secret_hint": "must-not-pass",
            "authorization_header": "must-not-pass",
            "credential_id": "must-not-pass",
            "api_key_backup": "must-not-pass",
            "calibration_snapshot": "must-not-pass",
            "shuttle_sequence": "must-not-pass",
            "bitstrings_sample": "must-not-pass",
            "pauli_operator_terms": "must-not-pass",
            "compiled_qasm": "must-not-pass",
            "safe": "kept",
        }
    }
    assert short_result(raw) == {"summary": {"safe": "kept"}}


def test_short_result_caps_nesting_depth() -> None:
    value: object = "leaf"
    for _ in range(12):
        value = {"nested": value}
    dumped = str(short_result(value))
    assert "[truncated]" in dumped
    assert "leaf" not in dumped


def test_short_result_replaces_non_finite_numbers() -> None:
    assert short_result({"nan": math.nan, "positive": math.inf, "negative": -math.inf}) == {
        "nan": None,
        "positive": None,
        "negative": None,
    }


def test_short_result_rejects_non_string_key_as_lossy() -> None:
    assert has_forbidden_output({1: "value"}) is True


def test_forbidden_output_detection_matches_lossy_sanitization() -> None:
    assert has_forbidden_output({"summary": {"service_token": "secret"}}) is True
    assert has_forbidden_output({"rows": list(range(33))}) is True
    assert has_forbidden_output({"summary": "x" * 4001}) is True
    assert has_forbidden_output({"summary": {"asset_id": "asset_nested"}}) is True
    assert has_forbidden_output({"summary": {"circuit_id": "circ_nested"}}) is True
    assert has_forbidden_output({"twin_id": "twin_x"}, allow_twin_id=True) is False
    assert has_forbidden_output({"summary": {"twin_id": "twin_nested"}}, allow_twin_id=True) is True
    assert has_forbidden_output({"summary": "safe"}) is False


def test_asset_list_keeps_only_explicitly_allowed_asset_references() -> None:
    raw = {"assets": [{"asset_id": "asset_existing", "label": "Existing asset"}]}
    assert has_forbidden_output(raw) is True
    assert has_forbidden_output(raw, allow_asset_list=True) is False
    assert short_result(raw, allow_asset_list=True) == raw


@pytest.mark.parametrize(
    "raw",
    [
        {"summary": {"asset_id": "asset_hidden"}},
        {"rows": [{"asset_id": "asset_hidden"}]},
        {"assets": {"*": {"asset_id": "asset_hidden"}}},
        {"assets": [[{"asset_id": "asset_hidden"}]]},
        {"assets": [{"summary": {"asset_id": "asset_hidden"}}]},
        {"assets": [{"circuit_id": "circ_hidden"}]},
        {"assets": [{"twin_id": "twin_hidden"}]},
        {"assets": [{"asset_id": "asset_ok", "service_token": "hidden"}]},
    ],
)
def test_asset_list_exception_cannot_expose_other_nested_data(raw: dict) -> None:
    assert has_forbidden_output(raw, allow_twin_id=True, allow_asset_list=True) is True
    assert short_result(raw, allow_twin_id=True, allow_asset_list=True) != raw


def test_twin_id_is_only_kept_at_top_level() -> None:
    raw = {
        "twin_id": "twin_top",
        "summary": {
            "asset_id": "asset_nested",
            "circuit_id": "circ_nested",
            "twin_id": "twin_nested",
            "safe": True,
        },
        "rows": [{"twin_id": "twin_list"}],
    }
    assert short_result(raw, allow_twin_id=True) == {
        "twin_id": "twin_top",
        "summary": {"safe": True},
        "rows": [{}],
    }
