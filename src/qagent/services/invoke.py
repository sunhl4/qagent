from __future__ import annotations

from typing import Any, Mapping

from qagent.models.fill import FillSlotError
from qagent.models.invoke import (
    STATUS_DENIED,
    STATUS_ERROR,
    STATUS_NEEDS_ASK,
    STATUS_NOT_WIRED,
    STATUS_OK,
    InvokeResult,
)
from qagent.models.handles import B3_QUANTUM_WINS
from qagent.services.eln import (
    append_b3,
    append_claim_blocked,
    append_estimate,
    append_recipe_pin,
    append_twin_signoff,
)
from qagent.services.errors import explain_failure
from qagent.services.notify import record_ask
from qagent.services.policy import decide
from qagent.services.ports import method_for_tool
from qagent.services.registry import PortRegistry, default_registry
from qagent.services.usage import record_usage
from qagent.services.witness import first_finding


def _record_denied(tool: str, args: Mapping[str, Any], assignment_id: str | None) -> None:
    if tool == "qdata_dequant_gate" and args.get("force_verdict") == B3_QUANTUM_WINS:
        append_claim_blocked(reason="force_verdict", assignment_id=assignment_id)
        return
    if tool == "qiskit_aer_run" and args.get("claim_twin_id"):
        append_claim_blocked(reason="aer_claim_twin_id", assignment_id=assignment_id)
        return
    if tool == "cirq_simulator_run" and args.get("claim_twin_id"):
        append_claim_blocked(reason="cirq_claim_twin_id", assignment_id=assignment_id)
        return
    if tool in {"cal_edit", "shuttle_write", "cordis_define", "cordis_run"}:
        append_claim_blocked(reason="southbound", assignment_id=assignment_id)


def _record_ok(
    tool: str,
    args: Mapping[str, Any],
    payload: Mapping[str, Any],
    assignment_id: str | None,
) -> None:
    if tool == "qdata_run_recipe":
        append_recipe_pin(
            recipe=str(args.get("name") or ""),
            params={"shots": args.get("shots")},
            assignment_id=assignment_id,
        )
    if tool == "qdata_dequant_gate":
        verdict = payload.get("b3", {})
        if isinstance(verdict, dict) and verdict.get("verdict"):
            append_b3(verdict=str(verdict["verdict"]), assignment_id=assignment_id)
    if tool == "ionstack_compile_estimate" and "makespan_ns" in payload:
        append_estimate(makespan_ns=float(payload["makespan_ns"]), assignment_id=assignment_id)
    if tool == "ionstack_twin_run" and payload.get("twin_id"):
        append_twin_signoff(
            twin_id=str(payload["twin_id"]),
            shots_actual=int(payload.get("shots_actual") or args.get("shots") or 0),
            assignment_id=assignment_id,
        )


def _explain(tool: str, status: str, message: str = "", slot: str = "") -> dict[str, Any]:
    return explain_failure(tool, message, status=status, slot=slot).to_public()


def invoke(
    tool: str,
    preset: str,
    args: Mapping[str, Any] | None = None,
    *,
    registry: PortRegistry | None = None,
    approved: bool = False,
    assignment_id: str | None = None,
) -> InvokeResult:
    """Policy first. Ask never hits the port unless approved."""
    args = dict(args or {})
    decision = decide(tool, preset, args)
    if decision == "deny":
        _record_denied(tool, args, assignment_id)
        result = InvokeResult(
            tool=tool,
            decision=decision,
            status=STATUS_DENIED,
            explain=_explain(tool, STATUS_DENIED, "deny"),
        )
        record_usage(tool=tool, preset=preset, status=result.status, decision=decision)
        return result
    if decision == "ask" and not approved:
        record_ask(tool=tool, preset=preset, args=args)
        result = InvokeResult(tool=tool, decision=decision, status=STATUS_NEEDS_ASK)
        record_usage(tool=tool, preset=preset, status=result.status, decision=decision)
        return result

    binding = method_for_tool(tool)
    port = (registry or default_registry()).get(binding.port_id)
    method = getattr(port, binding.method)
    try:
        payload = method(args)
    except FillSlotError as exc:
        if tool == "qdata_run_recipe" and args.get("name"):
            append_recipe_pin(
                recipe=str(args["name"]),
                params={"shots": args.get("shots")},
                assignment_id=assignment_id,
            )
        result = InvokeResult(
            tool=tool,
            decision=decision,
            status=STATUS_NOT_WIRED,
            slot_id=exc.slot_id,
            explain=_explain(tool, STATUS_NOT_WIRED, "empty slot", slot=exc.slot_id),
        )
        record_usage(tool=tool, preset=preset, status=result.status, decision=decision)
        return result
    except (ValueError, KeyError, RuntimeError, PermissionError, TypeError) as exc:
        result = InvokeResult(
            tool=tool,
            decision=decision,
            status=STATUS_ERROR,
            slot_id=binding.slot,
            payload={"error": str(exc)},
            error=str(exc),
            explain=_explain(tool, STATUS_ERROR, str(exc), slot=binding.slot),
        )
        record_usage(tool=tool, preset=preset, status=result.status, decision=decision)
        return result
    hit = first_finding(tool, payload)
    if hit:
        append_claim_blocked(reason=hit.kind, assignment_id=assignment_id)
        result = InvokeResult(
            tool=tool,
            decision=decision,
            status=STATUS_ERROR,
            slot_id=binding.slot,
            error=hit.message,
            explain=_explain(tool, STATUS_ERROR, hit.message, slot=binding.slot),
        )
        record_usage(tool=tool, preset=preset, status=result.status, decision=decision)
        return result
    _record_ok(tool, args, payload, assignment_id)
    result = InvokeResult(
        tool=tool,
        decision=decision,
        status=STATUS_OK,
        slot_id=binding.slot,
        payload=payload,
    )
    record_usage(tool=tool, preset=preset, status=result.status, decision=decision)
    return result
