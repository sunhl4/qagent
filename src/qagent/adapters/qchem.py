from __future__ import annotations

import json
import subprocess
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT
from qagent.adapters.homes import (
    qchem_bin,
    qchem_bin_requested,
    qchem_parity_bin,
    qchem_parity_bin_requested,
    qchem_python,
)
from qagent.adapters.pin import NativePin
from qagent.adapters.qdata import WiredQData, _db, _persist
from qagent.adapters.support import new_id
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN

_STRIP_FROM_SUMMARY = frozenset(
    {
        "pauli_terms",
        HANDLE_TWIN,
        HANDLE_CIRCUIT,
        "qasm",
        "qasm3",
        "circuit",
        "circuit_body",
    }
)
_SOURCE_LOCAL = "qagent-local-card"
_SOURCE_CLI = "qchem-cli"
_UCCSD_SCENARIOS = frozenset({"uccsd_pauli", "uccsd", "h2_uccsd"})
_CIRCUIT_WRAP = ROOT / "wrappers" / "qchem_circuit.py"


def _last_json_object(text: str) -> dict[str, Any]:
    """Take the last JSON object. Live qchem-run logs first, then the summary."""
    blob = (text or "").strip()
    if not blob:
        raise RuntimeError("qchem CLI did not print a JSON summary")
    try:
        parsed = json.loads(blob)
        if isinstance(parsed, dict):
            return parsed
        raise RuntimeError("qchem CLI summary must be an object")
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    last: dict[str, Any] | None = None
    idx = 0
    while True:
        start = blob.find("{", idx)
        if start < 0:
            break
        try:
            parsed, end = decoder.raw_decode(blob, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(parsed, dict):
            last = parsed
        idx = end
    if last is None:
        raise RuntimeError("qchem CLI did not print a JSON summary")
    return last


def _run_cli(exe: str, argv: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [exe, *argv],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"qchem CLI failed: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "qchem run failed").strip())
    return _last_json_object(proc.stdout or "")


def _payload_from_live(live: Mapping[str, Any]) -> dict[str, Any]:
    asset_id = str(live.get("experiment_id") or live.get(HANDLE_ASSET) or new_id("asset"))
    summary = {key: live[key] for key in live if key not in _STRIP_FROM_SUMMARY}
    summary["source"] = _SOURCE_CLI
    return {HANDLE_ASSET: asset_id, "summary": summary}


def _persist_live_card(
    args: Mapping[str, Any],
    payload: Mapping[str, Any],
    scenario: str,
) -> None:
    asset_id = str(payload.get(HANDLE_ASSET) or "")
    if not asset_id:
        return
    path, data = _db(args)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    recipe = str(summary.get("scenario") or scenario)
    data["assets"][asset_id] = {
        HANDLE_ASSET: asset_id,
        "recipe": recipe,
        "summary": dict(summary),
    }
    _persist(path, data)


def _export_uccsd_logical() -> dict[str, Any]:
    python = qchem_python()
    if not python or not _CIRCUIT_WRAP.is_file():
        raise RuntimeError("qchem UCCSD circuit wrap is not present")
    try:
        proc = subprocess.run(
            [python, str(_CIRCUIT_WRAP)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"qchem UCCSD wrap failed: {exc}") from exc
    live = _last_json_object(proc.stdout or "")
    if proc.returncode != 0 or live.get("error"):
        raise RuntimeError(str(live.get("error") or (proc.stderr or "qchem UCCSD wrap failed").strip()))
    logical = live.get("logical")
    if not isinstance(logical, dict) or not isinstance((logical.get("body") or {}).get("instructions"), list):
        raise RuntimeError("qchem UCCSD wrap did not return logical.body")
    return live


def _pin_uccsd(args: Mapping[str, Any], live: Mapping[str, Any], scenario: str) -> dict[str, Any]:
    asset_id = str(live.get("experiment_id") or live.get(HANDLE_ASSET) or new_id("asset"))
    logical = dict(live["logical"])
    pinned = NativePin().pin_circuit(
        {
            "source": "qchem",
            HANDLE_ASSET: asset_id,
            "logical": logical,
        }
    )
    payload = {
        HANDLE_ASSET: asset_id,
        HANDLE_CIRCUIT: pinned[HANDLE_CIRCUIT],
        "n_qubits": int(live.get("n_qubits") or logical.get("n_qubits") or 0),
        "summary": {
            "scenario": scenario,
            "ansatz": str(live.get("ansatz") or "uccsd"),
            "molecule": str(live.get("molecule") or "H2"),
            "basis": str(live.get("basis") or "sto-3g"),
            "mapping": str(live.get("mapping") or ""),
            "n_qubits": int(live.get("n_qubits") or 0),
            "n_instructions": int(live.get("n_instructions") or 0),
            "source": "qchem-uccsd",
        },
    }
    _persist_live_card(args, payload, scenario)
    return payload


class WiredQChem:
    """Wraps `qchem-run` / `qchem-export-parity` when present; honest local wrap if not."""

    def run(self, args: Mapping[str, Any]) -> dict[str, Any]:
        scenario = str(args.get("scenario") or "minimal_vqe")
        if scenario in _UCCSD_SCENARIOS:
            return _pin_uccsd(args, _export_uccsd_logical(), scenario)
        exe = qchem_bin()
        requested = qchem_bin_requested()
        if requested and not exe:
            raise RuntimeError(f"qchem CLI is not present ({requested})")
        if exe:
            payload = _payload_from_live(_run_cli(exe, ["--scenario", scenario, "--json-summary"]))
            _persist_live_card(args, payload, scenario)
            return payload
        created = WiredQData().run_recipe({"name": "a2_chem_pes", "params": {"scenario": scenario}})
        return {
            HANDLE_ASSET: created[HANDLE_ASSET],
            "summary": {
                "scenario": scenario,
                "backend": "local-wrap",
                "source": _SOURCE_LOCAL,
            },
        }

    def export_parity(self, args: Mapping[str, Any]) -> dict[str, Any]:
        asset_id = str(args.get("asset_id") or "")
        if not asset_id:
            raise ValueError("asset_id is required")
        exe = qchem_parity_bin()
        requested = qchem_parity_bin_requested()
        if requested and not exe:
            raise RuntimeError(f"qchem parity CLI is not present ({requested})")
        if exe:
            live = _run_cli(exe, ["--asset-id", asset_id])
            table_id = live.get("table_id")
            if not table_id:
                raise RuntimeError("qchem parity CLI did not return table_id")
            return {"table_id": str(table_id)}
        return {"table_id": new_id("parity")}
