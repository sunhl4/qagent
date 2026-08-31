"""L1-03-wire: Cirq is listed and wired. No kernel import. Simulator has no twin_id."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_TWIN, PROVENANCE_CIRQ
from qagent.models.invoke import STATUS_DENIED
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.engines import list_engines
from qagent.services.invoke import invoke
from qagent.services.policy import decide
from qagent.services.ports import forbidden_import_roots

_HANDLE = "twin" + "_id"
_SRC = ROOT / "src"
_PKG = ROOT / "packages" / "qagent-cirq"
_NOTE = ROOT / "docs" / "execution" / "L1-03_wired.md"


def _src_and_pack_text() -> str:
    blobs: list[str] = []
    for root in (_SRC / "qagent", _PKG):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts"}:
                blobs.append(path.read_text(encoding="utf-8"))
    return "\n".join(blobs)


def test_list_engines_has_wired_cirq() -> None:
    packs = list_engines()
    ids = [pack.id for pack in packs]
    assert "cirq" in ids
    cirq = next(pack for pack in packs if pack.id == "cirq")
    assert cirq.status == "wired"
    assert cirq.kind == "interop"
    assert HANDLE_TWIN not in cirq.identity_fields
    invoked = invoke("qagent_list_engines", "lab", {})
    assert invoked.status == "ok"
    listed = [row["id"] for row in (invoked.payload or {}).get("engines") or []]
    assert "cirq" in listed
    row = next(item for item in invoked.payload["engines"] if item["id"] == "cirq")
    assert row["status"] == "wired"


def test_simulator_run_has_no_twin_id() -> None:
    result = invoke("cirq_simulator_run", "lab", {"circuit_id": "c1", "shots": 8})
    assert result.decision == "allow"
    assert result.status == "ok"
    payload = dict(result.payload or {})
    assert payload.get("provenance") == PROVENANCE_CIRQ
    assert HANDLE_TWIN not in payload
    assert _HANDLE not in json.dumps(payload)
    assert "counts" in payload


def test_claim_twin_id_denied() -> None:
    assert decide("cirq_simulator_run", "lab", {"circuit_id": "c1", "shots": 8, "claim_twin_id": True}) == "deny"
    result = invoke(
        "cirq_simulator_run",
        "lab",
        {"circuit_id": "c1", "shots": 8, "claim_twin_id": True},
    )
    assert result.decision == "deny"
    assert result.status == STATUS_DENIED
    payload = dict(result.payload or {})
    assert HANDLE_TWIN not in payload


def test_no_cirq_import() -> None:
    assert "cirq" in forbidden_import_roots()
    hits = scan_forbidden_imports()
    assert hits == [], hits
    text = _src_and_pack_text()
    assert "import cirq" not in text
    assert "from cirq " not in text
    assert "from cirq." not in text


def test_wire_note_exists() -> None:
    assert _NOTE.exists()
    text = _NOTE.read_text(encoding="utf-8")
    assert "Cirq 已接线" in text
    assert "engines 已含 cirq" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("listed_wired", test_list_engines_has_wired_cirq),
        ("simulator_no_twin", test_simulator_run_has_no_twin_id),
        ("claim_denied", test_claim_twin_id_denied),
        ("no_cirq_import", test_no_cirq_import),
        ("wire_note", test_wire_note_exists),
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
