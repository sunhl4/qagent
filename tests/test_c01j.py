"""C-01j: inbox / receipt face does not read columns. Text on html/js only. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01j_face_row.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = (
    "G0 已通过",
    "G2 已通过",
    "G0 passed",
    "G2 passed",
    "Pennylane 已接线",
)
_FORBIDDEN = (
    "columns",
    "ask.args",
    ".brief",
    ".recipe",
    "row.columns",
    "row.brief",
    "row.recipe",
    "row.identity",
)
_LINE = "${pack.label} · ${pack.kind} · ${pack.status}"


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def _between(start: str, end: str) -> str:
    return _read("app.js").split(start)[1].split(end)[0]


def _ask_tool() -> str:
    return _between("function askTool", "function faceKind")


def _signed_twin() -> str:
    return _between("function signedTwinId", "function inboxKey")


def _inbox_key() -> str:
    return _between("function inboxKey", "function paintPreflight")


def _paint_preflight() -> str:
    return _between("function paintPreflight", "function loadPreflight")


def _load_preflight() -> str:
    return _between("function loadPreflight", "function paintInbox")


def _paint_inbox() -> str:
    return _between("function paintInbox", "function receiptKey")


def _receipt_key() -> str:
    return _between("function receiptKey", "function loadReceipt")


def _paint_face() -> str:
    return _between("function paintFaceRow", "function paintReceipts")


def _paint_receipts() -> str:
    return _between("function paintReceipts", "const ELN_KIND_MAP")


def _refresh() -> str:
    return _between("async function refreshInbox", "function addMessage")


def _welcome() -> str:
    return _between("function paintWelcome", "function fillSettings")


def _fill() -> str:
    return _between("function fillSettings", "function typingInField")


def _face() -> str:
    return "".join(
        (
            _ask_tool(),
            _signed_twin(),
            _inbox_key(),
            _paint_inbox(),
            _receipt_key(),
            _paint_face(),
            _paint_receipts(),
            _refresh(),
        )
    )


def test_inbox_face_slices_do_not_read_columns() -> None:
    face = _face()
    for token in _FORBIDDEN:
        assert token not in face, token
    assert "identity" not in _paint_inbox()
    assert "identity" not in _paint_face()
    assert "identity" not in _refresh()
    assert "ask.args" not in _ask_tool()
    assert "row.columns" not in _read("app.js")


def test_face_still_reads_ask_tool_and_handles() -> None:
    ask = _ask_tool()
    twin = _signed_twin()
    inbox = _paint_inbox()
    face = _paint_face()
    key = _inbox_key()
    receipt_key = _receipt_key()
    assert "askTool" in inbox
    assert "askTool" in key
    assert "row.ask.tool" in ask
    assert "row.ask_tool" in ask
    assert "assignment_id" in inbox
    assert "assignment_id" in face
    assert "assignment_id" in key
    assert "status" in inbox
    assert "status" in face
    assert "handles" in twin
    assert "handles.twin_id" in twin
    assert '!== "signed"' in twin
    assert twin.index('!== "signed"') < twin.index("handles.twin_id")
    assert "signedTwinId" in face
    assert "signedTwinId" in receipt_key
    assert "row.status" in face or "status" in face


def test_keeps_c01i_preflight_checks() -> None:
    paint = _paint_preflight()
    load = _load_preflight()
    js = _read("app.js")
    assert "has_asset" in paint
    assert "twin_live" in paint
    assert "has_circuit" in paint
    assert "textContent" in paint
    assert "identity" not in paint
    assert "identity" not in load
    assert "data.identity" not in js
    assert "data.checks" in load
    assert "paintPreflight" in load


def test_keeps_reserved_list_and_welcome_only_engines() -> None:
    html = _read("index.html")
    welcome = _welcome()
    fill = _fill()
    assert 'id="reserved-list"' in html
    assert "$(\"reserved-list\")" in fill or '$("reserved-list")' in fill
    assert "(status.reserved_engines || []).forEach" in fill
    assert "reserved_engines" not in welcome
    assert "pennylane" not in welcome
    assert "reserved-list" not in welcome
    assert "(status.engines || []).forEach" in welcome
    pack_loop = welcome.split("(status.engines || []).forEach")[1]
    assert "reserved" not in pack_loop
    assert _LINE in welcome
    assert _LINE in fill


def test_keeps_approve_eln_tenant_secret() -> None:
    html = _read("index.html")
    js = _read("app.js")
    refresh = _refresh()
    token_fn = _between("function token", "function role")
    headers_fn = _between("function headers", "function publicModelName")
    assert 'send("批准")' in js
    assert 'send("先不批")' in js
    assert "/api/assignments" in js
    assert "status=needs_ask" in js
    assert "/approve" not in js
    assert 'id="secret-fieldset"' in html
    assert 'method: "GET"' in refresh
    assert 'fetch("/api/eln"' in refresh
    assert "POST" not in refresh
    assert 'get("tenant")' in token_fn
    assert "?tenant=" in token_fn
    assert "X-QAGENT-TENANT" in headers_fn
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert "<select" not in html
    assert "assignment_id" not in html


def test_refuses_to_claim_wired_or_g2() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01j" in text
    assert "不算 G2" in text
    assert "不读 columns" in text
    assert "ask_tool" in text or "ask.tool" in text
    assert "assignment_id" in text
    assert "handles.twin_id" in text
    assert "reserved-list" in text
    assert "has_asset" in text
    assert "不算接线" in text
    assert "GET /api/eln" in text
    assert "secret-fieldset" in text


def test_no_rooms_or_finder_or_fourth_handle() -> None:
    blob = _blob()
    html = _read("index.html")
    js = _read("app.js")
    for word in _ROOMS:
        assert word not in blob
    for word in _WALLS:
        assert word not in blob
    assert "ionstack_twin_run" not in js
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert "/approve" not in js
    assert "<select" not in html
    assert "assignment_id" not in html


def main() -> int:
    failed = 0
    for name, fn in (
        ("inbox_face_slices_do_not_read_columns", test_inbox_face_slices_do_not_read_columns),
        ("face_still_reads_ask_tool_and_handles", test_face_still_reads_ask_tool_and_handles),
        ("keeps_c01i_preflight_checks", test_keeps_c01i_preflight_checks),
        ("keeps_reserved_list_and_welcome_only_engines", test_keeps_reserved_list_and_welcome_only_engines),
        ("keeps_approve_eln_tenant_secret", test_keeps_approve_eln_tenant_secret),
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
