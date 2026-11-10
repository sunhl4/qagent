from pathlib import Path

import pytest

from company_agent.cli import main
from company_agent.super_dsh import (
    SuperDshError,
    ingest_platform_signal,
    record_device_handoff,
    topology,
)
from company_agent.work_items import WorkItemError, WorkItemStore, work_item


def test_topology_is_one_company_runtime() -> None:
    shape = topology()
    assert shape["name"] == "company-super-dsh"
    assert shape["audience"] == "company"
    assert shape["runtime"] == "deepseek-harness"
    assert shape["second_runtime"] is False
    assert shape["clocks"] == ["agent", "platform"]
    assert shape["planes"] == ["control", "execution", "platform"]
    assert shape["platform_entry"] == "research-trigger"
    assert shape["channels"]["github"] is False
    assert shape["channels"]["feishu"] is False
    assert shape["channels"]["dingtalk"] is True
    assert shape["channels"]["research"] is True
    assert shape["company_fact_store"] is False
    assert shape["execution_fields"] == ["session_ref", "tool_pack"]
    assert shape["recover_fields"] == [
        "assignment_id", "ticket_id", "execution_state", "session_ref", "tool_pack", "thread_key",
    ]
    assert shape["watchdog"] == {
        "may_open_ticket": False,
        "may_change_policy": False,
        "may_retry_unknown": False,
    }
    assert shape["flow_foundation"]["required_upstream"] == [
        "router", "subscription", "attention",
    ]
    assert shape["flow_foundation"]["unattended"] == {
        "entry": "source-event",
        "opens_ticket_when": "written-rule",
        "default_until_rule": "observe",
        "company_policy_still_applies": True,
    }


def test_platform_signal_stays_a_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    result = work_item({
        "action": "signal",
        "signal_type": "experiment.completed.v1",
        "tenant_id": "tenant-a",
        "resource_id": "run-1",
        "resource_version": 2,
        "time": "2026-11-04T00:00:00Z",
    })
    assert result["source"] == "research"
    assert result["authority"] == "candidate"
    assert result["trigger_id"]
    assert result["ticket_id"] == ""
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        assert store.recoverable("tenant-a") == []


def test_platform_signal_rejects_sensitive_fields(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        with pytest.raises(SuperDshError, match="unknown field"):
            ingest_platform_signal(store, {
                "signal_type": "budget.exhausted.v1",
                "tenant_id": "tenant-a",
                "resource_id": "lease-1",
                "resource_version": 1,
                "time": "2026-11-04T00:00:00Z",
                "api_key": "hidden",
            })


def test_research_trigger_can_enter_a_company_mandate(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        signal = ingest_platform_signal(store, {
            "signal_type": "lease.changed.v1",
            "tenant_id": "tenant-a",
            "project_id": "chip",
            "resource_id": "lease-1",
            "resource_version": 1,
            "time": "2026-11-04T00:00:00Z",
        })
        accepted = store.evaluate(
            signal["trigger_id"], mode="auto", scope="lab", title="Review lease",
            reason="platform signal", evidence="lease-1", tenant_id="tenant-a",
        )
        assert accepted["ticket_id"]
        with pytest.raises(WorkItemError, match="company preset"):
            store.evaluate(
                signal["trigger_id"], mode="auto", scope="shell", title="Review lease",
                reason="platform signal", evidence="lease-1", tenant_id="tenant-a",
            )


def test_signal_conflict_keeps_its_own_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    payload = {
        "action": "signal",
        "signal_type": "lease.changed.v1",
        "tenant_id": "tenant-a",
        "resource_id": "lease-1",
        "resource_version": 1,
        "time": "2026-11-04T00:00:00Z",
    }
    work_item(payload)
    with pytest.raises(WorkItemError, match="idempotency conflict"):
        work_item({**payload, "project_id": "chip"})
    with pytest.raises(WorkItemError, match="unknown field"):
        work_item({**payload, "api_key": "hidden"})


def test_repeated_signal_keeps_one_trigger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    payload = {
        "action": "signal",
        "signal_type": "budget.exhausted.v1",
        "tenant_id": "tenant-a",
        "resource_id": "budget-1",
        "resource_version": 1,
        "time": "2026-11-04T00:00:00Z",
    }
    first = work_item(payload)
    second = work_item(payload)
    assert first["trigger_id"] == second["trigger_id"]
    assert first["ticket_id"] == second["ticket_id"] == ""
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        assert store.recoverable("tenant-a") == []
        with pytest.raises(WorkItemError, match="cross-tenant"):
            store.evaluate(
                first["trigger_id"], mode="auto", scope="lab", title="Review",
                reason="signal", evidence="budget-1", tenant_id="tenant-b",
            )


def test_unknown_execution_is_not_retryable(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        trigger = store.receive(
            "company", "thread", "alice", "Fix", addressed="mention",
            tenant_id="tenant-a", idempotency_key="idem-1", subject_id="alice",
        )
        accepted = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix", tenant_id="tenant-a",
        )
        noted = store.note_execution(accepted["assignment_id"], "unknown", tenant_id="tenant-a")
        assert noted["retryable"] is False
        with pytest.raises(WorkItemError, match="not retryable"):
            store.note_execution(accepted["assignment_id"], "running", tenant_id="tenant-a")
        again = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix", tenant_id="tenant-a",
        )
        assert again["ticket_id"] == accepted["ticket_id"]
        with pytest.raises(WorkItemError, match="cross-tenant"):
            store.note_execution(accepted["assignment_id"], "ended", tenant_id="tenant-b")


def test_device_handoff_stays_a_candidate(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        handoff = {
            "tenant_id": "tenant-a",
            "request_id": "req-1",
            "idempotency_key": "idem-qpu",
            "mandate": "lab",
            "tool": "quantum_device_run",
        }
        first = record_device_handoff(store, handoff)
        second = record_device_handoff(store, handoff)
        assert first["trigger_id"] == second["trigger_id"]
        assert first["ticket_id"] == ""
        assert first["tool"] == "quantum_device_run"
        assert store.recoverable("tenant-a") == []
        with pytest.raises(SuperDshError, match="unknown field"):
            record_device_handoff(store, {**handoff, "circuit": "full circuit text"})


def test_execution_binding_keeps_only_the_session_reference(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="tenant-a")
        accepted = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix", tenant_id="tenant-a",
        )
        bound = store.bind_execution(
            accepted["assignment_id"], "dsh:session-1", "company.workflow", tenant_id="tenant-a",
        )
        again = store.bind_execution(
            accepted["assignment_id"], "dsh:session-1", "company.workflow", tenant_id="tenant-a",
        )
        assert again == bound
        assert set(bound) == {"assignment_id", "ticket_id", "session_ref", "tool_pack"}
        with pytest.raises(WorkItemError, match="execution binding conflict"):
            store.bind_execution(
                accepted["assignment_id"], "dsh:session-2", "company.workflow", tenant_id="tenant-a",
            )
        with pytest.raises(WorkItemError, match="execution record is invalid"):
            store.bind_execution(
                accepted["assignment_id"], "dsh:api_key", "company.workflow", tenant_id="tenant-a",
            )
        with pytest.raises(WorkItemError, match="tool pack is invalid"):
            store.bind_execution(
                accepted["assignment_id"], "dsh:session-1", "shell", tenant_id="tenant-a",
            )
        store.note_execution(accepted["assignment_id"], "unknown", tenant_id="tenant-a")
        with pytest.raises(WorkItemError, match="not retryable"):
            store.bind_execution(
                accepted["assignment_id"], "dsh:session-1", "company.workflow", tenant_id="tenant-a",
            )
        with pytest.raises(WorkItemError, match="unknown assignment"):
            store.bind_execution("missing", "dsh:session-1", "company.workflow", tenant_id="tenant-a")
        with pytest.raises(WorkItemError, match="cross-tenant"):
            store.bind_execution(
                accepted["assignment_id"], "dsh:session-1", "company.workflow", tenant_id="tenant-b",
            )


def test_bind_rejects_a_session_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="tenant-a")
        accepted = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="boot", title="Fix",
            reason="request", evidence="Fix", tenant_id="tenant-a",
        )
    result = work_item({
        "action": "bind",
        "assignment_id": accepted["assignment_id"],
        "tenant_id": "tenant-a",
        "session_ref": "dsh:session-9",
        "tool_pack": "company.workflow",
    })
    assert result["session_ref"] == "dsh:session-9"
    assert result["tool_pack"] == "company.workflow"
    with pytest.raises(WorkItemError, match="unknown field"):
        work_item({
            "action": "bind",
            "assignment_id": accepted["assignment_id"],
            "tenant_id": "tenant-a",
            "session_ref": "dsh:session-9",
            "tool_pack": "company.workflow",
            "transcript": "full session body",
        })


def test_evaluate_binds_the_live_dsh_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:session-current")
    with WorkItemStore(tmp_path / "work.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="tenant-a")
    accepted = work_item({
        "action": "evaluate",
        "trigger_id": trigger["trigger_id"],
        "mode": "auto",
        "strength": "explicit",
        "scope": "lab",
        "title": "Fix",
        "reason": "request",
        "evidence": "Fix",
        "tenant_id": "tenant-a",
    })
    assert accepted["session_ref"] == "dsh:session-current"
    assert accepted["tool_pack"] == "company.workflow"
    recovered = work_item({"action": "recover", "tenant_id": "tenant-a"})
    assert recovered["items"][0]["session_ref"] == "dsh:session-current"
    assert recovered["items"][0]["execution_state"] == "running"
    assert recovered["items"][0]["tool_pack"] == "company.workflow"
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:other-session")
    with pytest.raises(WorkItemError, match="execution binding conflict"):
        work_item({
            "action": "evaluate",
            "trigger_id": trigger["trigger_id"],
            "mode": "auto",
            "strength": "explicit",
            "scope": "lab",
            "title": "Fix",
            "reason": "request",
            "evidence": "Fix",
            "tenant_id": "tenant-a",
        })


def test_architecture_command_reports_the_company_shape(capsys) -> None:
    assert main(["architecture"]) == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "company-super-dsh"
    assert payload["second_runtime"] is False
