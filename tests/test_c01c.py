"""C-01c: G2 customer demo script exists. Refuses to claim G2 pass. No fourth handle."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G2_demo.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G2 已通过", "G2 passed")
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")


def _read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file(), SCRIPT
    text = _read()
    assert text.strip(), SCRIPT


def test_required_words() -> None:
    text = _read()
    assert "租户" in text or "TENANT" in text
    assert "回执" in text
    assert "IBM" in text
    assert "绿封条" in text


def test_refuses_to_claim_pass() -> None:
    text = _read()
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def test_no_fourth_handle() -> None:
    text = _read()
    found = set(_ID_RE.findall(text))
    extra = found - _HANDLES
    assert not extra, f"invented handles: {sorted(extra)}"
    for fake in _FAKE_TWIN:
        assert fake not in text
    assert "第四个句柄是" not in text
    assert "第四个句柄：" not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("script_exists", test_script_exists),
        ("required_words", test_required_words),
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
