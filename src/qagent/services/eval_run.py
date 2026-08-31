from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from qagent.adapters.contracts import load_eval_cases, load_tool_catalog
from qagent.models.gov import GOV_EVAL_IDS
from qagent.models.handles import HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.models.invoke import STATUS_ERROR, STATUS_OK, InvokeResult
from qagent.models.types import EvalCase
from qagent.services.invoke import invoke
from qagent.services.policy import decide

_MISSING = object()
DEFAULT_EVAL_IDS = tuple([*(f"E{i:02d}" for i in range(1, 22)), *GOV_EVAL_IDS])

DEFAULT_CIRCUIT = {
    "n_qubits": 2,
    "n_instructions": 2,
    "body": {
        "schema_version": "3",
        "ir_kind": "logical",
        "n_qubits": 2,
        "instructions": [
            {"kind": "gate", "name": "H", "qubits": [0], "params": []},
            {"kind": "gate", "name": "CX", "qubits": [0, 1], "params": []},
        ],
    },
}


@dataclass(frozen=True)
class EvalResult:
    id: str
    ok: bool
    detail: str = ""


def _path_get(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _args_for(case: EvalCase) -> dict[str, Any]:
    if case.invoke_args:
        return dict(case.invoke_args)
    return {}


def _result_for(
    case: EvalCase,
    assertion: dict[str, Any],
    results: dict[str, InvokeResult],
) -> InvokeResult:
    tool = assertion.get("tool") or case.invoke_tool
    if tool and tool in results:
        return results[tool]
    if "primary" in results:
        return results["primary"]
    if case.invoke_tool and case.invoke_tool in results:
        return results[case.invoke_tool]
    return next(iter(results.values()))


def _check(
    case: EvalCase,
    assertion: dict[str, Any],
    results: dict[str, InvokeResult],
    store: dict[str, Any],
) -> str | None:
    if assertion.get("tool_must_not_exist"):
        names = {spec.name for spec in load_tool_catalog()}
        leaked = [name for name in assertion["tool_must_not_exist"] if name in names]
        if leaked:
            return f"tools exist: {leaked}"
        for name in assertion["tool_must_not_exist"]:
            if decide(name, case.preset, {}) != "deny":
                return f"{name} was not denied"
        return None

    result = _result_for(case, assertion, results)
    payload = dict(result.payload or {})

    if "decision" in assertion and result.decision != assertion["decision"]:
        return f"decision {result.decision!r} != {assertion['decision']!r}"

    if assertion.get("engines_contain"):
        if result.status != "ok" or not result.payload:
            return f"list_engines status={result.status}"
        got = {row["id"] for row in result.payload["engines"]}
        missing = [name for name in assertion["engines_contain"] if name not in got]
        if missing:
            return f"missing engines {missing}"

    if assertion.get("error_contains"):
        text = f"{result.error or ''} {json.dumps(payload)}"
        if assertion["error_contains"] not in text:
            return f"error missing {assertion['error_contains']!r}"

    if assertion.get("twin_run_live_or_honest_error"):
        if result.status == STATUS_OK:
            twin_id = payload.get(HANDLE_TWIN)
            if not isinstance(twin_id, str) or not twin_id:
                return "live TwinRun missing twin_id"
            if not payload.get("counts"):
                return "live TwinRun missing counts"
            if payload.get("provenance") != PROVENANCE_QCCD_TWIN:
                return f"provenance {payload.get('provenance')!r}"
            return None
        if result.status == STATUS_ERROR:
            if HANDLE_TWIN in payload:
                return "error minted twin_id"
            return None
        return f"status {result.status!r} is not live TwinRun or honest error"

    if assertion.get("path"):
        value = _path_get(payload, assertion["path"])
        if value is _MISSING:
            return f"missing path {assertion['path']}"
        if "in" in assertion and value not in assertion["in"]:
            return f"{value!r} not in {assertion['in']}"
        if assertion.get("type") == "string" and not isinstance(value, str):
            return f"{assertion['path']} is not a string"
        if assertion.get("type") == "number" and not isinstance(value, (int, float)):
            return f"{assertion['path']} is not a number"
        if assertion.get("eq") is not None and value != assertion["eq"]:
            return f"{assertion['path']} {value!r} != {assertion['eq']!r}"
        if assertion.get("nonempty") and not value:
            return f"{assertion['path']} is empty"

    if assertion.get("absent_keys"):
        leaked = [key for key in assertion["absent_keys"] if key in payload]
        if leaked:
            return f"leaked keys {leaked}"

    if assertion.get("cannot_write"):
        verdict = _path_get(payload, "b3.verdict")
        unless = assertion.get("unless")
        unless_ok = bool(_path_get(payload, unless) is True) if unless else False
        if verdict == assertion["cannot_write"] and not unless_ok:
            return f"wrote {assertion['cannot_write']} without {unless}"

    if assertion.get("hits_contain"):
        blob = json.dumps(payload.get("hits") or [])
        missing = [needle for needle in assertion["hits_contain"] if needle not in blob]
        if missing:
            return f"hits missing {missing}"

    if "ok" in assertion and isinstance(assertion["ok"], bool):
        if payload.get("ok") != assertion["ok"]:
            return f"ok {payload.get('ok')!r} != {assertion['ok']!r}"

    if assertion.get("no_rest_call") and payload.get("rest_called"):
        return "sandbox made a REST call"

    if assertion.get("twin_id_must_differ_from"):
        other_key = str(assertion["twin_id_must_differ_from"])
        other = store.get(other_key) or store.get("E05")
        mine = payload.get("twin_id")
        if mine and mine == other:
            return f"twin_id copied from {other_key}"

    if assertion.get("tool_name") and result.tool != assertion["tool_name"]:
        return f"tool {result.tool!r} != {assertion['tool_name']!r}"

    if assertion.get("approval_item") and payload.get("approval_item") != assertion["approval_item"]:
        return f"approval_item {payload.get('approval_item')!r}"

    if assertion.get("no_diff_until_approved"):
        if payload.get("applied") or payload.get("diff"):
            return "diff applied before approval"

    if assertion.get("tests_green"):
        if payload.get("needs_app_server"):
            return "needs_app_server is not tests_green"
        if not payload.get("tests_green"):
            return "tests not green"

    if assertion.get("needs_app_server") and not payload.get("needs_app_server"):
        return "needs_app_server not set"

    if assertion.get("did_not_call"):
        called = payload.get("tools_called") or []
        if assertion["did_not_call"] in called:
            return f"called {assertion['did_not_call']}"

    if assertion.get("decide"):
        spec = assertion["decide"]
        got = decide(str(spec["tool"]), str(spec.get("preset") or case.preset), spec.get("args") or {})
        if got != spec.get("eq"):
            return f"decide {got!r} != {spec.get('eq')!r}"
        return None

    if assertion.get("witness"):
        from qagent.services.witness import first_finding

        spec = assertion["witness"]
        hit = first_finding(str(spec.get("tool") or ""), spec.get("payload") or {})
        must = spec.get("must_fail")
        if must and (hit is None or hit.kind != must):
            return f"witness {getattr(hit, 'kind', None)!r} != {must!r}"
        if spec.get("ok") and hit is not None:
            return f"witness {hit.kind}"
        return None

    if "handoff" in assertion:
        from qagent.services.handoff import HandoffError, create_handoff

        spec = assertion["handoff"]
        try:
            create_handoff(
                source_preset=case.preset,
                target_preset=case.preset,
                handles=spec.get("handles") or {},
                intent="eval",
            )
            if spec.get("ok") is False:
                return "handoff accepted extra keys"
        except HandoffError:
            if spec.get("ok", True):
                return "handoff rejected honest handles"
        return None

    if assertion.get("doctor_payload"):
        from qagent.services.doctor import probe

        report = probe(tool=result.tool, payload=payload, scan_store=False)
        if bool(report["ok"]) != bool(assertion["doctor_payload"].get("ok")):
            return f"doctor {report}"
        return None

    return None


def _twin_args(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"mode": "pipeline", "shots": 1000, "circuit": DEFAULT_CIRCUIT}
    if extra:
        body.update(extra)
    return body


def _scenario(case: EvalCase, store: dict[str, Any]) -> dict[str, InvokeResult]:
    preset = case.preset
    cid = case.id

    if cid == "E01":
        recipe = invoke("qdata_run_recipe", preset, {"name": "a2_spin_shadow"})
        dequant = invoke("qdata_dequant_gate", preset, {"asset_id": recipe.payload["asset_id"]})
        return {"primary": dequant, "qdata_run_recipe": recipe, "qdata_dequant_gate": dequant}

    if cid == "E02":
        recipe = invoke(
            "qdata_run_recipe",
            preset,
            {"name": "a2_chem_pes", "data_dir": tempfile.gettempdir()},
        )
        return {"primary": recipe, "qdata_run_recipe": recipe}

    if cid == "E03":
        submitted = invoke("qdata_submit_job", preset, {"kind": "shadow-predict", "payload": {}})
        job = invoke("qdata_get_job", preset, {"job_id": submitted.payload["job_id"]})
        return {"primary": job, "qdata_submit_job": submitted, "qdata_get_job": job}

    if cid == "E04":
        recipe = invoke("qdata_run_recipe", preset, {"name": "foo_bar"})
        return {"primary": recipe, "qdata_run_recipe": recipe}

    if cid == "E05":
        twin = invoke("ionstack_twin_run", preset, _twin_args(), approved=True)
        if twin.payload and twin.payload.get("twin_id"):
            store["E05"] = twin.payload["twin_id"]
            store["fork_source"] = twin.payload["twin_id"]
        return {"primary": twin, "ionstack_twin_run": twin}

    if cid == "E06":
        if "E05" not in store:
            _scenario(next(c for c in load_eval_cases() if c.id == "E05"), store)
        pinned = invoke(
            "qagent_pin_circuit",
            "lab",
            {"source": "logical", "logical": {"n_qubits": 2}, "asset_id": "e06"},
        )
        aer = invoke(
            "qiskit_aer_run",
            "lab",
            {"circuit_id": pinned.payload["circuit_id"], "shots": 128},
        )
        return {"primary": aer, "qiskit_aer_run": aer, "ionstack_twin_run": aer}

    if cid == "E09":
        recipe = invoke("qdata_run_recipe", preset, {"name": "qem_triad"})
        dequant = invoke("qdata_dequant_gate", preset, {"asset_id": recipe.payload["asset_id"]})
        return {"primary": dequant, "qdata_run_recipe": recipe, "qdata_dequant_gate": dequant}

    if cid == "E10":
        docs = invoke("qccd_docs_search", preset, {"query": "TwinRun circuit.body mode shots"})
        return {"primary": docs, "qccd_docs_search": docs}

    if cid == "E11":
        sandbox = invoke(
            "qdata_sandbox_exec",
            preset,
            {"code": "from ionstack.api.twin_run import execute_twin_run\nexecute_twin_run()"},
        )
        return {"primary": sandbox, "qdata_sandbox_exec": sandbox}

    if cid == "E12":
        estimate = invoke("ionstack_compile_estimate", preset, {"circuit": DEFAULT_CIRCUIT})
        return {"primary": estimate, "ionstack_compile_estimate": estimate}

    if cid == "E13":
        codex = invoke("subagent_codex", preset, {"task": "add a test ProblemProvider"})
        return {"primary": codex, "subagent_codex": codex}

    if cid == "E14":
        previous = os.environ.get("QAGENT_ROUTE_BACKEND")
        os.environ["QAGENT_ROUTE_BACKEND"] = "route-alt"
        try:
            estimate = invoke("ionstack_compile_estimate", preset, {"circuit": DEFAULT_CIRCUIT})
        finally:
            if previous is None:
                os.environ.pop("QAGENT_ROUTE_BACKEND", None)
            else:
                os.environ["QAGENT_ROUTE_BACKEND"] = previous
        return {"primary": estimate, "ionstack_compile_estimate": estimate}

    if cid == "E15":
        recipe = invoke("qdata_run_recipe", preset, {"name": "a2_chem_pes", "shots": 32})
        return {"primary": recipe, "qdata_run_recipe": recipe}

    if cid == "E17":
        attended = invoke("subagent_codex_attended", preset, {"task": "edit a file"})
        return {"primary": attended, "subagent_codex_attended": attended}

    if cid == "E18":
        if "fork_source" not in store:
            _scenario(next(c for c in load_eval_cases() if c.id == "E05"), store)
        pinned = invoke(
            "qagent_pin_circuit",
            "lab",
            {"source": "logical", "logical": {"n_qubits": 2}, "asset_id": "fork"},
        )
        aer = invoke(
            "qiskit_aer_run",
            "lab",
            {"circuit_id": pinned.payload["circuit_id"], "shots": 128},
        )
        return {"primary": aer, "qiskit_aer_run": aer, "ionstack_twin_run": aer}

    if cid == "E19":
        imported = invoke("qiskit_import_circuit", preset, {"qasm3": "OPENQASM 3.0; qubit[2] q;"})
        aer = invoke(
            "qiskit_aer_run",
            preset,
            {"circuit_id": imported.payload["circuit_id"], "shots": 1000},
        )
        return {"primary": aer, "qiskit_import_circuit": imported, "qiskit_aer_run": aer}

    if cid == "E21":
        chem = invoke("qchem_run", preset, {"scenario": "minimal_vqe"})
        pinned = invoke(
            "qagent_pin_circuit",
            preset,
            {"source": "qchem", "asset_id": chem.payload["asset_id"], "logical": {"n_qubits": 2}},
        )
        invoke("qiskit_export_circuit", preset, {"circuit_id": pinned.payload["circuit_id"]})
        invoke("ionstack_compile_estimate", preset, {"circuit": DEFAULT_CIRCUIT})
        twin = invoke("ionstack_twin_run", preset, _twin_args())
        return {
            "primary": pinned,
            "qchem_run": chem,
            "qagent_pin_circuit": pinned,
            "ionstack_twin_run": twin,
        }

    tool = case.invoke_tool or (case.allowed_tools[0] if case.allowed_tools else "")
    args = _args_for(case)
    result = invoke(tool, preset, args)
    return {"primary": result, tool: result}


def run_eval(case: EvalCase, store: dict[str, Any] | None = None) -> EvalResult:
    store = store if store is not None else {}
    results = _scenario(case, store)
    for assertion in case.assertions:
        detail = _check(case, assertion, results, store)
        if detail:
            return EvalResult(id=case.id, ok=False, detail=detail)
    return EvalResult(id=case.id, ok=True)


def run_evals(*ids: str) -> list[EvalResult]:
    wanted = set(ids)
    store: dict[str, Any] = {}
    out: list[EvalResult] = []
    for case in load_eval_cases():
        if wanted and case.id not in wanted:
            continue
        out.append(run_eval(case, store))
    return out
