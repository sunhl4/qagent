"""L1-03 plan: Cirq stays reserved until listed asserts relax. Does not wire Cirq."""

from __future__ import annotations

import os
import subprocess
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
PLAN = REPO / "docs" / "execution" / "L1-03_wired_plan.md"

_MUST_NAME = (
    "test_engines.py",
    "test_a05",
    "company_shell",
    "test_l103.py",
    "test_ports",
)

_REFUSED_CURRENT = (
    "Cirq 已接线",
    "engines 已含 cirq",
)

_REFUSE_MARKERS = (
    "拒绝",
    "不是当前",
    "不得写成当前",
    "未接线",
    "不是现状",
)


def _plan() -> str:
    return PLAN.read_text(encoding="utf-8")


def test_plan_exists() -> None:
    assert PLAN.is_file(), PLAN


def test_lists_those_test_file_names() -> None:
    text = _plan()
    missing = [name for name in _MUST_NAME if name not in text]
    assert not missing, missing
    assert "test_a05.py" in text
    assert "run_evals" in text
    assert "E01" in text
    assert "E21" in text
    assert "range(1, 22)" in text


def test_cirq_stays_reserved_until_relaxed() -> None:
    text = _plan()
    assert "Cirq stays reserved until those are relaxed" in text
    assert "reserved" in text
    assert "放松" in text
    assert "不标" in text and "L1-03 wired" in text


def test_refuses_wired_as_current_state() -> None:
    text = _plan()
    for phrase in _REFUSED_CURRENT:
        assert phrase in text, phrase
        lines = [line for line in text.splitlines() if phrase in line]
        assert lines, phrase
        for line in lines:
            assert any(marker in line for marker in _REFUSE_MARKERS), line


def test_l103_still_green() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        ["python3", "tests/test_l103.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    failed = 0
    for name, fn in (
        ("plan_exists", test_plan_exists),
        ("lists_test_names", test_lists_those_test_file_names),
        ("reserved_until_relaxed", test_cirq_stays_reserved_until_relaxed),
        ("refuses_current_claims", test_refuses_wired_as_current_state),
        ("l103_still_green", test_l103_still_green),
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
