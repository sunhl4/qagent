"""R-01e: vibe-across-engines Skill matches wired catalog. Pennylane stays reserved."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_r01d import _ASK_LOCK, _AUTO_APPROVE, _DEFAULT_HINT

SKILL_PATHS = (
    ROOT / "skills" / "vibe-across-engines" / "SKILL.md",
    ROOT / "profiles" / "qagent" / "skills" / "vibe-across-engines" / "SKILL.md",
    ROOT / ".dsh-home" / "profiles" / "qagent" / "skills" / "vibe-across-engines" / "SKILL.md",
)
NOTE = ROOT / "docs" / "execution" / "R-01e_skill_wired.md"
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_LIE = "现在都是 reserved"
_STALE = ("Pennylane 已接线", "Cirq reserved")
_WIRED = ("Cirq", "wired", "interop")
_RESERVED = ("Pennylane", "reserved_engines", "reserved")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _list_engines_line(text: str) -> str:
    for line in text.splitlines():
        if "qagent_list_engines" in line:
            return line
    raise AssertionError("missing qagent_list_engines line")


def test_no_all_reserved_lie() -> None:
    for path in SKILL_PATHS:
        assert path.is_file(), path
        assert _LIE not in _read(path), path


def test_wired_cirq_reserved_pennylane() -> None:
    for path in SKILL_PATHS:
        text = _read(path)
        for needle in _WIRED + _RESERVED:
            assert needle in text, (path, needle)
        for phrase in _STALE:
            assert phrase not in text, (path, phrase)


def test_r01d_locks() -> None:
    for path in SKILL_PATHS:
        text = _read(path)
        assert _DEFAULT_HINT.search(text), path
        assert _ASK_LOCK.search(text), path
        assert _AUTO_APPROVE.search(text) is None, path
        matter = _FRONTMATTER.match(text)
        assert matter, path
        assert "name:" in matter.group(1)
        assert "description:" in matter.group(1)


def test_hard_rails() -> None:
    for path in SKILL_PATHS:
        text = _read(path)
        assert "CAL" in text and "shuttle" in text
        assert "ionstack_twin_run" in text
        assert "ask" in text
        assert "Aer" in text
        assert "没有" in text and "twin_id" in text


def test_copies_agree() -> None:
    texts = [_read(path) for path in SKILL_PATHS]
    assert texts[0] == texts[1] == texts[2]
    lines = [_list_engines_line(text) for text in texts]
    assert lines[0] == lines[1] == lines[2]
    assert "engines[]" in lines[0]
    assert "Cirq" in lines[0] and "wired" in lines[0] and "interop" in lines[0]
    assert "Pennylane" in lines[0] and "reserved_engines" in lines[0]


def test_no_fourth_handle() -> None:
    for path in (*SKILL_PATHS, NOTE):
        text = _read(path)
        extra = set(_ID_RE.findall(text)) - _HANDLES
        assert not extra, f"{path} invented handles: {sorted(extra)}"
        assert "twin_id=" not in text
        assert "第四个句柄是" not in text


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "R-01e" in text
    assert "qagent_list_engines" in text
    assert "engines[]" in text
    assert "Cirq" in text and "wired" in text and "interop" in text
    assert "Pennylane" in text and "reserved_engines" in text
    assert "默认建议" in text and "不是唯一入口" in text
    assert "不能绕过" in text
    assert "ionstack_twin_run" in text
    assert "不算接线 Pennylane" in text
    assert "第三套" in text
    for phrase in _STALE:
        assert phrase not in text, phrase
    assert "G0 已通过" not in text
    assert "G1 已通过" not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("no_all_reserved_lie", test_no_all_reserved_lie),
        ("wired_cirq_reserved_pennylane", test_wired_cirq_reserved_pennylane),
        ("r01d_locks", test_r01d_locks),
        ("hard_rails", test_hard_rails),
        ("copies_agree", test_copies_agree),
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
