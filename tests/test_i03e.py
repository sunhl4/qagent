"""I-03e: 3080 read-only ELN face. Text on html/js/css only. Does not claim G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "I-03e_eln_face.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_SECRETS = ("hpc_secret", "llm_api_key", "quantum_secret")
_TYPES = ("recipe_pin", "estimate", "twin_signoff", "b3", "assignment")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def test_eln_face_ids() -> None:
    html = _read("index.html")
    css = _read("app.css")
    assert 'id="eln-face"' in html
    assert 'id="eln-list"' in html
    assert 'id="eln-empty"' in html
    assert "实验记录 / ELN" in html
    assert "还没有实验记录" in html
    assert html.index('id="receipt-face"') < html.index('id="eln-face"')
    assert "assignment_id" not in html
    assert "recipe_pin" not in html
    assert "twin_id" not in html
    assert "<select" not in html
    assert "btn-twin" not in html
    assert ".eln-face" in css
    assert ".eln-list" in css
    assert ".eln-empty" in css


def test_get_eln_no_post() -> None:
    js = _read("app.js")
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


def test_paint_type_and_assignment_only() -> None:
    js = _read("app.js")
    types = js.split("const ELN_KIND_MAP")[1].split("function elnType")[0]
    paint = js.split("function paintEln")[1].split("async function refreshInbox")[0]
    aid = js.split("function elnAssignmentId")[1].split("function elnKey")[0]
    for name in _TYPES:
        assert name in types
    assert "textContent" in paint
    assert "innerHTML" not in paint
    assert "elnType" in paint
    assert "elnAssignmentId" in paint
    assert "assignment_id" in aid
    assert "shortAssignmentId" in paint
    for key in _SECRETS:
        assert key not in paint
        assert key not in types
        assert key not in aid
        assert key not in js.split("async function refreshInbox")[1].split("function addMessage")[0]
    assert "qasm3" not in paint
    assert "row.body" not in paint
    assert ".body" not in paint
    assert "twin_id" not in paint
    assert "twin_id" not in types
    assert "twin_id" not in aid


def test_refuses_to_claim_g0_g2_pass() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_keeps_c01e() -> None:
    html = _read("index.html")
    js = _read("app.js")
    boot = js.split("async function boot")[1]
    send_fn = js.split("async function send")[1].split("async function pollStatus")[0]
    assert 'id="settings"' in html
    assert 'id="secret-fieldset"' in html
    assert 'id="receipt-list"' in html
    assert 'id="health-line"' in html
    assert 'id="hpc_secret"' in html
    assert "showModal" in boot
    assert "!state.ready" in boot
    assert "open_settings" in send_fn
    assert "!state.ready" in send_fn
    assert "/api/assignments/" in js
    assert "/api/receipts/verify" in js
    assert "downloadSignedReceipt" in js
    assert "verifySignedReceipt" in js
    assert "applyCustomerRole" in js
    assert 'role() === "customer"' in js
    assert "ev.isComposing" in js
    assert '$("stage").setAttribute("aria-busy"' in js
    assert 'document.addEventListener("keydown"' not in js
    assert "btn-twin" not in html
    assert "btn-twin" not in js


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "I-03e" in text
    assert "GET /api/eln" in text
    assert "eln-face" in text
    assert "没有 POST" in text or "无 POST" in text
    assert "hpc_secret" in text or "密钥" in text
    assert "不算" in text or "不是过门" in text
    assert "assignment_id" in text


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


def main() -> int:
    failed = 0
    for name, fn in (
        ("eln_face_ids", test_eln_face_ids),
        ("get_eln_no_post", test_get_eln_no_post),
        ("paint_type_and_assignment_only", test_paint_type_and_assignment_only),
        ("refuses_to_claim_g0_g2_pass", test_refuses_to_claim_g0_g2_pass),
        ("keeps_c01e", test_keeps_c01e),
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
