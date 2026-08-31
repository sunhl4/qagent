from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.assignment_store import AssignmentStore
from qagent.adapters.support import new_id
from qagent.models.assignment import (
    HANDLE_KEYS,
    LIST_ORDER,
    ROOM_ALGO,
    ROOM_LAB,
    ROOM_SIGN,
    SOURCE_AER,
    SOURCE_TWIN,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_NEEDS_ASK,
    STATUS_REJECTED,
    STATUS_RUNNING,
    STATUS_SIGNED,
    Assignment,
    AssignmentError,
    can_sign,
    face_shots_actual,
    receipt_payload,
    sanitize_handles,
    seal_receipt,
    verify_receipt,
    sanitize_sources,
    normalize_tenant,
    utc_now,
)
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.models.invoke import STATUS_OK
from qagent.services.eln import append_assignment, copy_events_for_fork
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke
from qagent.services.vibe_path import run_vibe_path

def _store() -> AssignmentStore:
    return AssignmentStore()


def _persist(row: Assignment, *, parent_assignment_id: str | None = None) -> Assignment:
    row.updated_at = utc_now()
    saved = _store().put(row)
    handles = sanitize_handles(saved.handles)
    append_assignment(
        assignment_id=saved.assignment_id,
        status=saved.status,
        room=saved.room,
        parent_assignment_id=parent_assignment_id,
        circuit_id=handles.get(HANDLE_CIRCUIT) or None,
        asset_id=handles.get(HANDLE_ASSET) or None,
    )
    return saved


def create(
    *,
    room: str = ROOM_LAB,
    brief: str = "",
    recipe: str = "a2_chem_pes",
    shots: int = 1000,
    handles: dict[str, str] | None = None,
    sources: list[str] | None = None,
    columns: dict[str, Any] | None = None,
    tenant_id: str = "",
    parent_assignment_id: str | None = None,
) -> Assignment:
    row = Assignment(
        assignment_id=new_id("asg"),
        room=room,
        brief=brief,
        recipe=recipe or "a2_chem_pes",
        shots=int(shots or 1000),
        status=STATUS_DRAFT,
        handles=sanitize_handles(handles),
        sources=sanitize_sources(sources),
        columns=dict(columns or {}),
        tenant_id=normalize_tenant(tenant_id),
    )
    return _persist(row, parent_assignment_id=parent_assignment_id)


def list_assignments(status: str | None = None, tenant_id: str = "") -> list[Assignment]:
    rows = _store().list(tenant_id=normalize_tenant(tenant_id))
    if status:
        rows = [row for row in rows if row.status == status]
    rows.sort(key=lambda row: LIST_ORDER.get(row.status, 9))
    return rows


def get_assignment(assignment_id: str, tenant_id: str = "") -> Assignment:
    return _store().get(assignment_id, tenant_id=normalize_tenant(tenant_id))


def _refuse_if_signed(row: Assignment, *, action: str) -> None:
    if row.status == STATUS_SIGNED:
        raise AssignmentError(f"signed work cannot be {action}")


def run(assignment_id: str, *, approved: bool = False, attended: bool = False, tenant_id: str = "") -> Assignment:
    row = get_assignment(assignment_id, tenant_id=tenant_id)
    _refuse_if_signed(row, action="rerun")
    row.status = STATUS_RUNNING
    row.error = None
    row.ask_tool = None
    row = _persist(row)
    if row.room == ROOM_ALGO:
        return _finish(row, _run_algo(row, approved=approved, attended=attended))
    if row.room == ROOM_SIGN:
        return _finish(row, _run_sign(row, approved=approved))
    return _finish(row, _run_lab(row, approved=approved))


def approve(assignment_id: str, tenant_id: str = "") -> Assignment:
    row = get_assignment(assignment_id, tenant_id=tenant_id)
    if row.status == STATUS_NEEDS_ASK and row.ask:
        row.status = STATUS_RUNNING
        row.error = None
        row = _persist(row)
        return _finish(row, _resume(row))
    return run(assignment_id, approved=True)


def receipt(assignment_id: str, tenant_id: str = "") -> dict[str, Any]:
    return seal_receipt(receipt_payload(get_assignment(assignment_id, tenant_id=tenant_id)))


def verify_assignment_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    return verify_receipt(payload)


def preflight(assignment_id: str, tenant_id: str = "") -> dict[str, Any]:
    row = get_assignment(assignment_id, tenant_id=tenant_id)
    room = row.room if row.room != ROOM_ALGO else ROOM_LAB
    identity = invoke("ionstack_twin_identity", room, {})
    live = bool((identity.payload or {}).get("live"))
    has_circuit = bool(row.handles.get("circuit_id") or (row.ask or {}).get("args", {}).get("circuit"))
    estimate_args: dict[str, Any] = {}
    circuit_id = row.handles.get(HANDLE_CIRCUIT)
    if circuit_id:
        estimate_args[HANDLE_CIRCUIT] = circuit_id
    asked = row.ask.get("args") if isinstance(row.ask, dict) else None
    circuit = asked.get("circuit") if isinstance(asked, dict) else None
    if isinstance(circuit, dict):
        estimate_args["circuit"] = circuit
    estimate_ok = False
    estimate_ns: float | None = None
    if estimate_args:
        estimate = invoke("ionstack_compile_estimate", room, estimate_args)
        payload = estimate.payload or {}
        estimate_ok = estimate.status == STATUS_OK and "makespan_ns" in payload
        if estimate_ok:
            estimate_ns = float(payload["makespan_ns"])
    checks = {
        "twin_live": live,
        "has_circuit": has_circuit,
        "has_asset": bool(row.handles.get("asset_id")),
        "estimate_ok": estimate_ok,
        "shots": row.shots,
        "ask_tool": row.ask_tool,
    }
    if estimate_ns is not None:
        checks["estimate_ns"] = estimate_ns
    return {
        "ok": live and has_circuit and row.status == STATUS_NEEDS_ASK,
        "checks": checks,
    }


def cancel(assignment_id: str, tenant_id: str = "") -> Assignment:
    row = get_assignment(assignment_id, tenant_id=tenant_id)
    _refuse_if_signed(row, action="cancelled")
    row.status = STATUS_REJECTED
    row.ask_tool = None
    row.ask = None
    row.error = "cancelled"
    return _persist(row)


def reject(assignment_id: str, tenant_id: str = "") -> Assignment:
    row = get_assignment(assignment_id, tenant_id=tenant_id)
    _refuse_if_signed(row, action="cancelled")
    row.status = STATUS_REJECTED
    row.ask_tool = None
    row.ask = None
    return _persist(row)


def fork(assignment_id: str, *, room: str | None = None, tenant_id: str = "") -> Assignment:
    src = get_assignment(assignment_id, tenant_id=tenant_id)
    handles = {key: value for key, value in src.handles.items() if key != HANDLE_TWIN}
    sources = [item for item in src.sources if item != SOURCE_TWIN]
    columns = {
        key: value
        for key, value in src.columns.items()
        if key not in {"counts", "identity"}
    }
    created = create(
        room=room or src.room,
        brief=src.brief,
        recipe=src.recipe,
        shots=src.shots,
        handles=handles,
        sources=sources,
        columns=columns,
        tenant_id=src.tenant_id,
        parent_assignment_id=src.assignment_id,
    )
    copy_events_for_fork(src.assignment_id, created.assignment_id)
    return created


def _finish(row: Assignment, update: dict[str, Any]) -> Assignment:
    row.handles = sanitize_handles({**row.handles, **(update.get("handles") or {})})
    row.sources = sanitize_sources([*row.sources, *(update.get("sources") or [])])
    row.columns = {**row.columns, **(update.get("columns") or {})}
    row.ask_tool = update.get("ask_tool")
    if "ask" in update:
        row.ask = update.get("ask")
    row.error = update.get("error")
    status = str(update.get("status") or STATUS_FAILED)
    if status == STATUS_SIGNED and not can_sign(row.handles, row.sources):
        raise AssignmentError("unsigned work cannot look signed")
    row.status = status
    return _persist(row)


def _copy_shots_actual(columns: dict[str, Any], raw: Any) -> None:
    shots = face_shots_actual(raw)
    if shots is not None:
        columns["shots_actual"] = shots


def _sources_from_payload(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    found: list[str] = []
    summary = payload.get("summary")
    if isinstance(summary, dict) and summary.get("source"):
        found.append(str(summary["source"]))
    provenance = payload.get("provenance")
    if provenance == SOURCE_AER:
        found.append(SOURCE_AER)
    if provenance == SOURCE_TWIN:
        found.append(SOURCE_TWIN)
    return found


def _run_lab(row: Assignment, *, approved: bool) -> dict[str, Any]:
    path = run_vibe_path(
        ROOM_LAB,
        recipe=row.recipe,
        shots=row.shots,
        approved=approved,
        assignment_id=row.assignment_id,
    )
    sources: list[str] = []
    columns: dict[str, Any] = {}
    for step in path.get("steps") or []:
        payload = step.get("payload") if isinstance(step, dict) else None
        sources.extend(_sources_from_payload(payload if isinstance(payload, dict) else None))
        if isinstance(payload, dict):
            if "makespan_ns" in payload:
                columns["makespan_ns"] = payload["makespan_ns"]
            if payload.get("provenance") == SOURCE_AER:
                columns["aer_provenance"] = SOURCE_AER
            if payload.get("counts"):
                columns["counts"] = payload["counts"]
            if payload.get("b3"):
                columns["b3"] = payload["b3"]
            if payload.get(HANDLE_TWIN):
                _copy_shots_actual(columns, payload.get("shots_actual"))
    handles = path.get("handles") or {}
    if handles.get("makespan_ns") is not None:
        columns["makespan_ns"] = handles["makespan_ns"]
    if handles.get("aer_provenance"):
        columns["aer_provenance"] = handles["aer_provenance"]
    if handles.get("b3"):
        columns["b3"] = handles["b3"]
    status = str(path.get("status") or STATUS_FAILED)
    if status == "ok" and can_sign(sanitize_handles(handles), sanitize_sources(sources)):
        status = STATUS_SIGNED
    elif status == "ok":
        status = STATUS_FAILED
    elif status == STATUS_NEEDS_ASK:
        status = STATUS_NEEDS_ASK
    else:
        status = STATUS_FAILED
    identity = invoke("ionstack_twin_identity", ROOM_LAB, {}, assignment_id=row.assignment_id)
    if identity.payload:
        columns["identity"] = dict(identity.payload)
    columns["stages"] = [
        str(step.get("tool"))
        for step in path.get("steps") or []
        if isinstance(step, dict) and step.get("tool")
    ]
    ask = None
    if status == STATUS_NEEDS_ASK:
        ask = {
            "tool": "ionstack_twin_run",
            "args": {
                "mode": "pipeline",
                "shots": row.shots,
                "circuit": DEFAULT_CIRCUIT,
                "circuit_id": handles.get("circuit_id"),
            },
        }
    return {
        "status": status,
        "handles": {key: handles[key] for key in HANDLE_KEYS if handles.get(key)},
        "sources": sources,
        "columns": columns,
        "ask_tool": path.get("tool") if status == STATUS_NEEDS_ASK else None,
        "ask": ask,
        "error": None if status != STATUS_FAILED else path.get("summary"),
    }


def _run_sign(row: Assignment, *, approved: bool) -> dict[str, Any]:
    sources: list[str] = []
    columns: dict[str, Any] = {}
    handles: dict[str, str] = dict(row.handles)
    identity = invoke("ionstack_twin_identity", ROOM_SIGN, {}, assignment_id=row.assignment_id)
    if identity.payload:
        columns["identity"] = dict(identity.payload)
        if not identity.payload.get("live"):
            columns["twin_live"] = False
    twin = invoke(
        "ionstack_twin_run",
        ROOM_SIGN,
        {
            "mode": "pipeline",
            "shots": row.shots,
            "circuit": DEFAULT_CIRCUIT,
            "circuit_id": handles.get("circuit_id"),
        },
        approved=approved,
        assignment_id=row.assignment_id,
    )
    if twin.status == STATUS_NEEDS_ASK:
        return {
            "status": STATUS_NEEDS_ASK,
            "handles": handles,
            "sources": sources,
            "columns": columns,
            "ask_tool": twin.tool,
            "ask": {
                "tool": "ionstack_twin_run",
                "args": {
                    "mode": "pipeline",
                    "shots": row.shots,
                    "circuit": DEFAULT_CIRCUIT,
                    "circuit_id": handles.get("circuit_id"),
                },
            },
        }
    if twin.status != "ok" or not (twin.payload or {}).get(HANDLE_TWIN):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "sources": sources,
            "columns": columns,
            "ask_tool": None,
            "error": twin.error or "TwinRun 失败；不会本地伪造 twin_id。",
        }
    handles[HANDLE_TWIN] = str(twin.payload[HANDLE_TWIN])
    sources.append(SOURCE_TWIN)
    columns["counts"] = twin.payload.get("counts")
    _copy_shots_actual(columns, twin.payload.get("shots_actual"))
    if handles.get("asset_id"):
        b3 = invoke(
            "qdata_dequant_gate",
            ROOM_SIGN,
            {"asset_id": handles["asset_id"]},
            assignment_id=row.assignment_id,
        )
        if b3.payload and b3.payload.get("b3"):
            columns["b3"] = b3.payload["b3"]
    return {"status": STATUS_SIGNED, "handles": handles, "sources": sources, "columns": columns}


def _run_algo(row: Assignment, *, approved: bool, attended: bool) -> dict[str, Any]:
    tool = "subagent_codex_attended" if attended else "subagent_codex"
    result = invoke(
        tool,
        ROOM_ALGO,
        {"task": row.brief or "spi", "approved": approved},
        assignment_id=row.assignment_id,
    )
    columns = {"codex": dict(result.payload) if result.payload else {"status": result.status}}
    if result.status == STATUS_NEEDS_ASK:
        return {"status": STATUS_NEEDS_ASK, "handles": row.handles, "columns": columns, "ask_tool": tool}
    if result.status != "ok":
        return {
            "status": STATUS_FAILED,
            "handles": row.handles,
            "columns": columns,
            "error": result.error or result.status,
        }
    return {"status": STATUS_DRAFT, "handles": row.handles, "columns": columns}


def _resume(row: Assignment) -> dict[str, Any]:
    ask = row.ask or {}
    tool = str(ask.get("tool") or "ionstack_twin_run")
    args = dict(ask.get("args") or {})
    preset = row.room if row.room != ROOM_ALGO else ROOM_SIGN
    twin = invoke(tool, preset, args, approved=True, assignment_id=row.assignment_id)
    columns = dict(row.columns)
    handles = dict(row.handles)
    sources = list(row.sources)
    if twin.status != "ok" or not (twin.payload or {}).get(HANDLE_TWIN):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "sources": sources,
            "columns": columns,
            "ask": ask,
            "ask_tool": tool,
            "error": twin.error or "TwinRun 失败；不会本地伪造 twin_id。",
        }
    handles[HANDLE_TWIN] = str(twin.payload[HANDLE_TWIN])
    sources.append(SOURCE_TWIN)
    columns["counts"] = twin.payload.get("counts")
    _copy_shots_actual(columns, (twin.payload or {}).get("shots_actual"))
    stages = list(columns.get("stages") or [])
    stages.append("ionstack_twin_run")
    if handles.get("asset_id"):
        b3 = invoke(
            "qdata_dequant_gate",
            ROOM_LAB if row.room == ROOM_ALGO else row.room,
            {"asset_id": handles["asset_id"]},
            assignment_id=row.assignment_id,
        )
        if b3.payload and b3.payload.get("b3"):
            columns["b3"] = b3.payload["b3"]
            stages.append("qdata_dequant_gate")
    columns["stages"] = stages
    return {
        "status": STATUS_SIGNED,
        "handles": handles,
        "sources": sources,
        "columns": columns,
        "ask": None,
        "ask_tool": None,
    }
