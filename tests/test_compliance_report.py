"""Architecture gates for the repeatable compliance gate (survey P1 4)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("compliance_gate", ROOT / "scripts/compliance_gate.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "src"))
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def isolated_receipt_store(tmp_path_factory, monkeypatch) -> None:
    store = tmp_path_factory.mktemp("gate-receipts", numbered=True) / "receipts"
    store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(store))


CATEGORY_SESSIONS = {"normal", "denied", "fault", "reconciliation"}


def test_gate_report_binds_versions_and_is_all_green(gate, tmp_path) -> None:
    output = tmp_path / "report.json"
    assert gate.main(["--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["report"] == "company-agent-compliance/1.0"
    assert payload["task_set_version"] == gate.TASK_SET_VERSION
    assert len(payload["task_set_sha256"]) == 64
    bound = payload["bound"]
    assert bound["contract_digest"].startswith("sha256:")
    assert bound["skill_registry_version"] == "1.0.0"
    assert isinstance(bound["skill_registry_count"], int)
    assert bound["model_routes"]["company_local_default"] is True
    assert bound["model_routes"]["relay_token_value_present"] is False, "no secret values in reports"
    scenarios = payload["scenarios"]
    assert scenarios
    assert {row["category"] for row in scenarios} <= CATEGORY_SESSIONS
    assert {row["category"] for row in scenarios} == CATEGORY_SESSIONS
    assert payload["summary"] == {"total": len(scenarios), "ok": len(scenarios)}
    assert all(row["ok"] for row in scenarios)


def test_gate_explains_unavailable_model_stack_evidence(gate, tmp_path) -> None:
    output = tmp_path / "report.json"
    assert gate.main(["--output", str(output), "--model-stack-evidence", str(tmp_path / "missing.json")]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bound"]["model_stack_evidence"]["executed"] is False
    assert "unreadable" in str(payload["bound"]["model_stack_evidence"]["reason"])


def test_gate_binds_real_probe_evidence_when_present(gate, tmp_path) -> None:
    evidence = tmp_path / "probe.json"
    evidence.write_text(json.dumps({"executed": True, "ok": True, "checks": []}), encoding="utf-8")
    output = tmp_path / "report.json"
    assert gate.main(["--output", str(output), "--model-stack-evidence", str(evidence)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bound"]["model_stack_evidence"]["ok"] is True


def test_reconciliation_scenarios_cover_unknown_and_resolved_states(gate) -> None:
    with __import__("tempfile").TemporaryDirectory() as scope:
        store = Path(scope) / "receipts"
        store.mkdir(parents=True)
        __import__("os").environ["COMPANY_AGENT_RECEIPT_DIR"] = str(store)
        try:
            scenarios = gate.run_scenarios(store)
        finally:
            __import__("os").environ.pop("COMPANY_AGENT_RECEIPT_DIR", None)
    rows = {row["scenario"]: row for row in scenarios}
    assert rows["unresolved-dispatch-flagged"]["ok"] is True
    assert rows["unknown-outcome-flagged"]["ok"] is True
    assert rows["resolved-clears"]["ok"] is True
