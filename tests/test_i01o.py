"""I-01o: assignment face carries b3_verdict after signoff. Not a handle."""

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

from qagent.models.assignment import Assignment, face_b3_verdict
from qagent.models.handles import HANDLE_TWIN

_NOTE = REPO / "docs" / "execution" / "I-01o_face_b3.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_COPIED = "asg_b281b611c8f6"
_VERDICT = "inconclusive"
_FAT = ("columns", "identity", "counts", "circuit", "body", "qasm3", "args", "brief", "recipe", "b3")


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-QAGENT-DEBUG-TOKEN": _TOKEN,
        "X-QAGENT-APPROVE-TOKEN": _TOKEN,
    }


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(_FACE + path, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
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


def test_face_b3_helper() -> None:
    assert face_b3_verdict({"verdict": "inconclusive", "qem_contract_ok": False}) == "inconclusive"
    assert face_b3_verdict("quantum_wins") == "quantum_wins"
    assert face_b3_verdict("classical_wins") == "classical_wins"
    assert face_b3_verdict("nope") is None
    assert face_b3_verdict(None) is None
    assert face_b3_verdict({"verdict": "forged"}) is None


def test_model_face_copies_verdict_not_columns() -> None:
    row = Assignment(
        assignment_id="asg_i01o_b3",
        room="lab",
        brief="i01o",
        recipe="a2_chem_pes",
        shots=8,
        status="signed",
        columns={
            "b3": {"verdict": "inconclusive", "qem_contract_ok": False},
            "identity": {"preset": "t_junction"},
            "counts": {"00": 1},
        },
        handles={"circuit_id": "circ_i01o", "asset_id": "asset_i01o", HANDLE_TWIN: "twin_from_qccd_rest"},
        sources=["qccd-twin"],
    )
    face = row.face_payload()
    assert face["b3_verdict"] == "inconclusive"
    assert "b3" not in face
    assert "columns" not in face
    assert "qem_contract_ok" not in _keys(face)
    assert "identity" not in _keys(face)
    empty = Assignment(
        assignment_id="asg_i01o_empty",
        room="lab",
        brief="i01o-empty",
        recipe="a2_chem_pes",
        shots=8,
        status="draft",
    )
    assert "b3_verdict" not in empty.face_payload()


def test_live_http_signed_has_verdict() -> None:
    code, one = _call("GET", f"/api/assignments/{_COPIED}")
    assert code == 200, one
    assert one.get("status") == "signed", one
    assert one.get("b3_verdict") == _VERDICT, one
    for name in _FAT:
        assert name not in _keys(one), name
    print(f"http face b3_verdict={one['b3_verdict']} assignment_id={_COPIED}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "b3_verdict" in text
    assert "face_payload" in text
    assert _COPIED in text
    assert _VERDICT in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert "G0 已通过" not in text
    assert "G1 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "columns" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("face_b3_helper", test_face_b3_helper),
        ("model_face_copies_verdict_not_columns", test_model_face_copies_verdict_not_columns),
        ("live_http_signed_has_verdict", test_live_http_signed_has_verdict),
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
