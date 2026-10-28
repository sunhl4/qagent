"""P3-B2 bounded CSV table profiler (company_table_profile)."""

from __future__ import annotations

import pytest

from company_agent import table_profile
from company_agent.invoke import invoke
from company_agent.table_profile import profile

_NORMAL = "name,shots,fidelity\nalpha,1024,0.97\nbeta,1024,0.93\ngamma,512,0.95\n"


def test_normal_numeric_profile_has_exact_shape() -> None:
    result = profile({"table": _NORMAL})
    assert result["rows"] == 3
    assert result["columns"] == [
        {"name": "name", "kind": "text", "complete": True},
        {"name": "shots", "kind": "numeric", "complete": True},
        {"name": "fidelity", "kind": "numeric", "complete": True},
    ]
    shots, fidelity = result["numeric"]
    assert shots["name"] == "shots" and shots["count"] == 3
    assert (shots["min"], shots["max"]) == (512.0, 1024.0)
    assert shots["mean"] == pytest.approx(853.33333, abs=1e-4)
    assert fidelity["count"] == 3 and fidelity["min"] == pytest.approx(0.93)
    assert fidelity["max"] == 0.97 and fidelity["mean"] == pytest.approx(0.95)
    assert result["integrity"] == {"complete": True, "reasons": []}


def test_semicolon_delimiter_is_supported() -> None:
    result = profile({"table": "a;b\nc;2\nd;4\n", "delimiter": ";"})
    assert result["columns"][0]["kind"] == "text"
    assert result["numeric"][0]["name"] == "b"
    assert result["numeric"][0]["count"] == 2
    assert result["numeric"][0]["mean"] == 3.0


def test_header_only_table_is_valid_with_zero_rows() -> None:
    result = profile({"table": "x\n"})
    assert result["rows"] == 0
    assert result["columns"] == [{"name": "x", "kind": "text", "complete": False}]
    assert result["numeric"] == []
    assert result["integrity"] == {"complete": True, "reasons": []}


def test_ragged_and_mixed_columns_are_flagged_not_raised() -> None:
    result = profile({"table": "a,b\n1,2,3\n4,x\n"})
    reasons = result["integrity"]["reasons"]
    assert "column_mismatch" in reasons
    assert result["columns"][1]["kind"] == "text"
    # Column "a" stays numeric over the values that were well formed.
    col_a = next(item for item in result["numeric"] if item["name"] == "a")
    assert col_a["count"] == 2 and col_a["mean"] == 2.5


def test_duplicate_header_covers_both_names_and_flags() -> None:
    result = profile({"table": "shots,shots\n1,2\n3,4\n"})
    reasons = result["integrity"]["reasons"]
    assert "duplicate_header" in reasons
    assert result["numeric"] == []
    assert [row["name"] for row in result["columns"]] == ["shots", "shots"]


def test_row_budget_caps_deterministically() -> None:
    table = "x\n" + "".join(f"{i}\n" for i in range(100))
    result = profile({"table": table})
    assert result["rows"] == table_profile.MAX_ROWS
    assert "row_budget" in result["integrity"]["reasons"]


def test_column_budget_caps_deterministically() -> None:
    header = ",".join(f"c{i}" for i in range(20))
    row = ",".join("1" for _ in range(20))
    result = profile({"table": header + "\n" + row + "\n"})
    assert len(result["columns"]) == table_profile.MAX_COLUMNS
    assert "column_budget" in result["integrity"]["reasons"]


def test_oversize_cell_becomes_empty_and_text() -> None:
    big = "x" * 300
    result = profile({"table": f"a\n{big}\n"})
    reasons = result["integrity"]["reasons"]
    assert "cell_budget" in reasons
    assert result["columns"][0]["kind"] == "text"


def test_non_finite_and_empty_values_make_text() -> None:
    result = profile({"table": "a\nNaN\n1.5\n"})
    assert result["columns"][0]["kind"] == "text"
    result = profile({"table": "a,b\n,7\n8,\n"})
    assert {row["name"]: row["kind"] for row in result["columns"]} == {"a": "text", "b": "text"}


def test_invalid_arguments_fail_closed() -> None:
    for args in (
        {"table": ""},
        {"table": "1", "delimiter": ":"},
        {"table": 1},
        {},
        {"table": "x\n", "extra": 1},
    ):
        with pytest.raises((ValueError, TypeError)):
            profile(args)


def test_invoke_wires_the_tool_and_budget_keeps_counting(monkeypatch, capsys) -> None:
    import os

    from company_agent import budget

    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "table-check")
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", "operator@corp.example.com")
    try:
        result = invoke("company_table_profile", "lab", {"table": _NORMAL})
        assert result.status == "ok"
        assert result.payload["rows"] == 3
        assert invoke("company_table_profile", "sign", {"table": _NORMAL}).status == "denied"
        assert budget.counts()["invocations"] == 1
    finally:
        budget.reset("table-check")
        os.environ.pop("COMPANY_AGENT_SUBJECT", None)
