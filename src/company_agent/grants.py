"""Session grants: one approval covers a bounded number of later calls.

The ledger is one file per DSH session under the receipt store. A missing
session, an expired file, or another session's file leaves the call on the
ask path. Opening a grant replaces the previous grant for that session.
Consumption happens when the call actually runs, under a file lock.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterator

from company_agent.catalog import load_policy
from company_agent.receipts import ReceiptError, _root

_VERSION = "1.1"
_SESSION = "COMPANY_AGENT_SESSION_ID"
_SUBMIT_RESOURCE = {
    "quantum_device_run": "device",
    "hpc_submit": "hpc",
    "quantum_cloud_submit": "cloud",
}
GRANT_TOOLS = (
    "quantum_device_run",
    "hpc_submit",
    "hpc_stage_file",
    "hpc_job_cancel",
    "hpc_dir_create",
    "hpc_file_remove",
    "quantum_cloud_submit",
    "company_latex_edit",
    "company_latex_batch_edit",
    "company_latex_revert",
    "company_latex_push",
    "company_latex_overleaf_push",
    "company_latex_issue_note",
    "company_plan_issue_create",
    "company_plan_note_create",
    "company_plan_issue_write",
    "company_plan_milestone_create",
    "company_research_run",
    "company_dingtalk_reply",
)


class GrantError(ValueError):
    """The grant could not be opened or read."""


def session_id() -> str:
    raw = str(os.environ.get(_SESSION) or "").strip()
    if not raw.startswith("dsh:") or len(raw) > 80 or any(ord(char) < 33 or ord(char) > 126 for char in raw):
        raise GrantError("session reference is required")
    return raw


def grantable_tools() -> tuple[str, ...]:
    tools = load_policy()["session_grant"]["tools"]
    if tuple(tools) != GRANT_TOOLS:
        raise GrantError("grant tools are invalid")
    return GRANT_TOOLS


def _path(session: str) -> Path:
    try:
        root = _root()
    except (ReceiptError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise GrantError("grant store unavailable") from exc
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:32]
    return root / "grants" / f"grant_{digest}.json"


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    token = f"{os.getpid()}:{time.time_ns()}".encode("ascii")
    fd: int | None = None
    for _ in range(50):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, token)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 5:
                    lock.unlink()
            except OSError:
                pass
            time.sleep(0.02)
        except OSError:
            if fd is not None:
                os.close(fd)
                fd = None
            with contextlib.suppress(OSError):
                if lock.is_file() and lock.read_bytes() == token:
                    lock.unlink()
            time.sleep(0.02)
    if fd is None:
        raise GrantError("grant store unavailable")
    try:
        yield
    finally:
        os.close(fd)
        try:
            current = lock.read_bytes()
        except OSError:
            current = b""
        if current == token:
            with contextlib.suppress(OSError):
                lock.unlink()


def _read(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != _VERSION:
        return None
    return payload


def _live(payload: dict[str, Any], session: str) -> dict[str, int] | None:
    if payload.get("session") != session:
        return None
    expires = payload.get("expires_epoch")
    remaining = payload.get("remaining")
    if isinstance(expires, bool) or not isinstance(expires, int) or expires < int(time.time()):
        return None
    if not isinstance(remaining, dict):
        return None
    cleaned: dict[str, int] = {}
    for name, count in remaining.items():
        if isinstance(name, str) and isinstance(count, int) and not isinstance(count, bool) and count > 0:
            cleaned[name] = count
    return cleaned


def _subject(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise GrantError("grant subject is invalid")
    kind = value.get("kind")
    resource = value.get("resource")
    limit_kind = value.get("limit_kind")
    limit = value.get("limit")
    identifier = value.get("id")
    if kind not in {"circuit", "experiment", "program"} or resource not in {"hpc", "cloud", "device"}:
        raise GrantError("grant subject is invalid")
    if limit_kind not in {"shots", "node_hours"}:
        raise GrantError("grant subject is invalid")
    if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
        raise GrantError("grant subject is invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000_000:
        raise GrantError("grant subject is invalid")
    return {
        "kind": kind,
        "id": identifier,
        "resource": resource,
        "limit_kind": limit_kind,
        "limit": limit,
    }


def _limit_holds(subject: dict[str, Any], arguments: Mapping[str, Any]) -> bool:
    if subject["limit_kind"] == "shots":
        shots = arguments.get("shots")
        return isinstance(shots, int) and not isinstance(shots, bool) and 1 <= shots <= subject["limit"]
    nodes = arguments.get("nodes")
    return isinstance(nodes, int) and not isinstance(nodes, bool) and 1 <= nodes <= subject["limit"]


def _subject_holds(subject: dict[str, Any], tool: str, arguments: Mapping[str, Any]) -> bool:
    if subject["resource"] != _SUBMIT_RESOURCE.get(tool):
        return False
    if not _limit_holds(subject, arguments):
        return False
    if subject["kind"] == "circuit":
        return arguments.get("circuit_id") == subject["id"]
    if subject["kind"] == "experiment":
        return arguments.get("experiment_id") == subject["id"]
    return arguments.get("program_sha256") == subject["id"]


def grant_covers(tool: str, arguments: Mapping[str, Any] | None = None) -> bool:
    """True when this session still has a matching call of this tool left."""
    try:
        session = session_id()
        path = _path(session)
    except GrantError:
        return False
    payload = _read(path)
    if payload is None:
        return False
    remaining = _live(payload, session)
    if not remaining or remaining.get(tool, 0) <= 0:
        return False
    if tool not in _SUBMIT_RESOURCE:
        return True
    subject = payload.get("subject")
    if not isinstance(subject, dict):
        return False
    return _subject_holds(subject, tool, arguments or {})


def grant_view() -> dict[str, Any]:
    """Public status for the current session. Inactive when no live grant exists."""
    empty = {"active": False, "expires_epoch": 0, "tools": []}
    try:
        session = session_id()
        payload = _read(_path(session))
    except GrantError:
        return empty
    if payload is None:
        return empty
    remaining = _live(payload, session)
    if not remaining:
        return empty
    view = {
        "active": True,
        "expires_epoch": int(payload["expires_epoch"]),
        "tools": [{"name": name, "remaining": count} for name, count in remaining.items()],
    }
    if isinstance(payload.get("subject"), dict):
        view["subject"] = payload["subject"]
    return view


def open_grant(arguments: dict[str, Any]) -> dict[str, Any]:
    session = session_id()
    policy = load_policy()["session_grant"]
    names = arguments["tools"]
    allowed = list(policy["tools"])
    if len(names) != len(set(names)) or any(name not in allowed for name in names):
        raise GrantError("grant tools are invalid")
    needs_subject = any(name in _SUBMIT_RESOURCE for name in names)
    subject = _subject(arguments.get("subject"))
    if needs_subject and subject is None:
        raise GrantError("grant subject is required")
    calls = arguments["max_calls"]
    ttl = arguments["ttl_seconds"]
    if not isinstance(calls, int) or isinstance(calls, bool) or not 1 <= calls <= int(policy["max_calls_per_tool"]):
        raise GrantError("grant call count is invalid")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= int(policy["max_ttl_seconds"]):
        raise GrantError("grant lifetime is invalid")
    expires = int(time.time()) + ttl
    remaining = {name: calls for name in names}
    payload = {
        "version": _VERSION,
        "session": session,
        "expires_epoch": expires,
        "max_calls": calls,
        "remaining": remaining,
    }
    if subject is not None:
        payload["subject"] = subject
    path = _path(session)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with _locked(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    opened = {
        "ok": True,
        "expires_epoch": expires,
        "max_calls": calls,
        "tools": [{"name": name, "remaining": calls} for name in names],
    }
    if subject is not None:
        opened["subject"] = subject
    return opened


def consume_grant(tool: str) -> bool:
    """Decrement one covered call. False when this session has none left."""
    try:
        session = session_id()
        path = _path(session)
    except GrantError:
        return False
    with _locked(path):
        payload = _read(path)
        if payload is None:
            return False
        remaining = _live(payload, session)
        if not remaining or remaining.get(tool, 0) <= 0:
            return False
        remaining[tool] -= 1
        if remaining[tool] <= 0:
            del remaining[tool]
        payload["remaining"] = remaining
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
        return True


def _handoff_path(session: str) -> Path:
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:32]
    return _root() / "grants" / f"handoff_{digest}.json"


def write_handoff(experiment_id: str, next_tool: str) -> None:
    """Remember one research handoff. A missing session leaves no token."""
    try:
        session = session_id()
        path = _handoff_path(session)
    except (GrantError, ReceiptError, OSError, RuntimeError, TypeError, ValueError):
        return
    payload = {
        "version": _VERSION,
        "session": session,
        "experiment_id": experiment_id,
        "next_tool": next_tool,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with _locked(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)


def handoff_pending(tool: str) -> bool:
    try:
        session = session_id()
        payload = _read(_handoff_path(session))
    except (GrantError, ReceiptError, OSError, RuntimeError, TypeError, ValueError):
        return False
    if payload is None or payload.get("session") != session:
        return False
    return payload.get("next_tool") == tool


def clear_handoff(tool: str) -> None:
    try:
        session = session_id()
        path = _handoff_path(session)
    except (GrantError, ReceiptError, OSError, RuntimeError, TypeError, ValueError):
        return
    with _locked(path):
        payload = _read(path)
        if payload is None or payload.get("session") != session or payload.get("next_tool") != tool:
            return
        with contextlib.suppress(OSError):
            path.unlink()


def handoff_view() -> dict[str, Any]:
    empty = {"pending": False, "experiment_id": "", "next_tool": ""}
    try:
        session = session_id()
        payload = _read(_handoff_path(session))
    except (GrantError, ReceiptError, OSError, RuntimeError, TypeError, ValueError):
        return empty
    if payload is None or payload.get("session") != session:
        return empty
    experiment_id = payload.get("experiment_id")
    next_tool = payload.get("next_tool")
    if not isinstance(experiment_id, str) or not isinstance(next_tool, str):
        return empty
    return {"pending": True, "experiment_id": experiment_id, "next_tool": next_tool}
