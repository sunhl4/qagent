"""C-01f: G0/G2 scripts align landed face. New sentences exist. Refuses pass claims."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
G0 = REPO / "docs" / "execution" / "G0_demo.md"
G2 = REPO / "docs" / "execution" / "G2_demo.md"
NOTE = REPO / "docs" / "execution" / "C-01f_demo_align.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = (
    "G0 已通过",
    "G0 passed",
    "G2 已通过",
    "G2 passed",
    "正式演示完成",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _no_fourth_handle(text: str) -> None:
    found = set(_ID_RE.findall(text))
    extra = found - _HANDLES
    assert not extra, f"invented handles: {sorted(extra)}"


def test_g0_auto_settings_and_human_model() -> None:
    text = _read(G0)
    assert "工作设置" in text
    assert "设置对话框" in text
    assert "自动打开" in text
    assert "人填模型" in text
    assert "扫氢分子" in text or "H₂" in text
    assert "3080" in text
    assert "3081" in text
    assert "假 twin_id" in text or "假 `twin_id`" in text
    assert "禁止" in text
    assert "人还没走完之前，门禁未过" in text


def test_g2_download_and_verify_on_face() -> None:
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
    blob = _read(G0) + _read(G2) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    _no_fourth_handle(_read(G0))
    _no_fourth_handle(_read(G2))
    _no_fourth_handle(_read(NOTE))


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "C-01f" in text
    assert "工作设置" in text
    assert "设置对话框" in text
    assert "人填模型" in text
    assert "下载短 JSON" in text
    assert "脸上点核验" in text
    assert "不算过门" in text or "不是" in text and "过门" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("g0_auto_settings_and_human_model", test_g0_auto_settings_and_human_model),
        ("g2_download_and_verify_on_face", test_g2_download_and_verify_on_face),
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
