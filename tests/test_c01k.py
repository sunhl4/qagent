"""C-01k: inbox / receipt faceLabel eats reason. Text on js only. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01k_face_reason.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = (
    "G0 已通过",
    "G2 已通过",
    "G0 passed",
    "G2 passed",
    "Pennylane 已接线",
)


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _js() -> str:
    return _read("app.js")


def _between(start: str, end: str) -> str:
    return _js().split(start)[1].split(end)[0]


def _face_label() -> str:
    return _between("function faceLabel", "function signedTwinId")


def _paint_inbox() -> str:
    return _between("function paintInbox", "function receiptKey")


def _paint_face() -> str:
    return _between("function paintFaceRow", "function paintReceipts")


def _refresh() -> str:
    return _between("async function refreshInbox", "function addMessage")


def test_face_label_eats_reason() -> None:
    label = _face_label()
    assert "已取消" in label
    assert "已拒绝" in label
    assert "失败" in label
    assert "待批准" in label
    assert "已签收" in label
    assert "还在跑" in label
    assert "未签收" in label
    assert "reason" in label
    assert "已停" not in label
    assert 'return "needs_ask"' not in label
    assert label.index("cancelled") < label.index("已取消")
    assert label.index("rejected") < label.index("已拒绝")
    assert label.index("failed") < label.index("失败")
    assert label.index("needs_ask") < label.index("待批准")


def test_inbox_uses_face_label_not_raw_status() -> None:
    inbox = _paint_inbox()
    assert "statusEl.textContent = row.status" not in inbox
    assert "faceLabel" in inbox
    assert "statusEl.textContent = faceLabel" in inbox
    assert "row.reason" in inbox
    assert 'row.status === "needs_ask"' in inbox


def test_receipt_face_eats_reason() -> None:
    face = _paint_face()
    assert "faceLabel" in face
    assert "row.reason" in face
    assert "label.textContent = faceLabel" in face


def test_keeps_needs_ask_query_and_no_columns() -> None:
    js = _js()
    refresh = _refresh()
    assert "status=needs_ask" in js
    assert "status=needs_ask" in refresh
    assert "row.columns" not in js
    assert "ask.args" not in js
    assert "row.columns" not in _paint_inbox()
    assert "ask.args" not in _paint_inbox()
    assert "row.columns" not in _paint_face()
    assert "ask.args" not in _paint_face()
    assert 'send("批准")' in js
    assert "/approve" not in js


def test_refuses_to_claim_wired_or_g2() -> None:
    blob = _read("index.html") + _js() + _read("app.css") + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01k" in text
    assert "不算 G2" in text
    assert "吃 reason" in text
    assert "不算接线" in text
    assert "已取消" in text
    assert "待批准" in text
    assert "Pennylane 已接线" not in text


def test_no_rooms_or_finder_or_fourth_handle() -> None:
    js = _js()
    html = _read("index.html")
    blob = html + js + _read("app.css")
    for word in _ROOMS:
        assert word not in blob
    for word in _WALLS:
        assert word not in blob
    assert "ionstack_twin_run" not in js
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert "<select" not in html


def main() -> int:
    failed = 0
    for name, fn in (
        ("face_label_eats_reason", test_face_label_eats_reason),
        ("inbox_uses_face_label_not_raw_status", test_inbox_uses_face_label_not_raw_status),
        ("receipt_face_eats_reason", test_receipt_face_eats_reason),
        ("keeps_needs_ask_query_and_no_columns", test_keeps_needs_ask_query_and_no_columns),
        ("refuses_to_claim_wired_or_g2", test_refuses_to_claim_wired_or_g2),
        ("note_exists", test_note_exists),
        ("no_rooms_or_finder_or_fourth_handle", test_no_rooms_or_finder_or_fourth_handle),
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
