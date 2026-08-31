"""L1-02-live: HTTP app-server stays unwired. Note only. No official spawn."""

from __future__ import annotations

import os
import subprocess
import traceback
from pathlib import Path

from qagent.adapters.codex import WiredCodex

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "execution" / "L1-02_app_server.md"
_HANDLE = "twin" + "_id"
_TOOL = "ionstack_" + "twin" + "_run"

_REFUSED_DONE = (
    "Codex 真接线已通",
)

_REFUSE_MARKERS = (
    "拒绝",
    "不是现状",
    "不是成功",
    "不是 done",
    "未接线",
    "未证明",
    "不得",
    "不标",
    "造假",
)

_INVOKED_CLAIMS = (
    "official Codex invoked",
    "Official Codex invoked",
    "official Codex was invoked",
    "Codex invoked",
    "app-server invoked",
)


def _note() -> str:
    assert NOTE.is_file(), NOTE
    return NOTE.read_text(encoding="utf-8")


def test_note_exists_unproven() -> None:
    assert NOTE.is_file(), NOTE
    text = _note()
    assert "未接线" in text
    assert "unproven" in text.lower()
    assert "未证明" in text
    assert "_documented_app_server" in text
    assert "needs_app_server" in text
    assert "L1-02d" in text
    assert "L1-02d_e13_honest.md" in text
    assert "不标" in text and "attended" in text
    assert _HANDLE not in text
    assert _TOOL not in text


def test_refuses_tests_green_as_done() -> None:
    text = _note()
    assert "tests_green" in text
    assert "tests_green=False" in text
    assert "不是" in text and "成功" in text
    assert "不是" in text and "done" in text
    assert any(marker in text for marker in ("不得把未接线断言成绿", "写成已完成是造假"))
    for phrase in _REFUSED_DONE:
        assert phrase in text, phrase
        lines = [line for line in text.splitlines() if phrase in line]
        assert lines, phrase
        for line in lines:
            assert any(marker in line for marker in _REFUSE_MARKERS), line
    green_lines = [line for line in text.splitlines() if "tests_green" in line]
    assert green_lines
    for line in green_lines:
        if "True" in line and "False" not in line:
            assert any(marker in line for marker in _REFUSE_MARKERS), line


def test_no_codex_invoked_claim() -> None:
    text = _note()
    lowered = text.lower()
    for phrase in _INVOKED_CLAIMS:
        assert phrase not in text, phrase
        assert phrase.lower() not in lowered, phrase
    assert "不 spawn" in text or "不spawn" in "".join(text.split())
    assert "官方 Codex" in text
    assert "不 spawn 官方 Codex" in text or "不spawn官方 Codex" in "".join(text.split())


def test_oneshot_stays_unwired() -> None:
    out = WiredCodex().oneshot({"task": "add a test ProblemProvider"})
    assert out.get("needs_app_server") is True
    assert out.get("tests_green") is False
    assert out.get("not_wired") is True
    assert out.get("tools_called") == []


def test_l102_and_l102d_still_green() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    for name in ("tests/test_l102.py", "tests/test_l102d.py"):
        proc = subprocess.run(
            ["python3", name],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, name + "\n" + proc.stdout + proc.stderr


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_unproven", test_note_exists_unproven),
        ("refuse_tests_green", test_refuses_tests_green_as_done),
        ("no_invoked_claim", test_no_codex_invoked_claim),
        ("oneshot_unwired", test_oneshot_stays_unwired),
        ("l102_l102d_green", test_l102_and_l102d_still_green),
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
