from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT
from qagent.models.circuit_text import emit_qasm3, parse_qasm, program_filename
from qagent.models.handles import HANDLE_CIRCUIT

PIN_SOURCES = frozenset({"qchem", "qiskit", "qdata", "logical", "qasm3", "cirq"})
_NEED_BODY = frozenset({"qiskit", "qasm3", "logical", "cirq"})
_STORE = ROOT / ".qagent" / "circuit_pins.json"
_FORBIDDEN_OUT = frozenset({"qasm3", "body", "twin_id"})


def _store_path() -> Path:
    return _STORE


def _load() -> dict[str, Any]:
    path = _store_path()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _circuit_id(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "circ_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def get_pin(circuit_id: str) -> dict[str, Any] | None:
    stored = _load().get(circuit_id)
    return dict(stored) if isinstance(stored, dict) else None


def circuit_face(circuit_id: str) -> dict[str, Any] | None:
    """Face-only diagram payload. No qasm3 / body / twin_id."""
    stored = get_pin(circuit_id)
    if not stored:
        return None
    logical = stored.get("logical") if isinstance(stored.get("logical"), dict) else {}
    body = logical.get("body") if isinstance(logical.get("body"), dict) else {}
    raw = body.get("instructions") if isinstance(body.get("instructions"), list) else []
    gates: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        qubits = item.get("qubits") if isinstance(item.get("qubits"), list) else []
        if not name or not qubits:
            continue
        gates.append(
            {
                "name": name,
                "qubits": [int(q) for q in qubits],
                "params": list(item.get("params") or []),
            }
        )
    n_qubits = logical.get("n_qubits") or body.get("n_qubits")
    if not gates or not n_qubits:
        return None
    face = {
        HANDLE_CIRCUIT: circuit_id,
        "n_qubits": int(n_qubits),
        "n_instructions": len(gates),
        "ansatz": str(body.get("ansatz") or logical.get("ansatz") or ""),
        "gates": gates,
    }
    molecule = str(body.get("molecule") or logical.get("molecule") or "")
    if molecule:
        face["molecule"] = molecule
    return face


def circuit_program(circuit_id: str) -> dict[str, Any] | None:
    """Human/script download. qasm3 stays off the chat face."""
    stored = get_pin(circuit_id)
    if not stored:
        return None
    face = circuit_face(circuit_id)
    qasm3 = str(stored.get("qasm3") or "").strip()
    if not qasm3 and face:
        qasm3 = emit_qasm3(int(face["n_qubits"]), list(face.get("gates") or []))
    if not qasm3:
        return None
    n_qubits = (face or {}).get("n_qubits") or stored.get("n_qubits") or 0
    n_instructions = (face or {}).get("n_instructions") or 0
    ansatz = str((face or {}).get("ansatz") or "")
    molecule = str((face or {}).get("molecule") or "")
    return {
        HANDLE_CIRCUIT: circuit_id,
        "n_qubits": int(n_qubits) if n_qubits else 0,
        "n_instructions": int(n_instructions),
        "ansatz": ansatz,
        "molecule": molecule,
        "qasm3": qasm3,
        "filename": program_filename(ansatz, molecule),
    }


def pin_from_qasm(text: str) -> dict[str, Any]:
    """Customer upload. Stores qasm3 + parsed logical. No twin_id."""
    logical = parse_qasm(text)
    return NativePin().pin_circuit({"source": "qasm3", "qasm3": text, "logical": logical})


class NativePin:
    """Qagent-owned handle table. Does not import science packages."""

    def pin_circuit(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source = args.get("source")
        if source not in PIN_SOURCES:
            raise ValueError(f"unknown pin source {source!r}")
        has_body = bool(args.get("qasm3") or args.get("logical"))
        has_asset = bool(args.get("asset_id"))
        if source in _NEED_BODY and not has_body:
            raise ValueError(
                f"pin source={source} needs qasm3 or logical; asset_id is optional. "
                "pin needs qasm3, logical, or asset_id"
            )
        if not has_body and not has_asset:
            raise ValueError("pin needs qasm3, logical, or asset_id")
        logical = args.get("logical") if isinstance(args.get("logical"), dict) else {}
        record = {
            "source": source,
            "asset_id": args.get("asset_id"),
            "n_qubits": logical.get("n_qubits") if logical else None,
            "has_qasm3": bool(args.get("qasm3")),
            "has_logical": bool(logical),
        }
        circuit_id = _circuit_id(record | {"qasm3": args.get("qasm3"), "logical": logical})
        stored = dict(record)
        stored["qasm3"] = args.get("qasm3")
        stored["logical"] = logical or None
        pins = _load()
        pins[circuit_id] = stored
        _save(pins)
        out = {
            HANDLE_CIRCUIT: circuit_id,
            "source": source,
        }
        if record["n_qubits"] is not None:
            out["n_qubits"] = record["n_qubits"]
        if _FORBIDDEN_OUT & set(out):
            raise RuntimeError("pin leaked a forbidden key")
        return out
