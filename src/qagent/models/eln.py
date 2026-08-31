from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from qagent.models.handles import HANDLE_TWIN

EVENT_RECIPE_PIN = "qagent/recipe_pin"
EVENT_ESTIMATE = "qagent/estimate"
EVENT_TWIN_SIGNOFF = "qagent/twin_signoff"
EVENT_B3 = "qagent/b3"
EVENT_CLAIM_BLOCKED = "qagent/claim_blocked"
EVENT_ASSIGNMENT = "qagent/assignment"

ELN_EVENT_KINDS = (
    EVENT_RECIPE_PIN,
    EVENT_ESTIMATE,
    EVENT_TWIN_SIGNOFF,
    EVENT_B3,
    EVENT_ASSIGNMENT,
    EVENT_CLAIM_BLOCKED,
)

FIELD_ASSIGNMENT_ID = "assignment_id"
FIELD_PARENT_ASSIGNMENT_ID = "parent_assignment_id"

FORBIDDEN_ELN_KEYS = frozenset(
    {
        "pauli_terms",
        "bitstrings",
        "rows",
        "counts_full",
        "cal",
        "calibration",
        "shuttle",
        "ms_matrix",
        "qasm3",
        "body",
    }
)

SECRET_ELN_KEYS = frozenset(
    {
        "llm_api_key",
        "hpc_secret",
        "quantum_secret",
    }
)

_STRIP_KEYS = FORBIDDEN_ELN_KEYS | SECRET_ELN_KEYS


@dataclass(frozen=True)
class ElnEvent:
    type: str
    payload: Mapping[str, Any]


def short_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _STRIP_KEYS:
            continue
        if isinstance(value, Mapping):
            out[key] = short_payload(value)
        else:
            out[key] = value
    return out


def drop_twin(payload: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key == HANDLE_TWIN:
            continue
        if isinstance(value, Mapping):
            out[key] = drop_twin(value)
        else:
            out[key] = value
    return out


def belongs_to_assignment(row: Mapping[str, Any], assignment_id: str) -> bool:
    return row.get(FIELD_ASSIGNMENT_ID) == assignment_id
