"""Q-02b: PR CI runs E01–E21 + Q-01 hard rails. No secrets, no official Codex."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "qagent-eval.yml"

_RUN_TESTS = "PYTHONPATH=src python3 tests/run_tests.py"
_RUN_HARD = "PYTHONPATH=src python3 tests/run_qagent_vs_codex.py"


def test_workflow_exists() -> None:
    assert WORKFLOW.is_file(), WORKFLOW


def test_workflow_commands_and_cwd() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert _RUN_TESTS in text
    assert _RUN_HARD in text
    assert "working-directory: qagent" in text
    assert "secrets." not in text
    assert "upload-artifact" not in text
    assert "subagent_codex" not in text
    assert "ionstack_twin_run" not in text


def main() -> int:
    test_workflow_exists()
    print("ok  q02b_workflow_exists")
    test_workflow_commands_and_cwd()
    print("ok  q02b_commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
