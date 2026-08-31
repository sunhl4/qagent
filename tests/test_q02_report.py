"""Q-02 report: dual-track note exists; Codex stays a stub. No official Codex. No G3 pass claim."""

from __future__ import annotations

import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "docs" / "execution" / "Q-02_vs_codex.md"

_REQUIRED = ("30", "Q-h06", "stub", "twin_id", "qagent-eval")

_OFFICIAL_INVOKED = (
    "official Codex was invoked",
    "invoked official Codex",
    "spawned official Codex",
    "已调官方 Codex",
    "已调用官方 Codex",
    "官方 Codex 已跑",
)

_G3_PASSED = (
    "G3 通过",
    "G3通过",
    "G3 passed",
    "G3 已通过",
    "G3 验收通过",
)


def test_report_exists() -> None:
    assert REPORT.is_file(), REPORT


def test_report_mentions_required() -> None:
    text = REPORT.read_text(encoding="utf-8")
    missing = [needle for needle in _REQUIRED if needle not in text]
    assert not missing, f"report missing {missing}"
    assert "bare Codex" in text
    assert "may_fail" in text
    assert "30/30" in text
    assert "PYTHONPATH=src python3 tests/run_qagent_vs_codex.py" in text


def test_no_official_codex_invoked() -> None:
    text = REPORT.read_text(encoding="utf-8")
    hits = [phrase for phrase in _OFFICIAL_INVOKED if phrase in text]
    assert not hits, f"report claims official Codex was invoked: {hits}"
    assert "official Codex was invoked" not in text


def test_no_g3_passed() -> None:
    text = REPORT.read_text(encoding="utf-8")
    hits = [phrase for phrase in _G3_PASSED if phrase in text]
    assert not hits, f"report claims G3 passed: {hits}"
    assert "G3 通过" not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("exists", test_report_exists),
        ("mentions", test_report_mentions_required),
        ("no_official_codex", test_no_official_codex_invoked),
        ("no_g3_passed", test_no_g3_passed),
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
