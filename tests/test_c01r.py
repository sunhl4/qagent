"""C-01r: signed receipt forks via assignmentAction. Chat mux still send(批准)."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01r_receipt_fork.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _paint_face() -> str:
    return _js().split("function paintFaceRow")[1].split("function paintReceipts")[0]


def _action() -> str:
    return _js().split("function assignmentAction")[1].split("function paintInbox")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_signed_receipt_has_fork_action() -> None:
    js = _js()
    face = _paint_face()
    action = _action()
    assert "再走一遍" in face
    assert 'assignmentAction(row.assignment_id, "fork")' in face
    assert "下载回执" in face
    assert "核验" in face
    assert 'kind === "signed"' in face
    assert "不会带走 twin_id" in action
    assert 'verb === "fork"' in action
    assert "/approve" not in js
    assert "twin_id=" not in js
    assert "row.columns" not in face
    assert 'send("批准")' not in face


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "再走一遍" in text
    assert "fork" in text
    assert "不会带走 twin_id" in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert 'send("批准")' in text
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
        ("signed_receipt_has_fork_action", test_signed_receipt_has_fork_action),
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
