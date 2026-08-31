"""I-01n: assignment face carries makespan_ns after estimate. Not a handle."""

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

from qagent.models.assignment import Assignment, face_makespan_ns
from qagent.models.handles import HANDLE_TWIN
from qagent.services.assignment import create, run

_NOTE = REPO / "docs" / "execution" / "I-01n_face_makespan.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_COPIED = 4800
_FAT = ("columns", "identity", "counts", "circuit", "body", "qasm3", "args", "brief", "recipe")


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


def test_face_makespan_helper() -> None:
    assert face_makespan_ns(4800.0) == 4800
    assert face_makespan_ns("3040") == 3040
    assert face_makespan_ns(-1) is None
    assert face_makespan_ns(None) is None
    assert face_makespan_ns("nope") is None


def test_model_face_copies_makespan_not_columns() -> None:
    row = Assignment(
        assignment_id="asg_i01n_est",
        room="lab",
        brief="i01n",
        recipe="a2_chem_pes",
        shots=8,
        status="needs_ask",
        ask_tool="ionstack_twin_run",
        columns={"makespan_ns": 4800.0, "identity": {"preset": "t_junction"}, "counts": {"00": 1}},
        handles={"circuit_id": "circ_i01n", "asset_id": "asset_i01n"},
    )
    face = row.face_payload()
    assert face["makespan_ns"] == 4800
    assert "columns" not in face
    assert "identity" not in _keys(face)
    assert "counts" not in _keys(face)
    assert HANDLE_TWIN not in _keys(face)
    empty = Assignment(
        assignment_id="asg_i01n_empty",
        room="lab",
        brief="i01n-empty",
        recipe="a2_chem_pes",
        shots=8,
        status="draft",
    )
    assert "makespan_ns" not in empty.face_payload()


def test_service_run_face_has_estimate() -> None:
    row = create(room="lab", brief="i01n-run", shots=8)
    ran = run(row.assignment_id)
    assert ran.status == "needs_ask", ran.status
    face = ran.face_payload()
    assert face.get("status") == "needs_ask"
    assert face.get("makespan_ns") is not None, f"no makespan on face: {face}"
    assert int(face["makespan_ns"]) > 0
    assert "columns" not in face
    assert HANDLE_TWIN not in (face.get("handles") or {})
    print(f"service face makespan_ns={face['makespan_ns']} assignment_id={face['assignment_id']}")


def test_live_http_face_has_estimate() -> None:
    code, created = _call("POST", "/api/assignments", {"room": "lab", "brief": "i01n-http", "shots": 8})
    assert code == 200, created
    aid = created["assignment_id"]
    code, ran = _call("POST", f"/api/assignments/{aid}/run", {})
    assert code == 200, ran
    assert ran.get("status") == "needs_ask"
    assert ran.get("makespan_ns") is not None, f"HTTP run face missing makespan: {ran}"
    assert int(ran["makespan_ns"]) > 0
    for name in _FAT:
        assert name not in _keys(ran), name
    assert HANDLE_TWIN not in (ran.get("handles") or {})
    code, one = _call("GET", f"/api/assignments/{aid}")
    assert code == 200, one
    assert one.get("makespan_ns") == ran.get("makespan_ns")
    print(f"http face makespan_ns={ran['makespan_ns']} assignment_id={aid}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "makespan_ns" in text
    assert "face_payload" in text
    assert str(_COPIED) in text
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
        ("face_makespan_helper", test_face_makespan_helper),
        ("model_face_copies_makespan_not_columns", test_model_face_copies_makespan_not_columns),
        ("service_run_face_has_estimate", test_service_run_face_has_estimate),
        ("live_http_face_has_estimate", test_live_http_face_has_estimate),
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
