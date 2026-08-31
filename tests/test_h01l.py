"""H-01l: H2 UCCSD pins a real circuit and the face can draw it. No H+CX fallback."""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.dsh_session import fold_history
from qagent.adapters.pin import NativePin, circuit_face
from qagent.adapters.qchem import WiredQChem
from qagent.entrypoints.shell_http import dispatch
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.invoke import invoke

NOTE = ROOT / "docs" / "execution" / "H-01l_h2_uccsd_circuit.md"
JS = ROOT / "apps" / "customer-shell" / "app.js"
QCHEM_TS = ROOT / "packages" / "qagent-qchem" / "src" / "index.ts"
ION = ROOT / "src" / "qagent" / "adapters" / "ionstack.py"
ASSIGNMENT = ROOT / "src" / "qagent" / "services" / "assignment.py"
SKILL = ROOT / "skills" / "h2-uccsd" / "SKILL.md"
VIBE = ROOT / "skills" / "vibe-across-engines" / "SKILL.md"
QCHEM_PY = ROOT / "src" / "qagent" / "adapters" / "qchem.py"
QCHEM_HOME = Path("/Users/shl/nvidia/qcchem-qml-md")
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_KNOWN = _HANDLES | {"rpc_id", "approval_id", "sessionId"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_FAKE_UCCSD = {
    "n_qubits": 4,
    "n_instructions": 2,
    "ansatz": "uccsd",
    "molecule": "H2",
    "basis": "sto-3g",
    "mapping": "jordan_wigner",
    "logical": {
        "n_qubits": 4,
        "body": {
            "schema_version": "3",
            "ir_kind": "logical",
            "n_qubits": 4,
            "ansatz": "uccsd",
            "instructions": [
                {"kind": "gate", "name": "X", "qubits": [2], "params": []},
                {"kind": "gate", "name": "X", "qubits": [3], "params": []},
            ],
        },
    },
}


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01l" in text
    assert "UCCSD" in text
    assert "circuit_id" in text
    assert "电路图" in text
    assert "uccsd_pauli" in text
    assert "不回退" in text or "will not fall back" in text
    assert "twin_id" in text
    assert "不算 G0" in text
    print("note names H2 UCCSD circuit face")


def test_face_draws_circuit_and_keeps_approve_literal() -> None:
    js = _text(JS)
    assert "批准上机" in js
    assert 'send("批准")' in js
    assert "/approve" not in js
    assert "ionstack_twin_run" not in js
    assert "/api/circuits/" in js
    assert "circuitMount" in js
    assert "drawCircuitSvg" in js
    assert "function circuitMount" in js
    print("face fetches circuit diagram; 批准上机 still in js")


def test_lab_is_told_uccsd_not_recipe_as_circuit() -> None:
    plugin = _text(QCHEM_TS)
    skill = _text(SKILL)
    vibe = _text(VIBE)
    vis_rows = json.loads(_text(ROOT / "profiles" / "qagent" / "skill-visibility.json"))["skills"]
    lab_ids = {row["id"] for row in vis_rows if "lab" in row["visible"]}
    assert "uccsd_pauli" in plugin
    assert "Do not TwinRun" in plugin or "do not TwinRun" in plugin
    assert "a2_chem_pes" in plugin
    assert "H2 UCCSD / circuit diagram" not in plugin
    assert "uccsd_pauli" in skill
    assert "a2_chem_pes" in skill
    assert "uccsd_pauli" in vibe
    assert "人没点名" in vibe
    assert "h2-uccsd" not in lab_ids
    print("uccsd_pauli stays a scenario; it is not the default lab prompt")


def test_uccsd_pauli_pins_four_qubits() -> None:
    with patch("qagent.adapters.qchem._export_uccsd_logical", return_value=_FAKE_UCCSD):
        port = WiredQChem().run({"scenario": "uccsd_pauli"})
        invoked = invoke("qchem_run", "lab", {"scenario": "uccsd_pauli"})
    assert port.get(HANDLE_ASSET)
    assert port.get(HANDLE_CIRCUIT)
    assert HANDLE_TWIN not in port
    assert int(port.get("n_qubits") or 0) == 4
    assert (port.get("summary") or {}).get("ansatz") == "uccsd"
    assert (port.get("summary") or {}).get("source") == "qchem-uccsd"
    assert invoked.status == "ok", invoked.error
    payload = dict(invoked.payload or {})
    circuit_id = str(payload.get(HANDLE_CIRCUIT) or "")
    assert circuit_id.startswith("circ_")
    assert HANDLE_TWIN not in payload
    face = circuit_face(circuit_id)
    assert face is not None
    assert face["n_qubits"] == 4
    assert face["gates"]
    assert "qasm3" not in face
    assert "body" not in face
    assert HANDLE_TWIN not in face
    print(f"uccsd_pauli pinned {circuit_id}")


def test_circuit_http_face() -> None:
    pinned = NativePin().pin_circuit(
        {
            "source": "logical",
            "logical": {
                "n_qubits": 4,
                "body": {
                    "schema_version": "3",
                    "ir_kind": "logical",
                    "n_qubits": 4,
                    "ansatz": "uccsd",
                    "instructions": [
                        {"kind": "gate", "name": "X", "qubits": [2], "params": []},
                        {"kind": "gate", "name": "CX", "qubits": [0, 1], "params": []},
                    ],
                },
            },
        }
    )
    circuit_id = pinned[HANDLE_CIRCUIT]
    code, row = dispatch("GET", f"/api/circuits/{circuit_id}")
    assert code == 200
    assert isinstance(row, dict)
    assert row[HANDLE_CIRCUIT] == circuit_id
    assert row["n_qubits"] == 4
    assert row["gates"]
    assert "qasm3" not in row
    assert "body" not in row
    assert HANDLE_TWIN not in row
    miss_code, miss = dispatch("GET", "/api/circuits/circ_deadbeefdead")
    assert miss_code == 404
    assert isinstance(miss, dict)
    assert miss.get("error") == "circuit not pinned"
    print("GET /api/circuits returns gates only")


def test_unknown_circuit_id_does_not_fallback() -> None:
    empty = invoke("ionstack_twin_run", "lab", {}, approved=True)
    fake = invoke(
        "ionstack_twin_run",
        "lab",
        {"mode": "pipeline", "shots": 8, HANDLE_CIRCUIT: "a2_chem_pes"},
        approved=True,
    )
    for got in (empty, fake):
        assert got.status != "ok"
        assert not (got.payload or {}).get(HANDLE_TWIN)
    err = (fake.error or "").lower()
    assert "fall back" in err or "logical.body" in err or "required" in err
    ion = _text(ION)
    assert "will not fall back to H+CX" in ion
    assert "_FALLBACK_CIRCUIT" not in ion
    print("unknown circuit_id does not mint twin_id")


def test_fold_history_exposes_circuit_for_face() -> None:
    snap = fold_history(
        {
            "events": [
                {
                    "event": {
                        "type": "tool/result",
                        "data": {
                            "message": {
                                "name": "qchem_run",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": (
                                            '{"asset_id":"asset_h01l","circuit_id":'
                                            '"circ_aaaaaaaaaaaa","n_qubits":4,'
                                            '"summary":{"ansatz":"uccsd"}}'
                                        ),
                                    }
                                ],
                            }
                        },
                    }
                }
            ]
        },
        session_id="session-h01l",
    )
    circuit = snap.get("circuit")
    assert isinstance(circuit, dict)
    assert circuit[HANDLE_CIRCUIT] == "circ_aaaaaaaaaaaa"
    assert circuit.get("n_qubits") == 4
    assert circuit.get("ansatz") == "uccsd"
    print("history fold carries circuit_id to the face")


def test_live_wrap_when_qchem_home() -> None:
    python = QCHEM_HOME / ".venv" / "bin" / "python"
    wrap = ROOT / "wrappers" / "qchem_circuit.py"
    assert python.is_file(), f"missing qchem python {python}"
    assert wrap.is_file(), f"missing wrap {wrap}"
    previous = {key: os.environ.get(key) for key in ("QAGENT_QCHEM_HOME", "QAGENT_QCHEM_PYTHON")}
    os.environ["QAGENT_QCHEM_HOME"] = str(QCHEM_HOME)
    os.environ.pop("QAGENT_QCHEM_PYTHON", None)
    try:
        invoked = invoke("qchem_run", "lab", {"scenario": "uccsd_pauli"})
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    assert invoked.status == "ok", invoked.error
    payload = dict(invoked.payload or {})
    assert payload.get(HANDLE_ASSET)
    circuit_id = str(payload.get(HANDLE_CIRCUIT) or "")
    assert circuit_id.startswith("circ_")
    assert int(payload.get("n_qubits") or 0) == 4
    assert HANDLE_TWIN not in payload
    face = circuit_face(circuit_id)
    assert face is not None
    assert face["n_qubits"] == 4
    assert face["n_instructions"] >= 4
    assert face.get("ansatz") == "uccsd"
    code, http = dispatch("GET", f"/api/circuits/{circuit_id}")
    assert code == 200
    assert isinstance(http, dict)
    assert len(http.get("gates") or []) >= 4
    print(f"live wrap circuit_id={circuit_id} gates={face['n_instructions']}")


def test_no_fourth_handle_or_src_qchem_import() -> None:
    for path in (NOTE, QCHEM_TS, SKILL):
        for match in _ID_RE.findall(_text(path)):
            assert match in _KNOWN, (path.name, match)
    assert _text(ASSIGNMENT).count('"mode": "pipeline"') == 3
    text = _text(QCHEM_PY)
    assert "import qchem" not in text
    assert "from qchem " not in text
    assert "from qchem." not in text
    hits = [row for row in scan_forbidden_imports() if "adapters/qchem.py" in row]
    assert hits == []
    print("still three handles; qagent/src does not import qchem")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("face_draws_circuit_and_keeps_approve_literal", test_face_draws_circuit_and_keeps_approve_literal),
        ("lab_is_told_uccsd_not_recipe_as_circuit", test_lab_is_told_uccsd_not_recipe_as_circuit),
        ("uccsd_pauli_pins_four_qubits", test_uccsd_pauli_pins_four_qubits),
        ("circuit_http_face", test_circuit_http_face),
        ("unknown_circuit_id_does_not_fallback", test_unknown_circuit_id_does_not_fallback),
        ("fold_history_exposes_circuit_for_face", test_fold_history_exposes_circuit_for_face),
        ("live_wrap_when_qchem_home", test_live_wrap_when_qchem_home),
        ("no_fourth_handle_or_src_qchem_import", test_no_fourth_handle_or_src_qchem_import),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
