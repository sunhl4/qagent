"""R-03g: live assignment approve signs only with TwinRun twin_id + qccd-twin."""

from __future__ import annotations

import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.assignment import SOURCE_TWIN, STATUS_FAILED, STATUS_NEEDS_ASK, STATUS_SIGNED
from qagent.models.handles import HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.services.assignment import approve, create, receipt, run

_LIVE_URL = "http://127.0.0.1:8765"
_DEAD_URL = "http://127.0.0.1:1"
_NOTE = REPO / "docs" / "execution" / "R-03g_live_receipt.md"
_STORE = ROOT / ".qagent" / "test-r03g-store"
_COPIED_TWIN = "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
_SOUTHBOUND = ("calibration", "cal", "shuttle", "ms_matrix")
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


def test_assignment_twin_args_are_pipeline() -> None:
    src = (ROOT / "src" / "qagent" / "services" / "assignment.py").read_text(encoding="utf-8")
    assert src.count('"mode": "pipeline"') == 3
    assert '"mode": "signoff"' not in src
    for leaked in ('"calibration"', '"shuttle"', '"ms_matrix"'):
        assert leaked not in src
    assert "import qdata" not in src
    assert "import ionstack" not in src


def test_unapproved_ask_is_pipeline() -> None:
    with isolated_assignment_env(_LIVE_URL):
        row = create(room="lab", brief="r03g-ask", shots=8)
        ran = run(row.assignment_id, approved=False)
        sealed = receipt(ran.assignment_id)
    assert ran.status == STATUS_NEEDS_ASK
    assert ran.ask_tool == "ionstack_twin_run"
    assert ran.ask and ran.ask.get("tool") == "ionstack_twin_run"
    args = ran.ask.get("args") or {}
    assert args.get("mode") == "pipeline"
    assert args.get("mode") != "signoff"
    assert HANDLE_TWIN not in ran.handles
    assert SOURCE_TWIN not in ran.sources
    assert sealed["signed"] is False
    print(f"unapproved ask mode={args.get('mode')} signed=false")


def test_live_approve_signs_receipt() -> None:
    with isolated_assignment_env(_LIVE_URL):
        assert os.environ.get("QAGENT_TWIN_URL") == _LIVE_URL
        row = create(room="lab", brief="r03g-live", shots=8)
        ran = run(row.assignment_id, approved=False)
        assert ran.status == STATUS_NEEDS_ASK, f"expected needs_ask, got {ran.status}: {ran.error}"
        done = approve(ran.assignment_id)
        sealed = receipt(done.assignment_id)
    assert done.status == STATUS_SIGNED, f"expected signed, got {done.status}: {done.error}"
    twin_id = str(done.handles.get(HANDLE_TWIN) or "").strip()
    assert twin_id, "no live assignment twin_id — R-03g is not done"
    assert SOURCE_TWIN in done.sources
    assert PROVENANCE_QCCD_TWIN in done.sources
    assert sealed["signed"] is True
    assert sealed["handles"].get(HANDLE_TWIN) == twin_id
    assert SOURCE_TWIN in sealed["sources"]
    print(
        f"live receipt signed=true twin_id={twin_id} sources={done.sources} "
        f"assignment_id={done.assignment_id}"
    )


def test_dead_url_approve_unsigned() -> None:
    with isolated_assignment_env(_DEAD_URL):
        row = create(room="lab", brief="r03g-dead", shots=8)
        ran = run(row.assignment_id, approved=False)
        assert ran.status == STATUS_NEEDS_ASK
        done = approve(ran.assignment_id)
        sealed = receipt(done.assignment_id)
    assert done.status == STATUS_FAILED
    assert HANDLE_TWIN not in done.handles
    assert SOURCE_TWIN not in done.sources
    assert sealed["signed"] is False
    assert HANDLE_TWIN not in (sealed.get("handles") or {})
    print(f"dead approve failed unsigned error={done.error!r}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_TWIN in text
    assert "qccd-twin" in text
    assert "signed" in text
    assert "pipeline" in text
    assert "approve" in text
    assert "ionstack_twin_run" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "G0 已通过" not in text
    assert "G2 已通过" not in text
    assert "signoff" in text
    assert "CAL" in text
    assert "不进工具" in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "诚实" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("assignment_twin_args_are_pipeline", test_assignment_twin_args_are_pipeline),
        ("unapproved_ask_is_pipeline", test_unapproved_ask_is_pipeline),
        ("live_approve_signs_receipt", test_live_approve_signs_receipt),
        ("dead_url_approve_unsigned", test_dead_url_approve_unsigned),
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
