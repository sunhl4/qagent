from __future__ import annotations

from typing import Any, Mapping

from qagent.models.eln import (
    EVENT_B3,
    EVENT_RECIPE_PIN,
    EVENT_TWIN_SIGNOFF,
    FIELD_ASSIGNMENT_ID,
    drop_twin,
    short_payload,
)
from qagent.services.eln import read_eln

_SUMMARY_KEYS = frozenset(
    {
        "type",
        FIELD_ASSIGNMENT_ID,
        "recipe",
        "shots_actual",
        "verdict",
    }
)


def _face_event(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    washed = short_payload(drop_twin(row))
    return {key: washed[key] for key in _SUMMARY_KEYS if key in washed}


def _last(event_type: str) -> dict[str, Any] | None:
    rows = [row for row in read_eln() if row.get("type") == event_type]
    return _face_event(rows[-1]) if rows else None


def pes_card() -> dict[str, Any]:
    return {"kind": "pes", "recipe": _last(EVENT_RECIPE_PIN)}


def signoff_card() -> dict[str, Any]:
    return {
        "kind": "signoff",
        "twin": _last(EVENT_TWIN_SIGNOFF),
        "b3": _last(EVENT_B3),
    }
