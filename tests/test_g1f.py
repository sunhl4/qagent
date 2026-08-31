"""G1f: G1 script says Pennylane is not wired. Keeps G1e. Refuses G1 pass."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G1_demo.md"
NOTE = REPO / "docs" / "execution" / "G1f_pennylane.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G1 已通过", "G1 passed", "正式演示完成")
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


def _section_after(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.index(marker)
    rest = text[start + len(marker) :]
    nxt = rest.find("\n## ")
    return rest if nxt < 0 else rest[:nxt]


def test_script_keeps_g1e() -> None:
    text = _read(SCRIPT)
    assert "打头" in text
    assert "engines[]" in text
    assert "kind=interop" in text
    assert "provenance=cirq" in text
    assert "qccd-twin" in text
    assert "不许发" in text and "twin_id" in text
    assert "我们的机器" in text
    assert "3080" in text
    assert "3081" in text
    assert "list_engines" in text
    assert "makespan_ns" in text
    assert "不会伪造" in text or "假 twin_id" in text or "假 `twin_id`" in text
    assert "Aer" in text
    assert "provenance" in text
    for phrase in _STALE:
        assert phrase not in text, phrase


def test_script_pennylane_unlisted() -> None:
    text = _read(SCRIPT)
    unseen = _section_after(text, "当场不要看见")
    assert "Pennylane" in unseen
    assert "出现在" in unseen
    assert "engines[]" in unseen
    assert "已接线" in unseen
    expect = _section_after(text, "1. 「现在有哪些包？」")
    assert "Pennylane" in expect
    assert "不要把 Pennylane 写进" in expect
    assert "不要把 Pennylane 说成已接线" in expect


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "G1f" in text
    assert "打头" in text
    assert "kind=interop" in text
    assert "provenance=cirq" in text
    assert "我们的机器" in text
    assert "Pennylane" in text
    assert "出现在" in text
    assert "engines[]" in text
    assert "已接线" in text
    assert "不算 G1 过门" in text or "不是 G1 过门" in text
    for phrase in _STALE:
        assert phrase not in text, phrase


def test_refuses_to_claim_pass() -> None:
    blob = _read(SCRIPT) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    for path in (SCRIPT, NOTE):
        found = set(_ID_RE.findall(_read(path)))
        extra = found - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
        assert "tenant_id" not in _read(path)


def main() -> int:
    failed = 0
    for name, fn in (
        ("script_keeps_g1e", test_script_keeps_g1e),
        ("script_pennylane_unlisted", test_script_pennylane_unlisted),
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
