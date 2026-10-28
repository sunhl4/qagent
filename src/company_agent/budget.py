"""Kernel termination budgets: bounded tool-call, wall-clock and approval-wait spend.

P3「token、调用次数、墙钟、费用和审批等待等终止预算」work package. The ledger is
a per-turn durable counter under the receipt store: the turn key comes from
``COMPANY_AGENT_TURN_ID`` (hashed together with the receipt subject, never
stored in plaintext) and a missing turn id falls back to a per-process
bucket, so a host that does not yet declare turns stays bounded inside one
process. Checks run after policy but before any dispatch; a denied call
never charges. ``precheck`` fails closed on invocations, remaining wall
budget and the per-tool sublimits; ``charge`` is best effort so ledger I/O
can never mask a tool response. This module creates no model, session or
tool loops.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

from company_agent import receipts
from company_agent.catalog import load_budgets

Version = "1.0.0"

LIMIT_KEYS = ("invocations", "wall_ms", "approval_waits", "device_runs", "submissions")

_SUBLIMIT_BY_TOOL: dict[str, str] = {
    "quantum_device_run": "device_runs",
    "quantum_cloud_submit": "submissions",
    "hpc_submit": "submissions",
}

_PLACEHOLDER_TURN = "process"
_TURN_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


class BudgetError(ValueError):
    """A termination-budget boundary was reached before the next dispatch."""


def _turn() -> str:
    contract = load_budgets()
    raw = _TURN_CONTROL_PATTERN.sub("", str(os.environ.get(contract["turn_env"]) or "")).strip()
    key = (raw or _PLACEHOLDER_TURN).casefold()
    if len(key.encode("utf-8")) > int(contract["ledger"]["max_turn_key_bytes"]):
        raise BudgetError("termination budget turn identifier is too long")
    return key


def _turn_digest() -> str:
    return "turn_" + hashlib.sha256(f"{_subject()}\n{_turn()}".encode()).hexdigest()[:32]


def _subject() -> str:
    try:
        return str(receipts.subject())
    except (OSError, ValueError, RuntimeError):
        return "unknown@unknown"


def ledger_path() -> Path | None:
    """Durable ledger file for the current turn; None when the store is unusable."""
    try:
        contract = load_budgets()
    except (OSError, ValueError, RuntimeError, TypeError):
        return None
    try:
        root = receipts._root()
    except (OSError, ValueError, RuntimeError):
        return None
    return root / str(contract["ledger"]["dir_name"]) / f"{_turn_digest()}.json"


def _read_counts() -> dict[str, int]:
    path = ledger_path()
    if path is None:
        return dict.fromkeys(LIMIT_KEYS, 0)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return dict.fromkeys(LIMIT_KEYS, 0)
    counts_row = payload.get("counts") if isinstance(payload, dict) else None
    if payload.get("version") != Version or not isinstance(counts_row, dict):
        return dict.fromkeys(LIMIT_KEYS, 0)
    counts_map: dict[str, int] = {}
    for key in LIMIT_KEYS:
        value = counts_row.get(key)
        counts_map[key] = value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0
    return counts_map


def counts() -> dict[str, int]:
    return _read_counts()


def precheck(tool: str, *, wait: bool = False) -> None:
    """Fail closed when the turn budget has no room for the next call."""
    try:
        limits = load_budgets()["limits"]
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        raise BudgetError("termination budget contract is invalid") from exc
    counts_map = counts()
    if wait:
        if counts_map["approval_waits"] >= limits["approval_waits"]:
            raise BudgetError("termination budget exhausted (approval_waits)")
        return
    if counts_map["invocations"] >= limits["invocations"]:
        raise BudgetError("termination budget exhausted (invocations)")
    if counts_map["wall_ms"] >= limits["wall_ms"]:
        raise BudgetError("termination budget exhausted (wall_ms)")
    limit = _SUBLIMIT_BY_TOOL.get(tool)
    if limit and counts_map[limit] >= limits[limit]:
        raise BudgetError(f"termination budget exhausted ({limit})")


def charge(tool: str, *, elapsed_ms: int = 0) -> None:
    """Charge one executed call; never raises."""
    counts_map = counts()
    counts_map["invocations"] += 1
    counts_map["wall_ms"] += max(0, int(elapsed_ms))
    limit = _SUBLIMIT_BY_TOOL.get(tool)
    if limit:
        counts_map[limit] += 1
    _save(counts_map)


def charge_approval_wait() -> None:
    """Charge one ask decision that went out for human approval; never raises."""
    counts_map = counts()
    counts_map["approval_waits"] += 1
    _save(counts_map)


def _save(counts_map: dict[str, int]) -> None:
    path = ledger_path()
    if path is None:
        return
    payload = {
        "version": Version,
        "turn_digest": _turn_digest(),
        "updated_epoch": int(time.time()),
        "counts": {key: int(counts_map[key]) for key in LIMIT_KEYS},
    }
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, encoded)
    except (OSError, ValueError, TypeError):
        # The tool response must never be masked by ledger I/O failures.
        pass


def _atomic_write(path: Path, encoded: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        handle.flush()
        name = handle.name
    os.replace(name, path)


def reset(turn: str | None = None) -> None:
    """Test and operations helper: drop the durable ledger for one turn key."""
    previous = os.environ.get("COMPANY_AGENT_TURN_ID")
    if turn is not None:
        os.environ["COMPANY_AGENT_TURN_ID"] = turn
    path = ledger_path()
    if turn is not None:
        if previous is None:
            os.environ.pop("COMPANY_AGENT_TURN_ID", None)
        else:
            os.environ["COMPANY_AGENT_TURN_ID"] = previous
    if path is not None:
        with contextlib.suppress(OSError):
            path.unlink()
