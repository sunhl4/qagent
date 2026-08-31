"""L1-04c: same CI job as Q-02. missing_pack_tests nonempty = fail. No G3 pass claim."""

from __future__ import annotations

import os
import subprocess
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "qagent-eval.yml"
NOTE = REPO / "docs" / "execution" / "L1-04c_ci.md"
HELPER = ROOT / "scripts" / "check_missing_pack_tests.py"

_RUN_TESTS = "PYTHONPATH=src python3 tests/run_tests.py"
_RUN_HARD = "PYTHONPATH=src python3 tests/run_qagent_vs_codex.py"

_G3_PASSED = (
    "G3 通过",
    "G3通过",
    "G3 passed",
    "G3 已通过",
    "G3 验收通过",
)

_OFFICIAL_INVOKED = (
    "official Codex was invoked",
    "invoked official Codex",
    "spawned official Codex",
    "已调官方 Codex",
    "已调用官方 Codex",
    "官方 Codex 已跑",
)


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _note() -> str:
    return NOTE.read_text(encoding="utf-8")


def test_q02b_commands_remain() -> None:
    text = _workflow()
    assert _RUN_TESTS in text
    assert _RUN_HARD in text
    assert "working-directory: qagent" in text


def test_new_step_mentions_gate() -> None:
    text = _workflow()
    assert "missing_pack_tests" in text or "benchmark_v1" in text
    assert "scripts/check_missing_pack_tests.py" in text
    assert HELPER.is_file(), HELPER
    helper = HELPER.read_text(encoding="utf-8")
    assert "missing_pack_tests(Path(" in helper
    assert "cirq" not in helper


def test_no_secrets_or_official() -> None:
    blobs = (_workflow(), _note(), HELPER.read_text(encoding="utf-8"))
    for text in blobs:
        assert "secrets." not in text
        assert "upload-artifact" not in text
        assert "subagent_codex" not in text
        assert "ionstack_twin_run" not in text
        hits = [phrase for phrase in _OFFICIAL_INVOKED if phrase in text]
        assert not hits, hits


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _note()
    assert "missing_pack_tests" in text
    assert "benchmark_v1" in text
    assert _RUN_TESTS in text
    assert _RUN_HARD in text


def test_no_g3_passed() -> None:
    text = _note()
    hits = [phrase for phrase in _G3_PASSED if phrase in text]
    assert not hits, f"note claims G3 passed: {hits}"
    assert "G3 通过" not in text


def test_helper_green_on_current_tree() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        ["python3", str(HELPER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "missing_pack_tests" in proc.stdout


def main() -> int:
    failed = 0
    for name, fn in (
        ("q02b_commands", test_q02b_commands_remain),
        ("new_step", test_new_step_mentions_gate),
        ("no_secrets_official", test_no_secrets_or_official),
        ("note", test_note_exists),
        ("no_g3_passed", test_no_g3_passed),
        ("helper_green", test_helper_green_on_current_tree),
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
