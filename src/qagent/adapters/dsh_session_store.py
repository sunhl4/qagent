from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from qagent.adapters.contracts import ROOT
from qagent.models.assignment import normalize_tenant

_BY_TENANT = "by_tenant"


def session_path() -> Path:
    raw = os.environ.get("QAGENT_DSH_SESSION_FILE")
    return Path(raw) if raw else ROOT / ".qagent" / "dsh-session.json"


def tenants_path() -> Path:
    """Sidecar for set tenants. Staff file stays {sessionId} only."""
    path = session_path()
    return path.with_name(f"{path.stem}.tenants.json")


def _bucket_key(raw: object = "") -> str:
    """normalize_tenant first; never use the key as a path component."""
    key = normalize_tenant(raw)
    if not key:
        return ""
    if "/" in key or "\\" in key or "\0" in key:
        key = key.replace("/", "_").replace("\\", "_").replace("\0", "_")
    return key


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def load_session_id(tenant_id: str = "") -> str | None:
    key = _bucket_key(tenant_id)
    if not key:
        session_id = str(_read_json(session_path()).get("sessionId") or "").strip()
        return session_id or None
    buckets = _read_json(tenants_path()).get(_BY_TENANT)
    if not isinstance(buckets, dict):
        return None
    session_id = str(buckets.get(key) or "").strip()
    return session_id or None


def save_session_id(session_id: str, tenant_id: str = "") -> None:
    key = _bucket_key(tenant_id)
    if not key:
        _write_json(session_path(), {"sessionId": session_id})
        return
    path = tenants_path()
    buckets = _read_json(path).get(_BY_TENANT)
    if not isinstance(buckets, dict):
        buckets = {}
    buckets[key] = session_id
    _write_json(path, {_BY_TENANT: buckets})


def clear_session_id(tenant_id: str = "") -> None:
    key = _bucket_key(tenant_id)
    if not key:
        path = session_path()
        if path.is_file():
            path.unlink()
        return
    path = tenants_path()
    buckets = _read_json(path).get(_BY_TENANT)
    if not isinstance(buckets, dict):
        return
    buckets.pop(key, None)
    if buckets:
        _write_json(path, {_BY_TENANT: buckets})
    elif path.is_file():
        path.unlink()


def journal_path() -> Path:
    """Sidecar listing sessions per tenant. Staff file stays {sessionId} only."""
    path = session_path()
    return path.with_name(f"{path.stem}.journal.json")


def journal_session(session_id: str, tenant_id: str = "", title: str = "") -> None:
    """Record or touch a session. Never invents ids; a title is set once."""
    sid = str(session_id or "").strip()
    if not sid:
        return
    key = _bucket_key(tenant_id)
    path = journal_path()
    buckets = _read_json(path).get(_BY_TENANT)
    if not isinstance(buckets, dict):
        buckets = {}
    entries = buckets.get(key)
    if not isinstance(entries, list):
        entries = []
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    found: dict[str, Any] | None = None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("session_id") == sid:
            found = entry
            break
    if found is None:
        found = {"session_id": sid, "title": "", "created_at": now, "archived": False}
        entries.append(found)
    found["updated_at"] = now
    clean = str(title or "").strip()
    if clean and not str(found.get("title") or "").strip():
        found["title"] = clean
    buckets[key] = entries[-16:]
    _write_json(path, {_BY_TENANT: buckets})


def archive_session_id(session_id: str, tenant_id: str = "") -> None:
    """Mark a journaled session closed. The list keeps it as 已清, not a room."""
    sid = str(session_id or "").strip()
    if not sid:
        return
    key = _bucket_key(tenant_id)
    path = journal_path()
    buckets = _read_json(path).get(_BY_TENANT)
    entries = buckets.get(key) if isinstance(buckets, dict) else None
    if not isinstance(entries, list):
        return
    changed = False
    for entry in entries:
        if isinstance(entry, dict) and entry.get("session_id") == sid and not entry.get("archived"):
            entry["archived"] = True
            changed = True
    if changed:
        _write_json(path, {_BY_TENANT: buckets})


def list_journal(tenant_id: str = "") -> list[dict[str, Any]]:
    key = _bucket_key(tenant_id)
    buckets = _read_json(journal_path()).get(_BY_TENANT)
    entries = buckets.get(key) if isinstance(buckets, dict) else None
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("session_id")]
