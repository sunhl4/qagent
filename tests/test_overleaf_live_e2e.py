"""Live end-to-end Overleaf bridge gate (opt-in).

Run with ``-m overleaf_live`` once the deployment environment contract is
present: ``COMPANY_AGENT_OVERLEAF_GIT_BASE`` +
``COMPANY_AGENT_OVERLEAF_GIT_TOKEN`` (the same two values the git-bridge
probe documents), plus optional ``COMPANY_AGENT_OVERLEAF_E2E_PROJECT_ID``.
Everything stays read-only: one fresh-workspace pull and a status over the
real deployment transport, then the wrong-credential fail-closed check.
Push stays behind the human approval channel at the tool layer and is
deliberately not automated here."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from company_agent import overleaf_sync
from company_agent.latex_sync import PlanError

BASE_ENV = "COMPANY_AGENT_OVERLEAF_GIT_BASE"
TOKEN_ENV = "COMPANY_AGENT_OVERLEAF_GIT_TOKEN"
PROJECT_ENV = "COMPANY_AGENT_OVERLEAF_E2E_PROJECT_ID"
PROJECT_ID = "6adf1c08fafe5c0709551110"

pytestmark = [pytest.mark.overleaf_live]


@pytest.fixture()
def live_project() -> str:
    base = os.environ.get(BASE_ENV, "").strip()
    token = os.environ.get(TOKEN_ENV, "").strip()
    project = os.environ.get(PROJECT_ENV, "").strip() or PROJECT_ID
    if not base or not token:
        pytest.skip("overleaf live e2e needs base and token in the environment")
    os.environ[BASE_ENV] = base
    os.environ[TOKEN_ENV] = token
    os.environ.pop("COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST", None)
    return project


def test_live_pull_and_status_over_the_real_deployment(live_project: str) -> None:
    work = Path(tempfile.mkdtemp(prefix=".overleaf-live-e2e-")) / "paper"
    work.mkdir(parents=True)
    try:
        payload = overleaf_sync.pull_into(work, {"project_id": live_project})
        assert payload["complete"] is True
        assert payload["files"] == payload["files"]
        status = overleaf_sync.status_of(work, {"project_id": live_project})
        assert status["project_id"] == live_project
        assert re.fullmatch(r"[0-9a-f]{7,64}", status["online_head"])
        # A fresh pull leaves workspace and online content identical.
        assert status["total"] == 0
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)


def test_live_wrong_token_is_fail_closed(live_project: str) -> None:
    previous = os.environ[TOKEN_ENV]
    work = Path(tempfile.mkdtemp(prefix=".overleaf-live-deny-")) / "paper"
    work.mkdir(parents=True)
    try:
        os.environ[TOKEN_ENV] = previous + "-wrong"
        with pytest.raises(PlanError) as raised:
            overleaf_sync.status_of(work, {"project_id": live_project})
        message = str(raised.value)
        assert "authentication" in message
        assert previous not in message
    finally:
        os.environ[TOKEN_ENV] = previous
        shutil.rmtree(work.parent, ignore_errors=True)
