"""C-01m: inbox 批准上机 posts assignment action. Chat mux still send(批准)."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01m_inbox_http_approve.md"
_JS = SHELL / "app.js"
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")


def _js() -> str:
    return _JS.read_text(encoding="utf-8")


def _paint_inbox() -> str:
    return _js().split("function paintInbox")[1].split("function receiptKey")[0]


def _paint_receipts() -> str:
    return _js().split("function paintReceipts")[1].split("const ELN_KIND_MAP")[0]


def _add_message() -> str:
    return _js().split("if (extras && extras.awaiting === \"approve\")")[1].split("function paintWelcome")[0]


def test_inbox_uses_assignment_action() -> None:
    js = _js()
    inbox = _paint_inbox()
    assert "function assignmentAction" in js
    assert 'assignmentAction(row.assignment_id, "approve")' in inbox
    assert 'assignmentAction(row.assignment_id, "cancel")' in inbox
    assert 'send("批准")' not in inbox
    assert 'send("先不批")' not in inbox
    assert "/api/assignments/" in js
    assert 'method: "POST"' in js
    assert "X-QAGENT-APPROVE-TOKEN" in js
    assert "/approve" not in js
    assert "twin_id=" not in js
    receipts = _paint_receipts()
    assert 'row.status === "signed"' in receipts
    assert "signed.concat(other)" in receipts


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "assignmentAction" in text
    assert "批准上机" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "G0 已通过" not in text
    assert "G2 已通过" not in text
    assert "send(\"批准\")" in text
    assert "不编" in text or "不伪造" in text
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
        ("inbox_uses_assignment_action", test_inbox_uses_assignment_action),
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
