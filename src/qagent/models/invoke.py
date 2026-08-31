from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from qagent.models.types import Decision

InvokeStatus = Literal["denied", "needs_ask", "not_wired", "ok", "error"]

STATUS_DENIED: InvokeStatus = "denied"
STATUS_NEEDS_ASK: InvokeStatus = "needs_ask"
STATUS_NOT_WIRED: InvokeStatus = "not_wired"
STATUS_OK: InvokeStatus = "ok"
STATUS_ERROR: InvokeStatus = "error"


@dataclass(frozen=True)
class PortMethod:
    port_id: str
    method: str
    tool: str
    slot: str
    status: str


@dataclass(frozen=True)
class InvokeResult:
    tool: str
    decision: Decision
    status: InvokeStatus
    slot_id: str | None = None
    payload: Mapping[str, Any] | None = None
    error: str | None = None
    explain: Mapping[str, Any] | None = None
