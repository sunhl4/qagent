"""O-01d: customer handbook documents ?role=customer; not a G2 pass."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CUSTOMER = REPO / "docs" / "handbooks" / "customer.md"
NOTE = REPO / "docs" / "execution" / "O-01d_customer_role.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G2 已通过", "G2 passed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_customer_mentions_role_and_3080() -> None:
    text = _read(CUSTOMER)
    assert "role=customer" in text
    assert "3080" in text
    assert "?token=" in text
    assert "密钥" in text
    assert "藏" in text
    assert "看不到密钥值" in text
    assert "G2 过门" in text
    assert "仍不是" in text


def test_no_g2_pass_claim() -> None:
    blob = _read(CUSTOMER) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    for path in (CUSTOMER, NOTE):
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
    assert "O-01d" in text
    assert "customer.md" in text
    assert "role=customer" in text
    assert "3080" in text
    assert "G2 过门" in text or "不是 G2" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("customer_mentions_role_and_3080", test_customer_mentions_role_and_3080),
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
