from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.eln import NativeEln
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT
from qagent.models.eln import (
    EVENT_ASSIGNMENT,
    EVENT_B3,
    EVENT_CLAIM_BLOCKED,
    EVENT_ESTIMATE,
    EVENT_RECIPE_PIN,
    EVENT_TWIN_SIGNOFF,
    FIELD_ASSIGNMENT_ID,
    FIELD_PARENT_ASSIGNMENT_ID,
    ElnEvent,
    belongs_to_assignment,
    drop_twin,
    short_payload,
)


def _eln() -> NativeEln:
    return NativeEln()


def _tagged(assignment_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    if assignment_id:
        payload[FIELD_ASSIGNMENT_ID] = assignment_id
    return payload


def append_event(event_type: str, payload: Mapping[str, Any]) -> ElnEvent:
    return _eln().append(event_type, short_payload(payload))


def append_recipe_pin(
    *,
    recipe: str,
    params: Mapping[str, Any] | None = None,
    assignment_id: str | None = None,
) -> ElnEvent:
    return append_event(
        EVENT_RECIPE_PIN,
        _tagged(assignment_id, {"recipe": recipe, "params": dict(params or {})}),
    )


def append_estimate(*, makespan_ns: float, assignment_id: str | None = None) -> ElnEvent:
    return append_event(EVENT_ESTIMATE, _tagged(assignment_id, {"makespan_ns": makespan_ns}))


def append_twin_signoff(
    *,
    twin_id: str,
    shots_actual: int,
    assignment_id: str | None = None,
) -> ElnEvent:
    return append_event(
        EVENT_TWIN_SIGNOFF,
        _tagged(assignment_id, {"twin_id": twin_id, "shots_actual": shots_actual}),
    )


def append_b3(*, verdict: str, assignment_id: str | None = None) -> ElnEvent:
    return append_event(EVENT_B3, _tagged(assignment_id, {"verdict": verdict}))


def append_claim_blocked(*, reason: str, assignment_id: str | None = None) -> ElnEvent:
    return append_event(EVENT_CLAIM_BLOCKED, _tagged(assignment_id, {"reason": reason}))


def append_assignment(
    *,
    assignment_id: str,
    status: str,
    room: str,
    parent_assignment_id: str | None = None,
    circuit_id: str | None = None,
    asset_id: str | None = None,
) -> ElnEvent:
    payload: dict[str, Any] = {
        FIELD_ASSIGNMENT_ID: assignment_id,
        "status": status,
        "room": room,
    }
    if parent_assignment_id:
        payload[FIELD_PARENT_ASSIGNMENT_ID] = parent_assignment_id
    if circuit_id:
        payload[HANDLE_CIRCUIT] = circuit_id
    if asset_id:
        payload[HANDLE_ASSET] = asset_id
    return append_event(EVENT_ASSIGNMENT, payload)


def collapse_assignment_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest assignment row per assignment_id. Disk is unchanged."""
    latest: dict[str, int] = {}
    for index, row in enumerate(rows):
        if row.get("type") != EVENT_ASSIGNMENT:
            continue
        latest[str(row.get(FIELD_ASSIGNMENT_ID) or "")] = index
    keep = set(latest.values())
    return [
        row
        for index, row in enumerate(rows)
        if row.get("type") != EVENT_ASSIGNMENT or index in keep
    ]


def read_eln(*, assignment_id: str | None = None) -> list[dict[str, Any]]:
    rows = _eln().read()
    if assignment_id is None:
        return rows
    return [row for row in rows if belongs_to_assignment(row, assignment_id)]


def filter_eln_for_assignments(
    rows: list[dict[str, Any]],
    assignment_ids: set[str],
) -> list[dict[str, Any]]:
    visible = {item for item in assignment_ids if item}
    return [
        row
        for row in rows
        if any(belongs_to_assignment(row, assignment_id) for assignment_id in visible)
    ]


def replay(assignment_id: str) -> list[dict[str, Any]]:
    return read_eln(assignment_id=assignment_id)


def copy_events_for_fork(source_assignment_id: str, new_assignment_id: str) -> None:
    """Copy ELN rows onto a new assignment. Drops twin_id. Skips assignment events."""
    for row in replay(source_assignment_id):
        _copy_for_fork(row, new_assignment_id)


def _copy_for_fork(row: Mapping[str, Any], new_assignment_id: str) -> None:
    event_type = str(row.get("type") or "")
    if not event_type or event_type == EVENT_ASSIGNMENT:
        return
    payload = drop_twin({key: value for key, value in row.items() if key != "type"})
    payload.pop(FIELD_PARENT_ASSIGNMENT_ID, None)
    payload[FIELD_ASSIGNMENT_ID] = new_assignment_id
    append_event(event_type, payload)


def fork(
    source_assignment_id: str,
    new_assignment_id: str,
    *,
    room: str = "lab",
    status: str = "draft",
) -> ElnEvent:
    copy_events_for_fork(source_assignment_id, new_assignment_id)
    return append_assignment(
        assignment_id=new_assignment_id,
        status=status,
        room=room,
        parent_assignment_id=source_assignment_id,
    )
