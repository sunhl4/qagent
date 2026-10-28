"""Company.plan adapter gates: contract wiring, preset matrix and GitLab client
behavior against a loopback stub. Every GitLab interaction here is a fake
server; no real instance or credential is ever contacted."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from company_agent.catalog import load_tools
from company_agent.invoke import invoke, validate_invocation
from company_agent.plan_hub import PlanError
from company_agent.policy import decide

URL_ENV = "COMPANY_AGENT_GITLAB_URL"
TOKEN_ENV = "COMPANY_AGENT_GITLAB_TOKEN"
ALLOWLIST_ENV = "COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST"

PROJECT_PATH = "team-a/report"
PROJECT_ID = 7

READ_TOOLS = (
    "company_plan_projects",
    "company_plan_issues",
    "company_plan_issue_get",
    "company_plan_mrs",
    "company_plan_milestones",
)
WRITE_TOOLS = (
    "company_plan_issue_create",
    "company_plan_note_create",
    "company_plan_issue_write",
    "company_plan_milestone_create",
)
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS


class _GitlabStub(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, Any]] = {}
    requests: list[dict[str, Any]] = []

    def _send(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, body: bytes | None) -> None:
        self.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "token": str(self.headers.get("PRIVATE-TOKEN") or ""),
                "body": json.loads(body.decode()) if body else None,
            }
        )

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._record(None)
        route = (self.command, self.path.split("?")[0])
        status, payload = self.routes.get(route, (404, {"message": "not found"}))
        self._send(status, payload)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        self._record(body)
        route = (self.command, self.path.split("?")[0])
        status, payload = self.routes.get(route, (404, {"message": "not found"}))
        self._send(status, payload)

    def do_PUT(self) -> None:  # noqa: N802 - http.server API
        self.do_POST()

    def log_message(self, *_args) -> None:
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return


PROJECT_FIXTURE = {
    "id": PROJECT_ID,
    "path_with_namespace": PROJECT_PATH,
    "name": "report",
    "default_branch": "main",
    "visibility": "internal",
}
ISSUES_FIXTURE = [
    {
        "iid": 11,
        "title": "draft outline",
        "state": "opened",
        "labels": ["doc"],
        "assignees": [{"name": "a"}],
        "updated_at": "2026-10-26T09:00:00.000Z",
    },
    {
        "iid": 12,
        "title": "review pass",
        "state": "closed",
        "labels": [],
        "assignees": None,
        "updated_at": "2026-10-25T09:00:00.000Z",
    },
]
ISSUE_GET_FIXTURE = {
    "iid": 11,
    "title": "draft outline",
    "state": "opened",
    "description": "需要导出周报框架。",
    "author": {"name": "owner"},
    "labels": ["doc"],
    "user_notes_count": 3,
    "created_at": "2026-10-20T09:00:00.000Z",
    "updated_at": "2026-10-26T09:00:00.000Z",
}
MILESTONES_FIXTURE = [
    {
        "id": 55,
        "title": "2026-Q4 archive",
        "state": "active",
        "start_date": "2026-10-01",
        "due_date": "2026-12-31",
    },
]

MRS_FIXTURE = [
    {
        "iid": 31,
        "title": "outline MR",
        "state": "opened",
        "source_branch": "feat/outline",
        "target_branch": "main",
        "draft": True,
        "sha": "abc123",
        "updated_at": "2026-10-26T09:10:00.000Z",
    }
]


@pytest.fixture(autouse=True)
def plan_stub(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GitlabStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    issue_base = f"/api/v4/projects/{PROJECT_PATH}/issues"
    mr_base = f"/api/v4/projects/{PROJECT_PATH}/merge_requests"
    ms_base = f"/api/v4/projects/{PROJECT_PATH}/milestones"
    _GitlabStub.routes = {
        ("GET", f"/api/v4/projects/{PROJECT_PATH}"): (200, PROJECT_FIXTURE),
        ("GET", "/api/v4/projects"): (
            200,
            [
                {"id": 1, "path_with_namespace": "team-a/aaa", "name": "aaa",
                 "default_branch": "main", "visibility": "private"},
                {"id": 2, "path_with_namespace": "team-b/bbb", "name": "bbb",
                 "default_branch": "dev", "visibility": "public"},
            ],
        ),
        ("GET", issue_base): (200, ISSUES_FIXTURE),
        ("GET", f"{issue_base}/11"): (200, ISSUE_GET_FIXTURE),
        ("GET", mr_base): (200, MRS_FIXTURE),
        ("POST", issue_base): (200, {"iid": 42, "title": "new task", "state": "opened"}),
        ("POST", f"{issue_base}/11/notes"): (200, {"id": 9001}),
        ("POST", f"{mr_base}/31/notes"): (200, {"id": 9002}),
        ("PUT", f"{issue_base}/11"): (
            200,
            {"iid": 11, "title": "draft outline", "state": "closed", "labels": ["doc", "archived"]},
        ),
        ("GET", f"{ms_base}"): (
            200,
            MILESTONES_FIXTURE,
        ),
        ("POST", f"{ms_base}"): (
            200,
            {
                "id": 77, "title": "2026-Q4 archive", "state": "active",
                "start_date": "2026-10-01", "due_date": "2026-12-31",
            },
        ),
    }
    _GitlabStub.requests = []
    monkeypatch.setenv(URL_ENV, f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv(TOKEN_ENV, "plan-stub-token")
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    try:
        yield _GitlabStub
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _ok(tool: str, args: dict[str, Any] | None = None, *, preset: str = "lab", approved: bool = False):
    result = invoke(tool, preset, args or {}, approved=approved)
    assert result.status == "ok", (result.status, result.error)
    return result.payload


# ------------------------------------------------------------- contract wiring


def test_plan_capability_contract_wiring() -> None:
    tools = load_tools()
    for name in ALL_TOOLS:
        row = tools[name]
        assert row["capability"] == "company.plan"
        assert row["operation"].startswith("plan.")
        assert row["input_handles"] == [] and row["output_handles"] == []


def test_preset_visibility_matrix() -> None:
    for tool in ALL_TOOLS:
        assert decide(tool, "lab", {}) in {"allow", "ask"}
    for tool in READ_TOOLS:
        assert decide(tool, "algo", {}) == "allow"
        assert decide(tool, "boot", {}) == "deny"
        assert decide(tool, "sign", {}) == "deny"
    for tool in WRITE_TOOLS:
        assert decide(tool, "algo", {}) == "deny"
        assert decide(tool, "boot", {}) == "deny"
        assert decide(tool, "sign", {}) == "deny"


def test_write_tools_need_approval_in_lab() -> None:
    for tool, args in (
        ("company_plan_issue_create", {"project": PROJECT_PATH, "title": "t"}),
        ("company_plan_note_create", {"target": "issue", "project": PROJECT_PATH, "iid": 11, "body": "b"}),
        ("company_plan_issue_write", {"project": PROJECT_PATH, "iid": 11, "state_event": "close"}),
        ("company_plan_milestone_create", {"project": PROJECT_PATH, "title": "M2"}),
    ):
        assert decide(tool, "lab", args) == "ask"
        result = invoke(tool, "lab", args)
        assert result.status == "needs_ask"


# ------------------------------------------------------------ fail-closed config


def test_unconfigured_plan_hub_reports_honest_error(monkeypatch) -> None:
    monkeypatch.delenv(URL_ENV, raising=False)
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "not configured" in str(result.error)
    monkeypatch.setenv(URL_ENV, "http://127.0.0.1:1")
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error"
    assert "not configured" in str(result.error) or "unreachable" in str(result.error)


def test_missing_credential_reports_honest_error(monkeypatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "credential" in str(result.error)


def test_plain_http_outside_loopback_opt_in(monkeypatch) -> None:
    # Default: encryption is mandatory outside the loopback segment.
    monkeypatch.setenv(URL_ENV, "http://192.168.110.71:8001")
    monkeypatch.setenv(TOKEN_ENV, "plan-stub-token")
    monkeypatch.delenv("COMPANY_AGENT_GITLAB_ALLOW_PLAINTEXT", raising=False)
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "must use https outside loopback" in str(result.error)
    # The operator opt-in (documented in the deployment note) allows the
    # trusted LAN plain-HTTP GitLab the company tutorial uses.
    monkeypatch.setenv("COMPANY_AGENT_GITLAB_ALLOW_PLAINTEXT", "1")
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error"
    # Fail-closed transport mapping survives: the live LAN host may answer
    # (auth rejected) or be unreachable; the https rule itself no longer fires.
    assert "must use https" not in str(result.error)


# ------------------------------------------------------------ stub happy paths


def test_projects_lists_bounded_inventory() -> None:
    payload = _ok("company_plan_projects")
    assert payload["allowlisted"] is False and payload["complete"] is True
    assert [row["path"] for row in payload["projects"]] == ["team-a/aaa", "team-b/bbb"]
    sent = _GitlabStub.requests[-1]
    assert sent["path"].startswith("/api/v4/projects")
    assert sent["token"] == "plan-stub-token"


def test_issues_maps_rows_to_contract_shape() -> None:
    payload = _ok("company_plan_issues", {"project": PROJECT_PATH})
    assert payload["complete"] is True
    first = payload["issues"][0]
    assert first == {
        "iid": 11, "title": "draft outline", "state": "opened",
        "labels": ["doc"], "assignees": 1, "updated_at": "2026-10-26T09:00:00.000Z",
    }
    assert payload["issues"][1]["assignees"] == 0
    sent = _GitlabStub.requests[-1]
    assert "state=opened" in sent["path"] and "per_page=24" in sent["path"]


def test_issue_get_returns_bounded_description() -> None:
    payload = _ok("company_plan_issue_get", {"project": PROJECT_PATH, "iid": 11})
    assert payload["title"] == "draft outline"
    assert payload["description"].startswith("需要导出")
    assert payload["author"] == "owner" and payload["comments"] == 3


def test_mrs_maps_review_state() -> None:
    payload = _ok("company_plan_mrs", {"project": PROJECT_PATH})
    row = payload["mrs"][0]
    assert row["source_branch"] == "feat/outline" and row["draft"] is True


def test_issue_create_and_note_flow_requires_and_honors_approval() -> None:
    payload = _ok("company_plan_issue_create",
                  {"project": PROJECT_PATH, "title": "new task", "labels": ["doc"]}, approved=True)
    assert payload == {"project": PROJECT_PATH, "iid": 42, "title": "new task", "state": "opened"}
    sent = _GitlabStub.requests[-1]
    assert sent["method"] == "POST" and sent["body"]["title"] == "new task"

    payload = _ok(
        "company_plan_note_create",
        {"target": "merge_request", "project": PROJECT_PATH, "iid": 31, "body": "reviewed, fix the intro"},
        approved=True,
    )
    assert payload == {"project": PROJECT_PATH, "target": "merge_request", "iid": 31, "note_id": 9002}
    sent = _GitlabStub.requests[-1]
    assert sent["path"].endswith("/merge_requests/31/notes")


def test_issue_write_updates_state_and_labels() -> None:
    payload = _ok(
        "company_plan_issue_write",
        {"project": PROJECT_PATH, "iid": 11, "state_event": "close", "labels": ["doc", "archived"]},
        approved=True,
    )
    assert payload == {
        "project": PROJECT_PATH, "iid": 11, "title": "draft outline",
        "state": "closed", "labels": ["doc", "archived"],
    }
    sent = _GitlabStub.requests[-1]
    assert sent["method"] == "PUT" and sent["body"]["state_event"] == "close"


def test_issue_write_rejects_empty_update() -> None:
    result = invoke(
        "company_plan_issue_write", "lab", {"project": PROJECT_PATH, "iid": 11}, approved=True,
    )
    assert result.status == "error" and "no fields" in str(result.error)


def test_milestones_map_schedule_rows() -> None:
    payload = _ok("company_plan_milestones", {"project": PROJECT_PATH})
    row = payload["milestones"][0]
    assert row == {
        "id": 55, "title": "2026-Q4 archive", "state": "active",
        "start_date": "2026-10-01", "due_date": "2026-12-31",
    }
    sent = _GitlabStub.requests[-1]
    assert "state=active" in sent["path"]


def test_milestone_create_honors_approval_and_dates() -> None:
    payload = _ok(
        "company_plan_milestone_create",
        {"project": PROJECT_PATH, "title": "2026-Q4 archive", "due_date": "2026-12-31"},
        approved=True,
    )
    assert payload["state"] == "active" and payload["id"] == 77
    sent = _GitlabStub.requests[-1]
    assert sent["method"] == "POST" and sent["body"]["due_date"] == "2026-12-31"


def test_issue_write_can_assign_milestone() -> None:
    payload = _ok(
        "company_plan_issue_write",
        {"project": PROJECT_PATH, "iid": 11, "milestone_id": 55},
        approved=True,
    )
    assert payload["state"] == "closed"
    sent = _GitlabStub.requests[-1]
    assert sent["body"]["milestone_id"] == 55


# ---------------------------------------------------------------- allowlist


def test_allowlist_filters_reads_and_gates_writes(monkeypatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, PROJECT_PATH)
    payload = _ok("company_plan_projects")
    assert payload["allowlisted"] is True
    assert [row["path"] for row in payload["projects"]] == [PROJECT_PATH]

    result = invoke(
        "company_plan_issue_create", "lab", {"project": "team-x/ooo", "title": "t"}, approved=True,
    )
    for reader in ("company_plan_issues", "company_plan_mrs"):
        blocked = invoke(reader, "lab", {"project": "team-x/ooo"})
        assert blocked.status == "error" and "allowlist" in str(blocked.error)
        assert result is not None


def test_allowlist_must_be_well_formed(monkeypatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, f"{PROJECT_PATH},bad/../path")
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "allowlist" in str(result.error)


# ---------------------------------------------------------------- error mapping


def test_http_status_mapping_is_generic(monkeypatch) -> None:
    _GitlabStub.routes[("GET", "/api/v4/projects")] = (401, {"message": "401 Unauthorized"})
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "authentication" in str(result.error)
    _GitlabStub.routes[("GET", "/api/v4/projects")] = (500, {"message": "boom"})
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "service error" in str(result.error)
    monkeypatch.setenv(URL_ENV, "http://127.0.0.1:1")
    result = invoke("company_plan_projects", "lab", {})
    assert result.status == "error" and "unreachable" in str(result.error)


# ---------------------------------------------------------- argument validation


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("company_plan_issues", {"project": "../escape"}),
        ("company_plan_issues", {"project": PROJECT_PATH, "state": "bogus"}),
        ("company_plan_issue_get", {"project": PROJECT_PATH, "iid": 0}),
        ("company_plan_issue_create", {"project": PROJECT_PATH, "title": "x" * 256}),
        ("company_plan_issue_create", {"project": PROJECT_PATH, "title": "t", "labels": ["l" * 65]}),
        ("company_plan_note_create", {"target": "wiki", "project": PROJECT_PATH, "iid": 1, "body": "b"}),
        (
            "company_plan_note_create",
            {"target": "issue", "project": PROJECT_PATH, "iid": 1, "body": "x" * 4001},
        ),
        ("company_plan_issue_write", {"project": PROJECT_PATH, "iid": 11, "state_event": "merge"}),
        ("company_plan_issue_write", {"project": PROJECT_PATH, "iid": 11, "title": "x" * 256}),
        ("company_plan_milestones", {"project": PROJECT_PATH, "state": "frozen"}),
        ("company_plan_milestone_create", {"project": PROJECT_PATH, "title": "t", "due_date": "2026-13-40"}),
        (
            "company_plan_milestone_create",
            {"project": PROJECT_PATH, "title": "t", "start_date": "1899-12-31"},
        ),
    ],
)
def test_argument_validation_is_fail_closed(tool: str, args: dict[str, Any]) -> None:
    assert validate_invocation(tool, args) is not None or invoke(tool, "lab", args).status == "error"


def test_credential_echo_is_rejected(monkeypatch) -> None:
    # A GitLab field that contains the configured credential string must fail
    # closed rather than echo it; the public error must stay generic.
    _GitlabStub.routes[("GET", f"/api/v4/projects/{PROJECT_PATH}/issues")] = (
        200,
        [{
            "iid": 1, "title": "plan-stub-token leaked", "state": "opened",
            "labels": [], "assignees": [], "updated_at": "z",
        }],
    )
    result = invoke("company_plan_issues", "lab", {"project": PROJECT_PATH})
    assert result.status == "error"
    monkeypatch.setenv(TOKEN_ENV, "leaked-in-env")
    _GitlabStub.routes[("GET", f"/api/v4/projects/{PROJECT_PATH}/issues")] = (
        200,
        [{
            "iid": 2, "title": "says leaked-in-env", "state": "opened",
            "labels": [], "assignees": [], "updated_at": "z",
        }],
    )
    result = invoke("company_plan_issues", "lab", {"project": PROJECT_PATH})
    assert result.status == "error"


def test_plan_error_messages_stay_bounded() -> None:
    with pytest.raises(PlanError):
        from company_agent.plan_hub import _project  # noqa: PLC0415

        _project("team ok spaces")
