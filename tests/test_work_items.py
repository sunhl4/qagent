from pathlib import Path

from company_agent.work_items import WorkItemStore


def test_accept_persists_ticket(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "alice", "Fix", addressed="mention")
        result = store.evaluate(
            trigger["trigger_id"], mode="auto", scope="bounded", title="Fix",
            reason="request", evidence="Fix",
        )
        assert result["ticket_id"]
        assert store.recoverable()[0]["assignment_id"] == result["assignment_id"]


def test_observe_does_not_create_ticket(tmp_path: Path) -> None:
    with WorkItemStore(tmp_path / "w.sqlite3") as store:
        trigger = store.receive("company", "thread", "bot", "Possible", human=False)
        result = store.evaluate(
            trigger["trigger_id"], mode="observe", strength="inferred", scope="possible",
            title="Possible", reason="candidate", evidence="Possible",
        )
        assert result["observed"] is True
        assert result["ticket_id"] is None
