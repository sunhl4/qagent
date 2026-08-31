"""I-03r: assignment ELN rows carry circuit_id/asset_id. No twin_id."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.eln import EVENT_ASSIGNMENT
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.assignment import create, run
from qagent.services.eln import replay

_NOTE = REPO / "docs" / "execution" / "I-03r_eln_assignment_handles.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_ENV = ("QAGENT_ASSIGNMENTS_FILE", "QAGENT_ELN_FILE")
SHELL = ROOT / "apps" / "customer-shell"


@contextmanager
def isolated_asg_eln() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV}
    tmp = tempfile.TemporaryDirectory()
    folder = Path(tmp.name)
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(folder / "assignments.json")
    os.environ["QAGENT_ELN_FILE"] = str(folder / "eln.jsonl")
    try:
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _paint() -> str:
    return _js().split("function paintEln")[1].split("async function refreshInbox")[0]


def test_run_writes_handles_without_twin() -> None:
    with isolated_asg_eln():
        row = create(room="lab", brief="i03r", shots=8)
        ran = run(row.assignment_id, approved=False)
        events = [item for item in replay(ran.assignment_id) if item.get("type") == EVENT_ASSIGNMENT]
        assert events
        last = events[-1]
        assert last.get(HANDLE_CIRCUIT)
        assert last.get(HANDLE_ASSET)
        blob = json.dumps(events, ensure_ascii=False)
        assert HANDLE_TWIN not in blob
        assert ran.handles.get(HANDLE_CIRCUIT) == last.get(HANDLE_CIRCUIT)
        print(
            f"assignment_id={ran.assignment_id} circuit_id={last.get(HANDLE_CIRCUIT)} "
            f"asset_id={last.get(HANDLE_ASSET)}"
        )


def test_eln_face_paints_handles_not_twin() -> None:
    js = _js()
    paint = _paint()
    assert "function elnCircuitId" in js
    assert "function elnAssetId" in js
    assert "row.circuit_id" in js
    assert "row.asset_id" in js
    assert "这份线路" in paint
    assert "已备好的数据" in paint
    assert "eln-circuit" in paint
    assert "eln-asset" in paint
    assert "twin_id" not in paint
    assert "row.columns" not in paint
    assert "qasm3" not in paint


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "circuit_id" in text
    assert "asset_id" in text
    assert "eln-circuit" in text
    assert "不算 G0" in text
    assert "未 commit" in text
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
        ("run_writes_handles_without_twin", test_run_writes_handles_without_twin),
        ("eln_face_paints_handles_not_twin", test_eln_face_paints_handles_not_twin),
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
