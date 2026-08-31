"""I-03n: assignment invoke writes ELN rows tagged with assignment_id."""

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

from qagent.models.eln import EVENT_B3, EVENT_ESTIMATE, EVENT_RECIPE_PIN, EVENT_TWIN_SIGNOFF
from qagent.models.handles import HANDLE_TWIN
from qagent.services.assignment import approve, create, fork, run
from qagent.services.eln import replay
from qagent.services.invoke import invoke

_NOTE = REPO / "docs" / "execution" / "I-03n_invoke_eln_assignment.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_ENV = ("QAGENT_ASSIGNMENTS_FILE", "QAGENT_ELN_FILE")


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


def _types(assignment_id: str) -> set[str]:
    return {str(row.get("type") or "") for row in replay(assignment_id)}


def test_unapproved_run_tags_estimate() -> None:
    with isolated_asg_eln():
        row = create(room="lab", brief="i03n-ask", shots=8)
        ran = run(row.assignment_id, approved=False)
        events = replay(row.assignment_id)
        kinds = _types(row.assignment_id)
        assert ran.status == "needs_ask"
        assert EVENT_ESTIMATE in kinds
        assert EVENT_RECIPE_PIN in kinds
        assert all(row.get("assignment_id") == ran.assignment_id for row in events)
        blob = json.dumps(events, ensure_ascii=False)
        assert HANDLE_TWIN not in blob
        child = fork(ran.assignment_id)
        copied = replay(child.assignment_id)
        copied_kinds = {str(row.get("type") or "") for row in copied}
        assert EVENT_ESTIMATE in copied_kinds
        assert HANDLE_TWIN not in json.dumps(copied, ensure_ascii=False)
        print(
            f"unapproved assignment_id={ran.assignment_id} kinds={sorted(kinds)} "
            f"fork={child.assignment_id} copied={sorted(copied_kinds)}"
        )


def test_approved_run_tags_signoff_and_b3() -> None:
    with isolated_asg_eln():
        row = create(room="lab", brief="i03n-sign", shots=8)
        ran = run(row.assignment_id, approved=False)
        signed = approve(ran.assignment_id)
        assert signed.status == "signed"
        assert signed.handles.get(HANDLE_TWIN)
        kinds = _types(signed.assignment_id)
        assert EVENT_TWIN_SIGNOFF in kinds
        assert EVENT_B3 in kinds
        events = replay(signed.assignment_id)
        assert any(row.get(HANDLE_TWIN) == signed.handles[HANDLE_TWIN] for row in events)
        child = fork(signed.assignment_id)
        copied = replay(child.assignment_id)
        assert HANDLE_TWIN not in child.handles
        assert HANDLE_TWIN not in json.dumps(copied, ensure_ascii=False)
        assert EVENT_ESTIMATE in {str(row.get("type") or "") for row in copied}
        print(
            f"signed assignment_id={signed.assignment_id} kinds={sorted(kinds)} "
            f"fork={child.assignment_id} twin_in_child={HANDLE_TWIN in child.handles}"
        )


def test_invoke_without_assignment_stays_untagged() -> None:
    with isolated_asg_eln():
        from qagent.services.eln import read_eln

        invoke("qiskit_aer_run", "lab", {"circuit_id": "c1", "shots": 8, "claim_twin_id": True})
        blocked = [row for row in read_eln() if row.get("type") == "qagent/claim_blocked"]
        assert blocked
        assert all(not row.get("assignment_id") for row in blocked)


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "assignment_id" in text
    assert "invoke" in text
    assert "copy_events_for_fork" in text or "fork" in text
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
        ("unapproved_run_tags_estimate", test_unapproved_run_tags_estimate),
        ("approved_run_tags_signoff_and_b3", test_approved_run_tags_signoff_and_b3),
        ("invoke_without_assignment_stays_untagged", test_invoke_without_assignment_stays_untagged),
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
