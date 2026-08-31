from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

KIND_MISSING = "missing"
KIND_UNREADY = "unready"
KIND_REFUSED = "refused"
KIND_UNSUPPORTED = "unsupported"
KIND_QUOTA = "quota"
KIND_LEAK = "leak"
KIND_FORGED = "forged"
KINDS = (
    KIND_MISSING,
    KIND_UNREADY,
    KIND_REFUSED,
    KIND_UNSUPPORTED,
    KIND_QUOTA,
    KIND_LEAK,
    KIND_FORGED,
)

PHASE_ESTIMATE = "estimate"
PHASE_PIN = "pin"
PHASE_SIGNOFF = "signoff"
PHASE_POLICY = "policy"

CODE_ESTIMATE_MISSING = "ESTIMATE_MISSING"
CODE_ESTIMATE_UNREADY = "ESTIMATE_UNREADY"
CODE_ESTIMATE_REFUSED = "ESTIMATE_REFUSED"
CODE_PIN_MISSING = "PIN_MISSING"
CODE_TWIN_UNREADY = "TWIN_UNREADY"
CODE_POLICY_DENY = "POLICY_DENY"
CODE_UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ErrorFace:
    code: str
    kind: str
    severity: str
    phase: str
    retryable: bool
    hint: str
    health: str
    slot: str = ""
    message: str = ""

    def to_public(self) -> dict[str, Any]:
        row = {
            "code": self.code,
            "kind": self.kind,
            "severity": self.severity,
            "phase": self.phase,
            "retryable": self.retryable,
            "hint": self.hint,
            "health": self.health,
        }
        if self.slot:
            row["slot"] = self.slot
        if self.message:
            row["message"] = self.message
        return row


def classify_kind(tool: str, message: str, *, status: str = "") -> str:
    """Map a raw invoke failure to a catalog kind. Slot id is not a kind."""
    text = f"{tool} {message} {status}".lower()
    if status == "not_wired" or "empty slot" in text:
        return KIND_UNSUPPORTED
    if status == "denied" or message.strip().lower() == "deny":
        return KIND_REFUSED
    if "southbound" in text or "leaked" in text:
        return KIND_LEAK if "leaked" in text else KIND_REFUSED
    if "circuit.body" in text or "circuit_id is required" in text or "no logical.body" in text:
        return KIND_MISSING
    if "pin needs" in text or "unknown pin source" in text or "export needs" in text:
        return KIND_MISSING
    if "no local" in text or "not reachable" in text or "did not return" in text:
        return KIND_UNREADY
    if "quota" in text or "queue" in text:
        return KIND_QUOTA
    if "forged" in text or "qccd-twin" in text:
        return KIND_FORGED
    if status == "error":
        return KIND_REFUSED
    return KIND_REFUSED


def code_for(tool: str, kind: str) -> str:
    if tool == "ionstack_compile_estimate":
        if kind == KIND_MISSING:
            return CODE_ESTIMATE_MISSING
        if kind == KIND_UNREADY:
            return CODE_ESTIMATE_UNREADY
        return CODE_ESTIMATE_REFUSED
    if tool == "qagent_pin_circuit" or tool.endswith("_export_circuit"):
        return CODE_PIN_MISSING
    if tool == "ionstack_twin_run":
        return CODE_TWIN_UNREADY
    if kind == KIND_UNSUPPORTED:
        return CODE_UNSUPPORTED
    return CODE_POLICY_DENY


def overlay_catalog(face: ErrorFace, catalog: Mapping[str, Any] | None) -> ErrorFace:
    """Fill hint/severity from contracts/errors.json when the code matches."""
    entries = (catalog or {}).get("entries") if isinstance(catalog, Mapping) else None
    if not isinstance(entries, list):
        return face
    for row in entries:
        if not isinstance(row, Mapping) or row.get("code") != face.code:
            continue
        return ErrorFace(
            code=face.code,
            kind=str(row.get("kind") or face.kind),
            severity=str(row.get("severity") or face.severity),
            phase=str(row.get("phase") or face.phase),
            retryable=bool(row.get("retryable") if row.get("retryable") is not None else face.retryable),
            hint=str(row.get("hint") or face.hint),
            health=str(row.get("health") or face.health),
            slot=str(row.get("slot") or face.slot),
            message=face.message,
        )
    return face
