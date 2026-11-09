from company_agent.superagent_adapt import admit_source_event
from company_agent.work_items import WorkItemError, WorkItemStore

import pytest


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    return tmp_path


def test_source_event_without_a_written_rule_stays_observe(isolated) -> None:
    result = admit_source_event({
        "schema_version": "1",
        "source": "research",
        "thread_id": "exp-1",
        "actor_id": "team-a",
        "text": "metric ready",
        "tenant_id": "team-a",
        "idempotency_key": "event-1",
        "written_rule": False,
        "mode": "auto",
        "strength": "explicit",
    })
    assert result["accept_mode"] == "observe"
    assert result["ticket_id"] == ""
    assert result["authority"] == "candidate"
    assert result["policy_applies"] is True
    assert "subscription" in result["upstream_objects"]
    store = WorkItemStore()
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0


def test_written_rule_opens_one_ticket(isolated) -> None:
    result = admit_source_event({
        "schema_version": "1",
        "source": "workspace",
        "thread_id": "exp-2",
        "actor_id": "team-a",
        "text": "written rule ready",
        "tenant_id": "team-a",
        "idempotency_key": "event-2",
        "written_rule": True,
        "mode": "auto",
        "strength": "explicit",
        "scope": "lab",
        "title": "exp-2",
    })
    assert result["accept_mode"] == "auto"
    assert result["ticket_id"]
    assert result["authority"] == "mandate"
    store = WorkItemStore()
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 1
    assert store.db.execute("select count(*) from subscriptions").fetchone()[0] == 1


def test_unknown_upstream_field_fails_closed(isolated) -> None:
    with pytest.raises(ValueError, match="unknown field"):
        admit_source_event({
            "schema_version": "1",
            "source": "research",
            "thread_id": "exp-3",
            "actor_id": "team-a",
            "text": "later field",
            "tenant_id": "team-a",
            "idempotency_key": "event-3",
            "router_hint": "new",
        })


def test_future_schema_and_closed_channel_fail(isolated) -> None:
    with pytest.raises(ValueError, match="schema"):
        admit_source_event({
            "schema_version": "2",
            "source": "research",
            "thread_id": "exp-4",
            "actor_id": "team-a",
            "text": "next schema",
            "tenant_id": "team-a",
            "idempotency_key": "event-4",
        })
    with pytest.raises(WorkItemError, match="closed"):
        admit_source_event({
            "schema_version": "1",
            "source": "github",
            "thread_id": "exp-5",
            "actor_id": "team-a",
            "text": "closed channel",
            "tenant_id": "team-a",
            "idempotency_key": "event-5",
        })
