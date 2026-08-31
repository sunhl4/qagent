"""L1-03-how: add-pack page aligns Cirq already wired. Next pack still reserved first."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
HOW = ROOT / "contracts" / "engines" / "HOW_TO_ADD.md"
NOTE = REPO / "docs" / "execution" / "L1-03_how.md"

_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_STALE = (
    "Pennylane 已接线",
    "Cirq reserved",
    "Cirq 是 reserved",
    "G3 已通过",
    "G3 passed",
    "G3 验收通过",
    "G3 通过",
    "G3通过",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_how_cirq_already_wired_example() -> None:
    text = _read(HOW)
    assert "Cirq" in text
    assert "已经" in text
    assert "`engines[]`" in text
    assert "wired" in text
    assert "互通范例" in text
    assert "provenance" in text
    assert "qccd-twin" in text
    assert "不许发" in text and "twin_id" in text
    assert "不要新写 agent" in text
    assert "TwinRun" in text


def test_how_next_pack_reserved_first() -> None:
    text = _read(HOW)
    assert "Pennylane" in text
    assert "真机" in text
    assert "先 reserved" in text
    assert "不要一上来写进" in text
    assert "`engines[]`" in text
    assert "reserved_engines" in text
    assert "的 `engines` 加一条" not in text
    assert "未接线" in text
    assert "import" in text


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "L1-03-how" in text
    assert "HOW_TO_ADD.md" in text
    assert "Cirq" in text
    assert "wired" in text
    assert "互通范例" in text
    assert "`engines[]`" in text
    assert "provenance" in text
    assert "qccd-twin" in text
    assert "不许发" in text and "twin_id" in text
    assert "先 reserved" in text
    assert "不要一上来写进" in text
    assert "Pennylane" in text
    assert "真机" in text
    assert "不要新写 agent" in text
    assert "未接线" in text
    assert "import" in text
    assert "TwinRun" in text
    assert "不算接线 Pennylane" in text
    assert "不算 G3" in text


def test_no_stale_claims() -> None:
    blob = _read(HOW) + _read(NOTE)
    hits = [phrase for phrase in _STALE if phrase in blob]
    assert not hits, hits


def test_no_fourth_handle() -> None:
    for path in (HOW, NOTE):
        text = _read(path)
        extra = set(_ID_RE.findall(text)) - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
        assert _HANDLES <= set(_ID_RE.findall(text))


def main() -> int:
    failed = 0
    for name, fn in (
        ("how_cirq_wired", test_how_cirq_already_wired_example),
        ("how_reserved_first", test_how_next_pack_reserved_first),
        ("note_exists", test_note_exists),
        ("no_stale", test_no_stale_claims),
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
