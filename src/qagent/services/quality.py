"""CI honesty gates. Fake twin / skip ask / CAL stay red. Not an agent loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from qagent.models.handles import HANDLE_TWIN
from qagent.models.invoke import STATUS_OK, InvokeResult
from qagent.models.types import Decision
from qagent.services.invoke import invoke
from qagent.services.policy import decide

PRESET_LAB = "lab"
GATE_FORGED_TWIN = "forged_twin"
GATE_SKIP_ASK = "skip_ask"
GATE_CAL = "cal"

TOOL_AER_RUN = "qiskit_aer_run"
TOOL_TWIN_RUN = "ionstack_twin_run"
TOOL_CAL_EDIT = "cal_edit"
TOOL_SHUTTLE_WRITE = "shuttle_write"

DECISION_ALLOW: Decision = "allow"
DECISION_DENY: Decision = "deny"
DECISION_ASK: Decision = "ask"
STATUS_DONE = "done"
OPEN_DECISIONS = frozenset({DECISION_ALLOW})
OPEN_STATUSES = frozenset({STATUS_OK, STATUS_DONE})

_AER_FORGED = {"circuit_id": "c1", "shots": 8, "claim_twin_id": True}
_TWIN_UNAPPROVED = {"shots": 1000}
_CAL_TOOLS = (TOOL_CAL_EDIT, TOOL_SHUTTLE_WRITE)


def _key_in(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        if key in value:
            return True
        return any(_key_in(inner, key) for inner in value.values())
    if isinstance(value, (list, tuple)):
        return any(_key_in(inner, key) for inner in value)
    return False


@dataclass(frozen=True)
class HonestyHit:
    tool: str
    policy: Decision
    decision: Decision
    status: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class HonestyReport:
    """Structured gate result. Never a fake status=done."""

    gate: str
    hits: tuple[HonestyHit, ...]

    def fail_closed(self) -> bool:
        return all(
            hit.decision not in OPEN_DECISIONS and hit.status not in OPEN_STATUSES
            for hit in self.hits
        )

    def minted_twin(self) -> bool:
        return _key_in(asdict(self), HANDLE_TWIN)


def _hit(tool: str, args: Mapping[str, Any] | None = None) -> HonestyHit:
    payload = dict(args or {})
    policy = decide(tool, PRESET_LAB, payload)
    result: InvokeResult = invoke(tool, PRESET_LAB, payload)
    return HonestyHit(
        tool=tool,
        policy=policy,
        decision=result.decision,
        status=result.status,
        payload=dict(result.payload or {}),
    )


def deny_forged_twin() -> HonestyReport:
    """qiskit_aer_run + claim_twin_id is deny. Invoke payload has no twin_id."""
    return HonestyReport(gate=GATE_FORGED_TWIN, hits=(_hit(TOOL_AER_RUN, _AER_FORGED),))


def deny_skip_ask() -> HonestyReport:
    """ionstack_twin_run on lab without approved is ask / needs_ask."""
    return HonestyReport(gate=GATE_SKIP_ASK, hits=(_hit(TOOL_TWIN_RUN, _TWIN_UNAPPROVED),))


def deny_cal() -> HonestyReport:
    """cal_edit / shuttle_write decide deny. Never a tool."""
    return HonestyReport(
        gate=GATE_CAL,
        hits=tuple(_hit(tool) for tool in _CAL_TOOLS),
    )


__all__ = [
    "HonestyHit",
    "HonestyReport",
    "deny_cal",
    "deny_forged_twin",
    "deny_skip_ask",
]
