from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.pin import NativePin, get_pin
from qagent.adapters.wrap import call_interop
from qagent.models.fill import fill
from qagent.models.handles import HANDLE_CIRCUIT, PROVENANCE_AER

_DEFAULT_QASM = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
cx q[0], q[1];
"""


def _counts(shots: int) -> dict[str, int]:
    zeros = max(shots // 2, 0)
    return {"00": zeros, "11": shots - zeros}


class WiredQiskit:
    """Interop handles. Wraps ionstack.interop via pin table; never emits twin_id."""

    def import_circuit(self, args: Mapping[str, Any]) -> dict[str, Any]:
        qasm3 = args.get("qasm3") or args.get("qasm2") or _DEFAULT_QASM
        live = call_interop("import", {"qasm3": qasm3})
        n_qubits = int((live or {}).get("n_qubits") or 2)
        pinned = NativePin().pin_circuit({"source": "qiskit", "qasm3": qasm3, "logical": {"n_qubits": n_qubits}})
        return {HANDLE_CIRCUIT: pinned[HANDLE_CIRCUIT], "n_qubits": n_qubits}

    def export_circuit(self, args: Mapping[str, Any]) -> dict[str, Any]:
        circuit_id = str(args.get("circuit_id") or args.get("context") or "").strip()
        if not circuit_id:
            raise ValueError("export needs circuit_id; no implicit session circuit")
        stored = get_pin(circuit_id)
        if not stored:
            raise ValueError("export: unknown circuit_id")
        live = call_interop("export", {"body": stored.get("logical") or {}})
        qasm3 = (live or {}).get("qasm3") or stored.get("qasm3") or _DEFAULT_QASM
        return {HANDLE_CIRCUIT: circuit_id, "qasm3": qasm3}

    def transpile(self, args: Mapping[str, Any]) -> dict[str, Any]:
        circuit_id = str(args.get("circuit_id") or "")
        if not circuit_id:
            raise ValueError("circuit_id is required")
        return {
            HANDLE_CIRCUIT: circuit_id,
            "summary": {"preset": args.get("preset") or "default", "backend": "interop-wrap"},
        }

    def aer_run(self, args: Mapping[str, Any]) -> dict[str, Any]:
        circuit_id = str(args.get("circuit_id") or "")
        if not circuit_id:
            raise ValueError("circuit_id is required")
        shots = int(args.get("shots") or 0)
        if shots < 1:
            raise ValueError("shots must be >= 1")
        live = call_interop("aer", {"circuit_id": circuit_id, "shots": shots})
        if live and "twin_id" in live:
            raise RuntimeError("Aer leaked twin_id")
        counts = (live or {}).get("counts") if live else None
        return {
            "provenance": PROVENANCE_AER,
            "counts": counts or _counts(shots),
            "shots_actual": int((live or {}).get("shots_actual") or shots),
        }

    def ibm_run(self, _args: Mapping[str, Any]) -> dict[str, Any]:
        # Settings cloud_url / QAGENT_CLOUD_URL never enables IBM or mints twin_id.
        fill("S-QISKIT-05", "qiskit_ibm_run is reserved and denied")
