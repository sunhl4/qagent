from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
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


_RECORD_MARKERS = (
    "secret", "token", "password", "credential", "api_key", "bitstring", "pauli", "shuttle",
)


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
        self.db = sqlite3.connect(self.path, timeout=5.0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
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
                text TEXT NOT NULL, disposition TEXT NOT NULL, created_at TEXT NOT NULL,
                schema_version TEXT NOT NULL DEFAULT '1',
                tenant_id TEXT NOT NULL DEFAULT 'local',
                idempotency_key TEXT,
                subject_id TEXT NOT NULL DEFAULT '',
                policy_version TEXT NOT NULL DEFAULT 'company-policy',
                mandate TEXT NOT NULL DEFAULT '',
                payload_fingerprint TEXT
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
                report_kind TEXT, report_text TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                execution_state TEXT NOT NULL DEFAULT 'pending',
                session_ref TEXT,
                tool_pack TEXT
            );
            CREATE TABLE IF NOT EXISTS subscriptions(
                ticket_id TEXT NOT NULL, thread_key TEXT NOT NULL, context_only INTEGER NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(ticket_id, thread_key)
            );
            """
        )
        self._migrate_control_plane()

    def _migrate_control_plane(self) -> None:
        additions = {
            "triggers": {
                "schema_version": "TEXT NOT NULL DEFAULT '1'",
                "tenant_id": "TEXT NOT NULL DEFAULT 'local'",
                "idempotency_key": "TEXT",
                "subject_id": "TEXT NOT NULL DEFAULT ''",
                "policy_version": "TEXT NOT NULL DEFAULT 'company-policy'",
                "mandate": "TEXT NOT NULL DEFAULT ''",
                "payload_fingerprint": "TEXT",
            },
            "assignments": {
                "execution_state": "TEXT NOT NULL DEFAULT 'pending'",
                "session_ref": "TEXT",
                "tool_pack": "TEXT",
            },
        }
        for table, columns in additions.items():
            found = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
            for name, declaration in columns.items():
                if name not in found:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        self.db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS triggers_tenant_idempotency
            ON triggers(tenant_id, idempotency_key)
            WHERE idempotency_key IS NOT NULL
            """
        )
        duplicates = self.db.execute(
            """
            SELECT origin_trigger_id FROM tickets
            WHERE state='open'
            GROUP BY origin_trigger_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        if duplicates:
            raise WorkItemError("open ticket invariant is already broken")
        self.db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS tickets_one_open_trigger
            ON tickets(origin_trigger_id)
            WHERE state='open'
            """
        )
        self.db.commit()

    def _control(self) -> dict:
        return _contract()["control_plane"]

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.db.rollback()
            raise
        else:
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def _tenant(self, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise WorkItemError("tenant_id is required")
        return _bounded(value, "tenant_id", _contract()["limits"]["tenant_id_bytes"])

    def _fingerprint(self, source: str, subject: str, text: str, policy: str) -> str:
        raw = "\n".join((source, subject, text, policy)).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _trigger_for_tenant(self, trigger_id: str, tenant_id: str) -> sqlite3.Row:
        trigger = self.db.execute("SELECT * FROM triggers WHERE trigger_id=?", (trigger_id,)).fetchone()
        if trigger is None:
            raise WorkItemError("unknown trigger")
        if trigger["tenant_id"] != tenant_id:
            raise WorkItemError("cross-tenant read is denied")
        return trigger

    def _open_ticket(self, trigger_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            """
            SELECT decisions.decision_id AS decision_id, mandates.mandate_id AS mandate_id,
                   tickets.ticket_id AS ticket_id, assignments.assignment_id AS assignment_id
            FROM tickets
            JOIN mandates ON mandates.mandate_id = tickets.mandate_id
            JOIN decisions ON decisions.decision_id = mandates.decision_id
            JOIN assignments ON assignments.ticket_id = tickets.ticket_id
            WHERE tickets.origin_trigger_id=? AND tickets.state='open'
            ORDER BY tickets.created_at
            LIMIT 1
            """,
            (trigger_id,),
        ).fetchone()

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
        tenant_id: object = None,
        idempotency_key: object = None,
        subject_id: object = None,
        policy_version: object = None,
        schema_version: object = None,
    ) -> dict:
        limits = _contract()["limits"]
        control = self._control()
        source = _bounded(source, "source", limits["source_bytes"])
        thread_id = _bounded(thread_id, "thread_id", limits["thread_id_bytes"])
        actor_id = _bounded(actor_id, "actor_id", limits["actor_id_bytes"])
        text = _bounded(text, "text", limits["trigger_text_bytes"])
        tenant = self._tenant(tenant_id)
        subject = _bounded(subject_id or actor_id, "subject_id", limits["subject_id_bytes"])
        policy = _bounded(
            policy_version or control["default_policy_version"],
            "policy_version",
            limits["policy_version_bytes"],
        )
        if schema_version is not None and schema_version != control["schema_version"]:
            raise WorkItemError("schema version is invalid")
        if idempotency_key is None:
            key = _new_id("idem")
        else:
            key = _bounded(idempotency_key, "idempotency_key", limits["idempotency_key_bytes"])
        if source not in _contract()["source_kinds"]:
            raise WorkItemError("source is invalid")
        if source not in control["open_sources"]:
            raise WorkItemError("source channel is closed")
        if not isinstance(human, bool):
            raise WorkItemError("human is invalid")
        if addressed not in {None, "mention", "direct"}:
            raise WorkItemError("addressed is invalid")
        fingerprint = self._fingerprint(source, subject, text, policy)
        thread_key = f"{source}:{thread_id}"
        trigger_id = _new_id("trg")
        now = _now()
        try:
            with self._transaction():
                row = self.db.execute(
                    "SELECT * FROM triggers WHERE tenant_id=? AND idempotency_key=?",
                    (tenant, key),
                ).fetchone()
                if row is not None:
                    if row["payload_fingerprint"] != fingerprint:
                        raise WorkItemError("idempotency conflict")
                    recorded = dict(row)
                else:
                    self.db.execute(
                        "INSERT OR IGNORE INTO sources VALUES(?,?,?,?)",
                        (source, source, policy, now),
                    )
                    self.db.execute(
                        "INSERT OR IGNORE INTO threads VALUES(?,?,?,?)",
                        (thread_key, source, thread_id, now),
                    )
                    self.db.execute(
                        """
                        INSERT INTO triggers(
                            trigger_id, source, thread_key, actor_id, human, addressed, text, disposition,
                            created_at, schema_version, tenant_id, idempotency_key, subject_id, policy_version,
                            mandate, payload_fingerprint
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            trigger_id, source, thread_key, actor_id, int(human), addressed, text, "candidate",
                            now, control["schema_version"], tenant, key, subject, policy, "", fingerprint,
                        ),
                    )
                    recorded = dict(self.db.execute(
                        "SELECT * FROM triggers WHERE trigger_id=?",
                        (trigger_id,),
                    ).fetchone())
        except sqlite3.IntegrityError:
            row = self.db.execute(
                "SELECT * FROM triggers WHERE tenant_id=? AND idempotency_key=?",
                (tenant, key),
            ).fetchone()
            if row is None:
                raise WorkItemError("trigger was not recorded") from None
            if row["payload_fingerprint"] != fingerprint:
                raise WorkItemError("idempotency conflict") from None
            recorded = dict(row)
        return recorded

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
        tenant_id: object = None,
    ) -> dict:
        contract = _contract()
        trigger_id = _text(trigger_id, "trigger_id")
        if mode not in contract["accept_modes"]:
            raise WorkItemError("mode is invalid")
        if strength not in {"explicit", "inferred"}:
            raise WorkItemError("strength is invalid")
        limits = contract["limits"]
        scope = _bounded(scope, "scope", limits["scope_bytes"])
        from company_agent.harness_compat import HarnessCompatError, mandate_scopes

        try:
            allowed_scopes = mandate_scopes()
        except HarnessCompatError as exc:
            raise WorkItemError("harness contract is invalid") from exc
        if scope not in allowed_scopes:
            raise WorkItemError("scope is not a company preset")
        title = _bounded(title, "title", limits["title_bytes"])
        reason = _bounded(reason, "reason", limits["report_bytes"])
        evidence = _bounded(evidence, "evidence", limits["report_bytes"])
        _bounded(worktree_name, "worktree_name", limits["worktree_name_bytes"])
        rule = self._control()["ticket_rule"]
        if rule.get("mode") != "auto" or rule.get("strength") != "explicit":
            raise WorkItemError("ticket rule is invalid")
        tenant = self._tenant(tenant_id)

        def _open_result(open_ticket: sqlite3.Row) -> dict:
            return {
                "decision_id": open_ticket["decision_id"],
                "kind": "accept",
                "observed": False,
                "mandate_id": open_ticket["mandate_id"],
                "ticket_id": open_ticket["ticket_id"],
                "assignment_id": open_ticket["assignment_id"],
                "trigger_id": trigger_id,
            }

        try:
            with self._transaction():
                trigger = self._trigger_for_tenant(trigger_id, tenant)
                open_ticket = self._open_ticket(trigger_id)
                if open_ticket is not None:
                    outcome = _open_result(open_ticket)
                else:
                    observed = mode == "observe"
                    accepted = mode == rule["mode"] and strength == rule["strength"]
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
                        self.db.execute(
                            "INSERT INTO mandates VALUES(?,?,?,?,?)",
                            (mandate_id, decision_id, scope, now, None),
                        )
                        self.db.execute(
                            "INSERT INTO tickets VALUES(?,?,?,?,?,?,?)",
                            (ticket_id, mandate_id, trigger_id, title, "open", now, None),
                        )
                        self.db.execute(
                            "INSERT INTO subscriptions VALUES(?,?,?,?)",
                            (ticket_id, trigger["thread_key"], 1, now),
                        )
                        self.db.execute(
                            """
                            INSERT INTO assignments(
                                assignment_id, ticket_id, state, report_kind, report_text,
                                created_at, updated_at, execution_state
                            ) VALUES(?,?,?,?,?,?,?,?)
                            """,
                            (assignment_id, ticket_id, "pending", None, None, now, now, "pending"),
                        )
                        self.db.execute(
                            "UPDATE triggers SET mandate=? WHERE trigger_id=?",
                            (scope, trigger_id),
                        )
                    outcome = {
                        "decision_id": decision_id,
                        "kind": "accept" if accepted else "ignore",
                        "observed": observed,
                        "mandate_id": mandate_id,
                        "ticket_id": ticket_id,
                        "assignment_id": assignment_id,
                        "trigger_id": trigger_id,
                    }
        except sqlite3.IntegrityError:
            open_ticket = self._open_ticket(trigger_id)
            if open_ticket is None:
                raise WorkItemError("open ticket invariant failed") from None
            outcome = _open_result(open_ticket)
        return outcome

    def recoverable(self, tenant_id: object = None) -> list[dict]:
        tenant = self._tenant(tenant_id)
        fields = self._control()["recover_fields"]
        limit = int(_contract()["limits"]["max_query_items"])
        rows = self.db.execute(
            """
            SELECT assignments.assignment_id AS assignment_id,
                   assignments.ticket_id AS ticket_id,
                   assignments.execution_state AS execution_state,
                   COALESCE(assignments.session_ref, '') AS session_ref,
                   COALESCE(assignments.tool_pack, '') AS tool_pack,
                   COALESCE(subscriptions.thread_key, '') AS thread_key
            FROM assignments
            JOIN tickets ON tickets.ticket_id = assignments.ticket_id
            JOIN triggers ON triggers.trigger_id = tickets.origin_trigger_id
            LEFT JOIN subscriptions ON subscriptions.ticket_id = tickets.ticket_id
            WHERE assignments.state IN ('pending','running') AND triggers.tenant_id=?
            ORDER BY assignments.created_at
            LIMIT ?
            """,
            (tenant, limit + 1),
        ).fetchall()
        self._recover_truncated = len(rows) > limit
        return [{name: row[name] for name in fields} for row in rows[:limit]]

    def note_execution(self, assignment_id: object, state: object, *, tenant_id: object = None) -> dict:
        assignment_id = _text(assignment_id, "assignment_id")
        if not isinstance(state, str) or state not in {"pending", "running", "unknown", "ended"}:
            raise WorkItemError("execution state is invalid")
        tenant = self._tenant(tenant_id)
        with self._transaction():
            row = self.db.execute(
                """
                SELECT assignments.execution_state AS execution_state,
                       assignments.ticket_id AS ticket_id,
                       triggers.tenant_id AS tenant_id
                FROM assignments
                JOIN tickets ON tickets.ticket_id = assignments.ticket_id
                JOIN triggers ON triggers.trigger_id = tickets.origin_trigger_id
                WHERE assignments.assignment_id=?
                """,
                (assignment_id,),
            ).fetchone()
            if row is None:
                raise WorkItemError("unknown assignment")
            if row["tenant_id"] != tenant:
                raise WorkItemError("cross-tenant read is denied")
            if row["execution_state"] == "unknown" and state != "unknown":
                raise WorkItemError("unknown execution is not retryable")
            now = _now()
            self.db.execute(
                "UPDATE assignments SET execution_state=?, updated_at=? WHERE assignment_id=?",
                (state, now, assignment_id),
            )
            if state == "ended":
                self.db.execute(
                    "UPDATE assignments SET state='ended' WHERE assignment_id=?",
                    (assignment_id,),
                )
                self.db.execute(
                    "UPDATE tickets SET state='ended', ended_at=? WHERE ticket_id=?",
                    (now, row["ticket_id"]),
                )
        return {"execution_state": state, "retryable": state != "unknown"}

    def bind_execution(
        self,
        assignment_id: object,
        session_ref: object,
        tool_pack: object,
        *,
        tenant_id: object = None,
    ) -> dict:
        """Record the DSH session reference and tool pack. Do not store a transcript or result."""
        assignment_id = _text(assignment_id, "assignment_id")
        tenant = self._tenant(tenant_id)
        limits = _contract()["limits"]
        session = _bounded(session_ref, "session_ref", limits["session_ref_bytes"])
        pack = _bounded(tool_pack, "tool_pack", limits["tool_pack_bytes"])
        if not session.startswith("dsh:") or len(session) <= 4 or any(character.isspace() for character in session[4:]):
            raise WorkItemError("session_ref is invalid")
        if any(marker in f"{session}\n{pack}".casefold() for marker in _RECORD_MARKERS):
            raise WorkItemError("execution record is invalid")
        from company_agent.capabilities import list_capabilities

        if pack not in {item.id for item in list_capabilities()}:
            raise WorkItemError("tool pack is invalid")
        with self._transaction():
            row = self.db.execute(
                """
                SELECT assignments.execution_state AS execution_state,
                       assignments.session_ref AS session_ref,
                       assignments.tool_pack AS tool_pack,
                       assignments.ticket_id AS ticket_id,
                       tickets.state AS ticket_state,
                       triggers.tenant_id AS tenant_id
                FROM assignments
                JOIN tickets ON tickets.ticket_id = assignments.ticket_id
                JOIN triggers ON triggers.trigger_id = tickets.origin_trigger_id
                WHERE assignments.assignment_id=?
                """,
                (assignment_id,),
            ).fetchone()
            if row is None:
                raise WorkItemError("unknown assignment")
            if row["tenant_id"] != tenant:
                raise WorkItemError("cross-tenant read is denied")
            if row["execution_state"] == "unknown":
                raise WorkItemError("unknown execution is not retryable")
            if row["session_ref"]:
                if row["session_ref"] == session and row["tool_pack"] == pack:
                    bound = {
                        "assignment_id": assignment_id,
                        "ticket_id": row["ticket_id"],
                        "session_ref": session,
                        "tool_pack": pack,
                    }
                else:
                    raise WorkItemError("execution binding conflict")
            elif row["ticket_state"] == "ended":
                raise WorkItemError("ticket has ended")
            else:
                updated = self.db.execute(
                    """
                    UPDATE assignments
                    SET session_ref=?, tool_pack=?, updated_at=?
                    WHERE assignment_id=? AND session_ref IS NULL
                    """,
                    (session, pack, _now(), assignment_id),
                )
                if updated.rowcount != 1:
                    raise WorkItemError("execution binding conflict")
                bound = {
                    "assignment_id": assignment_id,
                    "ticket_id": row["ticket_id"],
                    "session_ref": session,
                    "tool_pack": pack,
                }
        return bound

    def reconcile(self, assignment_id: object, evidence: object, *, tenant_id: object = None) -> dict:
        """Close an unknown execution. Do not bind a session or mark it running."""
        rule = self._control()["reconcile_rule"]
        if (
            rule.get("from_execution") != "unknown"
            or rule.get("to_execution") != "ended"
            or rule.get("to_ticket") != "ended"
        ):
            raise WorkItemError("reconcile rule is invalid")
        assignment_id = _text(assignment_id, "assignment_id")
        tenant = self._tenant(tenant_id)
        evidence_text = _bounded(evidence, "evidence", _contract()["limits"]["report_bytes"])
        if any(marker in evidence_text.casefold() for marker in _RECORD_MARKERS):
            raise WorkItemError("reconcile evidence is invalid")
        with self._transaction():
            row = self.db.execute(
                """
                SELECT assignments.execution_state AS execution_state,
                       assignments.ticket_id AS ticket_id,
                       triggers.tenant_id AS tenant_id
                FROM assignments
                JOIN tickets ON tickets.ticket_id = assignments.ticket_id
                JOIN triggers ON triggers.trigger_id = tickets.origin_trigger_id
                WHERE assignments.assignment_id=?
                """,
                (assignment_id,),
            ).fetchone()
            if row is None:
                raise WorkItemError("unknown assignment")
            if row["tenant_id"] != tenant:
                raise WorkItemError("cross-tenant read is denied")
            if row["execution_state"] != rule["from_execution"]:
                raise WorkItemError("reconcile requires unknown execution")
            now = _now()
            updated = self.db.execute(
                """
                UPDATE assignments
                SET execution_state=?, state='ended', report_kind='reconciled', report_text=?, updated_at=?
                WHERE assignment_id=? AND execution_state=?
                """,
                (rule["to_execution"], evidence_text, now, assignment_id, rule["from_execution"]),
            )
            if updated.rowcount != 1:
                raise WorkItemError("reconcile requires unknown execution")
            closed_ticket = self.db.execute(
                "UPDATE tickets SET state=?, ended_at=? WHERE ticket_id=? AND state='open'",
                (rule["to_ticket"], now, row["ticket_id"]),
            )
            if closed_ticket.rowcount != 1:
                raise WorkItemError("reconcile requires unknown execution")
            closed = {
                "assignment_id": assignment_id,
                "ticket_id": row["ticket_id"],
                "execution_state": rule["to_execution"],
            }
        return closed


def _host_session_ref() -> str | None:
    """Return the DSH session that is executing this call. The model cannot supply it."""
    raw = os.environ.get("COMPANY_AGENT_SESSION_ID", "").strip()
    if not raw:
        return None
    if (
        not raw.startswith("dsh:")
        or len(raw) <= 4
        or len(raw.encode("utf-8")) > _contract()["limits"]["session_ref_bytes"]
        or any(character.isspace() for character in raw[4:])
    ):
        raise WorkItemError("session_ref is invalid")
    return raw


def work_item(args: Mapping[str, object]) -> dict:
    action = _text(args.get("action"), "action")
    with WorkItemStore() as store:
        if action == "receive":
            row = store.receive(
                args.get("source", _contract()["default_source"]), args.get("thread_id"),
                args.get("actor_id"), args.get("text"), human=args.get("human", True),
                addressed=args.get("addressed"), tenant_id=args.get("tenant_id"),
                idempotency_key=args.get("idempotency_key"), subject_id=args.get("subject_id"),
                policy_version=args.get("policy_version"), schema_version=args.get("schema_version"),
            )
            return {
                "action": action, "status": "ok", "authority": "candidate", "items": [],
                "work_item_id": "", "trigger_id": row["trigger_id"], "thread_key": row["thread_key"],
                "decision_id": "", "mandate_id": "", "ticket_id": "", "assignment_id": "",
                "source": row["source"], "kind": "candidate", "count": 0, "available": True,
            }
        if action == "evaluate":
            session = _host_session_ref()
            result = store.evaluate(
                args.get("trigger_id"), mode=args.get("mode", "observe"),
                strength=args.get("strength", "explicit"), scope=args.get("scope"),
                title=args.get("title"), reason=args.get("reason"), evidence=args.get("evidence"),
                worktree_name=args.get("worktree_name", "work-item"), tenant_id=args.get("tenant_id"),
            )
            payload = {
                "action": action, "status": "ok", "authority": "mandate" if result["ticket_id"] else "none",
                "items": [], "work_item_id": result["ticket_id"] or "", "trigger_id": result["trigger_id"],
                "thread_key": "", "decision_id": result["decision_id"],
                "mandate_id": result["mandate_id"] or "", "ticket_id": result["ticket_id"] or "",
                "assignment_id": result["assignment_id"] or "", "source": "", "kind": result["kind"],
                "count": 0, "available": True,
            }
            if result["assignment_id"] and session:
                bound = store.bind_execution(
                    result["assignment_id"], session, "company.workflow",
                    tenant_id=args.get("tenant_id"),
                )
                store.note_execution(result["assignment_id"], "running", tenant_id=args.get("tenant_id"))
                payload["session_ref"] = bound["session_ref"]
                payload["tool_pack"] = bound["tool_pack"]
            return payload
        if action == "recover":
            rows = store.recoverable(args.get("tenant_id"))
            return {
                "action": action, "status": "ok", "authority": "none", "items": rows,
                "work_item_id": "", "trigger_id": "", "thread_key": "", "decision_id": "",
                "mandate_id": "", "ticket_id": "", "assignment_id": "", "source": "",
                "kind": "assignment", "count": len(rows),
                "available": not store._recover_truncated,
            }
        if action == "summary":
            return {
                "action": action, "status": "ok", "authority": "none", "items": [],
                "work_item_id": "", "trigger_id": "", "thread_key": "", "decision_id": "",
                "mandate_id": "", "ticket_id": "", "assignment_id": "", "source": "",
                "kind": "summary", "count": 0, "available": True,
            }
        if action == "bind":
            allowed = {"action", "assignment_id", "tenant_id", "session_ref", "tool_pack"}
            if not set(args) <= allowed:
                raise WorkItemError("execution record has an unknown field")
            bound = store.bind_execution(
                args.get("assignment_id"), args.get("session_ref"), args.get("tool_pack"),
                tenant_id=args.get("tenant_id"),
            )
            return {
                "action": action, "status": "ok", "authority": "mandate", "items": [],
                "work_item_id": bound["ticket_id"], "trigger_id": "", "thread_key": "",
                "decision_id": "", "mandate_id": "", "ticket_id": bound["ticket_id"],
                "assignment_id": bound["assignment_id"], "source": "", "kind": "assignment",
                "count": 0, "available": True,
                "session_ref": bound["session_ref"], "tool_pack": bound["tool_pack"],
            }
        if action == "reconcile":
            allowed = {"action", "assignment_id", "tenant_id", "evidence"}
            if not set(args) <= allowed:
                raise WorkItemError("reconcile record has an unknown field")
            closed = store.reconcile(
                args.get("assignment_id"), args.get("evidence"), tenant_id=args.get("tenant_id"),
            )
            return {
                "action": action, "status": "ok", "authority": "none", "items": [],
                "work_item_id": closed["ticket_id"], "trigger_id": "", "thread_key": "",
                "decision_id": "", "mandate_id": "", "ticket_id": closed["ticket_id"],
                "assignment_id": closed["assignment_id"], "source": "", "kind": "assignment",
                "count": 0, "available": True,
            }
        if action == "signal":
            from company_agent.super_dsh import SuperDshError, ingest_platform_signal

            allowed = {"action", "signal_type", "tenant_id", "project_id", "resource_id", "resource_version", "time"}
            if not set(args) <= allowed:
                raise WorkItemError("platform signal has an unknown field")
            fields = ("signal_type", "tenant_id", "project_id", "resource_id", "resource_version", "time")
            try:
                signal = ingest_platform_signal(store, {key: args[key] for key in fields if key in args})
            except SuperDshError as exc:
                raise WorkItemError(str(exc)) from exc
            return {
                "action": action, "status": "ok", "authority": signal["authority"], "items": [],
                "work_item_id": "", "trigger_id": signal["trigger_id"],
                "thread_key": signal["thread_key"], "decision_id": "", "mandate_id": "",
                "ticket_id": "", "assignment_id": "", "source": signal["source"],
                "kind": "candidate", "count": 0, "available": True,
            }
    raise WorkItemError("unknown work item action")
