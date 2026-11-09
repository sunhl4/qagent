"""Stand-in adapter for the upstream Super-agent flow.

Future upstream fields fail closed here. Router, subscription delivery, and the
attention panel stay upstream. This module only records a source event on the
local ledger and opens a ticket when a written rule says to.
"""

from __future__ import annotations

from typing import Any

from company_agent.catalog import _load_object
from company_agent.work_items import work_item

_EVENT_FIELDS = {
    "schema_version",
    "source",
    "thread_id",
    "actor_id",
    "text",
    "tenant_id",
    "idempotency_key",
    "written_rule",
    "mode",
    "strength",
    "scope",
    "title",
}


def foundation() -> dict[str, Any]:
    contract = _load_object("superagent.json")
    flow = contract["architecture"]["flow_foundation"]
    required = flow.get("required_upstream")
    if required != ["router", "subscription", "attention"]:
        raise ValueError("superagent foundation is invalid")
    if contract["control_plane"]["schema_version"] != "1":
        raise ValueError("superagent foundation is invalid")
    return flow


def admit_source_event(event: dict[str, Any]) -> dict[str, Any]:
    """Record one source event. A missing written rule stays observe and opens no ticket."""
    flow = foundation()
    if set(event) - _EVENT_FIELDS:
        raise ValueError("source event has an unknown field")
    schema_version = event.get("schema_version", "1")
    if schema_version != "1":
        raise ValueError("source event schema is invalid")
    written = event.get("written_rule") is True
    mode = event.get("mode") or "observe"
    strength = event.get("strength") or "explicit"
    if mode not in {"off", "observe", "auto"} or strength not in {"explicit", "inferred"}:
        raise ValueError("source event is invalid")
    received = work_item({
        "action": "receive",
        "source": event.get("source"),
        "thread_id": event.get("thread_id"),
        "actor_id": event.get("actor_id"),
        "text": event.get("text"),
        "human": False,
        "tenant_id": event.get("tenant_id"),
        "idempotency_key": event.get("idempotency_key"),
        "schema_version": "1",
    })
    ticket_id = ""
    authority = "candidate"
    accept_mode = "observe"
    if written and mode == "auto" and strength == "explicit":
        opened = work_item({
            "action": "evaluate",
            "trigger_id": received["trigger_id"],
            "mode": "auto",
            "strength": "explicit",
            "scope": event.get("scope"),
            "title": event.get("title") or event.get("thread_id"),
            "reason": "written rule",
            "evidence": "source-event",
            "tenant_id": event.get("tenant_id"),
        })
        ticket_id = opened.get("ticket_id") or ""
        authority = opened.get("authority") or "none"
        accept_mode = "auto"
    return {
        "ok": True,
        "authority": authority,
        "trigger_id": received["trigger_id"],
        "ticket_id": ticket_id,
        "accept_mode": accept_mode,
        "policy_applies": flow["unattended"]["company_policy_still_applies"] is True,
        "upstream_objects": list(_load_object("superagent.json")["framework"]["prototype_objects"]),
    }
