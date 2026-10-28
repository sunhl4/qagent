"""Overleaf Git-bridge adapter gates.

Covers ``company_latex_overleaf_pull`` / ``company_latex_overleaf_push``
against a local bare Git repository acting as the remote. No network host is
ever contacted and no credential is ever written to disk."""
from __future__ import annotations

import subprocess
import re
from pathlib import Path

import pytest

from company_agent import overleaf_sync
from company_agent.invoke import invoke
from company_agent.latex_sync import PlanError

BASE_ENV = "COMPANY_AGENT_OVERLEAF_GIT_BASE"
TOKEN_ENV = "COMPANY_AGENT_OVERLEAF_GIT_TOKEN"
ALLOWLIST_ENV = "COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST"

PROJECT_ID = "6adf1c08fafe5c0709551110"


def _git(target: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True)


def _author(target: Path, *args: str) -> None:
    _git(target, "-c", "user.name=seed", "-c", "user.email=seed@local", *args)


@pytest.fixture()
def workspace(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    project = root / "paper"
    project.mkdir(parents=True)
    (project / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nOverleaf pilot.\n\\end{document}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(root))
    return project


@pytest.fixture()
def remote(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """A bare seed repository used as the git-bridge remote."""

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init")
    (seed / "main.tex").write_text("online original\n", encoding="utf-8")
    (seed / "missing.suffix").write_text("not managed", encoding="utf-8")
    _git(seed, "add", "-A")
    _author(seed, "commit", "-m", "seed")
    _git(seed, "branch", "-M", "main")
    bare = tmp_path / "remote.git"
    _git(seed, "clone", "--bare", str(seed), str(bare))
    monkeypatch.setenv(BASE_ENV, "http://192.168.110.71:8001")
    monkeypatch.setenv(TOKEN_ENV, "bridge-stub-token")
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(overleaf_sync, "_remote_url", lambda base, token, pid: str(bare))
    return seed, bare


def test_pull_imports_only_managed_files(workspace: Path, remote) -> None:
    from company_agent.latex_workspace import _overleaf_pull_backup

    payload = overleaf_sync.pull_into(
        workspace,
        {"project_id": PROJECT_ID, "force": True},
        _overleaf_pull_backup(workspace),
    )
    assert payload["project"] == "paper" and payload["files"] == 1
    assert payload["overwritten"] == 1 and "checkpoint" in payload
    assert (workspace / "main.tex").read_text(encoding="utf-8") == "online original\n"
    assert not (workspace / "missing.suffix").exists()


def test_pull_fails_closed_when_local_edit_would_be_overwritten(
    workspace: Path, remote
) -> None:
    # The workspace copy differs from the online head: a plain pull must stop
    # and name the position instead of silently replacing the local edit.
    before = (workspace / "main.tex").read_text(encoding="utf-8")
    with pytest.raises(PlanError) as raised:
        overleaf_sync.pull_into(workspace, {"project_id": PROJECT_ID})
    message = str(raised.value)
    assert "locally modified" in message and "main.tex" in message and "force" in message
    assert (workspace / "main.tex").read_text(encoding="utf-8") == before


def test_same_content_pull_never_blocks(workspace: Path, remote) -> None:
    (workspace / "main.tex").write_text("online original\n", encoding="utf-8")
    payload = overleaf_sync.pull_into(workspace, {"project_id": PROJECT_ID})
    assert payload["files"] == 1 and payload["overwritten"] == 0


def test_pull_ignores_pure_newline_differences(workspace: Path, remote) -> None:
    (workspace / "main.tex").write_bytes(b"online original\r\n")
    payload = overleaf_sync.pull_into(workspace, {"project_id": PROJECT_ID})
    assert payload["overwritten"] == 0
    # No edit was lost: the pull keeps the online bytes (LF on this bridge)
    # because CRLF versus LF is a host artifact, not a content change.
    assert (workspace / "main.tex").read_bytes() == b"online original\n"


def test_force_pull_snapshots_replaced_content_before_overwrite(
    workspace: Path, remote
) -> None:
    from company_agent.latex_workspace import _overleaf_pull_backup

    backup = _overleaf_pull_backup(workspace)
    payload = overleaf_sync.pull_into(
        workspace, {"project_id": PROJECT_ID, "force": True}, backup
    )
    assert payload["overwritten"] == 1
    checkpoint = payload.get("checkpoint", "")
    assert re.fullmatch(r"chk-[0-9]{14}-[0-9a-f]{6}", checkpoint)
    restored = workspace / ".latex-snapshots" / checkpoint / "main.tex"
    assert restored.read_text(encoding="utf-8") == "\\documentclass{article}\n\\begin{document}\nOverleaf pilot.\n\\end{document}\n"
    assert (workspace / "main.tex").read_text(encoding="utf-8") == "online original\n"


def test_force_pull_without_backup_callback_is_refused(
    workspace: Path, remote
) -> None:
    with pytest.raises(PlanError):
        overleaf_sync.pull_into(workspace, {"project_id": PROJECT_ID, "force": True})


def test_overleaf_pull_divergence_is_reported_through_invoke(
    workspace: Path, remote
) -> None:
    result = invoke(
        "company_latex_overleaf_pull", "lab", {"project": "paper", "project_id": PROJECT_ID}
    )
    assert result.status == "error"
    assert "locally modified" in str(result.error) and "main.tex" in str(result.error)


def test_overleaf_force_pull_passes_the_output_contract(
    workspace: Path, remote
) -> None:
    payload = overleaf_sync.pull_into(
        workspace,
        {"project_id": PROJECT_ID, "force": True},
        _backup_callback(workspace),
    )
    from company_agent.schema import validate_json_schema
    from company_agent.catalog import load_tools

    contract = load_tools()["company_latex_overleaf_pull"]
    validate_json_schema(payload, contract["output"], path="result")
    payload_clean = {key: value for key, value in payload.items() if key != "checkpoint"}
    with pytest.raises(Exception):
        validate_json_schema(
            {**payload_clean, "bogus": True}, contract["output"], path="result"
        )


def _backup_callback(workspace: Path):
    from company_agent.latex_workspace import _overleaf_pull_backup

    return _overleaf_pull_backup(workspace)



def test_pull_is_fail_closed_without_config(workspace: Path, monkeypatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    result = invoke("company_latex_overleaf_pull", "lab", {"project": "paper", "project_id": PROJECT_ID})
    assert result.status == "error" and "credential" in str(result.error)


def test_pull_respects_allowlist(workspace: Path, remote, monkeypatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, "1111111111111111111111111111")
    result = invoke(
        "company_latex_overleaf_pull", "lab", {"project": "paper", "project_id": PROJECT_ID}, approved=True,
    )
    assert result.status == "error" and "allowlist" in str(result.error)


def test_remote_url_keeps_canonical_git_bridge_shape() -> None:
    # The deployment URL shape from the tutorial: <base>/git/<project_id>; a
    # pathless base must never silently drop the /git/<id> segment (a prior
    # regression here made live clones hit the server root).
    remote = overleaf_sync._remote_url(
        "http://192.168.110.71:8001", "tok", PROJECT_ID
    )
    assert remote == "http://git:tok@192.168.110.71:8001/git/" + PROJECT_ID
    remote = overleaf_sync._remote_url(
        "https://git.example.internal/ctl", "tok", PROJECT_ID
    )
    assert remote == "https://git:tok@git.example.internal/ctl/git/" + PROJECT_ID


def test_pull_rejects_bad_project_id(workspace: Path, remote) -> None:
    with pytest.raises(PlanError):
        overleaf_sync.pull_into(workspace, {"project_id": "../escape"})


def test_status_reports_workspace_vs_online_head(workspace: Path, remote) -> None:
    payload = overleaf_sync.status_of(workspace, {"project_id": PROJECT_ID})
    assert payload["project"] == "paper"
    assert payload["branch"] == "main" and re.fullmatch(r"[0-9a-f]{7,64}", payload["online_head"])
    assert payload["online_managed"] == 1 and payload["local_managed"] == 1
    assert payload["total"] >= 1
    paths = {row["path"] + ":" + row["difference"] for row in payload["differences"]}
    assert "main.tex:modified" in paths
    assert payload["differences"] == sorted(payload["differences"], key=lambda row: row["path"])


def test_status_is_fail_closed_without_config(workspace: Path, monkeypatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    result = invoke("company_latex_overleaf_status", "lab", {"project": "paper", "project_id": PROJECT_ID})
    assert result.status == "error" and "credential" in str(result.error)


def test_status_ignore_unmanaged_and_never_writes(workspace: Path, remote) -> None:
    before = (workspace / "main.tex").read_text(encoding="utf-8")
    overleaf_sync.status_of(workspace, {"project_id": PROJECT_ID})
    assert (workspace / "main.tex").read_text(encoding="utf-8") == before
    assert not (workspace / "missing.suffix").exists()


def test_status_respects_allowlist(workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv(BASE_ENV, "http://192.168.110.71:8001")
    monkeypatch.setenv(TOKEN_ENV, "bridge-stub-token")
    monkeypatch.setenv(ALLOWLIST_ENV, "1111111111111111111111111111")
    with pytest.raises(PlanError):
        overleaf_sync.status_of(workspace, {"project_id": PROJECT_ID})


def test_push_commits_on_top_of_online_head(workspace: Path, remote) -> None:
    seed, bare = remote
    (workspace / "refs.bib").write_text("@article{a, title={A}}\n", encoding="utf-8")
    (workspace / "main.tex").write_text("edited online copy\n", encoding="utf-8")
    (workspace / "untracked.bin").write_bytes(b"skip me")
    rows = [("main.tex", workspace / "main.tex"), ("refs.bib", workspace / "refs.bib")]
    payload = overleaf_sync.push_from(
        workspace,
        rows,
        {"project_id": PROJECT_ID, "message": "agent sync"},
    )
    assert payload["commit_sha"] and payload["changes"] == 2 and payload["branch"] == "main"
    checkout = bare.parent / "verify"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(bare), str(checkout)], check=True, capture_output=True
    )
    assert (checkout / "main.tex").read_text(encoding="utf-8") == "edited online copy\n"
    assert "@article{a" in (checkout / "refs.bib").read_text(encoding="utf-8")
    # push never deletes anything on the remote: the un-managed seed file stays
    assert (checkout / "missing.suffix").exists()


def test_push_is_fail_closed_without_message(workspace: Path, remote) -> None:
    result = invoke(
        "company_latex_overleaf_push", "lab",
        {"project": "paper", "project_id": PROJECT_ID, "message": " "},
    )
    assert result.status == "error"


def test_push_is_ask_gated_in_lab(workspace: Path, remote) -> None:
    result = invoke(
        "company_latex_overleaf_push", "lab",
        {"project": "paper", "project_id": PROJECT_ID, "message": "m"},
    )
    assert result.status == "needs_ask"
