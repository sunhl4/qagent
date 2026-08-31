"""C-02d: 3080 customer face sends tenant header. Text on html/js only. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-02d_tenant_face.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_SECRETS = ("hpc_secret", "llm_api_key", "quantum_secret")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def test_tenant_query_header_and_storage() -> None:
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


def test_empty_tenant_skips_header() -> None:
    js = _read("app.js")
    tenant_fn = js.split("function tenant")[1].split("function applyCustomerRole")[0]
    headers_fn = js.split("function headers")[1].split("function publicModelName")[0]
    assert '|| ""' in tenant_fn
    assert ".trim()" in tenant_fn
    assert "X-QAGENT-TENANT" in headers_fn
    before_assign = headers_fn.split('out["X-QAGENT-TENANT"]')[0]
    assert "if (" in before_assign
    assert "tenantId" in before_assign or "tenant()" in before_assign
    assert 'out["X-QAGENT-TENANT"] = ""' not in js
    assert 'out["X-QAGENT-TENANT"] = tenantId' in headers_fn or 'out["X-QAGENT-TENANT"] = tenant()' in headers_fn


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


def test_keeps_c01e() -> None:
    html = _read("index.html")
    js = _read("app.js")
    boot = js.split("async function boot")[1]
    send_fn = js.split("async function send")[1].split("async function pollStatus")[0]
    public = js.split("function publicModelName")[1].split("function paintHealth")[0]
    health = js.split("function paintHealth")[1].split("function openSettingsDialog")[0]
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
    assert "llm_model" in public
    assert "health-line" in health
    for key in _SECRETS:
        assert key not in health
        assert key not in public
    assert "btn-twin" not in html
    assert "btn-twin" not in js


def test_refuses_to_claim_g0_g2_pass() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-02d" in text
    assert "?tenant=" in text
    assert "X-QAGENT-TENANT" in text
    assert "QAGENT_SHELL_TENANT" in text
    assert "空租户" in text or "不带头" in text
    assert "GET /api/eln" in text
    assert "showModal" in text
    assert "secret-fieldset" in text or "role=customer" in text
    assert "不算" in text or "不是过门" in text
    assert "tenant_id" not in text or "不是句柄" in text


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
    assert "tenant-select" not in blob
    assert "assignment_id" not in html


def main() -> int:
    failed = 0
    for name, fn in (
        ("tenant_query_header_and_storage", test_tenant_query_header_and_storage),
        ("empty_tenant_skips_header", test_empty_tenant_skips_header),
        ("keeps_eln_get_only", test_keeps_eln_get_only),
        ("keeps_c01e", test_keeps_c01e),
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
