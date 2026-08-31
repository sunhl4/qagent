"""G0 script checklist exists. Refuses to claim G0 pass. No minted twin_id."""

from __future__ import annotations

import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G0_demo.md"
_CLAIM_PASS = ("G0 已通过", "G0 passed", "正式演示完成")


def _read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file(), SCRIPT
    text = _read()
    assert text.strip(), SCRIPT
    assert "G0" in text


def test_scan_hydrogen_line() -> None:
    text = _read()
    assert "扫氢分子" in text or "H₂" in text


def test_ports_3080_3081() -> None:
    text = _read()
    assert "3080" in text
    assert "3081" in text


def test_refuses_to_claim_pass() -> None:
    text = _read()
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def test_forbids_fake_twin_id() -> None:
    text = _read()
    assert "假 twin_id" in text or "假 `twin_id`" in text
    assert "禁止" in text


def test_human_fills_model() -> None:
    text = _read()
    assert "人填模型" in text
    assert "设置" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("script_exists", test_script_exists),
        ("scan_hydrogen_line", test_scan_hydrogen_line),
        ("ports_3080_3081", test_ports_3080_3081),
        ("refuses_to_claim_pass", test_refuses_to_claim_pass),
        ("forbids_fake_twin_id", test_forbids_fake_twin_id),
        ("human_fills_model", test_human_fills_model),
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
