from __future__ import annotations

import os
from typing import Any, Mapping

from qagent.models.handles import HANDLE_TWIN

_FORBIDDEN_OUT = frozenset({"ok", HANDLE_TWIN, "signoff", "signed", "signature"})
_SUMMARY_KEYS = ("backend", "n_qubits", "n_instructions")
_DEFAULT_BACKEND = "mapqccd"
_ALT_BACKEND = "route-alt"


def _size(circuit: Mapping[str, Any]) -> tuple[int, int]:
    body = circuit.get("body") if isinstance(circuit.get("body"), dict) else {}
    n_qubits = int(circuit.get("n_qubits") or body.get("n_qubits") or 2)
    n_inst = int(
        circuit.get("n_instructions")
        or len(body.get("gates") or [])
        or len(body.get("instructions") or [])
        or 2
    )
    return max(n_qubits, 1), max(n_inst, 1)


def _public_estimate(
    makespan: float,
    *,
    backend: str,
    n_qubits: int,
    n_instructions: int,
) -> dict[str, Any]:
    summary = {
        "backend": backend,
        "n_qubits": n_qubits,
        "n_instructions": n_instructions,
    }
    payload = {
        "makespan_ns": float(makespan),
        "summary": {key: summary[key] for key in _SUMMARY_KEYS},
    }
    leaked = _FORBIDDEN_OUT & (set(payload) | set(payload["summary"]))
    if leaked:
        raise RuntimeError(f"compile_estimate leaked a signoff field: {sorted(leaked)}")
    return payload


def route_backend() -> str:
    return os.environ.get("QAGENT_ROUTE_BACKEND", _DEFAULT_BACKEND)


def mapqccd_estimate(args: Mapping[str, Any]) -> dict[str, Any]:
    circuit = args.get("circuit") if isinstance(args.get("circuit"), dict) else {}
    n_qubits, n_inst = _size(circuit)
    return _public_estimate(
        float(1200 * n_qubits * n_inst),
        backend=_DEFAULT_BACKEND,
        n_qubits=n_qubits,
        n_instructions=n_inst,
    )


def alt_estimate(args: Mapping[str, Any]) -> dict[str, Any]:
    circuit = args.get("circuit") if isinstance(args.get("circuit"), dict) else {}
    n_qubits, n_inst = _size(circuit)
    return _public_estimate(
        float(1500 * n_qubits * n_inst + 100),
        backend=_ALT_BACKEND,
        n_qubits=n_qubits,
        n_instructions=n_inst,
    )


class WiredRoute:
    """Same ionstack_compile_estimate schema. Swap via QAGENT_ROUTE_BACKEND."""

    def compile_estimate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if route_backend() not in {"", _DEFAULT_BACKEND}:
            return alt_estimate(args)
        return mapqccd_estimate(args)
