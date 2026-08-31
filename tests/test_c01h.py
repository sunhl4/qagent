"""C-01h: settings paints reserved_engines separately. Text on html/js only. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01h_reserved_face.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = (
    "G0 已通过",
    "G2 已通过",
    "G0 passed",
    "G2 passed",
    "Pennylane 已接线",
)
_SECRETS = ("hpc_secret", "llm_api_key", "quantum_secret")
_LINE = "${pack.label} · ${pack.kind} · ${pack.status}"


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def _welcome() -> str:
    return _read("app.js").split("function paintWelcome")[1].split("function fillSettings")[0]


def _fill() -> str:
    return _read("app.js").split("function fillSettings")[1].split("function typingInField")[0]


def test_html_has_reserved_list() -> None:
    html = _read("index.html")
    assert 'id="reserved-list"' in html
    assert 'id="engine-list"' in html
    engine_ul = html.split('id="engine-list"')[1].split("</ul>")[0]
    assert "reserved-list" not in engine_ul
    reserved_block = html.split('id="reserved-list"')[0]
    assert "未接线" in reserved_block or "reserved" in reserved_block.lower()
    assert "不是已接" in html or "尚未接线" in html or "未接线" in html


def test_fill_settings_paints_reserved_engines() -> None:
    fill = _fill()
    html = _read("index.html")
    assert 'id="reserved-list"' in html
    assert "$(\"reserved-list\")" in fill or "$('reserved-list')" in fill or '$("reserved-list")' in fill
    assert "(status.reserved_engines || []).forEach" in fill
    reserved_loop = fill.split("(status.reserved_engines || []).forEach")[1]
    assert "item.textContent" in reserved_loop
    assert _LINE in reserved_loop
    assert "pack.label" in reserved_loop
    assert "pack.kind" in reserved_loop
    assert "pack.status" in reserved_loop
    assert "innerHTML" not in reserved_loop


def test_welcome_stays_engines_only() -> None:
    welcome = _welcome()
    assert "reserved_engines" not in welcome
    assert "pennylane" not in welcome
    assert "reserved-list" not in welcome
    assert 'class="packs"' in welcome
    assert "(status.engines || []).forEach" in welcome
    pack_loop = welcome.split("(status.engines || []).forEach")[1]
    assert "item.textContent" in pack_loop
    assert "innerHTML" not in pack_loop
    assert _LINE in pack_loop
    assert "reserved" not in pack_loop


def test_engine_list_still_only_engines() -> None:
    fill = _fill()
    assert "(status.engines || []).forEach" in fill
    engine_loop = fill.split("(status.engines || []).forEach")[1].split(
        "(status.reserved_engines || []).forEach"
    )[0]
    assert "item.textContent" in engine_loop
    assert _LINE in engine_loop
    assert "reserved_engines" not in engine_loop
    assert "pennylane" not in engine_loop
    assert "pack.kind" in engine_loop
    assert 'id="engine-list"' in _read("index.html")


def test_keeps_c01g_line_and_c01e() -> None:
    html = _read("index.html")
    js = _read("app.js")
    welcome = _welcome()
    fill = _fill()
    boot = js.split("async function boot")[1]
    send_fn = js.split("async function send")[1].split("async function pollStatus")[0]
    public = js.split("function publicModelName")[1].split("function paintHealth")[0]
    health = js.split("function paintHealth")[1].split("function openSettingsDialog")[0]
    assert _LINE in welcome
    assert _LINE in fill
    assert 'id="engine-list"' in html
    assert 'class="packs"' in welcome
    assert 'id="settings"' in html
    assert 'id="secret-fieldset"' in html
    assert 'id="receipt-list"' in html
    assert 'id="health-line"' in html
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
    assert "llm_model" in public
    assert "health-line" in health
    for key in _SECRETS:
        assert key not in health
        assert key not in public
    assert "btn-twin" not in html
    assert "btn-twin" not in js


def test_keeps_eln_get_only() -> None:
    js = _read("app.js")
    html = _read("index.html")
    refresh = js.split("async function refreshInbox")[1].split("function addMessage")[0]
    boot = js.split("async function boot")[1]
    assert "/api/eln" in js
    assert "/api/eln" in refresh
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
    assert "GET /api/eln" in NOTE.read_text(encoding="utf-8")


def test_keeps_tenant_header() -> None:
    js = _read("app.js")
    token_fn = js.split("function token")[1].split("function role")[0]
    tenant_fn = js.split("function tenant")[1].split("function applyCustomerRole")[0]
    headers_fn = js.split("function headers")[1].split("function publicModelName")[0]
    assert 'get("tenant")' in token_fn
    assert "?tenant=" in token_fn
    assert "QAGENT_SHELL_TENANT" in token_fn
    assert "localStorage.setItem" in token_fn
    assert "history.replaceState" in token_fn
    assert "QAGENT_SHELL_TENANT" in tenant_fn
    assert "X-QAGENT-TENANT" in headers_fn
    assert "tenant()" in headers_fn
    assert 'out["X-QAGENT-TENANT"]' in headers_fn
    assert ".trim()" in tenant_fn
    assert 'out["X-QAGENT-TENANT"] = ""' not in js
    assert 'out["X-QAGENT-TENANT"] = tenantId' in headers_fn or 'out["X-QAGENT-TENANT"] = tenant()' in headers_fn


def test_refuses_to_claim_wired_or_g2() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01h" in text
    assert "reserved-list" in text
    assert "reserved_engines" in text
    assert "engine-list" in text
    assert "packs" in text
    assert "textContent" in text
    assert "showModal" in text
    assert "GET /api/eln" in text
    assert "?tenant=" in text
    assert "X-QAGENT-TENANT" in text
    assert "secret-fieldset" in text
    assert "不算接线" in text
    assert "不算 G2" in text
    assert "assignment_id" not in _read("index.html")


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
        ("html_has_reserved_list", test_html_has_reserved_list),
        ("fill_settings_paints_reserved_engines", test_fill_settings_paints_reserved_engines),
        ("welcome_stays_engines_only", test_welcome_stays_engines_only),
        ("engine_list_still_only_engines", test_engine_list_still_only_engines),
        ("keeps_c01g_line_and_c01e", test_keeps_c01g_line_and_c01e),
        ("keeps_eln_get_only", test_keeps_eln_get_only),
        ("keeps_tenant_header", test_keeps_tenant_header),
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
