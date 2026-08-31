"""I-01p: assignment face carries aer_provenance. Never qccd-twin."""

from __future__ import annotations

import json
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.assignment import Assignment, face_aer_provenance
from qagent.models.handles import HANDLE_TWIN, PROVENANCE_AER, PROVENANCE_QCCD_TWIN

_NOTE = REPO / "docs" / "execution" / "I-01p_face_aer.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_COPIED = "asg_b281b611c8f6"
_FAT = ("columns", "identity", "counts", "circuit", "body", "qasm3", "args", "brief", "recipe")


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-QAGENT-DEBUG-TOKEN": _TOKEN,
        "X-QAGENT-APPROVE-TOKEN": _TOKEN,
    }


def _call(path: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(_FACE + path, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f"3080 not reachable ({path}): {exc}") from exc
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise AssertionError(f"3080 JSON must be an object: {raw!r}")
    return code, parsed


def _keys(obj: object) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(str(key))
            found.update(_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_keys(item))
    return found


def test_face_aer_helper() -> None:
    assert face_aer_provenance("aer") == PROVENANCE_AER
    assert face_aer_provenance("ibm") == "ibm"
    assert face_aer_provenance("cirq") == "cirq"
    assert face_aer_provenance(PROVENANCE_QCCD_TWIN) is None
    assert face_aer_provenance(None) is None
    assert face_aer_provenance("forged") is None


def test_model_face_copies_aer_not_twin_source() -> None:
    row = Assignment(
        assignment_id="asg_i01p_aer",
        room="lab",
        brief="i01p",
        recipe="a2_chem_pes",
        shots=8,
        status="signed",
        columns={
            "aer_provenance": "aer",
            "identity": {"preset": "t_junction"},
            "b3": {"verdict": "inconclusive"},
        },
        handles={"circuit_id": "circ_i01p", "asset_id": "asset_i01p", HANDLE_TWIN: "twin_from_qccd_rest"},
        sources=["aer", "qccd-twin"],
    )
    face = row.face_payload()
    assert face["aer_provenance"] == "aer"
    assert face.get("b3_verdict") == "inconclusive"
    assert "columns" not in face
    assert "identity" not in _keys(face)
    assert PROVENANCE_QCCD_TWIN not in str(face.get("aer_provenance"))
    empty = Assignment(
        assignment_id="asg_i01p_empty",
        room="lab",
        brief="i01p-empty",
        recipe="a2_chem_pes",
        shots=8,
        status="draft",
        columns={"aer_provenance": PROVENANCE_QCCD_TWIN},
    )
    assert "aer_provenance" not in empty.face_payload()


def test_live_http_signed_has_aer() -> None:
    code, one = _call(f"/api/assignments/{_COPIED}")
    assert code == 200, one
    assert one.get("status") == "signed", one
    assert one.get("aer_provenance") == "aer", one
    for name in _FAT:
        assert name not in _keys(one), name
    assert one.get("aer_provenance") != PROVENANCE_QCCD_TWIN
    print(f"http face aer_provenance={one['aer_provenance']} assignment_id={_COPIED}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "aer_provenance" in text
    assert "face_payload" in text
    assert _COPIED in text
    assert "aer" in text
    assert "qccd-twin" in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert "G0 已通过" not in text
    assert "G1 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("face_aer_helper", test_face_aer_helper),
        ("model_face_copies_aer_not_twin_source", test_model_face_copies_aer_not_twin_source),
        ("live_http_signed_has_aer", test_live_http_signed_has_aer),
        ("note_copies_hit", test_note_copies_hit),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
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
