"""I-03q: unfiltered GET /api/eln collapses assignment status churn. Disk stays full."""

from __future__ import annotations

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

from qagent.entrypoints.shell_http import dispatch
from qagent.models.eln import EVENT_ASSIGNMENT, EVENT_ESTIMATE, EVENT_TWIN_SIGNOFF
from qagent.services.eln import (
    append_assignment,
    append_estimate,
    append_twin_signoff,
    collapse_assignment_events,
    read_eln,
)

_NOTE = REPO / "docs" / "execution" / "I-03q_eln_collapse.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_AID = "asg_i03q_keep"
_TWIN = "twin_from_qccd_rest"


@contextmanager
def isolated_eln() -> Iterator[Path]:
    previous = os.environ.get("QAGENT_ELN_FILE")
    handle, name = tempfile.mkstemp(prefix="i03q-eln-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    os.environ["QAGENT_ELN_FILE"] = str(path)
    try:
        yield path
    finally:
        if previous is None:
            os.environ.pop("QAGENT_ELN_FILE", None)
        else:
            os.environ["QAGENT_ELN_FILE"] = previous
        path.unlink(missing_ok=True)


def test_collapse_keeps_newest_assignment() -> None:
    rows = [
        {"type": EVENT_ASSIGNMENT, "assignment_id": _AID, "status": "draft"},
        {"type": EVENT_ESTIMATE, "assignment_id": _AID, "makespan_ns": 3040.0},
        {"type": EVENT_ASSIGNMENT, "assignment_id": _AID, "status": "running"},
        {"type": EVENT_ASSIGNMENT, "assignment_id": _AID, "status": "signed"},
        {"type": EVENT_TWIN_SIGNOFF, "assignment_id": _AID, "shots_actual": 8},
    ]
    out = collapse_assignment_events(rows)
    asg = [row for row in out if row.get("type") == EVENT_ASSIGNMENT]
    assert len(asg) == 1
    assert asg[0]["status"] == "signed"
    assert out[-1]["type"] == EVENT_TWIN_SIGNOFF
    assert "twin_id" not in str(out)


def test_http_unfiltered_collapses_assignment() -> None:
    with isolated_eln():
        append_assignment(assignment_id=_AID, status="draft", room="lab")
        append_assignment(assignment_id=_AID, status="running", room="lab")
        append_assignment(assignment_id=_AID, status="needs_ask", room="lab")
        append_estimate(makespan_ns=3040.0, assignment_id=_AID)
        append_assignment(assignment_id=_AID, status="signed", room="lab")
        append_twin_signoff(twin_id=_TWIN, shots_actual=8, assignment_id=_AID)
        disk = read_eln()
        assert sum(1 for row in disk if row.get("type") == EVENT_ASSIGNMENT) == 4
        code, payload = dispatch("GET", "/api/eln")
        assert code == 200
        events = payload["events"]
        asg = [row for row in events if row.get("type") == EVENT_ASSIGNMENT]
        assert len(asg) == 1, asg
        assert asg[0].get("status") == "signed"
        assert any(row.get("type") == EVENT_TWIN_SIGNOFF and row.get("shots_actual") == 8 for row in events)
        assert all("twin_id" not in row for row in events)
        filtered = dispatch("GET", f"/api/eln?assignment_id={_AID}")[1]["events"]
        assert sum(1 for row in filtered if row.get("type") == EVENT_ASSIGNMENT) == 4


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "collapse_assignment_events" in text
    assert "20" in text
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
        ("collapse_keeps_newest_assignment", test_collapse_keeps_newest_assignment),
        ("http_unfiltered_collapses_assignment", test_http_unfiltered_collapses_assignment),
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
