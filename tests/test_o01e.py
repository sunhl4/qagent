"""O-01e: start_ui.sh prints a customer-role URL; still loopback; not a G2 pass."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
START_UI = REPO / "qagent" / "scripts" / "start_ui.sh"
NOTE = REPO / "docs" / "execution" / "O-01e_start_ui_customer.md"
INTERNAL = REPO / "docs" / "handbooks" / "internal.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G2 已通过", "G2 passed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_start_ui_loopback_and_customer() -> None:
    text = _read(START_UI)
    assert "127.0.0.1" in text
    assert "--host 127.0.0.1" in text
    assert "0.0.0.0" not in text
    assert "role=customer" in text
    assert "?token=" in text
    assert "客户脸" in text
    assert "?token=${QAGENT_SHELL_TOKEN}&role=customer" in text
    token_line = text.find("?token=${QAGENT_SHELL_TOKEN}")
    customer_line = text.find("?token=${QAGENT_SHELL_TOKEN}&role=customer")
    assert token_line != -1
    assert customer_line != -1
    assert token_line < customer_line


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
        for fake in _FAKE_TWIN:
            assert fake not in text
        assert "第四个句柄是" not in text
        assert "第四个句柄：" not in text


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "O-01e" in text
    assert "start_ui.sh" in text
    assert "role=customer" in text
    assert "127.0.0.1" in text
    assert "客户脸" in text
    assert "G2 过门" in text or "不是 G2" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def main() -> int:
    failed = 0
    for name, fn in (
        ("start_ui_loopback_and_customer", test_start_ui_loopback_and_customer),
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
