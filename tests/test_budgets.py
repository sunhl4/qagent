"""P3-B1 termination budgets: contract validation, ledger isolation and invocation wiring."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from company_agent import budget
from company_agent.catalog import load_budgets
from company_agent.invoke import invoke

ROOT = Path(__file__).resolve().parents[1]


def test_budgets_contract_shape_is_verified() -> None:
    contract = load_budgets()
    assert set(contract) == {"version", "fail_closed", "turn_env", "ledger", "limits"}
    assert contract["turn_env"] == "COMPANY_AGENT_TURN_ID"
    assert contract["ledger"]["dir_name"] == "budgets"
    assert set(contract["limits"]) == {
        "invocations", "wall_ms", "approval_waits", "device_runs", "submissions",
    }


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"version": "1.0.1"}),
    lambda d: d.update({"fail_closed": False}),
    lambda d: d.update({"unknown": 1}),
    lambda d: d["limits"].__setitem__("invocations", 0),
    lambda d: d["limits"].__setitem__("device_runs", 999),
    lambda d: d["ledger"].__setitem__("dir_name", "other"),
    lambda d: d.update({"turn_env": "OTHER_TURN"}),
])
def test_budgets_contract_fails_closed_on_mutation(mutate, tmp_path, monkeypatch) -> None:
    import shutil

    isolated = tmp_path / "contracts"
    shutil.copytree(ROOT / "contracts", isolated, ignore=shutil.ignore_patterns("__pycache__"))
    broken = json.loads(isolated.joinpath("budgets.json").read_text(encoding="utf-8"))
    mutate(broken)
    isolated.joinpath("budgets.json").write_text(json.dumps(broken), encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(isolated))
    with pytest.raises(RuntimeError, match="budgets.json"):
        load_budgets()


def test_ledger_is_per_turn_and_never_plaintext(monkeypatch) -> None:
    import os

    store_root = Path(os.environ["COMPANY_AGENT_RECEIPT_DIR"])
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "wired-session-42")
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", "operator@corp.example.com")
    ledger = budget.ledger_path()
    assert ledger is not None
    assert ledger.parent.parent == store_root
    # The raw turn identifier must never appear in the ledger path or body.
    assert "wired-session-42" not in str(ledger)
    budget.charge("company_capabilities", elapsed_ms=12)
    budget.charge("quantum_device_run", elapsed_ms=3)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    assert payload["counts"] == {
        "invocations": 2, "wall_ms": 15, "approval_waits": 0,
        "device_runs": 1, "submissions": 0,
    }
    assert "wired-session-42" not in json.dumps(payload)
    assert re.fullmatch(r"turn_[0-9a-f]{32}", payload["turn_digest"])
    budget.reset("wired-session-42")


def test_turns_are_isolated_from_each_other(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "turn-one")
    budget.charge("company_capabilities", elapsed_ms=10)
    first = budget.counts()
    assert first["invocations"] == 1
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "turn-two")
    assert budget.counts()["invocations"] == 0
    budget.precheck("company_capabilities")
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "turn-one")
    assert budget.counts() == first


def test_sublimits_and_wait_budget_fail_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "limits-check")
    try:
        limits = load_budgets()["limits"]
        for _ in range(limits["device_runs"]):
            budget.charge("quantum_device_run")
        with pytest.raises(budget.BudgetError) as caught:
            budget.precheck("quantum_device_run")
        assert "device_runs" in str(caught.value)
        for _ in range(limits["submissions"]):
            budget.charge("hpc_submit")
        with pytest.raises(budget.BudgetError) as caught:
            budget.precheck("quantum_cloud_submit")
        assert "submissions" in str(caught.value)
        budget.precheck("company_capabilities")
        for _ in range(limits["approval_waits"]):
            budget.charge_approval_wait()
        with pytest.raises(budget.BudgetError) as caught:
            budget.precheck("company_capabilities", wait=True)
        assert "approval_waits" in str(caught.value)
    finally:
        budget.reset("limits-check")


def test_wall_budget_exhausts(tmp_path, monkeypatch) -> None:
    import shutil

    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "wall-check")
    isolated = tmp_path / "contracts"
    shutil.copytree(ROOT / "contracts", isolated, ignore=shutil.ignore_patterns("__pycache__"))
    raw = json.loads(isolated.joinpath("budgets.json").read_text(encoding="utf-8"))
    raw["limits"]["wall_ms"] = 100
    isolated.joinpath("budgets.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(isolated))
    try:
        budget.charge("company_capabilities", elapsed_ms=150)
        with pytest.raises(budget.BudgetError) as caught:
            budget.precheck("company_capabilities")
        assert "wall_ms" in str(caught.value)
    finally:
        budget.reset("wall-check")


def test_invoke_charges_invocations_and_waits(tmp_path, monkeypatch, capsys) -> None:
    import os

    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "invoke-check")
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", "operator@corp.example.com")
    try:
        assert invoke("company_capabilities", "lab", {}).status == "ok"
        assert invoke("company_capabilities", "lab", {}).status == "ok"
        assert budget.counts()["invocations"] == 2 and budget.counts()["wall_ms"] > 0
        # A preset-hidden tool is denied by policy before any budget interaction.
        denied = invoke("hpc_queue", "boot", {})
        assert denied.status == "denied" and denied.decision == "deny"
        assert budget.counts()["invocations"] == 2, "denied calls must never charge"
        waited = invoke("quantum_device_run", "lab", {"circuit_id": "circ_x", "shots": 4})
        assert waited.status == "needs_ask"
        assert budget.counts()["approval_waits"] == 1 and budget.counts()["invocations"] == 2
    finally:
        budget.reset("invoke-check")
        os.environ.pop("COMPANY_AGENT_SUBJECT", None)


def test_invoke_budget_precheck_returns_error_status(tmp_path, monkeypatch, capsys) -> None:
    import os

    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "precheck-check")
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", "operator@corp.example.com")
    try:
        ledger = budget.ledger_path()
        assert ledger is not None
        ledger.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(999):
            budget.charge("company_capabilities")
        assert budget.counts()["invocations"] == 999
        result = invoke("company_capabilities", "lab", {})
        assert result.status == "error"
        assert "exhausted (invocations)" in str(result.error)
    finally:
        budget.reset("precheck-check")
        os.environ.pop("COMPANY_AGENT_SUBJECT", None)
