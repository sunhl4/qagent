"""Full-chain Overleaf git-bridge E2E.

Unlike ``test_overleaf_sync.py`` (which stubs ``_remote_url``), this module
talks to a real git smart-HTTP transport: a loopback ``git http-backend``
CGI server plays the deployment's AyakaLeaf git-bridge exactly (clone,
fetch, push over verbatim HTTP), so the chain status → divergence guard →
force pull (+ pre-overwrite snapshot) → edit → push → plan-hub issue note
runs end to end without any transport shortcut. Network stays on 127.0.0.1
and the token never leaves process memory."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from company_agent import overleaf_sync
from company_agent.catalog import load_tools
from company_agent.latex_workspace import _overleaf_pull_backup
from company_agent.latex_sync import PlanError
from company_agent.schema import validate_json_schema

PROJECT_ID = "6adf1c08fafe5c0709551110"
TOKEN = "e2e-bridge-token-v1"
BASE_PORT_ENV = "COMPANY_AGENT_OVERLEAF_GIT_BASE"
TOKEN_ENV = "COMPANY_AGENT_OVERLEAF_GIT_TOKEN"

SEED_MAIN = "online original\n"
PDF_BYTES = b"%PDF-1.4 compiled artifact for issue note\n" * 64


class _BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _backend(self) -> str:
        exec_path = subprocess.run(
            ["git", "--exec-path"], check=True, capture_output=True, text=True
        ).stdout.strip()
        for name in ("git-http-backend.exe", "git-http-backend"):
            candidate = Path(exec_path) / name
            if candidate.is_file():
                return str(candidate)
        raise RuntimeError("git http-backend is unavailable")

    def _run_cgi(self, body: bytes | None) -> tuple[int, dict[str, str], bytes]:
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        command, _, git_path = path.partition("/git/")
        if command != "" or "/git/" not in self.path:
            return 404, {"Content-Type": "text/plain"}, b"not a git bridge path"
        environment = dict(os.environ)
        environment.update({
            "GIT_PROJECT_ROOT": str(_BridgeHandler.repo_root),
            "GIT_HTTP_EXPORT_ALL": "1",
            "GATEWAY_INTERFACE": "CGI/1.1",
            "REQUEST_METHOD": self.command,
            "PATH_INFO": "/" + git_path,
            "QUERY_STRING": parsed.query,
            "REMOTE_ADDR": self.client_address[0],
            "SERVER_PROTOCOL": self.request_version,
        })
        expected = "Basic " + __import__("base64").b64encode(
            ("git:" + TOKEN).encode()
        ).decode()
        authorization = self.headers.get("Authorization") or ""
        if authorization != expected:
            # curl sends Basic auth only after a 401 challenge; the bridge
            # therefore challenges first and rejects a wrong token, exactly
            # like the deployment (username "git", token as password). Failed
            # auth responses also drop the keep-alive connection so a failed
            # client cannot linger on it.
            environment.pop("HTTP_AUTHORIZATION", None)
            self.close_connection = True
            return (401,
                    {"Content-Type": "text/plain",
                     "WWW-Authenticate": 'Basic realm="git-bridge"',
                     "Connection": "close"},
                    b"wrong bridge token")
        environment["HTTP_AUTHORIZATION"] = authorization
        if body is not None:
            environment["CONTENT_LENGTH"] = str(len(body))
        content_type = self.headers.get("Content-Type")
        if content_type:
            environment["CONTENT_TYPE"] = content_type
        backend = self._backend()
        process = subprocess.run(
            [backend],
            input=body if body is not None else b"",
            capture_output=True,
            env=environment,
            timeout=60,
        )
        raw = process.stdout
        head, _, payload = raw.partition(b"\r\n\r\n")
        if not payload:
            head, _, payload = raw.partition(b"\n\n")
        status = 200
        headers: dict[str, str] = {}
        for line in head.decode("latin-1").splitlines():
            if not line.strip():
                continue
            k, _, v = line.partition(":")
            if k.strip().casefold() == "status":
                status = int(v.strip().split()[0])
            else:
                headers[k.strip()] = v.strip()
        headers["Content-Length"] = str(len(payload))
        return (status if status else 200), headers, payload

    def _respond(self, body: bytes | None) -> None:
        status, headers, payload = self._run_cgi(body)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._respond(None)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._respond(body)

    def do_HEAD(self) -> None:  # noqa: N802 - http.server API
        self._respond(None)

    def log_message(self, *_args) -> None:  # noqa: N802 - http.server API
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return


_BridgeHandler.repo_root = None


def _seed_remote(root: Path) -> None:
    seed = root / "seed"
    seed.mkdir()
    def _git(*args: str) -> None:
        subprocess.run(["git", "-C", str(seed), *args], check=True, capture_output=True)
    _git("init", "-b", "main")
    (seed / "main.tex").write_text(SEED_MAIN, encoding="utf-8")
    _git("add", "-A")
    _git("-c", "user.name=seed", "-c", "user.email=seed@bridge", "commit", "-m", "seed")
    bare = _BridgeHandler.repo_root / f"{PROJECT_ID}.git"
    _git("clone", "--bare", ".", str(bare))
    subprocess.run(
        ["git", "-C", str(bare), "config", "http.receivepack", "true"],
        check=True, capture_output=True,
    )


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
def bridge(monkeypatch, tmp_path: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    _BridgeHandler.repo_root = tmp_path / "repos"
    _BridgeHandler.repo_root.mkdir()
    _seed_remote(_BridgeHandler.repo_root)
    thread.start()
    monkeypatch.setenv(BASE_PORT_ENV, f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    monkeypatch.delenv("COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST", raising=False)
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=3)
        _BridgeHandler.repo_root = None


def test_e2e_status_pull_push_is_real_http_transport(workspace, bridge) -> None:
    # 1. status compares the local edit against the online head over real HTTP.
    status = overleaf_sync.status_of(workspace, {"project_id": PROJECT_ID})
    assert status["online_head"] and status["total"] >= 1
    paths = {row["path"] + ":" + row["difference"] for row in status["differences"]}
    assert "main.tex:modified" in paths

    # 2. the divergence guard blocks a plain pull over the real transport.
    before = (workspace / "main.tex").read_text(encoding="utf-8")
    with pytest.raises(PlanError) as raised:
        overleaf_sync.pull_into(workspace, {"project_id": PROJECT_ID})
    assert "locally modified" in str(raised.value) and "force" in str(raised.value)
    assert (workspace / "main.tex").read_text(encoding="utf-8") == before

    # 3. force pull snapshots the replaced local bytes and imports online content.
    payload = overleaf_sync.pull_into(
        workspace, {"project_id": PROJECT_ID, "force": True}, _overleaf_pull_backup(workspace)
    )
    contract = load_tools()["company_latex_overleaf_pull"]
    validate_json_schema(payload, contract["output"], path="result")
    assert payload["overwritten"] == 1 and payload["files"] == 1
    assert (workspace / "main.tex").read_bytes() == SEED_MAIN.encode()
    checkpoint = payload["checkpoint"]
    snapshot = workspace / ".latex-snapshots" / checkpoint / "main.tex"
    assert "Overleaf pilot." in snapshot.read_text(encoding="utf-8")

    # 4. edit and push to the bridge: the bare repo advances for real.
    (workspace / "main.tex").write_text("edited online copy from e2e\n", encoding="utf-8")
    (workspace / "refs.bib").write_text("@article{a, title={A}}\n", encoding="utf-8")
    rows = sorted(
        (relative, workspace.joinpath(*relative.split("/")))
        for relative in ("main.tex", "refs.bib")
    )
    pushed = overleaf_sync.push_from(
        workspace, rows, {"project_id": PROJECT_ID, "message": "e2e push chain"}
    )
    assert pushed["changes"] == 2 and pushed["branch"] == "main"
    verify = _BridgeHandler.repo_root / "verify-clone"
    subprocess.run(
        ["git", "clone", "--branch", "main",
         str(_BridgeHandler.repo_root / f"{PROJECT_ID}.git"), str(verify)],
        check=True, capture_output=True,
    )
    assert (verify / "main.tex").read_text(encoding="utf-8") == "edited online copy from e2e\n"
    assert "@article{a" in (verify / "refs.bib").read_text(encoding="utf-8")

    # 5. a subsequent push with nothing new is refused honestly (fail-closed).
    with pytest.raises(PlanError) as raised:
        overleaf_sync.push_from(
            workspace, rows, {"project_id": PROJECT_ID, "message": "no-op"}
        )
    assert "no changes to commit" in str(raised.value)


def test_e2e_wrong_token_is_fail_closed(workspace, bridge, monkeypatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, "wrong-token")
    with pytest.raises(PlanError) as raised:
        overleaf_sync.status_of(workspace, {"project_id": PROJECT_ID})
    message = str(raised.value)
    assert "authentication" in message
    assert TOKEN not in message and "wrong-token" not in message


def test_e2e_no_token_leaks_into_results(workspace, bridge) -> None:
    payload = overleaf_sync.pull_into(
        workspace, {"project_id": PROJECT_ID, "force": True}, _overleaf_pull_backup(workspace)
    )
    encoded = json.dumps(payload)
    assert TOKEN not in encoded and "127.0.0.1" not in encoded
