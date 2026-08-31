"""I-03g: 3080 ELN rows paint a short reason. Text on html/js/css only. Does not claim G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "I-03g_eln_reason.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_SECRETS = ("hpc_secret", "llm_api_key", "quantum_secret")
_TYPES = ("recipe_pin", "estimate", "twin_signoff", "b3", "assignment", "claim_blocked")
_LINE = "${pack.label} · ${pack.kind} · ${pack.status}"


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def test_paint_short_reason() -> None:
    js = _read("app.js")
    css = _read("app.css")
    types = js.split("const ELN_KIND_MAP")[1].split("function elnType")[0]
    paint = js.split("function paintEln")[1].split("async function refreshInbox")[0]
    reason_fn = js.split("function elnReason")[1].split("function elnKey")[0]
    for name in _TYPES:
        assert name in types
    assert "qagent/claim_blocked" in types
    assert "claim_blocked" in types
    assert "row.reason" in reason_fn
    assert "row.payload.reason" in reason_fn
    assert "elnReason" in paint
    assert "eln-reason" in paint
    assert 'className = "eln-reason"' in paint
    assert "textContent" in paint
    assert "innerHTML" not in paint
    assert "slice(0, 40)" in paint
    assert ".eln-reason" in css
    for key in _SECRETS:
        assert key not in paint
        assert key not in types
        assert key not in reason_fn
    assert "qasm3" not in paint
    assert "row.body" not in paint
    assert ".body" not in paint
    assert "twin_id" not in paint
    assert "twin_id" not in types
    assert "twin_id" not in reason_fn


def test_get_eln_no_post() -> None:
    js = _read("app.js")
    html = _read("index.html")
    refresh = js.split("async function refreshInbox")[1].split("function addMessage")[0]
    boot = js.split("async function boot")[1]
    assert "/api/eln" in js
    assert "/api/eln" in refresh
    assert "GET" in refresh
    assert 'method: "GET"' in refresh
    assert 'fetch("/api/eln"' in refresh
    assert "headers()" in refresh
    assert "paintEln" in refresh
    assert "events" in refresh
    assert "POST" not in refresh
    assert 'fetch("/api/eln", { method: "POST"' not in js
    assert "POST /api/eln" not in js
    assert "refreshInbox()" in boot
    assert 'id="eln-face"' in html
    assert 'id="eln-list"' in html
    assert "assignment_id" not in html


def test_keeps_i03e() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    paint = js.split("function paintEln")[1].split("async function refreshInbox")[0]
    assert 'id="eln-face"' in html
    assert 'id="eln-list"' in html
    assert 'id="eln-empty"' in html
    assert "实验记录 / ELN" in html
    assert "还没有实验记录" in html
    assert html.index('id="receipt-face"') < html.index('id="eln-face"')
    assert "assignment_id" not in html
    assert "textContent" in paint
    assert "innerHTML" not in paint
    assert "elnType" in paint
    assert "elnAssignmentId" in paint
    assert "shortAssignmentId" in paint
    assert ".eln-face" in css
    assert ".eln-list" in css
    assert ".eln-empty" in css
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert "<select" not in html


def test_keeps_c01g() -> None:
    js = _read("app.js")
    html = _read("index.html")
    welcome = js.split("function paintWelcome")[1].split("function fillSettings")[0]
    fill = js.split("function fillSettings")[1].split("function typingInField")[0]
    assert 'class="packs"' in welcome
    assert 'id="engine-list"' in html
    assert "pack.kind" in welcome
    assert "pack.kind" in fill
    assert _LINE in welcome
    assert _LINE in fill
    pack_loop = welcome.split("(status.engines || []).forEach")[1]
    assert "item.textContent" in pack_loop
    assert "innerHTML" not in pack_loop
    assert "pack.label" in pack_loop
    assert "pack.kind" in pack_loop
    assert "pack.status" in pack_loop


def test_refuses_to_claim_g0_g2_pass() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "I-03g" in text
    assert "reason" in text
    assert "eln-reason" in text
    assert "claim_blocked" in text
    assert "GET /api/eln" in text
    assert "textContent" in text
    assert "40" in text
    assert "没有 POST" in text or "无 POST" in text
    assert "assignment_id" in text
    assert "不算" in text or "不是过门" in text
    assert "assignment_id" not in _read("index.html")


def test_no_rooms_or_finder() -> None:
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
        ("paint_short_reason", test_paint_short_reason),
        ("get_eln_no_post", test_get_eln_no_post),
        ("keeps_i03e", test_keeps_i03e),
        ("keeps_c01g", test_keeps_c01g),
        ("refuses_to_claim_g0_g2_pass", test_refuses_to_claim_g0_g2_pass),
        ("note_exists", test_note_exists),
        ("no_rooms_or_finder", test_no_rooms_or_finder),
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
