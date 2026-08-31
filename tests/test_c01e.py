"""C-01e: G0/G2 face leftovers. Text on html/js only. Does not claim G0/G2 pass."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01e_g2_face.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_SECRETS = ("hpc_secret", "llm_api_key", "quantum_secret")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def test_boot_opens_settings_when_not_ready() -> None:
    html = _read("index.html")
    js = _read("app.js")
    boot = js.split("async function boot")[1]
    assert 'id="settings"' in html
    assert "<dialog" in html
    assert "showModal" in boot
    assert "ready" in boot
    assert "!state.ready" in boot
    assert '$("settings").showModal()' in boot
    assert "open_settings" in js
    send_fn = js.split("async function send")[1].split("async function pollStatus")[0]
    assert "open_settings" in send_fn
    assert "showModal" in send_fn or "openSettingsDialog" in send_fn
    assert "!state.ready" in send_fn


def test_receipt_download_and_verify_paths() -> None:
    js = _read("app.js")
    html = _read("index.html")
    assert "/api/assignments/" in js
    assert "receipt" in js
    assert "/api/receipts/verify" in js
    assert 'id="receipt-list"' in html
    download = js.split("function downloadSignedReceipt")[1].split("function verifySignedReceipt")[0]
    verify = js.split("function verifySignedReceipt")[1].split("function paintFaceRow")[0]
    load = js.split("function loadReceipt")[1].split("function saveReceiptJson")[0]
    assert "/api/assignments/" in load
    assert "receipt" in load
    assert "/api/receipts/verify" in verify
    assert 'method: "POST"' in verify
    assert "downloadSignedReceipt" in js
    assert "verifySignedReceipt" in js
    paint = js.split("function paintFaceRow")[1].split("function paintReceipts")[0]
    assert 'kind === "signed"' in paint
    assert "downloadSignedReceipt" in paint
    assert "verifySignedReceipt" in paint
    assert "face-seal" in paint
    assert download.strip()
    assert "ok" in verify
    assert "fail" in verify


def test_health_uses_public_model_not_secrets() -> None:
    js = _read("app.js")
    html = _read("index.html")
    assert 'id="health-line"' in html
    health = js.split("function paintHealth")[1].split("function openSettingsDialog")[0]
    public = js.split("function publicModelName")[1].split("function paintHealth")[0]
    assert "llm_model" in public
    assert "health-line" in health
    for key in _SECRETS:
        assert key not in health
        assert key not in public
        assert f"row.{key}" not in js


def test_refuses_to_claim_g0_g2_pass() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_sibling_ids_kept() -> None:
    html = _read("index.html")
    js = _read("app.js")
    assert 'id="hpc_secret"' in html
    assert 'id="settings"' in html
    assert 'id="inbox"' in html
    assert 'id="secret-fieldset"' in html
    assert 'id="receipt-list"' in html
    assert 'id="health-line"' in html
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
    assert "C-01e" in text
    assert "showModal" in text
    assert "ready" in text
    assert "/api/receipts/verify" in text
    assert "hpc_secret" in text or "secret-fieldset" in text
    assert "不算" in text or "不是过门" in text


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
    assert "/approve" not in js


def main() -> int:
    failed = 0
    for name, fn in (
        ("boot_opens_settings_when_not_ready", test_boot_opens_settings_when_not_ready),
        ("receipt_download_and_verify_paths", test_receipt_download_and_verify_paths),
        ("health_uses_public_model_not_secrets", test_health_uses_public_model_not_secrets),
        ("refuses_to_claim_g0_g2_pass", test_refuses_to_claim_g0_g2_pass),
        ("sibling_ids_kept", test_sibling_ids_kept),
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
