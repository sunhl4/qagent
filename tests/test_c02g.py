"""C-02g: G2 dual-customer script splits chat. Refuses pass claims."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
G2 = REPO / "docs" / "execution" / "G2_demo.md"
NOTE = REPO / "docs" / "execution" / "C-02g_chat_split.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = (
    "G2 已通过",
    "G2 passed",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _no_fourth_handle(text: str) -> None:
    found = set(_ID_RE.findall(text))
    extra = found - _HANDLES
    assert not extra, f"invented handles: {sorted(extra)}"


def test_g2_two_customers_chat_split() -> None:
    text = _read(G2)
    section = text.split("## 两位客户")[1].split("## 当场要看见")[0]
    assert "对话分开" in section
    assert "不共用" in section
    assert "session" in section
    assert "气泡" in section
    assert "?tenant=" in section
    assert "cust-a" in section
    assert "cust-b" in section
    assert "请求头仍是租户头" in section
    assert "空租户是组内" in section
    assert "看见全部" in section
    assert "X-QAGENT-TENANT" in section


def test_c02e_and_c01f_kept() -> None:
    text = _read(G2)
    assert "已签收的回执可以在 3080 下载短 JSON" in text
    assert "脸上点核验" in text
    assert "python3 scripts/verify_receipt.py receipt.json" in text
    assert "租户" in text or "TENANT" in text
    assert "回执" in text
    assert "IBM" in text
    assert "绿封条" in text
    assert "人还没走完之前，门禁未过" in text


def test_refuses_to_claim_pass() -> None:
    blob = _read(G2) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    _no_fourth_handle(_read(G2))
    _no_fourth_handle(_read(NOTE))


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "C-02g" in text
    assert "对话分开" in text
    assert "不共用" in text
    assert "session" in text
    assert "气泡" in text
    assert "?tenant=" in text
    assert "cust-a" in text
    assert "cust-b" in text
    assert "请求头仍是租户头" in text
    assert "空租户是组内" in text
    assert "看见全部" in text
    assert "下载短 JSON" in text
    assert "脸上点核验" in text
    assert "verify_receipt.py" in text
    assert "G0_demo.md" in text
    assert "不算过门" in text or "不是" in text and "过门" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("g2_two_customers_chat_split", test_g2_two_customers_chat_split),
        ("c02e_and_c01f_kept", test_c02e_and_c01f_kept),
        ("refuses_to_claim_pass", test_refuses_to_claim_pass),
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
