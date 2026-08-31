"""Out-of-tree H2 UCCSD CircuitIR export. Runs in the qchem venv; qagent/src must not import qchem."""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np


def _fail(message: str) -> int:
    print(json.dumps({"error": message}))
    return 1


def _hf_x_gates(amplitudes: list[Any], n_qubits: int) -> list[dict[str, Any]]:
    vec = np.asarray(amplitudes, dtype=np.complex128).ravel()
    if vec.size != 2**n_qubits:
        return []
    idx = int(np.argmax(np.abs(vec) ** 2))
    ops: list[dict[str, Any]] = []
    for qubit in range(n_qubits):
        if (idx >> qubit) & 1:
            ops.append({"kind": "gate", "name": "X", "qubits": [qubit], "params": []})
    return ops


def _as_qagent_gate(op: dict[str, Any]) -> dict[str, Any] | None:
    name = str(op.get("name") or "").upper()
    qubits = [int(q) for q in (op.get("qubits") or [])]
    raw = op.get("params")
    params: list[Any] = []
    if isinstance(raw, dict) and raw.get("theta") is not None:
        params = [float(raw["theta"])]
    elif isinstance(raw, (list, tuple)):
        params = [float(x) for x in raw]
    if name in {"INIT_STATEVECTOR", "UNITARY", "PAULI_ROTATION"}:
        return None
    if not name or not qubits:
        return None
    return {"kind": "gate", "name": name, "qubits": qubits, "params": params}


def export_h2_uccsd() -> dict[str, Any]:
    from qchem_stack.chem.bridges.mean_field_reference import ClassicalMeanFieldReference
    from qchem_stack.chem.molecular_system_config import molecular_system_from_experiment
    from qchem_stack.chem.pre_quantum_build import build_pre_quantum_input
    from qchem_stack.chem.solvers.registry import create_solver
    from qchem_stack.config import load_experiment_config
    from qchem_stack.config.scenarios import scenario_base_config_path
    from qchem_stack.quantum.algorithms.uccsd_circuit import UCCSDCircuitContext, uccsd_circuit_ir
    from qchem_stack.quantum.algorithms.uccsd_pauli_decomposition import pauli_rotation_elementary_ops

    cfg_path = scenario_base_config_path("uccsd_pauli")
    cfg = load_experiment_config(cfg_path)
    solver = create_solver(cfg)
    solver.set_physical_data(cfg)
    pack = solver.compute_mean_field(periodic=False)
    ref = ClassicalMeanFieldReference.from_mean_field_pack(
        pack,
        molecular_system=molecular_system_from_experiment(cfg),
    )
    qh = build_pre_quantum_input(cfg, ref).hamiltonian
    ctx = UCCSDCircuitContext.from_hamiltonian(qh, trotter_steps=None)
    n_qubits = int(qh.n_qubits)
    angles = np.full(len(ctx.antiherm_mats), 0.2, dtype=float)
    ir = uccsd_circuit_ir(angles, ctx, n_qubits=n_qubits, decomposition_mode="pauli")
    instructions: list[dict[str, Any]] = []
    for op in ir.operations:
        name = str(op.get("name") or "")
        if name == "INIT_STATEVECTOR":
            params = op.get("params") if isinstance(op.get("params"), dict) else {}
            instructions.extend(_hf_x_gates(list(params.get("amplitudes") or []), n_qubits))
            continue
        if name == "PAULI_ROTATION":
            params = op.get("params") if isinstance(op.get("params"), dict) else {}
            for elem in pauli_rotation_elementary_ops(
                str(params.get("pauli_string") or ""),
                float(params.get("phi") or 0.0),
            ):
                gate = _as_qagent_gate(elem)
                if gate:
                    instructions.append(gate)
            continue
        gate = _as_qagent_gate(op)
        if gate:
            instructions.append(gate)
    if n_qubits < 4 or not instructions:
        raise RuntimeError("qchem UCCSD export produced no H2 circuit")
    return {
        "ansatz": "uccsd",
        "molecule": "H2",
        "basis": "sto-3g",
        "mapping": str(ctx.mapping),
        "n_qubits": n_qubits,
        "n_instructions": len(instructions),
        "logical": {
            "n_qubits": n_qubits,
            "n_instructions": len(instructions),
            "body": {
                "schema_version": "3",
                "ir_kind": "logical",
                "n_qubits": n_qubits,
                "ansatz": "uccsd",
                "instructions": instructions,
            },
        },
    }


def main() -> int:
    try:
        print(json.dumps(export_h2_uccsd()))
        return 0
    except Exception as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
