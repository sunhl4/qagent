from __future__ import annotations

import os
from typing import Any, Mapping

from qagent.adapters.pin import get_pin
from qagent.adapters.route import alt_estimate, mapqccd_estimate
from qagent.adapters.support import try_http_json
from qagent.adapters.wrap import call_interop
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN, PROVENANCE_QCCD_TWIN

_FORBIDDEN_IN = frozenset({"calibration", "cal", "shuttle", "ms_matrix"})


def _reject_southbound(args: Mapping[str, Any]) -> None:
    leaked = _FORBIDDEN_IN & set(args)
    if leaked:
        raise ValueError(f"southbound keys are forbidden: {sorted(leaked)}")


def _as_circuit(logical: Mapping[str, Any]) -> dict[str, Any] | None:
    if logical.get("body"):
        return dict(logical)
    if logical.get("instructions"):
        n_qubits = logical.get("n_qubits")
        wrapped: dict[str, Any] = {"body": dict(logical)}
        if n_qubits is not None:
            wrapped["n_qubits"] = n_qubits
        return wrapped
    return None


def _body_of(circuit: Mapping[str, Any] | None) -> object:
    if not isinstance(circuit, dict):
        return None
    body = circuit.get("body")
    if isinstance(body, dict):
        return body
    if circuit.get("instructions"):
        return dict(circuit)
    return None


def _circuit(args: Mapping[str, Any]) -> dict[str, Any]:
    circuit = args.get("circuit")
    if isinstance(circuit, dict) and circuit.get("body"):
        return circuit
    circuit_id = str(args.get(HANDLE_CIRCUIT) or "").strip()
    if circuit_id:
        stored = get_pin(circuit_id) or {}
        logical = stored.get("logical")
        resolved = _as_circuit(logical) if isinstance(logical, dict) else None
        if resolved:
            return resolved
        raise ValueError("pinned circuit_id has no logical.body; will not fall back to H+CX")
    raise ValueError("circuit.body or circuit_id is required")


def _assert_circuit_identity(args: Mapping[str, Any], circuit: Mapping[str, Any]) -> None:
    """Refuse a swapped body under a pinned circuit_id. Body-only runs stay allowed."""
    circuit_id = args.get(HANDLE_CIRCUIT)
    if not circuit_id:
        return
    stored = get_pin(str(circuit_id))
    if stored is None:
        return
    expected = stored.get("logical")
    expected_body = _body_of(expected if isinstance(expected, dict) else None)
    if not expected_body:
        return
    if _body_of(circuit) != expected_body:
        raise ValueError(
            "circuit.body does not match circuit_id; resume must reuse the asked circuit"
        )


def route_backend() -> str:
    return os.environ.get("QAGENT_ROUTE_BACKEND", "mapqccd")


class WiredIonstack:
    """Live TwinRun REST only. Estimate may fall back to MapQccd."""

    def twin_identity(self, _args: Mapping[str, Any]) -> dict[str, Any]:
        live = try_http_json("GET", "/v1/twin/identity")
        if live:
            return {
                "preset": str(live.get("preset") or "t_junction"),
                "n_qubits": int(live.get("n_qubits") or 8),
                "live": True,
            }
        return {"preset": "t_junction", "n_qubits": 8, "live": False}

    def twin_run(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _reject_southbound(args)
        mode = str(args.get("mode") or "")
        if mode not in {"pipeline", "signoff"}:
            raise ValueError("mode must be pipeline or signoff")
        shots = int(args.get("shots") or 0)
        if shots < 1:
            raise ValueError("shots must be >= 1")
        circuit = _circuit(args)
        _assert_circuit_identity(args, circuit)
        body = {
            "mode": mode,
            "shots": shots,
            "circuit": circuit,
        }
        if args.get("seed") is not None:
            body["seed"] = args.get("seed")
        live = try_http_json("POST", "/v1/twin/run", body)
        if live and live.get(HANDLE_TWIN) and live.get("counts"):
            return {
                HANDLE_TWIN: str(live[HANDLE_TWIN]),
                "counts": live["counts"],
                "shots_actual": int(live.get("shots_actual") or shots),
                "provenance": PROVENANCE_QCCD_TWIN,
            }
        raise RuntimeError(
            "TwinRun REST did not return twin_id and counts; no local twin_id is minted"
        )

    def compile_estimate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _reject_southbound(args)
        resolved = dict(args)
        resolved["circuit"] = _circuit(args)
        if route_backend() not in {"", "mapqccd"}:
            payload = alt_estimate(resolved)
        else:
            live = call_interop("estimate", {"circuit": resolved["circuit"]})
            payload = live if live and "makespan_ns" in live and "ok" not in live else mapqccd_estimate(resolved)
        if "ok" in payload or HANDLE_TWIN in payload:
            raise RuntimeError("compile_estimate leaked a signoff field")
        return payload
