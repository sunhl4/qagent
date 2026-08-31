"""G1 script checklist exists. Refuses to claim G1 pass. No fourth handle."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G1_demo.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G1 已通过", "G1 passed", "正式演示完成")


def _read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file(), SCRIPT
    text = _read()
    assert text.strip(), SCRIPT
    assert "G1" in text


def test_ports_and_engines() -> None:
    text = _read()
    assert "3080" in text
    assert "3081" in text
    assert "list_engines" in text or "哪些包" in text
    assert "makespan_ns" in text
    assert "不会伪造" in text or "假 twin_id" in text or "假 `twin_id`" in text


def test_aer_provenance() -> None:
    text = _read()
    assert "Aer" in text
    assert "provenance" in text


def test_refuses_to_claim_pass() -> None:
    text = _read()
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def test_no_fourth_handle() -> None:
    text = _read()
    found = set(_ID_RE.findall(text))
    extra = found - _HANDLES
    assert not extra, f"invented handles: {sorted(extra)}"


def main() -> int:
    failed = 0
    for name, fn in (
        ("script_exists", test_script_exists),
        ("ports_and_engines", test_ports_and_engines),
        ("aer_provenance", test_aer_provenance),
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
