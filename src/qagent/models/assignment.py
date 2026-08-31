from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from qagent.models.handles import (
    B3_VERDICTS,
    FOREIGN_PROVENANCE,
    HANDLE_ASSET,
    HANDLE_CIRCUIT,
    HANDLE_TWIN,
)

ROOM_LAB = "lab"
ROOM_ALGO = "algo"
ROOM_SIGN = "sign"
ROOMS = (ROOM_LAB, ROOM_ALGO, ROOM_SIGN)

STATUS_DRAFT = "draft"
STATUS_RUNNING = "running"
STATUS_NEEDS_ASK = "needs_ask"
STATUS_SIGNED = "signed"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"
STATUSES = (
    STATUS_DRAFT,
    STATUS_RUNNING,
    STATUS_NEEDS_ASK,
    STATUS_SIGNED,
    STATUS_FAILED,
    STATUS_REJECTED,
)

SOURCE_LOCAL_CARD = "qagent-local-card"
SOURCE_QDATA_CLI = "qdata-cli"
SOURCE_QCHEM_CLI = "qchem-cli"
SOURCE_TWIN = "qccd-twin"
SOURCE_AER = "aer"
SOURCES = (
    SOURCE_LOCAL_CARD,
    SOURCE_QDATA_CLI,
    SOURCE_QCHEM_CLI,
    SOURCE_TWIN,
    SOURCE_AER,
)
HANDLE_KEYS = (HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN)
LANE_ORDER = ("prepare", "compile", "approximate", "signoff", "b3")
LANE_FOR_TOOL = {
    "qdata_run_recipe": "prepare",
    "qagent_pin_circuit": "prepare",
    "ionstack_compile_estimate": "compile",
    "qiskit_aer_run": "approximate",
    "ionstack_twin_run": "signoff",
    "qdata_dequant_gate": "b3",
}


def lanes_from_stages(stages: Any) -> list[str]:
    seen: list[str] = []
    for tool in stages or []:
        lane = LANE_FOR_TOOL.get(str(tool))
        if lane and lane not in seen:
            seen.append(lane)
    return seen
LIST_ORDER = {
    STATUS_NEEDS_ASK: 0,
    STATUS_RUNNING: 1,
    STATUS_DRAFT: 2,
    STATUS_FAILED: 3,
    STATUS_REJECTED: 4,
    STATUS_SIGNED: 5,
}


class AssignmentError(ValueError):
    """Domain rule violation. Not an HTTP or I/O error."""


RECEIPT_SCHEMA = "qagent.receipt/v1"
RECEIPT_KIND = "qagent/receipt"
RECEIPT_IDENTITY_KEYS = ("preset", "n_qubits", "live")
RECEIPT_FORBIDDEN_KEYS = frozenset(
    {
        "pauli_terms",
        "bitstrings",
        "rows",
        "counts_full",
        "counts",
        "cal",
        "calibration",
        "shuttle",
        "ms_matrix",
        "qasm3",
        "body",
        "circuit",
        "token",
        "secret",
        "api_key",
        "password",
    }
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_address(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def seal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    body = {key: payload[key] for key in payload if key != "receipt_hash"}
    body["schema"] = RECEIPT_SCHEMA
    return {**body, "receipt_hash": content_address(body)}


def verify_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    given = payload.get("receipt_hash")
    body = {key: payload[key] for key in payload if key != "receipt_hash"}
    expected = content_address(body)
    handles = body.get("handles") if isinstance(body.get("handles"), Mapping) else {}
    sources = body.get("sources") if isinstance(body.get("sources"), list) else []
    looks_signed = bool(body.get("signed")) or body.get("status") == STATUS_SIGNED
    signed_ok = (not looks_signed) or can_sign(sanitize_handles(handles), sanitize_sources(sources))
    ok = given == expected and body.get("schema") == RECEIPT_SCHEMA and signed_ok
    return {"ok": ok, "expected": expected, "given": given}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def face_makespan_ns(raw: Any) -> int | float | None:
    """Inbox estimate only. Not a handle. Never a twin_id."""
    if raw is None or raw == "":
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    if number == int(number):
        return int(number)
    return number


def face_b3_verdict(raw: Any) -> str | None:
    """Inbox / receipt enum only. Not a handle. Never a twin_id."""
    if isinstance(raw, Mapping):
        raw = raw.get("verdict")
    text = str(raw or "").strip()
    if text in B3_VERDICTS:
        return text
    return None


def face_aer_provenance(raw: Any) -> str | None:
    """Foreign simulator only. Never qccd-twin. Not a handle."""
    text = str(raw or "").strip()
    if text in FOREIGN_PROVENANCE:
        return text
    return None


def face_shots_actual(raw: Any) -> int | None:
    """Signed shots only. Not a handle. Never a twin_id."""
    if raw is None or raw == "":
        return None
    try:
        number = int(raw)
    except (TypeError, ValueError):
        try:
            number = int(float(raw))
        except (TypeError, ValueError):
            return None
    if number <= 0:
        return None
    return number


def normalize_tenant(raw: Any) -> str:
    return str(raw or "").strip()


def tenant_visible(row_tenant: str, caller_tenant: str) -> bool:
    """Empty caller is staff and sees all. Set caller sees only own rows."""
    caller = normalize_tenant(caller_tenant)
    if not caller:
        return True
    return normalize_tenant(row_tenant) == caller


def sanitize_handles(raw: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in HANDLE_KEYS:
        value = (raw or {}).get(key)
        if value:
            out[key] = str(value)
    return out


def sanitize_sources(raw: Any) -> list[str]:
    seen: list[str] = []
    for item in raw or []:
        text = str(item)
        if text in SOURCES and text not in seen:
            seen.append(text)
    return seen


def can_sign(handles: Mapping[str, str], sources: list[str]) -> bool:
    return bool(handles.get(HANDLE_TWIN) and SOURCE_TWIN in sources)


def signoff_handles(handles: Mapping[str, str], sources: list[str]) -> dict[str, str]:
    if SOURCE_TWIN not in sources:
        return {key: value for key, value in handles.items() if key != HANDLE_TWIN}
    return dict(handles)


def _receipt_identity(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    return {key: raw[key] for key in RECEIPT_IDENTITY_KEYS if key in raw}


def _scrub_forbidden(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _scrub_forbidden(item)
            for key, item in value.items()
            if key not in RECEIPT_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_scrub_forbidden(item) for item in value]
    return value


def receipt_payload(row: "Assignment") -> dict[str, Any]:
    """Short export. No Pauli / bitstrings / circuit body / secrets."""
    payload: dict[str, Any] = {
        "kind": RECEIPT_KIND,
        "assignment_id": row.assignment_id,
        "room": row.room,
        "recipe": row.recipe,
        "shots": row.shots,
        "status": row.status,
        "handles": signoff_handles(row.handles, row.sources),
        "sources": list(row.sources),
        "signed": can_sign(row.handles, row.sources),
        "identity": _receipt_identity(row.columns.get("identity")),
        "b3": row.columns.get("b3"),
        "makespan_ns": row.columns.get("makespan_ns"),
        "aer_provenance": row.columns.get("aer_provenance"),
        "stages": list(row.columns.get("stages") or []),
        "lanes": lanes_from_stages(row.columns.get("stages") or []),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if row.tenant_id:
        payload["tenant_id"] = row.tenant_id
    return _scrub_forbidden(payload)


def validate_status(status: str, handles: Mapping[str, str], sources: list[str]) -> str:
    if status not in STATUSES:
        raise AssignmentError(f"unknown status {status!r}")
    if status == STATUS_SIGNED and not can_sign(handles, sources):
        raise AssignmentError("unsigned work cannot look signed")
    return status


@dataclass
class Assignment:
    assignment_id: str
    room: str
    brief: str
    recipe: str
    shots: int
    status: str
    handles: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    columns: dict[str, Any] = field(default_factory=dict)
    ask_tool: str | None = None
    ask: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    tenant_id: str = ""

    def __post_init__(self) -> None:
        if self.room not in ROOMS:
            raise AssignmentError(f"unknown room {self.room!r}")
        self.handles = sanitize_handles(self.handles)
        self.sources = sanitize_sources(self.sources)
        self.status = validate_status(self.status, self.handles, self.sources)
        self.tenant_id = normalize_tenant(self.tenant_id)
        stamp = utc_now()
        if not self.created_at:
            self.created_at = stamp
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "room": self.room,
            "brief": self.brief,
            "recipe": self.recipe,
            "shots": self.shots,
            "status": self.status,
            "handles": dict(self.handles),
            "sources": list(self.sources),
            "columns": dict(self.columns),
            "ask_tool": self.ask_tool,
            "ask": dict(self.ask) if self.ask else None,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tenant_id": self.tenant_id,
            "lanes": lanes_from_stages(self.columns.get("stages") or []),
            "signoff": {
                "eligible": can_sign(self.handles, self.sources),
                "handles": signoff_handles(self.handles, self.sources),
            },
        }

    def face_payload(self) -> dict[str, Any]:
        """3080 inbox row. No columns / brief / recipe / ask.args / identity."""
        payload: dict[str, Any] = {
            "assignment_id": self.assignment_id,
            "status": self.status,
            "ask_tool": self.ask_tool,
        }
        handles = sanitize_handles(self.handles)
        if handles:
            payload["handles"] = handles
        tool = None
        if isinstance(self.ask, Mapping) and self.ask.get("tool"):
            tool = str(self.ask["tool"])
        elif self.ask_tool:
            tool = str(self.ask_tool)
        if tool:
            payload["ask"] = {"tool": tool}
        if self.status in (STATUS_REJECTED, STATUS_FAILED):
            if self.error == "cancelled":
                payload["reason"] = "cancelled"
            elif self.status == STATUS_REJECTED:
                payload["reason"] = "rejected"
            else:
                payload["reason"] = "failed"
        estimate = face_makespan_ns(self.columns.get("makespan_ns"))
        if estimate is not None:
            payload["makespan_ns"] = estimate
        verdict = face_b3_verdict(self.columns.get("b3"))
        if verdict is not None:
            payload["b3_verdict"] = verdict
        foreign = face_aer_provenance(self.columns.get("aer_provenance"))
        if foreign is not None:
            payload["aer_provenance"] = foreign
        if self.status == STATUS_SIGNED:
            shots = face_shots_actual(self.columns.get("shots_actual"))
            if shots is not None:
                payload["shots_actual"] = shots
        if self.created_at:
            payload["created_at"] = self.created_at
        if self.updated_at:
            payload["updated_at"] = self.updated_at
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Assignment":
        return cls(
            assignment_id=str(raw.get("assignment_id") or ""),
            room=str(raw.get("room") or ROOM_LAB),
            brief=str(raw.get("brief") or ""),
            recipe=str(raw.get("recipe") or "a2_chem_pes"),
            shots=int(raw.get("shots") or 1000),
            status=str(raw.get("status") or STATUS_DRAFT),
            handles=dict(raw.get("handles") or {}),
            sources=list(raw.get("sources") or []),
            columns=dict(raw.get("columns") or {}),
            ask_tool=raw.get("ask_tool"),
            ask=dict(raw["ask"]) if isinstance(raw.get("ask"), dict) else None,
            error=raw.get("error"),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            tenant_id=normalize_tenant(raw.get("tenant_id")),
        )
