"""L1-03 relax2 note: remaining five-pack locks only. Does not mark Cirq wired."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
NOTE = REPO / "docs" / "execution" / "L1-03_relax2.md"

_MUST_NAME = (
    "test_invoke.py",
    "test_c03.py",
    "test_l104.py",
)

_REFUSED_CURRENT = (
    "Cirq 已接线",
    "engines 已含 cirq",
)

_REFUSE_MARKERS = (
    "拒绝",
    "不是当前",
    "不得写成当前",
    "未接线",
    "不是现状",
    "不算",
)


def _note() -> str:
    return NOTE.read_text(encoding="utf-8")


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE


def test_relax_only_not_wired() -> None:
    text = _note()
    assert "放松" in text
    assert "不算" in text
    assert "不标" in text and "L1-03 wired" in text
    assert "reserved" in text
    missing = [name for name in _MUST_NAME if name not in text]
    assert not missing, missing


def test_refuses_wired_as_current_state() -> None:
    text = _note()
    for phrase in _REFUSED_CURRENT:
        assert phrase in text, phrase
        lines = [line for line in text.splitlines() if phrase in line]
        assert lines, phrase
        for line in lines:
            assert any(marker in line for marker in _REFUSE_MARKERS), line


def test_does_not_claim_cirq_listed() -> None:
    text = _note()
    assert "不要读成" in text
    assert "cirq 已经在 engines" in text
    for line in text.splitlines():
        if "cirq 已经在 engines" in line:
            assert any(marker in line for marker in ("不要读成", "拒绝", "不算", "不是现状")), line


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_exists", test_note_exists),
        ("relax_only_not_wired", test_relax_only_not_wired),
        ("refuses_current_claims", test_refuses_wired_as_current_state),
        ("does_not_claim_listed", test_does_not_claim_cirq_listed),
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
