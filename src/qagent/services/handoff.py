from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.gov_store import handoff_dir, now_iso, read_json, write_json
from qagent.adapters.support import new_id
from qagent.models.gov import (
    SCHEMA_HANDOFF,
    Handoff,
    compact_intent,
    extra_handle_keys,
    only_handles,
)
from qagent.adapters.preset import PRESETS


class HandoffError(ValueError):
    """Fixed-schema handoff rejected. Original session is untouched."""


def _presets() -> set[str]:
    return set(PRESETS)


def create_handoff(
    *,
    source_preset: str,
    target_preset: str,
    handles: Mapping[str, Any] | None = None,
    intent: str = "",
    unresolved: list[str] | None = None,
    source_session: str = "",
) -> Handoff:
    extra = extra_handle_keys(handles)
    if extra:
        raise HandoffError(f"handoff only allows three handles; extra {list(extra)}")
    if source_preset not in _presets() or target_preset not in _presets():
        raise HandoffError("handoff presets must be boot|lab|algo|sign")
    row = Handoff(
        schema=SCHEMA_HANDOFF,
        source_preset=source_preset,
        target_preset=target_preset,
        handles=only_handles(handles),
        intent=compact_intent(intent),
        unresolved=tuple(str(item) for item in (unresolved or []) if str(item).strip()),
        handoff_id=new_id("hof"),
        source_session=str(source_session or "").strip(),
    )
    payload = row.to_public()
    payload["ts"] = now_iso()
    write_json(handoff_dir() / f"{row.handoff_id}.json", payload)
    return row


def get_handoff(handoff_id: str) -> dict[str, Any]:
    path = handoff_dir() / f"{handoff_id}.json"
    data = read_json(path)
    if not data:
        raise HandoffError(f"unknown handoff_id {handoff_id!r}")
    return data


def list_handoffs() -> list[dict[str, Any]]:
    folder = handoff_dir()
    if not folder.is_dir():
        return []
    rows = [read_json(path) for path in sorted(folder.glob("hof_*.json"))]
    return [row for row in rows if row]
