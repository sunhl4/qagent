from __future__ import annotations

from typing import Any

from qagent.models.invoke import InvokeResult
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke

GOLDEN_STEPS = (
    "qagent_list_engines",
    "qdata_run_recipe",
    "qagent_pin_circuit",
    "qiskit_aer_run",
    "ionstack_compile_estimate",
    "ionstack_twin_run",
    "qdata_dequant_gate",
)


def _as_dict(result: InvokeResult) -> dict[str, Any]:
    return {
        "tool": result.tool,
        "decision": result.decision,
        "status": result.status,
        "slot_id": result.slot_id,
        "payload": dict(result.payload) if result.payload else None,
        "error": result.error,
    }


def run_vibe_path(
    preset: str = "lab",
    *,
    recipe: str = "a2_chem_pes",
    shots: int = 1000,
    approved: bool = False,
    assignment_id: str | None = None,
) -> dict[str, Any]:
    """Scripted golden path. Same invoke() as the shell; not a third loop."""
    steps: list[dict[str, Any]] = []
    handles: dict[str, Any] = {}

    def _invoke(tool: str, args: dict[str, Any], *, approved: bool = False):
        return invoke(tool, preset, args, approved=approved, assignment_id=assignment_id)

    listed = _invoke("qagent_list_engines", {})
    steps.append(_as_dict(listed))

    recipe_run = _invoke("qdata_run_recipe", {"name": recipe, "shots": shots})
    steps.append(_as_dict(recipe_run))
    if recipe_run.payload and recipe_run.payload.get("asset_id"):
        handles["asset_id"] = recipe_run.payload["asset_id"]

    pin_args: dict[str, Any] = {"source": "logical", "logical": DEFAULT_CIRCUIT["body"]}
    if handles.get("asset_id"):
        pin_args["asset_id"] = handles["asset_id"]
    pinned = _invoke("qagent_pin_circuit", pin_args)
    steps.append(_as_dict(pinned))
    if pinned.payload and pinned.payload.get("circuit_id"):
        handles["circuit_id"] = pinned.payload["circuit_id"]

    aer = _invoke(
        "qiskit_aer_run",
        {"circuit_id": handles.get("circuit_id"), "shots": min(shots, 128)},
    )
    steps.append(_as_dict(aer))
    if aer.payload:
        handles["aer_provenance"] = aer.payload.get("provenance")
        if "twin_id" in aer.payload:
            handles["aer_leaked_twin_id"] = True

    estimate = _invoke(
        "ionstack_compile_estimate",
        {
            "circuit_id": handles.get("circuit_id"),
            "circuit": DEFAULT_CIRCUIT,
            "machine": "t_junction",
        },
    )
    steps.append(_as_dict(estimate))
    if estimate.payload and "makespan_ns" in estimate.payload:
        handles["makespan_ns"] = estimate.payload["makespan_ns"]

    twin = _invoke(
        "ionstack_twin_run",
        {
            "mode": "pipeline",
            "shots": shots,
            "circuit": DEFAULT_CIRCUIT,
            "circuit_id": handles.get("circuit_id"),
        },
        approved=approved,
    )
    steps.append(_as_dict(twin))
    if twin.status == "needs_ask":
        return {
            "status": "needs_ask",
            "tool": "ionstack_twin_run",
            "steps": steps,
            "handles": handles,
            "summary": "TwinRun 需要人批。批准后同一工具名续跑，才会出现 twin_id。",
        }
    if twin.status != "ok":
        return {
            "status": twin.status,
            "tool": "ionstack_twin_run",
            "steps": steps,
            "handles": handles,
            "summary": twin.error or "TwinRun 失败；不会本地伪造 twin_id。",
        }
    if twin.payload and twin.payload.get("twin_id"):
        handles["twin_id"] = twin.payload["twin_id"]

    b3 = _invoke("qdata_dequant_gate", {"asset_id": handles.get("asset_id")})
    steps.append(_as_dict(b3))
    if b3.payload:
        verdict = b3.payload.get("b3")
        if isinstance(verdict, dict):
            handles["b3"] = verdict

    return {"status": "ok", "tool": None, "steps": steps, "handles": handles, "summary": "黄金路径走完。"}
