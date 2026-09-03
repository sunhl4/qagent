from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.pin import circuit_face, get_pin
from qagent.models.assignment import (
    ROOM_LAB,
    SOURCE_AER,
    SOURCE_TWIN,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_NEEDS_ASK,
    STATUS_SIGNED,
    Assignment,
    can_sign,
    sanitize_handles,
    sanitize_sources,
)
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN  # twin stays on the assignment, not this tool face
from qagent.models.invoke import STATUS_OK
from qagent.services.invoke import invoke

STAGES = ("parse", "validate", "estimate", "ask", "execute", "receipt")
BACKEND_TWIN = "twin"
BACKEND_AER = "aer"
WORKFLOW = "circuit"


def public_job(row: Assignment) -> dict[str, Any]:
    """Short job face. No qasm3 / body / forged twin_id."""
    handles = sanitize_handles(row.handles)
    payload: dict[str, Any] = {
        "assignment_id": row.assignment_id,
        "workflow": WORKFLOW,
        "stage": str(row.columns.get("stage") or "parse"),
        "status": row.status,
        "backend": str(row.columns.get("backend") or BACKEND_TWIN),
    }
    if handles.get(HANDLE_CIRCUIT):
        payload[HANDLE_CIRCUIT] = handles[HANDLE_CIRCUIT]
        drawn = circuit_face(handles[HANDLE_CIRCUIT]) or {}
        if drawn.get("n_qubits"):
            payload["n_qubits"] = drawn["n_qubits"]
        if drawn.get("n_instructions"):
            payload["n_instructions"] = drawn["n_instructions"]
    if row.columns.get("makespan_ns") is not None:
        payload["makespan_ns"] = row.columns["makespan_ns"]
    if row.ask_tool:
        payload["ask_tool"] = row.ask_tool
    if row.columns.get("aer_provenance"):
        payload["aer_provenance"] = row.columns["aer_provenance"]
    if row.error:
        payload["error"] = row.error
    return payload


def start_job(
    *,
    circuit_id: str,
    shots: int = 1000,
    backend: str = BACKEND_TWIN,
    tenant_id: str = "",
    approved: bool = False,
) -> Assignment:
    from qagent.services.assignment import _finish, create

    pin = get_pin(circuit_id)
    if not pin:
        raise ValueError("unknown circuit_id")
    backend = BACKEND_AER if backend == BACKEND_AER else BACKEND_TWIN
    row = create(
        room=ROOM_LAB,
        brief="circuit job",
        recipe="circuit_job",
        shots=int(shots or 1000),
        handles={HANDLE_CIRCUIT: circuit_id},
        columns={
            "workflow": WORKFLOW,
            "stage": "parse",
            "backend": backend,
            "stages": ["qagent_pin_circuit"],
        },
        tenant_id=tenant_id,
    )
    return _finish(row, advance(row, approved=approved))


def advance(row: Assignment, *, approved: bool) -> dict[str, Any]:
    handles = dict(row.handles)
    circuit_id = handles.get(HANDLE_CIRCUIT)
    if not circuit_id or not get_pin(circuit_id):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "columns": {**row.columns, "stage": "validate"},
            "error": "unknown circuit_id",
        }
    drawn = circuit_face(circuit_id) or {}
    columns = dict(row.columns)
    columns["workflow"] = WORKFLOW
    columns["stage"] = "validate"
    stages = list(columns.get("stages") or [])
    if "qagent_pin_circuit" not in stages:
        stages.append("qagent_pin_circuit")

    estimate = invoke(
        "ionstack_compile_estimate",
        ROOM_LAB,
        {HANDLE_CIRCUIT: circuit_id, "machine": "t_junction"},
        assignment_id=row.assignment_id,
    )
    if estimate.status != STATUS_OK or "makespan_ns" not in (estimate.payload or {}):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "columns": {**columns, "stage": "estimate", "stages": stages},
            "error": estimate.error or "estimate failed",
        }
    columns["makespan_ns"] = estimate.payload["makespan_ns"]
    columns["stage"] = "estimate"
    stages.append("ionstack_compile_estimate")
    columns["stages"] = stages

    backend = str(columns.get("backend") or BACKEND_TWIN)
    if backend == BACKEND_AER:
        return _run_aer(row, handles, columns, stages)

    ask_args = {
        "mode": "pipeline",
        "shots": row.shots,
        "circuit_id": circuit_id,
    }
    columns["stage"] = "ask"
    if not approved:
        return {
            "status": STATUS_NEEDS_ASK,
            "handles": handles,
            "columns": columns,
            "ask_tool": "ionstack_twin_run",
            "ask": {"tool": "ionstack_twin_run", "args": ask_args},
        }
    return _run_twin(row, handles, columns, stages, ask_args, approved=True)


def _run_aer(
    row: Assignment,
    handles: dict[str, str],
    columns: dict[str, Any],
    stages: list[str],
) -> dict[str, Any]:
    aer = invoke(
        "qiskit_aer_run",
        ROOM_LAB,
        {HANDLE_CIRCUIT: handles.get(HANDLE_CIRCUIT), "shots": min(int(row.shots or 128), 128)},
        assignment_id=row.assignment_id,
    )
    stages.append("qiskit_aer_run")
    columns["stages"] = stages
    columns["stage"] = "receipt"
    if aer.status != STATUS_OK:
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "columns": columns,
            "error": aer.error or "aer failed",
        }
    payload = aer.payload or {}
    if payload.get(HANDLE_TWIN):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "columns": columns,
            "error": "aer leaked twin_id",
        }
    columns["aer_provenance"] = payload.get("provenance") or SOURCE_AER
    return {
        "status": STATUS_DRAFT,
        "handles": handles,
        "sources": [SOURCE_AER],
        "columns": columns,
        "ask": None,
        "ask_tool": None,
    }


def _run_twin(
    row: Assignment,
    handles: dict[str, str],
    columns: dict[str, Any],
    stages: list[str],
    ask_args: dict[str, Any],
    *,
    approved: bool,
) -> dict[str, Any]:
    twin = invoke(
        "ionstack_twin_run",
        ROOM_LAB,
        ask_args,
        approved=approved,
        assignment_id=row.assignment_id,
    )
    columns["stage"] = "execute"
    if twin.status == "needs_ask":
        columns["stage"] = "ask"
        return {
            "status": STATUS_NEEDS_ASK,
            "handles": handles,
            "columns": columns,
            "ask_tool": twin.tool,
            "ask": {"tool": "ionstack_twin_run", "args": ask_args},
        }
    if twin.status != STATUS_OK or not (twin.payload or {}).get(HANDLE_TWIN):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "columns": columns,
            "error": twin.error or "TwinRun 失败；不会本地伪造 twin_id。",
        }
    handles[HANDLE_TWIN] = str(twin.payload[HANDLE_TWIN])
    stages.append("ionstack_twin_run")
    columns["stages"] = stages
    columns["stage"] = "receipt"
    columns["shots_actual"] = twin.payload.get("shots_actual")
    sources = [SOURCE_TWIN]
    if not can_sign(sanitize_handles(handles), sanitize_sources(sources)):
        return {
            "status": STATUS_FAILED,
            "handles": handles,
            "columns": columns,
            "error": "unsigned work cannot look signed",
        }
    return {
        "status": STATUS_SIGNED,
        "handles": handles,
        "sources": sources,
        "columns": columns,
        "ask": None,
        "ask_tool": None,
    }


def run_tool(args: Mapping[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "start")
    if action == "status":
        from qagent.services.assignment import get_assignment

        row = get_assignment(str(args.get("assignment_id") or ""))
        return public_job(row)
    if action != "start":
        raise ValueError("action must be start or status")
    circuit_id = str(args.get("circuit_id") or "").strip()
    if not circuit_id:
        raise ValueError("circuit_id is required")
    row = start_job(
        circuit_id=circuit_id,
        shots=int(args.get("shots") or 1000),
        backend=str(args.get("backend") or BACKEND_TWIN),
        approved=bool(args.get("approved")),
    )
    return public_job(row)
