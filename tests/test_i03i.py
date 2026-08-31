"""I-03i: ELN_EVENT_KINDS includes claim_blocked after the five. Fork still drops twin_id."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from qagent.models.eln import (  # noqa: E402
    ELN_EVENT_KINDS,
    EVENT_ASSIGNMENT,
    EVENT_B3,
    EVENT_CLAIM_BLOCKED,
    EVENT_ESTIMATE,
    EVENT_RECIPE_PIN,
    EVENT_TWIN_SIGNOFF,
)
from qagent.models.handles import HANDLE_TWIN  # noqa: E402
from qagent.services.eln import fork, replay  # noqa: E402
from test_i03 import (  # noqa: E402
    _AID,
    _FORK,
    _TWIN,
    _append_kinds,
    _nested_keys,
    isolated_eln,
    test_append_five_kinds,
    test_fork_drops_twin_and_records_parent,
)

_NOTE = ROOT / "docs" / "execution" / "I-03i_kinds.md"


def test_kinds_include_claim_blocked_after_five() -> None:
    assert ELN_EVENT_KINDS == (
        EVENT_RECIPE_PIN,
        EVENT_ESTIMATE,
        EVENT_TWIN_SIGNOFF,
        EVENT_B3,
        EVENT_ASSIGNMENT,
        EVENT_CLAIM_BLOCKED,
    )
    assert ELN_EVENT_KINDS[-1] == EVENT_CLAIM_BLOCKED
    assert EVENT_CLAIM_BLOCKED == "qagent/claim_blocked"


def test_replay_types_equal_kinds() -> None:
    test_append_five_kinds()
    with isolated_eln():
        written = _append_kinds(_AID)
        rows = replay(_AID)
        assert [row["type"] for row in rows] == list(ELN_EVENT_KINDS)
        assert [event.type for event in written] == list(ELN_EVENT_KINDS)
        assert EVENT_CLAIM_BLOCKED in ELN_EVENT_KINDS
        assert rows[-1]["type"] == EVENT_CLAIM_BLOCKED
        assert rows[-1]["reason"] == "aer_claim_twin_id"


def test_fork_still_drops_twin_id() -> None:
    test_fork_drops_twin_and_records_parent()
    with isolated_eln():
        _append_kinds(_AID)
        fork(_AID, _FORK, room="lab")
        forked = replay(_FORK)
        blob = json.dumps(forked, ensure_ascii=False)
        assert all(HANDLE_TWIN not in _nested_keys(row) for row in forked)
        assert _TWIN not in blob
        assert any(row.get("type") == EVENT_CLAIM_BLOCKED for row in forked)


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "ELN_EVENT_KINDS" in text
    assert "claim_blocked" in text
    assert "twin_id" in text
    assert "不算" in text and "G2" in text
    assert "不铸" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("kinds_include_claim_blocked_after_five", test_kinds_include_claim_blocked_after_five),
        ("replay_types_equal_kinds", test_replay_types_equal_kinds),
        ("fork_still_drops_twin_id", test_fork_still_drops_twin_id),
        ("note_exists", test_note_exists),
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
