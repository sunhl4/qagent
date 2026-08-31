"""O-01h: start_ui.sh prints a ?tenant= customer example after the customer face."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
START_UI = REPO / "qagent" / "scripts" / "start_ui.sh"
NOTE = REPO / "docs" / "execution" / "O-01h_start_ui_tenant.md"
INTERNAL = REPO / "docs" / "handbooks" / "internal.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G2 已通过", "G2 passed")
_BANNED_IDS = ("tenant_id", "assignment_id", "rpc_id")
_CUSTOMER_QUERY = "?token=${QAGENT_SHELL_TOKEN}&role=customer"
_TENANT_QUERY = "?tenant=cust-a&token=${QAGENT_SHELL_TOKEN}&role=customer"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_start_ui_tenant_after_customer() -> None:
    text = _read(START_UI)
    assert "127.0.0.1" in text
    assert "--host 127.0.0.1" in text
    assert "0.0.0.0" not in text
    assert "role=customer" in text
    assert "?token=" in text
    assert "客户脸" in text
    assert "客户租户示例" in text
    assert _CUSTOMER_QUERY in text
    assert "?tenant=" in text
    assert "tenant=cust-a" in text
    assert _TENANT_QUERY in text
    assert "tenant_id" not in text
    token_line = text.find("?token=${QAGENT_SHELL_TOKEN}")
    customer_line = text.find(_CUSTOMER_QUERY)
    tenant_line = text.find(_TENANT_QUERY)
    assert token_line != -1
    assert customer_line != -1
    assert tenant_line != -1
    assert token_line < customer_line
    assert customer_line < tenant_line


def test_no_g2_pass_claim() -> None:
    blob = _read(START_UI) + _read(NOTE) + _read(INTERNAL)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    for path in (START_UI, NOTE):
        text = _read(path)
        found = set(_ID_RE.findall(text))
        extra = found - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
        for banned in _BANNED_IDS:
            assert banned not in text, f"{path.name} wrote {banned}"
        for fake in _FAKE_TWIN:
            assert fake not in text
        assert "第四个句柄是" not in text
        assert "第四个句柄：" not in text


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "O-01h" in text
    assert "start_ui.sh" in text
    assert "role=customer" in text
    assert "127.0.0.1" in text
    assert "客户脸" in text
    assert "客户租户示例" in text
    assert "?tenant=" in text
    assert "cust-a" in text
    assert "tenant_id" not in text
    assert "G2 过门" in text or "不是 G2" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def main() -> int:
    failed = 0
    for name, fn in (
        ("start_ui_tenant_after_customer", test_start_ui_tenant_after_customer),
        ("no_g2_pass_claim", test_no_g2_pass_claim),
        ("no_fourth_handle", test_no_fourth_handle),
        ("note_exists", test_note_exists),
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
