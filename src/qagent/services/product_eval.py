from __future__ import annotations

import json
import os
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from qagent.adapters.assignment_store import AssignmentStore
from qagent.adapters.contracts import ROOT, load_product_eval_cases
from qagent.models.assignment import (
    SOURCE_LOCAL_CARD,
    SOURCE_TWIN,
    STATUS_SIGNED,
    Assignment,
    AssignmentError,
    validate_status,
)
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN, PROVENANCE_AER, PROVENANCE_QCCD_TWIN
from qagent.models.invoke import InvokeResult
from qagent.models.types import ProductEvalCase
from qagent.services.assignment import (
    cancel,
    create,
    list_assignments,
    receipt,
    verify_assignment_receipt,
)
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke
from qagent.services.policy import decide
from qagent.services.workplace import workplace_status

_MISSING = object()
SKIP_NEEDS_LIVE = "needs live"
_SOUTHBOUND = frozenset(
    {"cal_edit", "shuttle_write", "cal_read", "shuttle_read", "cordis_define", "cordis_run"}
)
_HONEST_STATUSES = frozenset({"error", "not_wired", "denied", "needs_ask"})
_QASM_BODY = (
    "OPENQASM 3.0;\ninclude \"stdgates.inc\";\nqubit[2] q;\nh q[0];\ncx q[0], q[1];\n"
)
_SWAPPED_CIRCUIT = {
    "n_qubits": 2,
    "n_instructions": 1,
    "body": {
        "schema_version": "3",
        "ir_kind": "logical",
        "n_qubits": 2,
        "instructions": [
            {"kind": "gate", "name": "X", "qubits": [0], "params": []},
        ],
    },
}
_ENV_KEYS = (
    "QAGENT_ASSIGNMENTS_FILE",
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QCHEM_HOME",
    "QAGENT_QCHEM_BIN",
    "QAGENT_TWIN_URL",
    "QAGENT_DATA_DIR",
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_KNOWLEDGE_PATH",
    "QAGENT_ROUTE_BACKEND",
    "QAGENT_PRESET_FILE",
    "DEEPSEEK_API_KEY",
)


@dataclass(frozen=True)
class ProductEvalResult:
    id: str
    ok: bool
    detail: str = ""
    skipped: bool = False


@dataclass
class _Ctx:
    result: InvokeResult | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    invoked: list[InvokeResult] = field(default_factory=list)

    def add(self, result: InvokeResult) -> InvokeResult:
        self.invoked.append(result)
        self.result = result
        self.payload = dict(result.payload or {})
        self.status = result.status
        return result


def _path_get(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


@contextmanager
def isolate_product_eval() -> Iterator[Any]:
    """Dead Twin URL, local-card qdata, temp assignment/workplace. No live dsh."""
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    work = ROOT / ".qagent" / f"q01-{uuid.uuid4().hex[:10]}"
    work.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(work / "assignments.jsonl")
    os.environ["QAGENT_DATA_DIR"] = str(work / "store")
    os.environ["QAGENT_WORKPLACE_FILE"] = str(work / "workplace.json")
    os.environ["QAGENT_SECRETS_FILE"] = str(work / "secrets.json")
    os.environ["QAGENT_DSH_ENV_FILE"] = str(work / "dsh.env")
    os.environ["QAGENT_PRESET_FILE"] = str(work / "active_preset")
    os.environ["QAGENT_TWIN_URL"] = "http://127.0.0.1:1"
    for key in (
        "QAGENT_QDATA_URL",
        "QAGENT_QDATA_HOME",
        "QAGENT_QDATA_BIN",
        "QAGENT_QCHEM_HOME",
        "QAGENT_QCHEM_BIN",
        "QAGENT_KNOWLEDGE_PATH",
        "QAGENT_ROUTE_BACKEND",
        "DEEPSEEK_API_KEY",
    ):
        os.environ.pop(key, None)
    try:
        yield work
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(work, ignore_errors=True)


def _honesty(ctx: _Ctx) -> str | None:
    blob = json.dumps(ctx.payload, default=str)
    if "cal_edit" in blob or "shuttle_write" in blob:
        return "CAL in Qagent results"
    for result in ctx.invoked:
        payload = dict(result.payload or {})
        if result.tool in _SOUTHBOUND and result.status == "ok":
            return f"CAL in Qagent results ({result.tool})"
        if result.tool == "ionstack_twin_run" and result.decision == "ask" and result.status == "ok":
            return "skip ask"
        if HANDLE_TWIN in payload:
            if result.tool != "ionstack_twin_run":
                return "fake twin"
            if payload.get("provenance") != PROVENANCE_QCCD_TWIN:
                return "fake twin"
        if payload.get("provenance") in {PROVENANCE_AER, "ibm"} and HANDLE_TWIN in payload:
            return "fake twin"
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        if summary.get("source") == "qagent-local-card" and HANDLE_TWIN in payload:
            return "fake twin"
    if HANDLE_TWIN in ctx.payload and ctx.result and ctx.result.tool != "ionstack_twin_run":
        return "fake twin"
    return None


def _pin(preset: str, *, source: str = "logical", qasm3: str | None = None) -> InvokeResult:
    args: dict[str, Any] = {"source": source, "logical": {"n_qubits": 2}, "asset_id": "q01"}
    if qasm3 is not None:
        args["source"] = source
        args["qasm3"] = qasm3
    return invoke("qagent_pin_circuit", preset, args)


def _aer(preset: str, circuit_id: str, shots: int = 128) -> InvokeResult:
    return invoke("qiskit_aer_run", preset, {"circuit_id": circuit_id, "shots": shots})


def _estimate(preset: str) -> InvokeResult:
    return invoke("ionstack_compile_estimate", preset, {"circuit": DEFAULT_CIRCUIT})


def _recipe(preset: str, name: str = "a2_chem_pes") -> InvokeResult:
    return invoke("qdata_run_recipe", preset, {"name": name})


def _twin_ask(preset: str, shots: int = 1000) -> InvokeResult:
    return invoke("ionstack_twin_run", preset, {"shots": shots})


def _sealed_row() -> Assignment:
    return Assignment(
        assignment_id="asg_q_signed",
        room="sign",
        brief="q-h10",
        recipe="a2_chem_pes",
        shots=8,
        status=STATUS_SIGNED,
        handles={HANDLE_TWIN: "twin_qh10"},
        sources=[SOURCE_TWIN],
    )


def _scenario(case: ProductEvalCase) -> _Ctx | None:
    """None = cannot run without live Twin/dsh."""
    preset = case.preset
    cid = case.id
    ctx = _Ctx()

    if cid == "Q-h06":
        pinned = ctx.add(
            invoke(
                "qagent_pin_circuit",
                preset,
                {"source": "logical", "logical": DEFAULT_CIRCUIT["body"]},
            )
        )
        circuit_id = str((pinned.payload or {}).get(HANDLE_CIRCUIT) or "")
        ctx.extra["pin_circuit_id"] = circuit_id
        matching = {
            "mode": "signoff",
            "shots": 32,
            "circuit": DEFAULT_CIRCUIT,
            HANDLE_CIRCUIT: circuit_id,
        }
        ctx.extra["twin_circuit_id"] = str(matching[HANDLE_CIRCUIT])
        ctx.add(invoke("ionstack_twin_run", preset, matching))
        swapped = {**matching, "circuit": _SWAPPED_CIRCUIT}
        ctx.add(invoke("ionstack_twin_run", preset, swapped, approved=True))
        return ctx

    if cid in {"Q-h01", "Q-h02", "Q-h08", "Q-c05"}:
        return ctx

    if cid == "Q-h03":
        pinned = ctx.add(_pin(preset))
        ctx.add(_aer(preset, str((pinned.payload or {}).get("circuit_id") or ""), 16))
        return ctx

    if cid in {"Q-h04", "Q-h05", "Q-f03"}:
        shots = 10_000_000 if cid == "Q-h04" else 1000
        ctx.add(_twin_ask(preset, shots))
        return ctx

    if cid == "Q-h07":
        ctx.add(_recipe(preset))
        return ctx

    if cid == "Q-h09":
        ctx.add(_pin(preset, source="qasm3", qasm3=_QASM_BODY))
        ctx.extra["body"] = _QASM_BODY
        return ctx

    if cid == "Q-h10":
        AssignmentStore().put(_sealed_row())
        try:
            cancel("asg_q_signed")
        except AssignmentError:
            ctx.extra["signed_refused"] = True
        else:
            ctx.extra["signed_refused"] = False
        return ctx

    if cid == "Q-a01":
        ctx.add(invoke("qagent_list_engines", preset, {}))
        return ctx

    if cid == "Q-a02":
        ctx.add(_recipe(preset, "a2_chem_pes"))
        return ctx

    if cid in {"Q-a03", "Q-f04"}:
        recipe = ctx.add(_recipe(preset, "a2_spin_shadow" if cid == "Q-a03" else "a2_chem_pes"))
        asset_id = str((recipe.payload or {}).get("asset_id") or "")
        if asset_id:
            ctx.add(invoke("qdata_dequant_gate", preset, {"asset_id": asset_id}))
        return ctx

    if cid == "Q-a04":
        ctx.add(_pin(preset))
        return ctx

    if cid == "Q-a05":
        pinned = ctx.add(_pin(preset))
        ctx.add(_aer(preset, str((pinned.payload or {}).get("circuit_id") or ""), 128))
        return ctx

    if cid in {"Q-a06", "Q-f01"}:
        ctx.add(_estimate(preset))
        return ctx

    if cid == "Q-a07":
        ctx.add(invoke("qccd_docs_search", preset, {"query": "TwinRun circuit.body mode shots"}))
        return ctx

    if cid == "Q-a08":
        ctx.add(invoke("qdata_list_providers", preset, {}))
        return ctx

    if cid == "Q-a09":
        ctx.add(invoke("qchem_run", preset, {"scenario": "minimal_vqe"}))
        return ctx

    if cid == "Q-a10":
        os.environ["QAGENT_ROUTE_BACKEND"] = "route-alt"
        ctx.add(_estimate(preset))
        return ctx

    if cid == "Q-f02":
        ctx.add(invoke("qccd_docs_search", preset, {"query": "TwinRun circuit.body mode shots"}))
        ctx.add(_recipe(preset))
        return ctx

    if cid == "Q-f05":
        ctx.add(_recipe(preset, "a2_spin_shadow"))
        return ctx

    if cid == "Q-c01":
        row = create(brief="q-c01")
        ctx.payload = receipt(row.assignment_id)
        ctx.status = str(ctx.payload.get("status") or "")
        return ctx

    if cid == "Q-c02":
        row = create(brief="q-c02", shots=32)
        rec = receipt(row.assignment_id)
        tampered = dict(rec)
        tampered["shots"] = 1
        ctx.payload = rec
        ctx.extra["verify_ok"] = bool(verify_assignment_receipt(tampered).get("ok"))
        return ctx

    if cid == "Q-c03":
        public = workplace_status().get("workplace") or {}
        ctx.payload = dict(public) if isinstance(public, dict) else {}
        ctx.extra["public"] = ctx.payload
        return ctx

    if cid == "Q-c04":
        row = create(brief="tenant-a")
        other = ROOT / ".qagent" / f"q01-tenant-{uuid.uuid4().hex[:8]}.jsonl"
        previous = os.environ.get("QAGENT_ASSIGNMENTS_FILE")
        os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(other)
        try:
            listed = [item.assignment_id for item in list_assignments()]
        finally:
            if previous is None:
                os.environ.pop("QAGENT_ASSIGNMENTS_FILE", None)
            else:
                os.environ["QAGENT_ASSIGNMENTS_FILE"] = previous
            other.unlink(missing_ok=True)
        ctx.extra["isolated"] = row.assignment_id not in listed
        ctx.payload = {"foreign": row.assignment_id, "listed": listed}
        return ctx

    return ctx


def _check(case: ProductEvalCase, assertion: dict[str, Any], ctx: _Ctx) -> str | None:
    expected = assertion.get("decision")
    tool = assertion.get("tool")
    if expected and tool:
        got = decide(
            str(tool),
            case.preset,
            assertion.get("args") if isinstance(assertion.get("args"), dict) else {},
        )
        if got != expected:
            return f"{tool} {got} != {expected}"

    if tool and expected is None and ctx.result and ctx.result.tool != tool:
        return f"tool {ctx.result.tool!r} != {tool!r}"

    payload = ctx.payload

    if assertion.get("engines_contain"):
        if ctx.status != "ok":
            return f"list_engines status={ctx.status}"
        got = {row["id"] for row in payload.get("engines") or [] if isinstance(row, dict)}
        missing = [name for name in assertion["engines_contain"] if name not in got]
        if missing:
            return f"missing engines {missing}"

    if assertion.get("path"):
        value = _path_get(payload, assertion["path"])
        if assertion.get("present_or_honest"):
            if value is not _MISSING and value:
                pass
            elif ctx.status in _HONEST_STATUSES:
                pass
            else:
                return f"{assertion['path']} missing and status={ctx.status!r}"
        else:
            if value is _MISSING:
                return f"missing path {assertion['path']}"
            if assertion.get("present") and not value:
                return f"{assertion['path']} is empty"
            if "in" in assertion and value not in assertion["in"]:
                return f"{value!r} not in {assertion['in']}"
            if assertion.get("eq") is not None and value != assertion["eq"]:
                return f"{assertion['path']} {value!r} != {assertion['eq']!r}"
            if assertion.get("prefix") and not str(value).startswith(str(assertion["prefix"])):
                return f"{assertion['path']} missing prefix {assertion['prefix']!r}"

    if assertion.get("absent_keys"):
        leaked = [key for key in assertion["absent_keys"] if key in payload]
        if leaked:
            return f"leaked keys {leaked}"

    if "status" in assertion and assertion["status"] not in {None, True, False}:
        got_status = ctx.status or (ctx.result.status if ctx.result else "")
        if got_status != assertion["status"]:
            return f"status {got_status!r} != {assertion['status']!r}"

    if assertion.get("status_ne"):
        got_status = ctx.status or (ctx.result.status if ctx.result else "")
        if got_status == assertion["status_ne"]:
            return f"status is {got_status!r}"

    if assertion.get("body_not_used_as_id"):
        circuit_id = str(payload.get("circuit_id") or "")
        body = str(ctx.extra.get("body") or "")
        if not circuit_id:
            return "missing circuit_id"
        if body and (circuit_id == body or body in circuit_id):
            return "body used as id"
        if "OPENQASM" in circuit_id or "\n" in circuit_id:
            return "body used as id"

    if assertion.get("signed_cannot_cancel"):
        if not ctx.extra.get("signed_refused"):
            return "signed work was cancelled"
        try:
            cancel("asg_q_signed")
        except AssignmentError:
            pass
        else:
            return "signed work was cancelled"

    if assertion.get("unsigned_cannot_look_signed"):
        try:
            validate_status(STATUS_SIGNED, {}, [SOURCE_LOCAL_CARD])
        except AssignmentError:
            pass
        else:
            return "unsigned work looked signed"

    if assertion.get("schema") and payload.get("schema") != assertion["schema"]:
        return f"schema {payload.get('schema')!r} != {assertion['schema']!r}"

    if assertion.get("kind") and payload.get("kind") != assertion["kind"]:
        return f"kind {payload.get('kind')!r} != {assertion['kind']!r}"

    if "verify" in assertion:
        got = ctx.extra.get("verify_ok")
        if got is None:
            return "verify was not run"
        if bool(got) != bool(assertion["verify"]):
            return f"verify {got!r} != {assertion['verify']!r}"

    if assertion.get("workplace_secret_absent"):
        key = str(assertion["workplace_secret_absent"])
        public = ctx.extra.get("public") or payload
        if key in public:
            return f"workplace leaked {key}"

    if assertion.get("tenant_isolation") and not ctx.extra.get("isolated"):
        return "foreign assignment visible"

    if assertion.get("no_net"):
        if payload.get("rest_called"):
            return "docs went to the network"
        for result in ctx.invoked:
            if (result.payload or {}).get("rest_called"):
                return "docs went to the network"

    if assertion.get("recipe_allowed"):
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        name = summary.get("recipe")
        if name not in assertion["recipe_allowed"]:
            return f"recipe {name!r} not in {assertion['recipe_allowed']}"

    if assertion.get("hits_contain"):
        blob = json.dumps(payload.get("hits") or [])
        missing = [needle for needle in assertion["hits_contain"] if needle not in blob]
        if missing:
            return f"hits missing {missing}"

    if assertion.get("same_handle"):
        handle = str(assertion["same_handle"])
        if handle != HANDLE_CIRCUIT:
            return f"same_handle {handle!r} is not {HANDLE_CIRCUIT}"
        pinned = str(ctx.extra.get("pin_circuit_id") or "")
        asked = str(ctx.extra.get("twin_circuit_id") or "")
        if not pinned or pinned != asked:
            return f"{handle} pin {pinned!r} != twin {asked!r}"

    return None


def run_product_case(case: ProductEvalCase) -> ProductEvalResult:
    """Decision + invoke/receipt field assertions. No live Twin, no official Codex."""
    with isolate_product_eval():
        ctx = _scenario(case)
        if ctx is None:
            return ProductEvalResult(case.id, False, SKIP_NEEDS_LIVE, skipped=True)
        leaked = _honesty(ctx)
        if leaked:
            return ProductEvalResult(case.id, False, leaked)
        for assertion in case.assertions:
            detail = _check(case, assertion, ctx)
            if detail == SKIP_NEEDS_LIVE:
                return ProductEvalResult(case.id, False, SKIP_NEEDS_LIVE, skipped=True)
            if detail:
                return ProductEvalResult(case.id, False, detail)
        return ProductEvalResult(case.id, True)


def run_product_evals(*ids: str) -> list[ProductEvalResult]:
    cases = load_product_eval_cases()
    if ids:
        by_id = {case.id: case for case in cases}
        return [run_product_case(by_id[case_id]) for case_id in ids if case_id in by_id]
    return [run_product_case(case) for case in cases]
