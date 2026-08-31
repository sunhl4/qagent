"""I-03m: assignment.fork copies ELN without twin_id and records parent."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.eln import EVENT_ASSIGNMENT, EVENT_ESTIMATE, FIELD_PARENT_ASSIGNMENT_ID
from qagent.models.handles import HANDLE_TWIN
from qagent.services.assignment import create, fork
from qagent.services.eln import (
    append_b3,
    append_estimate,
    append_recipe_pin,
    append_twin_signoff,
    replay,
)

_NOTE = REPO / "docs" / "execution" / "I-03m_assignment_fork_eln.md"
_TWIN = "twin_from_qccd_rest"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")


@contextmanager
def isolated_stores() -> Iterator[None]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
    }
    handle, name = tempfile.mkstemp(prefix="i03m-asg-", suffix=".jsonl")
    os.close(handle)
    eln_handle, eln_name = tempfile.mkstemp(prefix="i03m-eln-", suffix=".jsonl")
    os.close(eln_handle)
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = name
    os.environ["QAGENT_ELN_FILE"] = eln_name
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        Path(name).unlink(missing_ok=True)
        Path(eln_name).unlink(missing_ok=True)


def _nested_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, inner in value.items():
            keys.add(str(key))
            keys.update(_nested_keys(inner))
    elif isinstance(value, list):
        for item in value:
            keys.update(_nested_keys(item))
    return keys


def test_assignment_fork_copies_eln_without_twin() -> None:
    with isolated_stores():
        src = create(
            brief="i03m",
            handles={"circuit_id": "circ_i03m", "asset_id": "asset_i03m", HANDLE_TWIN: _TWIN},
            sources=["qccd-twin"],
            columns={"makespan_ns": 3040, "b3": {"verdict": "inconclusive"}},
        )
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=src.assignment_id)
        append_estimate(makespan_ns=3040, assignment_id=src.assignment_id)
        append_twin_signoff(twin_id=_TWIN, shots_actual=32, assignment_id=src.assignment_id)
        append_b3(verdict="inconclusive", assignment_id=src.assignment_id)
        child = fork(src.assignment_id)
        assert child.assignment_id != src.assignment_id
        assert child.status == "draft"
        assert HANDLE_TWIN not in child.handles
        assert child.handles.get("circuit_id") == "circ_i03m"
        assert child.handles.get("asset_id") == "asset_i03m"
        face = child.face_payload()
        assert "handles" in face
        assert HANDLE_TWIN not in (face.get("handles") or {})
        assert face.get("status") == "draft"
        original = replay(src.assignment_id)
        assert any(row.get(HANDLE_TWIN) == _TWIN for row in original)
        copied = replay(child.assignment_id)
        assert HANDLE_TWIN not in _nested_keys(copied)
        assert _TWIN not in json.dumps(copied, ensure_ascii=False)
        assert any(row.get("type") == EVENT_ESTIMATE for row in copied)
        assert any(
            row.get("type") == EVENT_ASSIGNMENT
            and row.get(FIELD_PARENT_ASSIGNMENT_ID) == src.assignment_id
            for row in copied
        )
        print(
            f"fork parent={src.assignment_id} child={child.assignment_id} "
            f"eln_n={len(copied)} twin_in_child_handles={HANDLE_TWIN in child.handles}"
        )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "copy_events_for_fork" in text
    assert "twin_id" in text
    assert "parent_assignment_id" in text
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
        ("assignment_fork_copies_eln_without_twin", test_assignment_fork_copies_eln_without_twin),
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
