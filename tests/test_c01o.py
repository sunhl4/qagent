"""C-01o: receipts paint B3; inbox/ELN keep the newest eight. Chat mux still send(批准)."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01o_receipt_b3.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _paint_inbox() -> str:
    return _js().split("function paintInbox")[1].split("function receiptKey")[0]


def _paint_face() -> str:
    return _js().split("function paintFaceRow")[1].split("function paintReceipts")[0]


def _paint_eln() -> str:
    return _js().split("function paintEln")[1].split("async function refreshInbox")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_receipt_paints_b3_not_columns() -> None:
    js = _js()
    face = _paint_face()
    inbox = _paint_inbox()
    eln = _paint_eln()
    assert "function faceB3Verdict" in js
    assert "row.b3_verdict" in js
    assert "B3 · " in face
    assert "receipt-b3" in face
    assert "尚无定论" in js
    assert "量子赢" in js
    assert "经典赢" in js
    assert "row.columns" not in face
    assert "row.columns" not in inbox
    assert "row.columns" not in eln
    assert "asks.slice(-8)" in inbox
    assert "shown.slice(-8)" in eln or "painted = shown.slice(-8)" in eln
    assert "/approve" not in js
    assert "twin_id=" not in js


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "B3 · " in text
    assert "b3_verdict" in text
    assert "尚无定论" in text
    assert "receipt-b3" in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert "send(\"批准\")" in text
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
        ("receipt_paints_b3_not_columns", test_receipt_paints_b3_not_columns),
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
