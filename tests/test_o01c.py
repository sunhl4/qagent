"""O-01c: staff/customer handbooks exist; hard rails in some wording."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTERNAL = REPO / "docs" / "handbooks" / "internal.md"
CUSTOMER = REPO / "docs" / "handbooks" / "customer.md"
NOTE = REPO / "docs" / "execution" / "O-01c_handbooks.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_ID_RE = re.compile(r"\b[a-z]+_id\b")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def test_both_handbooks_exist() -> None:
    assert INTERNAL.is_file(), INTERNAL
    assert CUSTOMER.is_file(), CUSTOMER
    internal = _read(INTERNAL)
    customer = _read(CUSTOMER)
    assert len(internal.strip()) >= 1600, "internal handbook too short for ~2 pages"
    assert len(customer.strip()) >= 1400, "customer handbook too short for ~2 pages"


def test_internal_rails() -> None:
    text = _read(INTERNAL)
    assert "dsh" in text
    assert "--profile qagent" in text
    assert "3080" in text
    assert "脸" in text
    assert "circuit_id" in text
    assert "asset_id" in text
    assert "twin_id" in text
    assert _has_any(text, "三句柄", "三个句柄")
    assert "TwinRun" in text
    assert "只有" in text
    assert "上机" in text
    assert _has_any(text, "问人", "先问人")
    assert "批准" in text
    assert "session" in text
    assert "CAL" in text
    assert "shuttle" in text
    assert "工具" in text
    assert "设置" in text
    assert "组内" in text
    assert "密钥" in text
    assert "对话" in text


def test_customer_rails() -> None:
    text = _read(CUSTOMER)
    assert "平常话" in text
    assert _has_any(text, "recipe", "配方")
    assert "未签收" in text
    assert _has_any(text, "绿封条", "绿印")
    assert "回执" in text
    assert "电路正文" in text
    assert "IBM" in text
    assert "冒充" in text
    assert "我们的机器" in text


def test_no_fourth_handle() -> None:
    for path in (INTERNAL, CUSTOMER):
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
    assert "internal.md" in text
    assert "customer.md" in text
    assert "O-01c" in text
    assert "第三" in text or "第三套" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("both_handbooks_exist", test_both_handbooks_exist),
        ("internal_rails", test_internal_rails),
        ("customer_rails", test_customer_rails),
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
