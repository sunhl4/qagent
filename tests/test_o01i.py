"""O-01i: handbooks document per-tenant chat; no fourth handle."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTERNAL = REPO / "docs" / "handbooks" / "internal.md"
CUSTOMER = REPO / "docs" / "handbooks" / "customer.md"
NOTE = REPO / "docs" / "execution" / "O-01i_chat_tenant.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_BANNED_IDS = ("tenant_id", "session_id", "assignment_id", "rpc_id")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def test_internal_configured_tenant_own_chat() -> None:
    text = _read(INTERNAL)
    assert "已设租户" in text
    assert "各一条对话" in text
    assert "各走各的" in text
    assert "不共用" in text
    assert "session" in text
    assert "空租户仍是组内那条" in text
    assert "空租户" in text
    assert "全部" in text
    assert "交办" in text
    assert "实验记录" in text
    assert "?tenant=" in text
    assert "请求头" in text
    assert "不要带头" in text
    assert "同一张脸" in text
    assert "GET" in text
    assert _has_any(text, "ELN", "实验记录")
    assert "open_settings" in text
    assert "可按交办过滤" in text


def test_customer_cannot_see_other_talking() -> None:
    text = _read(CUSTOMER)
    assert "两位客户不要看见对方正在说的话" in text
    assert "?tenant=" in text
    assert "两位客户" in text
    assert "各走各的" in text
    assert "在办" in text
    assert "回执" in text
    assert "对方" in text
    assert "实验流水" in text
    assert "session_id" not in text


def test_no_g_pass_claim() -> None:
    blob = _read(INTERNAL) + _read(CUSTOMER) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    for path in (INTERNAL, CUSTOMER, NOTE):
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
    assert "O-01i" in text
    assert "internal.md" in text
    assert "customer.md" in text
    assert "已设租户" in text
    assert "各一条对话" in text
    assert "session" in text
    assert "空租户" in text
    assert "组内那条" in text
    assert "?tenant=" in text
    assert "请求头" in text
    assert _has_any(text, "GET", "open_settings")
    assert _has_any(text, "ELN", "实验记录")
    assert "可按交办过滤" in text
    assert "第三套" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase
    for banned in _BANNED_IDS:
        assert banned not in text, banned


def main() -> int:
    failed = 0
    for name, fn in (
        ("internal_configured_tenant_own_chat", test_internal_configured_tenant_own_chat),
        ("customer_cannot_see_other_talking", test_customer_cannot_see_other_talking),
        ("no_g_pass_claim", test_no_g_pass_claim),
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
