"""Company.plan adapter: a bounded GitLab REST v4 client for the plan hub.

This is the Agent-side half of the company plan management loop (GitLab CE
strength: issues, merge requests and review comments). The module is
fail-closed: without ``COMPANY_AGENT_GITLAB_URL`` and
``COMPANY_AGENT_GITLAB_TOKEN`` every tool reports an explicit configuration
error and never fakes success. An optional
``COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST`` restricts which
``path_with_namespace`` values may be read at all and gates every write.
Results are short, deterministic and never contain tokens, credentials or
request URLs. This module never imports the contract kernel and creates no
model, session or tool loops.
"""
from __future__ import annotations

import datetime
import http.client
import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from company_agent.jsonutil import loads as strict_json_loads

MAX_PROJECTS = 24
HTTP_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 1_000_000
MAX_ALLOWLIST = 16
TITLE_MAX_BYTES = 255
DESCRIPTION_MAX_BYTES = 4000
BODY_MAX_BYTES = 4000
LABEL_MAX_CHARS = 64

_PATH_PATTERN = re.compile(
    r"^(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}(?:/[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})*$"
)
LABEL_PATTERN = re.compile(r"^[^\r\n,]{1,64}$")

URL_ENV = "COMPANY_AGENT_GITLAB_URL"
TOKEN_ENV = "COMPANY_AGENT_GITLAB_TOKEN"
ALLOWLIST_ENV = "COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST"

TARGET_PATHS = {"issue": "issues", "merge_request": "merge_requests"}


class PlanError(ValueError):
    """Bounded plan-hub failure; messages stay free of URLs, tokens and paths."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_PROXY_HANDLER = urllib.request.ProxyHandler({})
_OPENER = urllib.request.build_opener(_PROXY_HANDLER, _NoRedirect)


def _plaintext_opt_in() -> bool:
    """Explicit opt-in for internal plain-HTTP GitLab deployments.

    Company Overleaf/GitLab instances live on trusted LAN segments served
    over plain HTTP (the git-bridge tutorial documents this); encryption is
    bypassed only when the operator turns this on — the default stays
    fail-closed HTTPS-outside-loopback."""

    return os.environ.get("COMPANY_AGENT_GITLAB_ALLOW_PLAINTEXT", "").strip() == "1"


def _base_url() -> str:
    raw = re.sub(r"[\x00-\x1f]", "", os.environ.get(URL_ENV, "")).strip()
    if not raw:
        raise PlanError("plan hub integration is not configured")
    if any(character in raw for character in ("\\", "<", ">", '"', " ")):
        raise PlanError("plan hub endpoint is invalid")
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError as exc:
        raise PlanError("plan hub endpoint is invalid") from exc
    if parsed.scheme not in {"http", "https"} or parsed.scheme != parsed.scheme.casefold():
        raise PlanError("plan hub endpoint is invalid")
    if not parsed.hostname:
        raise PlanError("plan hub endpoint is invalid")
    if parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query:
        raise PlanError("plan hub endpoint is invalid")
    if parsed.hostname != parsed.hostname.casefold() or parsed.netloc != parsed.netloc.casefold():
        raise PlanError("plan hub endpoint is invalid")
    if parsed.hostname.endswith(".") or len(parsed.hostname) > 253:
        raise PlanError("plan hub endpoint is invalid")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        labels = parsed.hostname.split(".")
        if any(not label or len(label) > 63 for label in labels):
            raise PlanError("plan hub endpoint is invalid") from None
        loopback = parsed.hostname == "localhost"
    try:
        port = parsed.port
    except ValueError as exc:
        raise PlanError("plan hub endpoint is invalid") from exc
    if port is not None and not 1 <= port <= 65535:
        raise PlanError("plan hub endpoint is invalid")
    if parsed.scheme == "http" and not loopback and not _plaintext_opt_in():
        raise PlanError("plan hub endpoint must use https outside loopback")
    path = parsed.path.rstrip("/")
    if any(segment in {".", ".."} for segment in path.split("/")) or "//" in path:
        raise PlanError("plan hub endpoint is invalid")
    if len(path) > 2048:
        raise PlanError("plan hub endpoint is invalid")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _token() -> str:
    token = re.sub(r"[\x00-\x1f]", "", os.environ.get(TOKEN_ENV, "")).strip()
    if not token:
        raise PlanError("plan hub credential is not configured")
    if len(token) > 8192:
        raise PlanError("plan hub credential is too long")
    return token


def _allowlist() -> tuple[str, ...]:
    raw = re.sub(r"[\x00-\x1f]", "", os.environ.get(ALLOWLIST_ENV, "")).strip()
    if not raw:
        return ()
    entries: list[str] = []
    seen: set[str] = set()
    for chunk in raw.split(","):
        entry = chunk.strip()
        if not entry or not _PATH_PATTERN.fullmatch(entry) or entry in seen:
            raise PlanError("plan hub allowlist entry is invalid")
        if len(entries) >= MAX_ALLOWLIST:
            raise PlanError("plan hub allowlist exceeds the bounded size")
        seen.add(entry)
        entries.append(entry)
    return tuple(entries)


def _project(project: object) -> str:
    if not isinstance(project, str) or not _PATH_PATTERN.fullmatch(project):
        raise PlanError("project has an invalid path")
    allowed = _allowlist()
    if allowed and project not in allowed:
        raise PlanError("project is outside the configured plan hub allowlist")
    return project


def _api_path(project: str) -> str:
    return "/".join(urllib.parse.quote(segment, safe="-._~") for segment in project.split("/"))


def _clip(value: object, limit: int, *, default: object = "") -> str:
    if not isinstance(value, str) or value == "":
        return str(default)
    encoded = value.encode("utf-8")[:limit]
    while encoded:
        try:
            return encoded.decode("utf-8")
        except UnicodeError:
            encoded = encoded[:-1]
    return str(default)


def _clip_or_none(value: object, limit: int) -> str:
    if not isinstance(value, str) or value == "":
        return ""
    return _clip(value, limit)


def _timestamp(value: object) -> str:
    return _clip_or_none(value, 32)


def _row_state(value: object) -> str:
    text = _clip_or_none(value, 16)
    return text if text in {"opened", "closed", "merged"} else "opened"


def _open_json(request: urllib.request.Request) -> Any:
    try:
        with _OPENER.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise PlanError("plan hub returned an unexpected HTTP status")
            media_type = str(response.headers.get("Content-Type") or "").casefold().split(";", 1)[0].strip()
            if media_type != "application/json" and not (
                media_type.startswith("application/") and media_type.endswith("+json")
            ):
                raise PlanError("plan hub returned a non-JSON content type")
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    declared = int(length)
                except ValueError as exc:
                    raise PlanError("plan hub returned an invalid content length") from exc
                if declared < 0 or declared > MAX_RESPONSE_BYTES:
                    raise PlanError("plan hub response is too large")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in {401, 403}:
            raise PlanError("plan hub rejected authentication") from exc
        if exc.code == 404:
            raise PlanError("plan hub project or object is not available") from exc
        if 400 <= exc.code < 500:
            raise PlanError("plan hub rejected the request") from exc
        raise PlanError("plan hub service error") from exc
    except PlanError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise PlanError("plan hub is unreachable") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise PlanError("plan hub response is too large")
    try:
        payload = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PlanError("plan hub returned invalid JSON") from exc
    if not isinstance(payload, (dict, list)):
        raise PlanError("plan hub returned an unexpected payload shape")
    return payload


def _request(
    method: str,
    endpoint_path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = _base_url() + endpoint_path
    if query:
        url = url + "?" + urllib.parse.urlencode(sorted(query.items()))
    headers = {"Accept": "application/json", "PRIVATE-TOKEN": _token()}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        try:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PlanError("plan hub request payload is not valid JSON") from exc
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    return _open_json(request)


MAX_UPLOAD_BYTES = 10_000_000
_UPLOAD_NAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}")
_UPLOAD_RELATIVE_PATTERN = re.compile(r"^/[A-Za-z0-9._/-]{1,260}$")


def upload_project_file(project_path: str, filename: str, payload: bytes) -> str:
    """Upload ONE bounded attachment; returns the plan hub's relative link.

    The transport reuses the shared fail-closed response mapping of this
    module. The result is bounded to a relative ``/uploads/...`` path so no
    absolute URL, credential or file body ever returns to the caller."""

    project = _project(project_path)
    if not isinstance(payload, bytes) or not payload:
        raise PlanError("plan hub attachment content is invalid")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise PlanError("plan hub attachment exceeds the bounded size")
    if not isinstance(filename, str) or not _UPLOAD_NAME_PATTERN.fullmatch(filename):
        raise PlanError("plan hub attachment name is invalid")
    boundary = "company-agent-" + uuid.uuid4().hex
    lines = bytearray()
    lines += f"--{boundary}\r\n".encode("ascii")
    lines += (
        "Content-Disposition: form-data; name=\"file\"; filename=\""
        + filename
        + "\"\r\n"
    ).encode("ascii")
    lines += b"Content-Type: application/pdf\r\n\r\n"
    lines += payload
    lines += f"\r\n--{boundary}--\r\n".encode("ascii")
    request = urllib.request.Request(
        _base_url() + "/api/v4/projects/" + _api_path(project) + "/uploads",
        data=bytes(lines),
        headers={
            "Accept": "application/json",
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "PRIVATE-TOKEN": _token(),
        },
        method="POST",
    )
    payload_json = _open_json(request)
    if not isinstance(payload_json, dict):
        raise PlanError("plan hub returned an unexpected upload shape")
    link = payload_json.get("url") or ""
    if not isinstance(link, str) or not _UPLOAD_RELATIVE_PATTERN.fullmatch(link):
        raise PlanError("plan hub returned an invalid attachment link")
    return link


def projects(args: dict[str, Any]) -> dict[str, Any]:
    del args
    allowed = _allowlist()
    if allowed:
        rows: list[dict[str, Any]] = []
        complete = True
        for path in allowed:
            try:
                payload = _request("GET", f"/api/v4/projects/{_api_path(path)}", query={"simple": "true"})
            except PlanError:
                continue
            if isinstance(payload, dict):
                rows.append(_project_row(payload))
                if len(rows) >= MAX_PROJECTS:
                    complete = False
                    break
        return {"projects": rows, "complete": complete, "allowlisted": True}
    payload = _request(
        "GET",
        "/api/v4/projects",
        query={"simple": "true", "per_page": str(MAX_PROJECTS), "order_by": "path", "sort": "asc"},
    )
    if not isinstance(payload, list):
        raise PlanError("plan hub returned an unexpected project shape")
    rows = [_project_row(item) for item in payload[:MAX_PROJECTS]]
    return {"projects": rows, "complete": len(payload) < MAX_PROJECTS, "allowlisted": False}


def _project_row(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PlanError("plan hub returned an unexpected project shape")
    identifier = item.get("id")
    if not isinstance(identifier, int) or identifier < 1:
        raise PlanError("plan hub returned an invalid project id")
    path = _clip_or_none(item.get("path_with_namespace"), 256)
    name = _clip_or_none(item.get("name"), 256)
    default_branch = _clip_or_none(item.get("default_branch"), 128) or "main"
    visibility = item.get("visibility")
    if not path or not name:
        raise PlanError("plan hub returned an invalid project row")
    return {
        "id": identifier,
        "path": path,
        "name": name,
        "default_branch": default_branch,
        "visibility": visibility if visibility in {"private", "internal", "public"} else "private",
    }


def issues(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    state = args.get("state")
    if state is None:
        state = "opened"
    if state not in {"opened", "closed", "all"}:
        raise PlanError("issue state filter is invalid")
    query: dict[str, str] = {
        "per_page": str(MAX_PROJECTS),
        "order_by": "updated_at",
        "sort": "desc",
        "state": str(state),
    }
    label = args.get("label")
    if isinstance(label, str) and label:
        if not LABEL_PATTERN.fullmatch(label):
            raise PlanError("label filter is invalid")
        query["labels"] = label
    payload = _request("GET", f"/api/v4/projects/{_api_path(project)}/issues", query=query)
    return _issue_collected(project, payload)


def _issue_collected(project: str, payload: object) -> dict[str, Any]:
    """Collect GitLab issue rows into the bounded contract shape."""

    if not isinstance(payload, list):
        raise PlanError("plan hub returned an unexpected issue shape")
    rows = [_issue_row(item) for item in payload[:MAX_PROJECTS]]
    return {"project": project, "issues": rows, "complete": len(payload) < MAX_PROJECTS}


def _string_rows(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out = [_clip_or_none(row, LABEL_MAX_CHARS) for row in value[:10] if isinstance(row, str)]
    return [row for row in out if row]


def _issue_row(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PlanError("plan hub returned an unexpected issue shape")
    iid = item.get("iid")
    title = _clip_or_none(item.get("title"), TITLE_MAX_BYTES)
    if not isinstance(iid, int) or iid < 1 or not title:
        raise PlanError("plan hub returned an invalid issue row")
    assignees = item.get("assignees")
    assignee_count = len(assignees) if isinstance(assignees, list) else int(bool(item.get("assignee")))
    return {
        "iid": iid,
        "title": title,
        "state": _row_state(item.get("state")),
        "labels": _string_rows(item.get("labels")),
        "assignees": min(max(assignee_count, 0), 999),
        "updated_at": _timestamp(item.get("updated_at")),
    }


def issue_get(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    iid = args.get("iid")
    if not isinstance(iid, int) or iid < 1:
        raise PlanError("issue iid is invalid")
    payload = _request("GET", f"/api/v4/projects/{_api_path(project)}/issues/{iid}")
    if not isinstance(payload, dict):
        raise PlanError("plan hub returned an unexpected issue shape")
    title = _clip_or_none(payload.get("title"), TITLE_MAX_BYTES)
    if not title:
        raise PlanError("plan hub returned an invalid issue row")
    author = payload.get("author")
    author_name = str(author.get("name", "")) if isinstance(author, dict) else ""
    notes = payload.get("user_notes_count")
    return {
        "project": project,
        "iid": iid,
        "title": title,
        "state": _row_state(payload.get("state")),
        "description": _clip(payload.get("description"), DESCRIPTION_MAX_BYTES),
        "author": _clip(author_name, 128),
        "labels": _string_rows(payload.get("labels")),
        "comments": notes if isinstance(notes, int) and 0 <= notes <= 1_000_000 else 0,
        "created_at": _timestamp(payload.get("created_at")),
        "updated_at": _timestamp(payload.get("updated_at")),
    }


def issue_create(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    title = args.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.encode("utf-8")) > TITLE_MAX_BYTES:
        raise PlanError("issue title is invalid")
    description = args.get("description")
    if description is None:
        description = ""
    if not isinstance(description, str) or len(description.encode("utf-8")) > DESCRIPTION_MAX_BYTES:
        raise PlanError("issue description is invalid")
    labels = args.get("labels")
    given = labels if isinstance(labels, list) else []
    label_rows = [row for row in given if isinstance(row, str) and row]
    payload = _request(
        "POST",
        f"/api/v4/projects/{_api_path(project)}/issues",
        body={
            "title": title,
            "description": description,
            "labels": [_clip(row, LABEL_MAX_CHARS) for row in label_rows if _clip(row, LABEL_MAX_CHARS)],
        },
    )
    if not isinstance(payload, dict):
        raise PlanError("plan hub returned an unexpected issue shape")
    created_iid = payload.get("iid")
    created_title = _clip_or_none(payload.get("title"), TITLE_MAX_BYTES)
    if not isinstance(created_iid, int) or created_iid < 1 or not created_title:
        raise PlanError("plan hub returned an invalid created issue")
    return {"project": project, "iid": created_iid, "title": created_title, "state": "opened"}


def mrs(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    state = args.get("state")
    if state is None:
        state = "opened"
    if state not in {"opened", "closed", "merged", "all"}:
        raise PlanError("merge request state filter is invalid")
    payload = _request(
        "GET",
        f"/api/v4/projects/{_api_path(project)}/merge_requests",
        query={"state": str(state), "per_page": str(MAX_PROJECTS), "order_by": "updated_at", "sort": "desc"},
    )
    if not isinstance(payload, list):
        raise PlanError("plan hub returned an unexpected merge request shape")
    rows = [_mr_row(item) for item in payload[:MAX_PROJECTS]]
    return {"project": project, "mrs": rows, "complete": len(payload) < MAX_PROJECTS}


def _mr_row(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PlanError("plan hub returned an unexpected merge request shape")
    iid = item.get("iid")
    title = _clip_or_none(item.get("title"), TITLE_MAX_BYTES)
    source = _clip_or_none(item.get("source_branch"), 128)
    target = _clip_or_none(item.get("target_branch"), 128)
    sha = _clip_or_none(item.get("sha"), 40)
    if (
        not isinstance(iid, int) or iid < 1 or not title
        or not source or not target or not sha
    ):
        raise PlanError("plan hub returned an invalid merge request row")
    return {
        "iid": iid,
        "title": title,
        "state": _row_state(item.get("state")),
        "source_branch": source,
        "target_branch": target,
        "draft": bool(item.get("draft")),
        "sha": sha,
        "updated_at": _timestamp(item.get("updated_at")),
    }


def note_create(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    target = args.get("target")
    if not isinstance(target, str) or target not in TARGET_PATHS:
        raise PlanError("note target is invalid")
    iid = args.get("iid")
    if not isinstance(iid, int) or iid < 1:
        raise PlanError("note iid is invalid")
    body = args.get("body")
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > BODY_MAX_BYTES:
        raise PlanError("note body is invalid")
    payload = _request(
        "POST",
        f"/api/v4/projects/{_api_path(project)}/{TARGET_PATHS[target]}/{iid}/notes",
        body={"body": body},
    )
    if not isinstance(payload, dict):
        raise PlanError("plan hub returned an unexpected note shape")
    note_id = payload.get("id")
    if not isinstance(note_id, int) or note_id < 1:
        raise PlanError("plan hub returned an invalid note id")
    return {"project": project, "target": target, "iid": iid, "note_id": note_id}


def issue_write(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    iid = args.get("iid")
    if not isinstance(iid, int) or iid < 1:
        raise PlanError("issue iid is invalid")
    body: dict[str, Any] = {}
    title = args.get("title")
    if title is not None:
        if not isinstance(title, str) or not title.strip() or len(title.encode("utf-8")) > TITLE_MAX_BYTES:
            raise PlanError("issue title is invalid")
        body["title"] = title
    description = args.get("description")
    if description is not None:
        if not isinstance(description, str) or len(description.encode("utf-8")) > DESCRIPTION_MAX_BYTES:
            raise PlanError("issue description is invalid")
        body["description"] = description
    state_event = args.get("state_event")
    if state_event is not None:
        if state_event not in {"close", "reopen"}:
            raise PlanError("issue state event is invalid")
        body["state_event"] = str(state_event)
    milestone_id = args.get("milestone_id")
    if milestone_id is not None:
        if not isinstance(milestone_id, int) or milestone_id < 1:
            raise PlanError("issue milestone is invalid")
        body["milestone_id"] = milestone_id
    labels = args.get("labels")
    if labels is not None:
        if not isinstance(labels, list):
            raise PlanError("issue labels are invalid")
        rows = [row for row in labels if isinstance(row, str) and row]
        if len(rows) != len(labels):
            raise PlanError("issue labels are invalid")
        body["labels"] = [_clip(row, LABEL_MAX_CHARS) for row in rows if _clip(row, LABEL_MAX_CHARS)]
    if not body:
        raise PlanError("issue write has no fields to update")
    payload = _request(
        "PUT",
        f"/api/v4/projects/{_api_path(project)}/issues/{iid}",
        body=body,
    )
    if not isinstance(payload, dict):
        raise PlanError("plan hub returned an unexpected issue shape")
    updated_title = _clip_or_none(payload.get("title"), TITLE_MAX_BYTES)
    if not updated_title:
        raise PlanError("plan hub returned an invalid issue row")
    return {
        "project": project,
        "iid": iid,
        "title": updated_title,
        "state": _row_state(payload.get("state")),
        "labels": _string_rows(payload.get("labels")),
    }


def _milestone_state(value: object) -> str:
    text = _clip_or_none(value, 16)
    return text if text in {"active", "closed"} else "active"


def _milestone_date(value: object) -> str:
    text = _clip_or_none(value, 10)
    if not text:
        return ""
    try:
        parsed = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise PlanError("plan hub returned an invalid milestone date") from exc
    return parsed.isoformat()


def milestones(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    state = args.get("state")
    if state is None:
        state = "active"
    if state not in {"active", "closed", "all"}:
        raise PlanError("milestone state filter is invalid")
    payload = _request(
        "GET",
        f"/api/v4/projects/{_api_path(project)}/milestones",
        query={"state": str(state), "per_page": str(MAX_PROJECTS)},
    )
    if not isinstance(payload, list):
        raise PlanError("plan hub returned an unexpected milestone shape")
    rows = [_milestone_row(item) for item in payload[:MAX_PROJECTS]]
    return {"project": project, "milestones": rows, "complete": len(payload) < MAX_PROJECTS}


def _milestone_row(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PlanError("plan hub returned an unexpected milestone shape")
    identifier = item.get("id")
    title = _clip_or_none(item.get("title"), TITLE_MAX_BYTES)
    if not isinstance(identifier, int) or identifier < 1 or not title:
        raise PlanError("plan hub returned an invalid milestone row")
    return {
        "id": identifier,
        "title": title,
        "state": _milestone_state(item.get("state")),
        "start_date": _milestone_date(item.get("start_date")),
        "due_date": _milestone_date(item.get("due_date")),
    }


def milestone_create(args: dict[str, Any]) -> dict[str, Any]:
    project = _project(args.get("project"))
    title = args.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.encode("utf-8")) > TITLE_MAX_BYTES:
        raise PlanError("milestone title is invalid")
    body: dict[str, Any] = {"title": title}
    for key in ("start_date", "due_date"):
        value = args.get(key)
        if value is not None:
            _milestone_date(value)
            body[key] = str(value)
    payload = _request(
        "POST",
        f"/api/v4/projects/{_api_path(project)}/milestones",
        body=body,
    )
    if not isinstance(payload, dict):
        raise PlanError("plan hub returned an unexpected milestone shape")
    identifier = payload.get("id")
    created_title = _clip_or_none(payload.get("title"), TITLE_MAX_BYTES)
    if not isinstance(identifier, int) or identifier < 1 or not created_title:
        raise PlanError("plan hub returned an invalid created milestone")
    state = _milestone_state(payload.get("state"))
    return {"project": project, "id": identifier, "title": created_title, "state": state}
