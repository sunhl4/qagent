import json
from pathlib import Path
from threading import Thread

import pytest

from company_agent.work_items import WorkItemError, WorkItemStore, work_item


def test_accept_persists_ticket(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive(
            "company", "thread", "alice", "Fix", addressed="mention", tenant_id="local",
        )
        result = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix", tenant_id="local",
        )
        assert result["ticket_id"]
        again = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix again",
            reason="request", evidence="Fix", tenant_id="local",
        )
        assert again["ticket_id"] == result["ticket_id"]
        assert store.recoverable("local")[0]["assignment_id"] == result["assignment_id"]


def test_observe_does_not_create_ticket(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "bot", "Possible", human=False, tenant_id="local")
        result = store.evaluate(
            trigger["trigger_id"], mode="observe", strength="inferred", scope="boot",
            title="Possible", reason="candidate", evidence="Possible", tenant_id="local",
        )
        assert result["observed"] is True
        assert result["ticket_id"] is None


def test_mandate_scope_must_be_a_company_preset(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", addressed="mention", tenant_id="local")
        with pytest.raises(WorkItemError, match="company preset"):
            store.evaluate(
                trigger["trigger_id"], mode="auto", scope="shell", title="Fix",
                reason="request", evidence="Fix", tenant_id="local",
            )


def test_idempotency_conflict_and_closed_channel(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        store.receive(
            "company", "thread", "alice", "Fix", tenant_id="local", idempotency_key="same",
        )
        with pytest.raises(WorkItemError, match="idempotency conflict"):
            store.receive(
                "company", "thread", "alice", "Other", tenant_id="local", idempotency_key="same",
            )
        with pytest.raises(WorkItemError, match="tenant_id is required"):
            store.receive("company", "thread", "alice", "Fix")
        with pytest.raises(WorkItemError, match="source channel is closed"):
            store.receive("github", "thread", "alice", "Fix", tenant_id="local")
        with pytest.raises(WorkItemError, match="schema version is invalid"):
            store.receive(
                "company", "thread", "alice", "Fix", tenant_id="local", schema_version="9",
            )
        with pytest.raises(WorkItemError, match="source channel is closed"):
            store.receive("feishu", "thread", "alice", "Fix", tenant_id="local")
        first = store.receive(
            "workspace", "thread", "alice", "Fix", tenant_id="local", idempotency_key="stable",
            policy_version="company-policy",
        )
        second = store.receive(
            "workspace", "thread", "alice", "Fix", tenant_id="local", idempotency_key="stable",
            policy_version="company-policy",
        )
        assert second["trigger_id"] == first["trigger_id"]
        with pytest.raises(WorkItemError, match="idempotency conflict"):
            store.receive(
                "workspace", "thread", "alice", "Fix", tenant_id="local", idempotency_key="stable",
                policy_version="other-policy",
            )


def test_ended_ticket_can_be_evaluated_again(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="local")
        first = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix", tenant_id="local",
        )
        store.note_execution(first["assignment_id"], "ended", tenant_id="local")
        assert store.recoverable("local") == []
        second = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix again",
            reason="request", evidence="Fix", tenant_id="local",
        )
        assert second["ticket_id"]
        assert second["ticket_id"] != first["ticket_id"]


def test_missing_record_is_not_a_cross_tenant_error(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        with pytest.raises(WorkItemError, match="unknown trigger"):
            store.evaluate(
                "missing", mode="auto", scope="lab", title="Fix",
                reason="request", evidence="Fix", tenant_id="local",
            )
        with pytest.raises(WorkItemError, match="unknown assignment"):
            store.note_execution("missing", "ended", tenant_id="local")


def test_recover_returns_only_the_short_execution_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "w.sqlite3"))
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix the leak", tenant_id="local")
        accepted = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix the leak", tenant_id="local",
        )
        store.bind_execution(
            accepted["assignment_id"], "dsh:session-1", "company.workflow", tenant_id="local",
        )
        stored = store.db.execute("SELECT context_only FROM subscriptions").fetchone()
        assert stored["context_only"] == 1
    recovered = work_item({"action": "recover", "tenant_id": "local"})
    assert recovered["count"] == 1
    assert recovered["available"] is True
    assert recovered["items"] == [{
        "assignment_id": accepted["assignment_id"],
        "ticket_id": accepted["ticket_id"],
        "execution_state": "pending",
        "session_ref": "dsh:session-1",
        "tool_pack": "company.workflow",
        "thread_key": "company:thread",
    }]
    assert "Fix the leak" not in str(recovered["items"])
    other = work_item({"action": "recover", "tenant_id": "tenant-b"})
    assert other["items"] == []
    assert other["count"] == 0


def test_only_explicit_auto_opens_a_ticket(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="local")
        observed = store.evaluate(
            trigger["trigger_id"], mode="observe", strength="explicit", scope="lab",
            title="Fix", reason="request", evidence="Fix", tenant_id="local",
        )
        inferred = store.evaluate(
            trigger["trigger_id"], mode="auto", strength="inferred", scope="lab",
            title="Fix", reason="request", evidence="Fix", tenant_id="local",
        )
        stopped = store.evaluate(
            trigger["trigger_id"], mode="off", strength="explicit", scope="lab",
            title="Fix", reason="request", evidence="Fix", tenant_id="local",
        )
        assert observed["ticket_id"] is None and observed["observed"] is True
        assert inferred["ticket_id"] is None and inferred["kind"] == "ignore"
        assert stopped["ticket_id"] is None and stopped["observed"] is False
        assert store.recoverable("local") == []


def test_reconcile_closes_unknown_without_a_new_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "w.sqlite3"))
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="local")
        accepted = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix",
            reason="request", evidence="Fix", tenant_id="local",
        )
        store.note_execution(accepted["assignment_id"], "unknown", tenant_id="local")
        with pytest.raises(WorkItemError, match="not retryable"):
            store.note_execution(accepted["assignment_id"], "ended", tenant_id="local")
        with pytest.raises(WorkItemError, match="reconcile evidence is invalid"):
            store.reconcile(accepted["assignment_id"], "api_key", tenant_id="local")
        with pytest.raises(WorkItemError, match="cross-tenant"):
            store.reconcile(accepted["assignment_id"], "lease-1", tenant_id="tenant-b")
    closed = work_item({
        "action": "reconcile",
        "assignment_id": accepted["assignment_id"],
        "tenant_id": "local",
        "evidence": "lease-1",
    })
    assert closed["ticket_id"] == accepted["ticket_id"]
    assert closed["assignment_id"] == accepted["assignment_id"]
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        assert store.recoverable("local") == []
        with pytest.raises(WorkItemError, match="reconcile requires unknown execution"):
            store.reconcile(accepted["assignment_id"], "lease-1", tenant_id="local")
        again = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="lab", title="Fix again",
            reason="request", evidence="Fix", tenant_id="local",
        )
        assert again["ticket_id"] != accepted["ticket_id"]
        with pytest.raises(WorkItemError, match="reconcile requires unknown execution"):
            store.reconcile(again["assignment_id"], "lease-1", tenant_id="local")
        with pytest.raises(WorkItemError, match="unknown field"):
            work_item({
                "action": "reconcile",
                "assignment_id": again["assignment_id"],
                "tenant_id": "local",
                "evidence": "lease-1",
                "session_ref": "dsh:session-2",
            })


def test_concurrent_accept_and_bind_keep_one_record(tmp_path: Path) -> None:
    path = tmp_path / "w.sqlite3"
    with WorkItemStore(path) as store:
        trigger = store.receive("company", "thread", "alice", "Fix", tenant_id="local")
        trigger_id = trigger["trigger_id"]
    tickets: list[str] = []
    errors: list[BaseException] = []

    def accept() -> None:
        try:
            with WorkItemStore(path) as store:
                result = store.evaluate(
                    trigger_id, mode="auto", scope="lab", title="Fix",
                    reason="request", evidence="Fix", tenant_id="local",
                )
                tickets.append(result["ticket_id"])
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=accept)
    second = Thread(target=accept)
    first.start()
    second.start()
    first.join()
    second.join()
    assert errors == []
    assert len(tickets) == 2
    assert tickets[0] == tickets[1]
    with WorkItemStore(path) as store:
        open_count = store.db.execute(
            "SELECT COUNT(*) AS count FROM tickets WHERE state='open'"
        ).fetchone()["count"]
        assert open_count == 1
        assignment_id = store.recoverable("local")[0]["assignment_id"]
    bound: list[str] = []
    conflicts: list[str] = []

    def bind(session: str) -> None:
        try:
            with WorkItemStore(path) as store:
                result = store.bind_execution(
                    assignment_id, session, "company.workflow", tenant_id="local",
                )
                bound.append(result["session_ref"])
        except WorkItemError as exc:
            conflicts.append(str(exc))

    left = Thread(target=bind, args=("dsh:session-1",))
    right = Thread(target=bind, args=("dsh:session-2",))
    left.start()
    right.start()
    left.join()
    right.join()
    assert len(bound) == 1
    assert conflicts == ["execution binding conflict"]
    assert bound[0] in {"dsh:session-1", "dsh:session-2"}


def test_catalog_and_cli_omit_trigger_text(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "w.sqlite3"))
    with WorkItemStore() as store:
        store.receive("company", "thread", "alice", "secret trigger body", tenant_id="local")
        opened = store.receive(
            "company", "thread-2", "alice", "another secret", addressed="mention", tenant_id="local",
        )
        accepted = store.evaluate(
            opened["trigger_id"], mode="auto", scope="lab", title="Visible  title",
            reason="request", evidence="card", tenant_id="local",
        )
        store.bind_execution(
            accepted["assignment_id"], "dsh:session-1", "company.workflow", tenant_id="local",
        )
        foreign = store.receive("company", "thread-3", "bob", "foreign secret", tenant_id="tenant-b")
        store.evaluate(
            foreign["trigger_id"], mode="auto", scope="boot", title="Foreign",
            reason="request", evidence="x", tenant_id="tenant-b",
        )
        listed = store.catalog("local")
        store.db.execute(
            "UPDATE assignments SET session_ref=? WHERE assignment_id=?",
            ("not a session", accepted["assignment_id"]),
        )
        store.db.commit()
        hidden = store.catalog("local")
    assert listed["observed"] == 1
    assert listed["truncated"] is False
    assert listed["items"][0]["title"] == "Visible title"
    assert listed["items"][0]["mandate"] == "lab"
    assert listed["items"][0]["state"] == "open"
    assert listed["items"][0]["session_ref"] == "dsh:session-1"
    assert "secret" not in json.dumps(listed)
    assert "Foreign" not in json.dumps(listed)
    assert hidden["items"][0]["session_ref"] == ""
    from company_agent.cli import main

    assert main(["automation", "--tenant", "local"]) == 0
    raw = capsys.readouterr().out
    payload = json.loads(raw)
    assert payload["available"] is True
    assert payload["items"][0]["ticket_id"] == listed["items"][0]["ticket_id"]
    assert "secret" not in raw
