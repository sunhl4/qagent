"""Company.latex remote sync adapter: bounded GitLab repository transport for
``company_latex_pull`` / ``company_latex_push``.

Transport and configuration reuse the plan-hub GitLab client
(``company_agent.plan_hub``): the same fail-closed base URL/token validation
and the same optional project allowlist with the same bounded, honest error
style. This module adds only the archive/commit shapes: ``pull_into``
downloads ONE repository archive (tar.gz) and writes managed LaTeX sources and
graphics into the given workspace project (no traversal, no symlinks, capped
size); ``push_from`` sends the managed sources and graphics of the project as
one GitLab commit (create/update only — deletions stay manual). Neither side
deletes anything, imports the contract kernel, or creates loops.
"""
from __future__ import annotations

import base64
import contextlib
import io
import os
import re
import tarfile
import urllib.error
from pathlib import Path
from typing import Any

from company_agent.plan_hub import (
    PlanError,
    _api_path,
    _base_url,
    _project,
    _request,
    _token,
)

MAX_ARCHIVE_BYTES = 16_000_000
MAX_SYNC_FILES = 300
MAX_SYNC_TOTAL = 50_000_000
COMMIT_MESSAGE_MAX_BYTES = 400
MANAGED_SUFFIXES = (
    ".tex", ".bib", ".cls", ".sty", ".bst", ".pdf", ".png", ".jpg", ".jpeg", ".eps",
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _managed_relative(relative: str) -> bool:
    lowered = relative.casefold()
    if any(part in {".", ".."} for part in lowered.split("/")):
        return False
    if lowered.startswith(".latex-build/") or "/.latex-build/" in lowered:
        return False
    if lowered.startswith(".latex-snapshots/") or "/.latex-snapshots/" in lowered:
        return False
    if Path(relative).name.startswith("."):
        return False
    return lowered.endswith(MANAGED_SUFFIXES)


def _atomic_write(target: Path, payload: bytes) -> None:
    temp = target.with_name(target.name + f".company-pull-{os.getpid()}.tmp")
    try:
        temp.write_bytes(payload)
        os.chmod(temp, 0o644)
        try:
            os.replace(temp, target)
        except OSError:
            # Windows write filters may reject rename/move operations that lay
            # down a text-like final file; clear the target and fall back to a
            # direct write of the fully written temp payload.
            if target.exists():
                target.unlink()
            if temp.read_bytes() != payload:
                raise
            target.write_bytes(payload)
            with contextlib.suppress(OSError):
                temp.unlink()
    except OSError:
        with contextlib.suppress(OSError):
            temp.unlink()
        raise PlanError("workspace file could not be written") from None


def _archive_bytes(repo: str) -> bytes:
    url = _base_url() + "/api/v4/projects/" + _api_path(repo) + "/repository/archive.tar.gz?sha=HEAD"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/x-gzip, application/octet-stream",
            "PRIVATE-TOKEN": _token(),
        },
        method="GET",
    )
    return raw_archive_bytes(request)


def _commit_payload(repo: str, branch: str, message: str, actions: list[dict[str, Any]]) -> Any:
    return _request(
        "POST",
        f"/api/v4/projects/{_api_path(repo)}/repository/commits",
        body={"branch": branch, "commit_message": message, "actions": actions},
    )


def _tree_paths(repo: str) -> set[str]:
    rows = _request(
        "GET",
        f"/api/v4/projects/{_api_path(repo)}/repository/tree",
        query={"recursive": "true", "per_page": "100"},
    )
    if not isinstance(rows, list):
        raise PlanError("plan hub returned an unexpected tree shape")
    paths: set[str] = set()
    for row in rows[:MAX_SYNC_FILES]:
        if isinstance(row, dict) and isinstance(row.get("path"), str):
            paths.add(row["path"])
    return paths


def pull_into(project_dir: Path, repo: object) -> dict[str, Any]:
    repo_path = _project(repo)
    raw = _archive_bytes(repo_path)
    imported: list[str] = []
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            members = [item for item in archive.getmembers() if item.isreg()]
            for member in members[: 4 * MAX_SYNC_FILES]:
                parts = member.name.split("/")
                if len(parts) < 2 or member.issym() or member.islnk():
                    continue
                # GitLab archives carry one safe top folder "<repo>-<sha>"; anything
                # dot-like there (including "../") is treated as an escape attempt.
                if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", parts[0]) or parts[0] in {".", ".."}:
                    raise PlanError("archive member escapes the workspace")
                relative = "/".join(parts[1:])
                if not relative or any(part in {".", ".."} for part in relative.split("/")):
                    raise PlanError("archive member escapes the workspace")
                if not _managed_relative(relative):
                    continue
                if len(imported) >= MAX_SYNC_FILES:
                    raise PlanError("repository snapshot exceeds the bounded file count")
                if total + member.size > MAX_SYNC_TOTAL:
                    raise PlanError("repository snapshot exceeds the bounded size")
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                data = stream.read(member.size)
                if len(data) != member.size:
                    raise PlanError("plan hub returned an invalid repository archive")
                target = project_dir / Path(*relative.split("/"))
                if not target.resolve().is_relative_to(project_dir.resolve()):
                    raise PlanError("archive member escapes the workspace")
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(target, data)
                imported.append(relative)
                total += len(data)
    except tarfile.TarError as exc:
        raise PlanError("plan hub returned an invalid repository archive") from exc
    return {
        "project": project_dir.name,
        "repo": repo_path,
        "files": len(imported),
        "bytes": total,
        "complete": True,
    }


def push_from(
    project_dir: Path,
    files: list[tuple[str, Path]],
    args: dict[str, Any],
) -> dict[str, Any]:
    repo_path = _project(args.get("repo"))
    message = args.get("message")
    if (
        not isinstance(message, str) or not message.strip()
        or len(message.encode("utf-8")) > COMMIT_MESSAGE_MAX_BYTES
    ):
        raise PlanError("commit message is invalid")
    branch = args.get("branch")
    branch = branch if isinstance(branch, str) and branch.strip() else "main"
    if (
        not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", branch)
        or branch.startswith("-") or branch.startswith(".") or branch.endswith("/")
        or ".." in branch
    ):
        raise PlanError("branch name is invalid")

    remote_paths = _tree_paths(repo_path)
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    encoded_total = 0
    for relative, source in files:
        relative_path = relative.replace("\\", "/")
        parts = [part for part in relative_path.split("/") if part]
        if any(part in {".", ".."} for part in parts):
            raise PlanError("file path escapes the project")
        relative_path = "/".join(parts)
        if relative_path in seen or not _managed_relative(relative_path):
            continue
        seen.add(relative_path)
        data = source.read_bytes()
        if not data:
            continue
        encoded = base64.b64encode(data).decode("ascii")
        encoded_total += len(encoded)
        if len(actions) >= MAX_SYNC_FILES or encoded_total > MAX_SYNC_TOTAL:
            raise PlanError("project exceeds the bounded push size; archive manually")
        actions.append({
            "action": "update" if relative_path in remote_paths else "create",
            "file_path": relative_path,
            "encoding": "base64",
            "content": encoded,
        })
    if not actions:
        raise PlanError("no managed latex files to push")
    payload = _commit_payload(repo_path, branch, message, actions)
    if not isinstance(payload, dict):
        raise PlanError("plan hub returned an unexpected commit shape")
    commit_value = payload.get("id")
    if not isinstance(commit_value, str) or not re.fullmatch(r"[0-9a-f]{7,64}", commit_value):
        raise PlanError("plan hub returned an invalid commit id")
    return {
        "project": project_dir.name,
        "repo": repo_path,
        "branch": branch,
        "commit_sha": commit_value,
        "changes": len(actions),
    }


def raw_archive_bytes(request: urllib.request.Request, *, timeout: float = 30.0) -> bytes:
    """Perform a raw binary GET with the shared fail-closed transport rules."""

    del timeout
    try:
        with _open_without_redirects(request) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise PlanError("plan hub returned an unexpected HTTP status")
            return _raw_read(response)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in {401, 403}:
            raise PlanError("plan hub rejected authentication") from exc
        if exc.code == 404:
            raise PlanError("plan hub repository is not available") from exc
        if 400 <= exc.code < 500:
            raise PlanError("plan hub rejected the request") from exc
        raise PlanError("plan hub service error") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PlanError("plan hub is unreachable") from exc


def _open_without_redirects(request: urllib.request.Request):
    import urllib.request as _u

    opener = _u.build_opener(_u.ProxyHandler({}), _NoRedirect)
    return opener.open(request, timeout=30)


def _raw_read(response: Any) -> bytes:
    raw = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise PlanError("plan hub response is too large")
    return raw
