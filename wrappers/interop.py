"""Out-of-tree wrap of ionstack.interop. Invoked via subprocess; not imported by qagent src."""

from __future__ import annotations

import json
import sys
from typing import Any


def _ok(payload: dict[str, Any]) -> int:
    print(json.dumps(payload))
    return 0


def _fail(message: str) -> int:
    print(json.dumps({"error": message}))
    return 1


def import_circuit(args: dict[str, Any]) -> int:
    qasm = args.get("qasm3") or args.get("qasm2")
    if not qasm:
        return _fail("qasm3 required")
    from qiskit import QuantumCircuit

    from ionstack.interop.qiskit_import import quantum_circuit_to_native_circuit

    qc = QuantumCircuit.from_qasm_str(qasm) if "OPENQASM 2" in qasm else None
    if qc is None:
        try:
            qc = QuantumCircuit.from_qasm_str(qasm)
        except Exception:
            from qiskit.qasm3 import loads

            qc = loads(qasm)
    native = quantum_circuit_to_native_circuit(qc)
    return _ok({"n_qubits": native.n_qubits, "n_instructions": len(native.instructions), "backend": "ionstack.interop"})


def export_circuit(args: dict[str, Any]) -> int:
    from ionstack.device.qccd_presets import preset_t_junction
    from ionstack.interop.qiskit_export import logical_circuit_to_quantum_circuit
    from ionstack.ir.logical import LogicalCircuit

    body = args.get("body") or {}
    circuit = LogicalCircuit.from_json_dict(body) if body.get("ir_kind") == "logical" else LogicalCircuit(2).h(0).cx(0, 1)
    qc = logical_circuit_to_quantum_circuit(circuit, preset_t_junction(n=circuit.n_qubits).target)
    qasm3 = str(qc)
    return _ok({"qasm3": qasm3, "n_qubits": circuit.n_qubits, "backend": "ionstack.interop"})


def aer_run(args: dict[str, Any]) -> int:
    from ionstack.interop.aer_bridge import native_circuit_to_aer_job
    from ionstack.ir.native import NativeCircuit
    from ionstack.ir.base import Gate

    shots = int(args.get("shots") or 0)
    native = NativeCircuit(2)
    native.append(Gate(name="h", qubits=(0,), params=()))
    native.append(Gate(name="cx", qubits=(0, 1), params=()))
    job = native_circuit_to_aer_job(native, shots)
    result = job.result()
    counts = {str(k): int(v) for k, v in dict(result.get_counts()).items()}
    return _ok({"provenance": "aer", "counts": counts, "shots_actual": shots, "backend": "ionstack.interop"})


def compile_estimate(args: dict[str, Any]) -> int:
    from ionstack.api.runner import Runner
    from ionstack.device.native_gates import make_default_native_registry
    from ionstack.device.qccd_presets import preset_t_junction
    from ionstack.ir.logical import LogicalCircuit

    circuit_block = args.get("circuit") or {}
    body = circuit_block.get("body") if isinstance(circuit_block, dict) else {}
    if isinstance(body, dict) and body.get("ir_kind") == "logical":
        logical = LogicalCircuit.from_json_dict(body)
    else:
        logical = LogicalCircuit(2).h(0).cx(0, 1)
    preset = preset_t_junction(n=max(logical.n_qubits, 2))
    result = Runner(default_target=preset.target, native_registry=make_default_native_registry()).run_qccd_pipeline(
        logical, shots=0
    )
    makespan = float(result.makespan_ns or 0)
    return _ok({"makespan_ns": makespan, "summary": {"backend": "mapqccd", "n_qubits": logical.n_qubits}})


def main(argv: list[str] | None = None) -> int:
    raw = json.loads(sys.stdin.read() or "{}")
    action = str(raw.get("action") or "")
    args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
    try:
        if action == "import":
            return import_circuit(args)
        if action == "export":
            return export_circuit(args)
        if action == "aer":
            return aer_run(args)
        if action == "estimate":
            return compile_estimate(args)
        return _fail(f"unknown action {action!r}")
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
