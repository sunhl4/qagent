"""C-01d: customer role must not see secret field values. Text on html/js only."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01d_customer_secrets.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = ("G2 已通过", "G2 passed")
_SECRETS = ("hpc_secret", "llm_api_key", "quantum_secret")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def _fields_block() -> str:
    return _read("app.js").split("const FIELDS")[1].split("]")[0]


def test_customer_role_path() -> None:
    js = _read("app.js")
    html = _read("index.html")
    token_fn = js.split("function token")[1].split("function role")[0]
    apply_fn = js.split("function applyCustomerRole")[1].split("function headers")[0]
    assert "role=customer" in js
    assert 'get("role")' in token_fn
    assert "QAGENT_SHELL_ROLE" in token_fn
    assert "localStorage.setItem" in token_fn
    assert "history.replaceState" in token_fn
    assert 'role() === "customer"' in apply_fn
    assert "secret-fieldset" in apply_fn
    assert "box.hidden = customer" in apply_fn
    assert "aria-hidden" in apply_fn
    assert "applyCustomerRole" in js
    assert 'id="secret-fieldset"' in html
    assert 'class="secret-fieldset"' in html
    assert "<fieldset" in html


def test_secret_values_never_from_api() -> None:
    html = _read("index.html")
    js = _read("app.js")
    fill = js.split("function fillSettings")[1].split("function typingInField")[0]
    poll = js.split("async function pollStatus")[1].split("async function saveSettings")[0]
    inbox = js.split("async function refreshInbox")[1].split("function addMessage")[0]
    fields = _fields_block()
    for key in _SECRETS:
        match = re.search(rf'<input id="{key}"[^>]*>', html)
        assert match, f"{key} input missing"
        tag = match.group(0)
        assert 'type="password"' in tag
        assert 'placeholder="已保存"' in tag
        assert key not in fields
        assert f"row.{key}" not in js
    assert 'el.value = ""' in fill
    assert 'el.placeholder = "已保存"' in fill
    for key in _SECRETS:
        assert key not in poll
        assert key not in inbox


def test_secret_ids_kept() -> None:
    html = _read("index.html")
    assert 'id="hpc_secret"' in html
    assert 'id="llm_api_key"' in html
    assert 'id="quantum_secret"' in html
    assert 'id="secret-fieldset"' in html


def test_no_rooms_or_finder() -> None:
    blob = _blob()
    html = _read("index.html")
    js = _read("app.js")
    for word in _ROOMS:
        assert word not in blob
    for word in _WALLS:
        assert word not in blob
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert "ionstack_twin_run" not in js


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01d" in text
    assert "role=customer" in text
    assert "hpc_secret" in text
    assert "secret-fieldset" in text or "密钥" in text
    assert "aria-hidden" in text or "hidden" in text


def test_refuses_to_claim_g2_pass() -> None:
    blob = _blob() + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def main() -> int:
    failed = 0
    for name, fn in (
        ("customer_role_path", test_customer_role_path),
        ("secret_values_never_from_api", test_secret_values_never_from_api),
        ("secret_ids_kept", test_secret_ids_kept),
        ("no_rooms_or_finder", test_no_rooms_or_finder),
        ("note_exists", test_note_exists),
        ("refuses_to_claim_g2_pass", test_refuses_to_claim_g2_pass),
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
