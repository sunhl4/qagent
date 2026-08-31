"""C-01i: preflight face paints checks only. Text on html/js only. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01i_preflight_face.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = (
    "G0 已通过",
    "G2 已通过",
    "G0 passed",
    "G2 passed",
    "Pennylane 已接线",
)
_LINE = "${pack.label} · ${pack.kind} · ${pack.status}"


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def _paint() -> str:
    return _read("app.js").split("function paintPreflight")[1].split("function loadPreflight")[0]


def _load() -> str:
    return _read("app.js").split("function loadPreflight")[1].split("function paintInbox")[0]


def _welcome() -> str:
    return _read("app.js").split("function paintWelcome")[1].split("function fillSettings")[0]


def _fill() -> str:
    return _read("app.js").split("function fillSettings")[1].split("function typingInField")[0]


def test_paint_preflight_draws_three_checks() -> None:
    paint = _paint()
    assert "has_asset" in paint
    assert "twin_live" in paint
    assert "has_circuit" in paint
    assert "textContent" in paint
    assert "Twin 已接通" in paint
    assert "Twin 未接通" in paint
    assert "有线路" in paint
    assert "还没有线路" in paint
    assert "有资产" in paint
    assert "还没有资产" in paint
    assert "innerHTML" not in paint
    assert "identity" not in paint


def test_js_never_reads_identity() -> None:
    js = _read("app.js")
    paint = _paint()
    load = _load()
    assert "data.identity" not in js
    assert ".identity" not in paint
    assert ".identity" not in load
    assert "data.identity" not in paint
    assert "data.identity" not in load
    assert "identity" not in load
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


def test_keeps_approve_and_assignments() -> None:
    js = _read("app.js")
    assert 'send("批准")' in js
    assert 'send("先不批")' in js
    assert "/api/assignments" in js
    assert "status=needs_ask" in js
    assert "/approve" not in js


def test_keeps_c01g_eln_tenant_secret() -> None:
    html = _read("index.html")
    js = _read("app.js")
    refresh = js.split("async function refreshInbox")[1].split("function addMessage")[0]
    token_fn = js.split("function token")[1].split("function role")[0]
    headers_fn = js.split("function headers")[1].split("function publicModelName")[0]
    assert _LINE in _welcome()
    assert _LINE in _fill()
    assert 'id="secret-fieldset"' in html
    assert 'id="engine-list"' in html
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
    assert "C-01i" in text
    assert "不算 G2" in text
    assert "不回显 identity" in text
    assert "has_asset" in text
    assert "twin_live" in text
    assert "has_circuit" in text
    assert "textContent" in text
    assert "reserved-list" in text
    assert "reserved_engines" in text
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
        ("paint_preflight_draws_three_checks", test_paint_preflight_draws_three_checks),
        ("js_never_reads_identity", test_js_never_reads_identity),
        ("keeps_reserved_list_and_welcome_only_engines", test_keeps_reserved_list_and_welcome_only_engines),
        ("keeps_approve_and_assignments", test_keeps_approve_and_assignments),
        ("keeps_c01g_eln_tenant_secret", test_keeps_c01g_eln_tenant_secret),
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
