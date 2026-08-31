"""G2e: G2 customer script aligns Cirq already wired. Refuses G2 pass. No fourth handle."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G2_demo.md"
NOTE = REPO / "docs" / "execution" / "G2e_cirq.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G2 已通过", "G2 passed", "正式演示完成")
_STALE = (
    "Cirq reserved",
    "Cirq 是 reserved",
    "不在 `engines[]`",
    "不在 engines[]",
    "只有五包",
    "把 Cirq reserved 算进",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_script_aligned() -> None:
    text = _read(SCRIPT)
    assert "Aer / IBM / 本地卡 / Cirq 都不许冒充" in text
    assert "Cirq 不是我们的机器" in text
    assert "不许铸" in text and "twin_id" in text
    assert "provenance" in text
    assert "qccd-twin" in text
    assert "已签收的回执可以在 3080 下载短 JSON" in text
    assert "脸上点核验" in text
    assert "python3 scripts/verify_receipt.py receipt.json" in text
    assert "人还没走完之前，门禁未过" in text
    assert "租户" in text or "TENANT" in text
    assert "回执" in text
    assert "IBM" in text
    assert "绿封条" in text
    for phrase in _STALE:
        assert phrase not in text, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "G2e" in text
    assert "Cirq 不是我们的机器" in text
    assert "不许铸" in text and "twin_id" in text
    assert "qccd-twin" in text
    assert "C-01c" in text
    assert "C-01f" in text
    assert "已签收的回执可以在 3080 下载短 JSON" in text
    assert "脸上点核验" in text
    assert "python3 scripts/verify_receipt.py receipt.json" in text
    assert "人还没走完之前，门禁未过" in text
    assert "不算 G2" in text or "不是 G2 过门" in text
    for phrase in _STALE:
        assert phrase not in text, phrase


def test_refuses_to_claim_pass() -> None:
    blob = _read(SCRIPT) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    for path in (SCRIPT, NOTE):
        text = _read(path)
        found = set(_ID_RE.findall(text))
        extra = found - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
        assert "tenant_id" not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("script_aligned", test_script_aligned),
        ("note_exists", test_note_exists),
        ("refuses_to_claim_pass", test_refuses_to_claim_pass),
        ("no_fourth_handle", test_no_fourth_handle),
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
