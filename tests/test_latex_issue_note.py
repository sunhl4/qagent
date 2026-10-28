"""``company_latex_issue_note`` gates: the latex push → plan-hub issue PDF
follow-up batch. Every GitLab interaction is a loopback fake; no real plan
hub is contacted and no credential is ever echoed."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from company_agent.catalog import load_tools
from company_agent.invoke import invoke, validate_invocation
from company_agent.policy import decide

URL_ENV = "COMPANY_AGENT_GITLAB_URL"
TOKEN_ENV = "COMPANY_AGENT_GITLAB_TOKEN"
ALLOWLIST_ENV = "COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST"

PROJECT_PATH = "team-a/report"
WORKSPACE_PROJECT = "paper"
ISSUE_IID = 11
PDF_BYTES = b"%PDF-1.4 fake compiled artifact\n"
UPLOAD_LINK = "/uploads/abc123def/main.pdf"


class _Stub(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, Any]] = {}
    requests: list[dict[str, Any]] = []

    def _send(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, body: bytes) -> None:
        self.requests.append({
            "method": self.command,
            "path": self.path.split("?")[0],
            "content_type": str(self.headers.get("Content-Type") or ""),
            "token": str(self.headers.get("PRIVATE-TOKEN") or ""),
            "raw": body,
        })

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._record(body)
        route = self.path.split("?")[0]
        status, payload = self.routes.get((self.command, route), (404, {"message": "not found"}))
        self._send(status, payload)

    def log_message(self, *_args) -> None:  # noqa: N802 - http.server API
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return


@pytest.fixture()
def workspace(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    project = root / WORKSPACE_PROJECT
    (project / ".latex-build" / "pdflatex" / "main").mkdir(parents=True)
    (project / ".latex-build" / "pdflatex" / "main" / "main.pdf").write_bytes(PDF_BYTES)
    (project / "main.tex").write_text("\\documentclass{article}\nhello\n", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(root))
    return project


@pytest.fixture()
def plan_stub(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Stub.routes = {
        ("POST", f"/api/v4/projects/{PROJECT_PATH}/uploads"): (
            200,
            {"alt": "main.pdf", "url": "/uploads/abc123def/main.pdf", "markdown": UPLOAD_LINK},
        ),
        ("POST", f"/api/v4/projects/{PROJECT_PATH}/issues/{ISSUE_IID}/notes"): (
            200,
            {"id": 9100, "body": "note"},
        ),
    }
    _Stub.requests = []
    monkeypatch.setenv(URL_ENV, f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv(TOKEN_ENV, "plan-stub-token")
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    try:
        yield _Stub
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _args(**overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "project": WORKSPACE_PROJECT,
        "repo": PROJECT_PATH,
        "issue_iid": ISSUE_IID,
        "artifact": ".latex-build/pdflatex/main/main.pdf",
        "note": "compiled report attached",
    }
    args.update(overrides)
    return args


def _ok(args: dict[str, Any]) -> dict[str, Any]:
    result = invoke("company_latex_issue_note", "lab", args, approved=True)
    assert result.status == "ok", (result.status, result.error)
    return result.payload


# ------------------------------------------------------------- contract wiring


def test_issue_note_capability_contract_wiring() -> None:
    row = load_tools()["company_latex_issue_note"]
    assert row["capability"] == "company.latex"
    assert row["operation"] == "latex.issue_note"
    assert row["input_handles"] == [] and row["output_handles"] == []


def test_issue_note_is_ask_gated_and_limited_to_lab(plan_stub) -> None:
    assert decide("company_latex_issue_note", "boot", {}) == "deny"
    assert decide("company_latex_issue_note", "algo", {}) == "deny"
    assert decide("company_latex_issue_note", "boot", _args()) == "deny"
    result = invoke("company_latex_issue_note", "lab", _args())
    assert result.status == "needs_ask"


# ------------------------------------------------------------ happy path


def test_issue_note_uploads_pdf_and_posts_one_note(workspace, plan_stub) -> None:
    payload = _ok(_args())
    assert payload == {
        "project": WORKSPACE_PROJECT,
        "repo": PROJECT_PATH,
        "issue_iid": ISSUE_IID,
        "note_id": 9100,
        "attachment": UPLOAD_LINK,
    }
    uploads = [row for row in _Stub.requests if row["path"].endswith("/uploads")]
    notes = [row for row in _Stub.requests if row["path"].endswith(f"/issues/{ISSUE_IID}/notes")]
    assert len(uploads) == 1 and len(notes) == 1
    assert "multipart/form-data" in uploads[0]["content_type"]
    up = uploads[0]["raw"]
    assert up.count(PDF_BYTES) == 1
    assert 'filename="main.pdf"' in up.decode("latin-1")
    note_body = json.loads(notes[0]["raw"].decode("utf-8"))["body"]
    assert "compiled report attached" in note_body and UPLOAD_LINK in note_body
    assert notes[0]["token"] == "plan-stub-token"


def test_issue_note_never_echoes_the_credential(workspace, plan_stub) -> None:
    payload = _ok(_args())
    encoded = json.dumps(payload)
    assert "plan-stub-token" not in encoded


# ------------------------------------------------------------ fail-closed paths


def test_issue_note_rejects_artifact_outside_latex_build(workspace, plan_stub) -> None:
    result = invoke("company_latex_issue_note", "lab", _args(artifact="figures/fig.pdf"), approved=True)
    assert result.status == "error"
    assert "artifact has an invalid format" in str(result.error)


def test_issue_note_rejects_missing_artifact(workspace, plan_stub, monkeypatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, "")
    result = invoke(
        "company_latex_issue_note", "lab",
        _args(artifact=".latex-build/pdflatex/other/main.pdf"), approved=True,
    )
    assert result.status == "error" and "not available" in str(result.error)


def test_issue_note_rejects_oversized_artifact(workspace, plan_stub) -> None:
    big = workspace / ".latex-build" / "pdflatex" / "main" / "main.pdf"
    big.write_bytes(b"\x00" * 10_000_001)
    result = invoke("company_latex_issue_note", "lab", _args(), approved=True)
    assert result.status == "error" and "bounded upload size" in str(result.error)


def test_issue_note_rejects_absolute_upload_link(workspace, plan_stub, monkeypatch) -> None:
    _Stub.routes[("POST", f"/api/v4/projects/{PROJECT_PATH}/uploads")] = (
        200,
        {"markdown": "![main.pdf](https://injh.example/uploads/main.pdf)"},
    )
    result = invoke("company_latex_issue_note", "lab", _args(), approved=True)
    assert result.status == "error" and "invalid attachment link" in str(result.error)


def test_issue_note_rejects_upload_failure(workspace, plan_stub) -> None:
    _Stub.routes[("POST", f"/api/v4/projects/{PROJECT_PATH}/uploads")] = (
        502,
        {"message": "bad gateway"},
    )
    result = invoke("company_latex_issue_note", "lab", _args(), approved=True)
    assert result.status == "error" and "service error" in str(result.error)


def test_issue_note_rejects_bad_repo_path(workspace, plan_stub) -> None:
    result = invoke("company_latex_issue_note", "lab", _args(repo="../escape"), approved=True)
    assert result.status == "error" and "invalid" in str(result.error)


def test_issue_note_argument_envelope_is_fail_closed() -> None:
    assert validate_invocation("company_latex_issue_note", _args(issue_iid=0)) is not None
    assert validate_invocation("company_latex_issue_note", _args(issue_iid=True)) is not None
    assert validate_invocation(
        "company_latex_issue_note", _args(artifact=".latex-build/../escape/main.pdf")
    ) is not None
    assert validate_invocation(
        "company_latex_issue_note", _args(artifact=".latex-build/pdflatex/main/main.log")
    ) is not None
    assert validate_invocation("company_latex_issue_note", _args(note="  ")) is not None
    assert validate_invocation("company_latex_issue_note", _args(note="x" * 401)) is not None
    assert validate_invocation("company_latex_issue_note", _args()) is None
