"""Allowlisted diagnostics, separate from the CLI response and scientific data."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from company_agent.catalog import current_contract_digest, load_result_policy, load_tools

PREFIX = "company-agent-diagnostic:"
contract_digest = current_contract_digest
_PROVIDER_EVENT: ContextVar[dict[str, Any] | None] = ContextVar("provider_event", default=None)


@contextmanager
def invocation_events() -> Iterator[dict[str, Any]]:
    """Keep request diagnostics scoped to this invocation, never across calls."""
    events: dict[str, Any] = {}
    token = _PROVIDER_EVENT.set(events)
    try:
        yield events
    finally:
        _PROVIDER_EVENT.reset(token)


def encode(event: dict[str, Any]) -> str:
    policy = load_result_policy()["diagnostics"]
    if set(event) != set(policy["fields"]):
        raise ValueError("invalid diagnostic fields")
    strings = set(event) - {"elapsed_ms"}
    if any(not isinstance(event[key], str) for key in strings):
        raise ValueError("invalid diagnostic values")
    row = load_tools().get(event["tool"])
    if (
        event["version"] != "1.0"
        or event["event"] not in {"provider", "invocation"}
        or event["status"] not in {"started", "ok", "error", "denied", "needs_ask"}
        or event["execution_state"] not in policy["execution_states"]
        or event["error_category"] not in policy["error_categories"]
        or (
            row is None
            and (
                event["event"] != "invocation"
                or event["tool"] != "unknown"
                or event["operation"] != "unknown"
            )
        )
        or (row is not None and row["operation"] != event["operation"])
        or not re.fullmatch(r"req_[0-9a-f]{32}|", event["request_id"])
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", event["contract_digest"])
        or type(event["elapsed_ms"]) is not int
        or not 0 <= event["elapsed_ms"] <= 2**53 - 1
        or (event["execution_state"] in {"dispatched", "unknown"} and not event["request_id"])
    ):
        raise ValueError("invalid diagnostic values")
    raw = json.dumps(event, separators=(",", ":"))
    if len(raw.encode()) > policy["max_event_bytes"]:
        raise ValueError("oversized diagnostic")
    return PREFIX + raw


def emit(event: dict[str, Any]) -> bool:
    """Logging failure never replaces the actual outcome, especially after dispatch."""
    try:
        raw = encode(event)
        if event["event"] == "provider" and (events := _PROVIDER_EVENT.get()) is not None:
            events.clear()
            events.update(event)
        print(raw, file=sys.stderr, flush=True)
    except (OSError, ValueError, RuntimeError, TypeError):
        return False
    return True
