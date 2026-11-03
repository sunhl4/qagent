"""Installed-wheel gates: the wheel must never read workspace contracts, and
the packaged kernel must run with the packaged contract set alone."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


def _hermetic_child_env(target: Path) -> dict[str, str]:
    """Parent environment minus workspace and agent overrides.

    Windows conda children need the interpreter's DLL/provider environment
    (PATH, CONDA, locale variables) to initialize SSL at import time; the
    workspace-isolation property only concerns code/contract discovery. Those
    paths (plus any inherited agent context) are re-pinned to the installed
    wheel tree instead."""

    env: dict[str, str] = {}
    for key, value in os.environ.items():
        folded = key.casefold()
        if folded.startswith(("python", "company_agent", "company_relay", "company_overleaf",
                              "uqc_", "deepseek", "openai", "anthropic", "gitlab")):
            continue
        env[key] = value
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(target)
    return env


def test_wheel_does_not_read_sibling_workspace_contracts(tmp_path: Path, built_wheel: Path) -> None:
    wheel = built_wheel
    target = tmp_path / "site"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    sibling_contracts = tmp_path / "contracts"
    sibling_contracts.mkdir()
    (sibling_contracts / "tools.json").write_text('{"tools": []}', encoding="utf-8")
    code = (
        "from company_agent.catalog import load_tools; "
        "from company_agent.knowledge import search; "
        "print(len(load_tools()), len(search({'query': '设备执行'})['hits']))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=_hermetic_child_env(target),
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "70 1"


def test_built_wheel_runs_without_workspace_source(tmp_path: Path, built_wheel: Path) -> None:
    wheel = built_wheel
    target = tmp_path / "site"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    code = (
        "from company_agent.capabilities import list_capabilities; "
        "from company_agent.invoke import invoke; "
        "assert invoke('company_capabilities', 'lab', {}).status == 'ok'; "
        "print(len(list_capabilities()))"
    )
    env = _hermetic_child_env(target)
    # The wheel proves it can work without workspace contracts; the
    # receipt/ledger identity still stays hermetic per run so the
    # termination budget never accumulates outside this test.
    env["COMPANY_AGENT_TURN_ID"] = f"probe-{uuid.uuid4().hex[:16]}"
    env["COMPANY_AGENT_RECEIPT_DIR"] = tempfile.mkdtemp(prefix="company-agent-wheel-")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "13"
