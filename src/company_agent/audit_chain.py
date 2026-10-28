"""Append-only HMAC-chained audit ledger for the WPS-suite porting (P0).

WPS-SUITE-PORTING §6.4 lists the audit anchor on the reference repo's
``audit/hash-chain``+``root-anchor`` shape: every action is one JSON line,
each line commits to the hash of the previous one, so any deletion, edit,
insert or reorder is detectable by re-walking the chain with the key. The
ledger is local-first: it needs an explicit log path and an explicit key
env, refuses to write when either is missing, and fsyncs every append.

One entry, no magic: ``seq`` starts at 1 and increments by one;
``prev_hmac`` of the first line is ``"genesis"``; ``hmac`` is
HMAC-SHA256(key, compact-json(payload) + "\n" + prev_hmac). Events carry a
human-readable reason (the ``purpose`` discipline of §6.1) in their detail;
the module never contents itself with inventing narrative.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

LOG_ENV = "COMPANY_AGENT_AUDIT_LOG"
KEY_ENV = "COMPANY_AGENT_AUDIT_KEY"
MAX_DETAIL_JSON_BYTES = 8192
MAX_EVENTS = 1_000_000

GENESIS = "genesis"


class AuditChainError(ValueError):
    """Audit ledger failure; nothing outside the ledger is implied."""


def _log_path() -> str:
    raw = str(os.environ.get(LOG_ENV) or "").strip()
    if not raw:
        raise AuditChainError(f"audit log is not configured ({LOG_ENV})")
    if os.path.isdir(raw):
        raise AuditChainError("audit log must be a file path")
    directory = os.path.dirname(os.path.abspath(raw))
    os.makedirs(directory, exist_ok=True)
    return raw


def _key() -> bytes:
    raw = str(os.environ.get(KEY_ENV) or "").strip()
    if len(raw) < 32:
        raise AuditChainError(f"audit key must be at least 32 characters ({KEY_ENV})")
    return raw.encode("utf-8")


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_hmac(key: bytes, payload: Mapping[str, Any], prev_hmac: str) -> str:
    material = _canonical(payload) + "\n" + prev_hmac
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()


def _read_entries(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    entries: list[dict[str, Any]] = []
    with open(path, "rb") as handle:
        raw = handle.read()
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise AuditChainError(f"audit ledger line {number} is not a JSON object") from exc
        if not isinstance(entry, dict):
            raise AuditChainError(f"audit ledger line {number} is not a JSON object")
        entries.append(entry)
    return entries


def last_entry() -> dict[str, Any] | None:
    """Return the newest intact line, or None on an empty or absent ledger."""

    path = _log_path()
    entries = _read_entries(path)
    return entries[-1] if entries else None


def append(event: str, detail: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Append one event and fsync it; returns the written ledger line."""

    if not isinstance(event, str) or not event.strip():
        raise AuditChainError("audit event must be a non-empty string")
    if detail is None:
        detail = {}
    if not isinstance(detail, dict):
        raise AuditChainError("audit detail must be a JSON object")
    path = _log_path()
    key = _key()
    entries = _read_entries(path)
    if len(entries) > MAX_EVENTS:
        raise AuditChainError("audit ledger exceeds the bounded count")
    previous = entries[-1] if entries else None
    if previous is not None:
        prev_hmac = previous.get("hmac")
        if not isinstance(prev_hmac, str) or len(prev_hmac) != 64:
            raise AuditChainError("audit ledger head is corrupt; refusing to extend")
    else:
        prev_hmac = GENESIS
    seq = (int(previous.get("seq", 0)) if previous is not None else 0) + 1
    payload = {
        "seq": seq,
        "ts": datetime.now(UTC).isoformat(timespec="microseconds"),
        "event": event,
        "detail": detail,
    }
    encoded = _canonical(payload)
    if len(encoded.encode("utf-8")) > MAX_DETAIL_JSON_BYTES * 4:
        raise AuditChainError("audit detail exceeds the bounded size")
    entry = dict(payload)
    entry["prev_hmac"] = prev_hmac
    entry["hmac"] = _entry_hmac(key, payload, prev_hmac)
    with open(path, "ab") as handle:
        handle.write((_canonical(entry) + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def _chain_status(path: str, key: bytes) -> dict[str, Any]:
    """Re-walk the chain tolerantly; malformed lines mark the break point."""

    entries: list[dict[str, Any]] = []
    if os.path.exists(path):
        with open(path, "rb") as handle:
            raw = handle.read()
        raw_lines = [line for line in raw.splitlines() if line.strip()]
    else:
        raw_lines = []
    parse_preview: list[dict[str, Any] | None] = []
    for line in raw_lines:
        try:
            parsed = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError):
            parsed = None
        parse_preview.append(parsed if isinstance(parsed, dict) else None)
    entries = [p for p in parse_preview if p is not None]

    previous_hmac = GENESIS
    expected_seq = 1
    for index, entry in enumerate(parse_preview, start=1):
        if not isinstance(entry, dict):
            break
        payload_keys = {"seq", "ts", "event", "detail"}
        if set(entry) - (payload_keys | {"prev_hmac", "hmac"}):
            break
        payload = {name: entry[name] for name in payload_keys if name in entry}
        if len(payload) != len(payload_keys):
            break
        if entry.get("seq") != expected_seq:
            break
        if entry.get("prev_hmac") != previous_hmac:
            break
        expected = _entry_hmac(key, payload, previous_hmac)
        if not hmac.compare_digest(str(entry.get("hmac")), expected):
            break
        previous_hmac = str(entry.get("hmac"))
        expected_seq += 1
    else:
        if len(entries) > MAX_EVENTS:
            raise AuditChainError("audit ledger exceeds the bounded count")
        return {"lines": len(entries), "intact": True, "first_bad_seq": 0}
    return {"lines": len(parse_preview), "intact": False, "first_bad_seq": min(expected_seq, index)}


def verify() -> dict[str, Any]:
    """Re-walk the whole chain; report the first broken position (1-based seq)."""

    path = _log_path()
    key = _key()
    return _chain_status(path, key)
