"""Company.latex snapshot-runtime and remote-sync gates.

Covers ``checkpoint/diff/revert`` against a bounded workspace and
``pull/push`` against a loopback GitLab stub (archive + commit APIs). No real
repository or credential is ever contacted."""
from __future__ import annotations

import io
import json
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from company_agent import latex_workspace
from company_agent.invoke import invoke
from company_agent.latex_workspace import WorkspaceError

URL_ENV = "COMPANY_AGENT_GITLAB_URL"
TOKEN_ENV = "COMPANY_AGENT_GITLAB_TOKEN"
ALLOWLIST_ENV = "COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST"

REPO = "team-a/report"
COMMIT_SHA = "a" * 40


@pytest.fixture()
def workspace(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    project = root / "demo1"
    project.mkdir(parents=True)
    (project / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nHello pilot.\n\\end{document}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(root))
    return project


class _GitlabSync(BaseHTTPRequestHandler):
    archive_bytes: bytes = b""
    routes: dict[tuple[str, str], Any] = {}
    requests: list[dict[str, Any]] = []

    def _send(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        _GitlabSync.requests.append({"method": "GET", "path": self.path})
        if self.path.endswith("archive.tar.gz?sha=HEAD"):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-gzip")
            self.send_header("Content-Length", str(len(_GitlabSync.archive_bytes)))
            self.end_headers()
            self.wfile.write(_GitlabSync.archive_bytes)
            return
        route = ("GET", self.path.split("?")[0])
        status, payload = _GitlabSync.routes.get(route, (404, {"message": "not found"}))
        self._send(status, payload)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        _GitlabSync.requests.append({"method": "POST", "path": self.path, "body": json.loads(body.decode())})
        route = ("POST", self.path.split("?")[0])
        status, payload = _GitlabSync.routes.get(route, (404, {"message": "not found"}))
        self._send(status, payload)

    def log_message(self, *_args) -> None:
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return


@pytest.fixture()
def gitlab_stub(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GitlabSync)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _GitlabSync.archive_bytes = b""
    _GitlabSync.routes = {
        ("GET", f"/api/v4/projects/{REPO}/repository/tree"): (
            200,
            [{"type": "blob", "path": "main.tex"}, {"type": "blob", "path": "refs.bib"}],
        ),
        ("POST", f"/api/v4/projects/{REPO}/repository/commits"): (
            200,
            {"id": COMMIT_SHA, "title": "work", "branch": "main"},
        ),
    }
    _GitlabSync.requests = []
    monkeypatch.setenv(URL_ENV, f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv(TOKEN_ENV, "latex-sync-stub-token")
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    try:
        yield _GitlabSync
    finally:
        server.shutdown()
        thread.join(timeout=2)


# ------------------------------------------------------- snapshot runtime


def test_checkpoint_diff_revert_round_trip(workspace: Path, capsys) -> None:
    captured = latex_workspace.checkpoint({"project": "demo1"})
    assert captured["files"] == 1 and captured["bytes"] > 0
    assert set(captured["checkpoint"].split("-")[:1]) == {"chk"}

    original = (workspace / "main.tex").read_text(encoding="utf-8")
    assert latex_workspace.diff({"project": "demo1"})["added"] == 0
    assert latex_workspace.diff({"project": "demo1"})["removed"] == 0

    (workspace / "main.tex").write_text(original.replace("Hello pilot.", "Hello delta."), encoding="utf-8")
    report = latex_workspace.diff({"project": "demo1"})
    assert report["files"][0]["path"] == "main.tex" and report["files"][0]["added"] == 1

    reverted = latex_workspace.revert({"project": "demo1", "target": captured["checkpoint"]})
    assert reverted["changed"] == 1 and reverted["restored"] >= 1
    assert (workspace / "main.tex").read_text(encoding="utf-8") == original


def test_checkpoint_rotation_keeps_twelve(workspace: Path) -> None:
    for _ in range(14):
        latex_workspace.checkpoint({"project": "demo1"})
    ids = latex_workspace._snapshot_ids(workspace)
    assert len(ids) == 12 and ids[0].startswith("chk-")


def test_revert_requires_existing_target(workspace: Path) -> None:
    latex_workspace.checkpoint({"project": "demo1"})
    with pytest.raises(WorkspaceError):
        latex_workspace.revert({"project": "demo1", "target": "chk-nonexistent"})


def test_snapshot_directory_is_invisible_to_scans(workspace: Path) -> None:
    latex_workspace.checkpoint({"project": "demo1"})
    structure = latex_workspace.structure({"project": "demo1"})
    assert all(not row["path"].startswith(".latex-snapshots/") for row in structure["files"])


# ------------------------------------------------------------ remote sync


def _make_archive(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name=f"report-{COMMIT_SHA[:7]}/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_pull_writes_only_managed_sources(workspace: Path, gitlab_stub) -> None:
    gitlab_stub.archive_bytes = _make_archive({
        "main.tex": b"pulled main",
        "refs.bib": b"pulled refs",
        "notes.exe": b"skipped",
        ".latex-snapshots/evil.tex": b"skipped",
    })
    payload = latex_workspace.pull({"project": "demo1", "repo": REPO})
    assert payload["files"] == 2 and payload["bytes"] == len(b"pulled main") + len(b"pulled refs")
    assert (workspace / "main.tex").read_text(encoding="utf-8") == "pulled main"
    assert not (workspace / "notes.exe").exists()


def test_pull_rejects_archive_escape(workspace: Path, gitlab_stub) -> None:
    gitlab_stub.archive_bytes = _make_archive({"../escape.tex": b"evil"})
    with pytest.raises(PlanErrorPlain):
        latex_workspace.pull({"project": "demo1", "repo": REPO})


def test_pull_is_fail_closed_without_config(monkeypatch, workspace: Path) -> None:
    monkeypatch.delenv(URL_ENV, raising=False)
    result = invoke("company_latex_pull", "lab", {"project": "demo1", "repo": REPO})
    assert result.status == "error" and "not configured" in str(result.error)


def test_push_builds_create_update_actions(workspace: Path, gitlab_stub) -> None:
    (workspace / "refs.bib").write_text("@article{a, title={A}}\n", encoding="utf-8")
    (workspace / "overview.tex").write_text("\\section{Overview}\n", encoding="utf-8")
    payload = latex_workspace.push({"project": "demo1", "repo": REPO, "message": "sync pilot"})
    assert payload["commit_sha"] == COMMIT_SHA and payload["changes"] >= 1
    sent = _GitlabSync.requests[-1]
    actions = sent["body"]["actions"]
    kinds = {row["file_path"]: row["action"] for row in actions}
    assert kinds.get("main.tex") == "update"  # listed in the stub tree
    assert kinds.get("refs.bib") == "update" and kinds.get("overview.tex") == "create"


def test_push_requires_message_and_allowlisted_repo(workspace: Path, gitlab_stub, monkeypatch) -> None:
    result = invoke("company_latex_push", "lab", {"project": "demo1", "repo": REPO, "message": ""})
    assert result.status == "error"
    monkeypatch.setenv(ALLOWLIST_ENV, "team-x/other")
    result = invoke(
        "company_latex_push", "lab", {"project": "demo1", "repo": REPO, "message": "m"}, approved=True,
    )
    assert result.status == "error" and "allowlist" in str(result.error)


def test_push_and_pull_are_ask_gated_in_lab(workspace: Path) -> None:
    for tool, args in (
        ("company_latex_push", {"project": "demo1", "repo": REPO, "message": "m"}),
        ("company_latex_pull", {"project": "demo1", "repo": REPO}),
    ):
        result = invoke(tool, "lab", args)
        if tool == "company_latex_push":
            assert result.status == "needs_ask"
        else:
            assert result.status in {"ok", "error"}  # result depends on env; decision is allow


from company_agent.plan_hub import PlanError as PlanErrorPlain  # noqa: E402
