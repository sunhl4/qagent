"""Offline regression for the Overleaf git-bridge probe.

The probe is the deployment-facing acceptance gate for the adapter's
``COMPANY_AGENT_OVERLEAF_*`` environment contract. It must stay fail-closed:

- offline runs never touch the network and record ``executed: false``;
- a missing credential, malformed base URL, or allowlist miss fails the run;
- the evidence file never contains the token, the base URL, or a full ref
  listing - the head SHA of the probed branch is the only observable fact;
- the read-only ``ls-remote`` listing accepts a healthy local repository and
  rejects a bounded-size violation.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location("probe_overleaf_git", ROOT / "scripts/probe_overleaf_git.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = "http://192.0.2.10:8001"
TOKEN = "s3cr3t-overleaf-token"
PROJECT_ID = "6adf1c08fafe5c0709551110"


@pytest.fixture()
def overleaf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_OVERLEAF_GIT_BASE", BASE)
    monkeypatch.setenv("COMPANY_AGENT_OVERLEAF_GIT_TOKEN", TOKEN)
    monkeypatch.delenv("COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST", raising=False)


def _evidence(output: Path) -> dict:
    return json.loads(output.read_text(encoding="utf-8"))


def test_offline_run_records_not_executed(probe, overleaf_env, tmp_path: Path) -> None:
    output = tmp_path / "probe.json"
    code = probe.main([
        "--base-url", BASE,
        "--project-id", PROJECT_ID,
        "--output", str(output),
    ])
    assert code == 0
    payload = _evidence(output)
    assert payload["executed"] is False
    assert payload["ok"] is False
    by_name = {row["check"]: row for row in payload["checks"]}
    assert by_name["config_shape"]["ok"] is True
    for name in ("authentication", "branch_present", "refs_shape"):
        assert by_name[name]["ok"] is False
        assert "not executed" in by_name[name]["detail"]
    assert TOKEN not in output.read_text(encoding="utf-8")


def test_offline_run_without_credential_fails_closed(probe, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("COMPANY_AGENT_OVERLEAF_GIT_TOKEN", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_OVERLEAF_GIT_BASE", raising=False)
    output = tmp_path / "probe.json"
    code = probe.main([
        "--base-url", BASE,
        "--project-id", PROJECT_ID,
        "--output", str(output),
    ])
    assert code == 1
    payload = _evidence(output)
    by_name = {row["check"]: row for row in payload["checks"]}
    assert by_name["config_shape"]["ok"] is False
    assert "credential is not configured" in by_name["config_shape"]["detail"]


def test_allowlist_miss_fails_configuration(probe, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_OVERLEAF_GIT_BASE", BASE)
    monkeypatch.setenv("COMPANY_AGENT_OVERLEAF_GIT_TOKEN", TOKEN)
    monkeypatch.setenv("COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST", "0123456789abcdef123456")
    output = tmp_path / "probe.json"
    code = probe.main([
        "--base-url", BASE,
        "--project-id", PROJECT_ID,
        "--output", str(output),
    ])
    assert code == 1
    payload = _evidence(output)
    by_name = {row["check"]: row for row in payload["checks"]}
    assert by_name["config_shape"]["ok"] is False


def test_online_head_with_bad_base_url_records_plan_error(probe, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_OVERLEAF_GIT_TOKEN", TOKEN)
    monkeypatch.delenv("COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST", raising=False)
    output = tmp_path / "probe.json"
    code = probe.main([
        "--base-url", "http://127.0.0.1:9",  # closed port: connection refused, nothing listens
        "--project-id", PROJECT_ID,
        "--live",
        "--output", str(output),
    ])
    assert code == 1
    payload = _evidence(output)
    assert payload["executed"] is True
    by_name = {row["check"]: row for row in payload["checks"]}
    assert by_name["config_shape"]["ok"] is True
    assert by_name["authentication"]["ok"] is False
    assert TOKEN not in output.read_text(encoding="utf-8")
    assert BASE not in output.read_text(encoding="utf-8")


def _committed_repo(directory: Path) -> None:
    def git(*arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=directory, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "probe@example.invalid")
    git("config", "user.name", "probe")
    (directory / "main.tex").write_text("\\section{probe}\n", encoding="utf-8")
    git("add", "main.tex")
    git("commit", "-m", "probe seed")


def test_ref_listing_accepts_local_repository_flat(probe, tmp_path: Path) -> None:
    repo = tmp_path / "upstream"
    repo.mkdir()
    _committed_repo(repo)
    rows = probe._ls_remote_ref_listing(str(repo), token="", base_url="")
    assert [row[1] for row in rows] == ["refs/heads/main"]
    assert all(len(row[0]) == 40 and row[0].lower() == row[0] for row in rows)


def test_ref_listing_rejects_oversized_listing(probe, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe, "MAX_REFS", 2)
    fake = "\n".join(
        f"{index:040x}\trefs/heads/branch-{index}" for index in range(3)
    )
    monkeypatch.setattr(
        "company_agent.overleaf_sync.subprocess.run",
        lambda *arguments, **keyword: _FakeCompleted(fake),  # noqa: ARG005
    )
    with pytest.raises(probe.PlanError):
        probe._ls_remote_ref_listing("http://192.0.2.10:8001/git/" + PROJECT_ID, token=TOKEN, base_url=BASE)


class _FakeCompleted:
    def __init__(self, stdout: str) -> None:
        self.returncode = 0
        self.stdout = stdout.encode("utf-8")
        self.stderr = b""


def test_ref_listing_scrubs_token_from_transport_failure(probe, monkeypatch: pytest.MonkeyPatch) -> None:
    leak = f"fatal: Authentication failed for git-bridge with token {TOKEN}"
    monkeypatch.setattr(
        "company_agent.overleaf_sync.subprocess.run",
        lambda *arguments, **keyword: _FakeFailure(leak),  # noqa: ARG005
    )
    with pytest.raises(probe.PlanError) as catch:
        probe._ls_remote_ref_listing("http://192.0.2.10:8001/git/" + PROJECT_ID, token=TOKEN, base_url=BASE)
    assert TOKEN not in str(catch.value)
    assert "rejected authentication" in str(catch.value)


class _FakeFailure:
    def __init__(self, stderr: str) -> None:
        self.returncode = 128
        self.stdout = b""
        self.stderr = stderr.encode("utf-8")
