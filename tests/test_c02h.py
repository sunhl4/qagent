"""C-02h: empty ?tenant= / ?role= clears staff face. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-02h_tenant_clear.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _js() -> str:
    return _read("app.js")


def _token_fn() -> str:
    return _js().split("function token")[1].split("function role")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_empty_tenant_query_clears_storage() -> None:
    token_fn = _token_fn()
    headers_fn = _js().split("function headers")[1].split("function publicModelName")[0]
    assert 'get("tenant")' in token_fn
    assert "?tenant=" in token_fn
    assert 'has("tenant")' in token_fn
    assert 'removeItem("QAGENT_SHELL_TENANT")' in token_fn
    assert "QAGENT_SHELL_TENANT" in token_fn
    assert "localStorage.setItem" in token_fn
    assert "history.replaceState" in token_fn
    assert "X-QAGENT-TENANT" in headers_fn
    assert 'out["X-QAGENT-TENANT"] = ""' not in _js()


def test_empty_role_query_clears_customer() -> None:
    token_fn = _token_fn()
    apply_fn = _js().split("function applyCustomerRole")[1].split("function headers")[0]
    assert 'get("role")' in token_fn
    assert 'has("role")' in token_fn
    assert 'removeItem("QAGENT_SHELL_ROLE")' in token_fn
    assert 'role() === "customer"' in apply_fn
    assert "secret-fieldset" in apply_fn


def test_keeps_inbox_http_and_chat_mux() -> None:
    js = _js()
    inbox = js.split("function paintInbox")[1].split("function receiptKey")[0]
    bubble = _add_message()
    assert 'assignmentAction(row.assignment_id, "approve")' in inbox
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "/approve" not in js
    assert "downloadSignedReceipt" in js
    assert "verifySignedReceipt" in js
    assert "/api/receipts/verify" in js
    assert "loadReceiptRaw" in js
    assert "res.text()" in js
    assert "JSON.stringify(payload)" not in js.split("function verifySignedReceipt")[1].split("function paintFaceRow")[0]
    receipts = js.split("function paintReceipts")[1].split("const ELN_KIND_MAP")[0]
    assert "signed.concat(other)" in receipts
    assert "receiptKey(painted)" in receipts
    assert "painted.length" in receipts


def test_no_rooms_or_finder() -> None:
    blob = _read("index.html") + _js() + _read("app.css")
    for word in _ROOMS:
        assert word not in blob
    for word in _WALLS:
        assert word not in blob
    assert "btn-twin" not in blob
    assert "tenant-select" not in blob
    assert "assignment_id" not in _read("index.html")


def test_refuses_to_claim_g0_g2_pass() -> None:
    blob = _read("index.html") + _js() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-02h" in text
    assert "?tenant=" in text
    assert "QAGENT_SHELL_TENANT" in text
    assert "removeItem" in text
    assert "空租户" in text or "不带头" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "G0 已通过" not in text
    assert "G2 已通过" not in text
    assert "send(\"批准\")" in text
    assert "未 commit" in text
    assert "不编" in text or "不伪造" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("empty_tenant_query_clears_storage", test_empty_tenant_query_clears_storage),
        ("empty_role_query_clears_customer", test_empty_role_query_clears_customer),
        ("keeps_inbox_http_and_chat_mux", test_keeps_inbox_http_and_chat_mux),
        ("no_rooms_or_finder", test_no_rooms_or_finder),
        ("refuses_to_claim_g0_g2_pass", test_refuses_to_claim_g0_g2_pass),
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
