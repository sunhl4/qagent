from __future__ import annotations

import os
import sqlite3
import time
import uuid
from collections.abc import Mapping
from pathlib import Path

from company_agent.catalog import _load_object


class WorkItemError(ValueError):
    """Raised when a bounded work-item request violates its contract."""


def _contract() -> dict:
    return _load_object("superagent.json")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkItemError(f"{field} is invalid")
    return value.strip()


def _bounded(value: object, field: str, maximum: int) -> str:
    result = _text(value, field)
    if len(result.encode("utf-8")) > maximum:
        raise WorkItemError(f"{field} is too long")
    return result


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class WorkItemStore:
    """SQLite ledger for source events and explicitly accepted work."""

    def __init__(self, path: str | Path | None = None) -> None:
        contract = _contract()
        configured = str(os.environ.get(contract["db_env"]) or "").strip()
        self.path = Path(path).expanduser().resolve() if path else (
            Path(configured).expanduser() if configured
            else Path.home() / ".local" / "state" / "company-agent" / "work-items.sqlite3"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources(
                source TEXT PRIMARY KEY, kind TEXT NOT NULL, policy_version TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS threads(
                thread_key TEXT PRIMARY KEY, source TEXT NOT NULL, thread_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS triggers(
                trigger_id TEXT PRIMARY KEY, source TEXT NOT NULL, thread_key TEXT NOT NULL,
                actor_id TEXT NOT NULL, human INTEGER NOT NULL, addressed TEXT,
                text TEXT NOT NULL, disposition TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions(
                decision_id TEXT PRIMARY KEY, trigger_id TEXT NOT NULL, kind TEXT NOT NULL,
                strength TEXT NOT NULL, scope TEXT NOT NULL, reason TEXT NOT NULL,
                evidence TEXT NOT NULL, observed INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mandates(
                mandate_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, scope TEXT NOT NULL,
                created_at TEXT NOT NULL, revoked_at TEXT
            );
            CREATE TABLE IF NOT EXISTS tickets(
                ticket_id TEXT PRIMARY KEY, mandate_id TEXT NOT NULL, origin_trigger_id TEXT NOT NULL,
                title TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS assignments(
                assignment_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, state TEXT NOT NULL,
                report_kind TEXT, report_text TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subscriptions(
                ticket_id TEXT NOT NULL, thread_key TEXT NOT NULL, context_only INTEGER NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(ticket_id, thread_key)
            );
            """
        )

    def __enter__(self) -> "WorkItemStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.db.close()

    def receive(
        self,
        source: object,
        thread_id: object,
        actor_id: object,
        text: object,
        *,
        human: bool = True,
        addressed: str | None = None,
    ) -> dict:
        contract = _contract()["limits"]
        source = _bounded(source, "source", contract["source_bytes"])
        thread_id = _bounded(thread_id, "thread_id", contract["thread_id_bytes"])
        actor_id = _bounded(actor_id, "actor_id", contract["actor_id_bytes"])
        text = _bounded(text, "text", contract["trigger_text_bytes"])
        if source not in _contract()["source_kinds"]:
            raise WorkItemError("source is invalid")
        if not isinstance(human, bool):
            raise WorkItemError("human is invalid")
        if addressed not in {None, "mention", "direct"}:
            raise WorkItemError("addressed is invalid")
        thread_key = f"{source}:{thread_id}"
        trigger_id = _new_id("trg")
        now = _now()
        self.db.execute(
            "INSERT OR IGNORE INTO sources VALUES(?,?,?,?)",
            (source, source, "local", now),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO threads VALUES(?,?,?,?)",
            (thread_key, source, thread_id, now),
        )
        self.db.execute(
            "INSERT INTO triggers VALUES(?,?,?,?,?,?,?,?,?)",
            (trigger_id, source, thread_key, actor_id, int(human), addressed, text, "candidate", now),
        )
        self.db.commit()
        row = self.db.execute("SELECT * FROM triggers WHERE trigger_id=?", (trigger_id,)).fetchone()
        return dict(row)

    def evaluate(
        self,
        trigger_id: object,
        *,
        mode: str = "observe",
        strength: str = "explicit",
        scope: object,
        title: object,
        reason: object,
        evidence: object,
        worktree_name: object = "work-item",
    ) -> dict:
        contract = _contract()
        trigger_id = _text(trigger_id, "trigger_id")
        if mode not in contract["accept_modes"]:
            raise WorkItemError("mode is invalid")
        if strength not in {"explicit", "inferred"}:
            raise WorkItemError("strength is invalid")
        limits = contract["limits"]
        scope = _bounded(scope, "scope", limits["scope_bytes"])
        title = _bounded(title, "title", limits["title_bytes"])
        reason = _bounded(reason, "reason", limits["report_bytes"])
        evidence = _bounded(evidence, "evidence", limits["report_bytes"])
        _bounded(worktree_name, "worktree_name", limits["worktree_name_bytes"])
        trigger = self.db.execute("SELECT * FROM triggers WHERE trigger_id=?", (trigger_id,)).fetchone()
        if trigger is None:
            raise WorkItemError("unknown trigger")
        observed = strength == "inferred" and mode == "observe"
        accepted = mode != "off" and not observed
        decision_id = _new_id("dec")
        now = _now()
        self.db.execute(
            "INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)",
            (decision_id, trigger_id, "accept" if accepted else "ignore", strength, scope,
             reason, evidence, int(observed), now),
        )
        mandate_id = ticket_id = assignment_id = None
        if accepted:
            mandate_id, ticket_id, assignment_id = _new_id("mnd"), _new_id("tic"), _new_id("asn")
            self.db.execute("INSERT INTO mandates VALUES(?,?,?,?,?)", (mandate_id, decision_id, scope, now, None))
            self.db.execute(
                "INSERT INTO tickets VALUES(?,?,?,?,?,?,?)",
                (ticket_id, mandate_id, trigger_id, title, "open", now, None),
            )
            self.db.execute(
                "INSERT INTO subscriptions VALUES(?,?,?,?)",
                (ticket_id, trigger["thread_key"], 0, now),
            )
            self.db.execute(
                "INSERT INTO assignments VALUES(?,?,?,?,?,?,?)",
                (assignment_id, ticket_id, "pending", None, None, now, now),
            )
        self.db.commit()
        return {
            "decision_id": decision_id,
            "kind": "accept" if accepted else "ignore",
            "observed": observed,
            "mandate_id": mandate_id,
            "ticket_id": ticket_id,
            "assignment_id": assignment_id,
            "trigger_id": trigger_id,
        }

    def recoverable(self) -> list[dict]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM assignments WHERE state IN ('pending','running') ORDER BY created_at"
        ).fetchall()]


def work_item(args: Mapping[str, object]) -> dict:
    action = _text(args.get("action"), "action")
    with WorkItemStore() as store:
        if action == "receive":
            row = store.receive(
                args.get("source", _contract()["default_source"]), args.get("thread_id"),
                args.get("actor_id"), args.get("text"), human=args.get("human", True),
                addressed=args.get("addressed"),
            )
            return {
                "action": action, "status": "ok", "authority": "candidate", "items": [],
                "work_item_id": "", "trigger_id": row["trigger_id"], "thread_key": row["thread_key"],
                "decision_id": "", "mandate_id": "", "ticket_id": "", "assignment_id": "",
                "source": row["source"], "kind": "candidate", "count": 0, "available": True,
            }
        if action == "evaluate":
            result = store.evaluate(
                args.get("trigger_id"), mode=args.get("mode", "observe"),
                strength=args.get("strength", "explicit"), scope=args.get("scope"),
                title=args.get("title"), reason=args.get("reason"), evidence=args.get("evidence"),
                worktree_name=args.get("worktree_name", "work-item"),
            )
            return {
                "action": action, "status": "ok", "authority": "mandate" if result["ticket_id"] else "none",
                "items": [], "work_item_id": result["ticket_id"] or "", "trigger_id": result["trigger_id"],
                "thread_key": "", "decision_id": result["decision_id"],
                "mandate_id": result["mandate_id"] or "", "ticket_id": result["ticket_id"] or "",
                "assignment_id": result["assignment_id"] or "", "source": "", "kind": result["kind"],
                "count": 0, "available": True,
            }
        if action == "recover":
            return {
                "action": action, "status": "ok", "authority": "none", "items": [],
                "work_item_id": "", "trigger_id": "", "thread_key": "", "decision_id": "",
                "mandate_id": "", "ticket_id": "", "assignment_id": "", "source": "",
                "kind": "assignment", "count": len(store.recoverable()), "available": True,
            }
        if action == "summary":
            return {
                "action": action, "status": "ok", "authority": "none", "items": [],
                "work_item_id": "", "trigger_id": "", "thread_key": "", "decision_id": "",
                "mandate_id": "", "ticket_id": "", "assignment_id": "", "source": "",
                "kind": "summary", "count": 0, "available": True,
            }
    raise WorkItemError("unknown work item action")
