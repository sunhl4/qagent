"""I-01q: assignment face carries shots_actual after signoff. Receipts paint 实打."""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.assignment import Assignment, face_shots_actual
from qagent.models.handles import HANDLE_TWIN
from qagent.services.assignment import approve, create, receipt, run

_NOTE = REPO / "docs/execution/I-01q_face_shots.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_FAT = ("columns", "identity", "counts", "circuit", "body", "qasm3", "args", "brief", "recipe", "b3")
_STORE = ROOT / ".qagent" / "test-i01q-store"
_LIVE_URL = "http://127.0.0.1:8765"
_ENV_KEYS = (
    "QAGENT_TWIN_URL",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
    "QAGENT_ASSIGNMENTS_FILE",
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QCHEM_HOME",
    "QAGENT_IONSTACK_HOME",
)
SHELL = ROOT / "apps" / "customer-shell"


@contextmanager
def isolated_assignment_env(url: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_TWIN_URL"] = url
    os.environ["QAGENT_DATA_DIR"] = str(_STORE)
    os.environ["QAGENT_ELN_FILE"] = str(_STORE / "eln.jsonl")
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(_STORE / "assignments.json")
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


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


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _paint_face() -> str:
    return _js().split("function paintFaceRow")[1].split("function paintReceipts")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_face_shots_helper() -> None:
    assert face_shots_actual(8) == 8
    assert face_shots_actual("8") == 8
    assert face_shots_actual(8.0) == 8
    assert face_shots_actual(0) is None
    assert face_shots_actual(-1) is None
    assert face_shots_actual(None) is None
    assert face_shots_actual("") is None
    assert face_shots_actual("nope") is None


def test_model_face_copies_shots_not_columns() -> None:
    row = Assignment(
        assignment_id="asg_i01q_shots",
        room="lab",
        brief="i01q",
        recipe="a2_chem_pes",
        shots=8,
        status="signed",
        columns={
            "shots_actual": 8,
            "identity": {"preset": "t_junction"},
            "counts": {"00": 1},
            "b3": {"verdict": "inconclusive", "qem_contract_ok": False},
        },
        handles={"circuit_id": "circ_i01q", "asset_id": "asset_i01q", HANDLE_TWIN: "twin_from_qccd_rest"},
        sources=["qccd-twin"],
    )
    face = row.face_payload()
    assert face["shots_actual"] == 8
    assert "columns" not in face
    assert "counts" not in _keys(face)
    assert "identity" not in _keys(face)
    assert "b3" not in face
    empty = Assignment(
        assignment_id="asg_i01q_empty",
        room="lab",
        brief="i01q-empty",
        recipe="a2_chem_pes",
        shots=8,
        status="draft",
    )
    assert "shots_actual" not in empty.face_payload()
    asking = Assignment(
        assignment_id="asg_i01q_ask",
        room="lab",
        brief="i01q-ask",
        recipe="a2_chem_pes",
        shots=8,
        status="needs_ask",
        columns={"shots_actual": 8},
    )
    assert "shots_actual" not in asking.face_payload()


def test_live_approve_face_has_shots() -> None:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    with isolated_assignment_env(_LIVE_URL):
        row = create(room="lab", brief="i01q-live", shots=8)
        ran = run(row.assignment_id, approved=False)
        assert ran.status == "needs_ask", f"expected needs_ask, got {ran.status}: {ran.error}"
        assert "shots_actual" not in ran.face_payload()
        done = approve(ran.assignment_id)
        face = done.face_payload()
        sealed = receipt(done.assignment_id)
    assert done.status == "signed", f"expected signed, got {done.status}: {done.error}"
    assert face.get("shots_actual") == 8, face
    assert "columns" not in face
    for name in _FAT:
        assert name not in _keys(face), name
    assert "shots_actual" not in sealed
    twin_id = str((face.get("handles") or {}).get(HANDLE_TWIN) or "").strip()
    assert twin_id, "signed face must keep handles.twin_id"
    print(f"isolated face shots_actual={face['shots_actual']} assignment_id={done.assignment_id}")


def test_live_http_signed_has_shots() -> None:
    code, listing = _call("GET", "/api/assignments?status=signed")
    assert code == 200, listing
    rows = listing.get("assignments") or listing.get("items") or []
    if not isinstance(rows, list):
        rows = []
    found: dict[str, Any] | None = None
    for row in reversed(rows):
        if isinstance(row, dict) and face_shots_actual(row.get("shots_actual")) is not None:
            found = row
            break
    if found is None:
        code, created = _call("POST", "/api/assignments", {"room": "lab", "brief": "i01q-http", "shots": 8})
        assert code == 200, created
        aid = str(created.get("assignment_id") or "")
        assert aid, created
        code, ran = _call("POST", f"/api/assignments/{aid}/run", {})
        assert code == 200, ran
        assert ran.get("status") == "needs_ask", ran
        code, found = _call("POST", f"/api/assignments/{aid}/approve", {})
        assert code == 200, found
    assert found is not None
    assert found.get("status") == "signed", found
    shots = face_shots_actual(found.get("shots_actual"))
    assert shots == 8, found
    for name in _FAT:
        assert name not in _keys(found), name
    print(f"http face shots_actual={shots} assignment_id={found.get('assignment_id')}")


def test_receipt_paints_shots_not_columns() -> None:
    js = _js()
    face = _paint_face()
    assert "function faceShots" in js
    assert "row.shots_actual" in js
    assert "实打 · " in face
    assert "receipt-shots" in face
    assert "eln-shots" not in face
    assert "row.columns" not in face
    assert "faceShots" in js.split("function receiptKey")[1].split("function loadReceipt")[0]
    assert "/approve" not in js
    assert "twin_id=" not in js


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "shots_actual" in text
    assert "face_payload" in text
    assert "实打 · " in text
    assert "receipt-shots" in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert 'send("批准")' in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "columns" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("face_shots_helper", test_face_shots_helper),
        ("model_face_copies_shots_not_columns", test_model_face_copies_shots_not_columns),
        ("live_approve_face_has_shots", test_live_approve_face_has_shots),
        ("live_http_signed_has_shots", test_live_http_signed_has_shots),
        ("receipt_paints_shots_not_columns", test_receipt_paints_shots_not_columns),
        ("chat_bubble_still_sends_approve", test_chat_bubble_still_sends_approve),
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
    if _STORE.exists():
        shutil.rmtree(_STORE)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
