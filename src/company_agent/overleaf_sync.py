"""Company.latex Overleaf Git-bridge adapter.

Bounded transport for ``company_latex_overleaf_pull`` /
``company_latex_overleaf_push`` against a self-hosted Overleaf instance that
exposes the git-bridge (username fixed to ``git``, Git token as the password,
clone URL ``<base>/git/<project_id>``).

Fail-closed rules shared with ``latex_sync``: configuration must be present and
well-formed or the tool refuses to run; file selection and sizes stay inside
the same bounded caps; nothing on the remote or in the workspace is ever
deleted; the Git token lives only in process memory and is scrubbed from any
git output or error text. No contract kernel import, no loops.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from company_agent.latex_sync import (
    COMMIT_MESSAGE_MAX_BYTES,
    MAX_SYNC_FILES,
    MAX_SYNC_TOTAL,
    PlanError,
    _atomic_write,
    _managed_relative,
)

GIT_TIMEOUT_SECONDS = 300

_BRANCH_PATTERN = re.compile(r"^(?!-)(?!.*\.lock$)[A-Za-z0-9._/-]{1,128}$")
_PROJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{12,64}$")
_CHECKPOINT_PATTERN = re.compile(r"^chk-[0-9]{14}-[0-9a-f]{6}$")


def _configured() -> tuple[str, str, tuple[str, ...]]:
    """Validate the Overleaf Git-bridge configuration; raise when malformed."""

    base = os.environ.get("COMPANY_AGENT_OVERLEAF_GIT_BASE", "")
    base = re.sub(r"[\x00-\x1f]", "", base).strip().rstrip("/")
    token = re.sub(r"[\x00-\x1f]", "", os.environ.get("COMPANY_AGENT_OVERLEAF_GIT_TOKEN", "")).strip()
    if not token:
        raise PlanError("overleaf git bridge credential is not configured")
    if not base:
        raise PlanError("overleaf git bridge base url is not configured")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PlanError("overleaf git bridge base url is invalid")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PlanError("overleaf git bridge base url must be a bare http(s) origin")
    allowlist_raw = os.environ.get("COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST", "")
    allowed: tuple[str, ...] = ()
    if allowlist_raw.strip():
        items = []
        for item in allowlist_raw.replace(";", ",").split(","):
            item = item.strip()
            if not item:
                continue
            if not _PROJECT_ID_PATTERN.fullmatch(item):
                raise PlanError("overleaf project allowlist is invalid")
            items.append(item)
        if not items:
            raise PlanError("overleaf project allowlist is empty")
        if len(items) != len(set(items)):
            raise PlanError("overleaf project allowlist has duplicates")
        allowed = tuple(items)
    return base, token, allowed


def _remote_url(base: str, token: str, project_id: str) -> str:
    parsed = urllib.parse.urlsplit(base)
    host = parsed.hostname or ""
    bracket = f"[{host}]" if ":" in host else host
    authority = bracket if parsed.port is None else f"{bracket}:{parsed.port}"
    userinfo = urllib.parse.quote("git", safe="") + ":" + urllib.parse.quote(token, safe="")
    # Canonical git-bridge URL shape: <base>/git/<project_id> (the deployment
    # tutorial documents this path under a bare origin). Keeping the base's
    # own path lets internal reverse-proxy prefixes work while a pathless
    # base never silently drops the /git/<id> segment.
    path = (parsed.path or "").rstrip("/") + "/git/" + project_id
    return urllib.parse.urlunsplit((parsed.scheme, userinfo + "@" + authority, path, "", ""))


def _scrub(payload: bytes, token: str, base: str) -> str:
    text = (payload or b"").decode("utf-8", errors="replace")
    for secret in {token, urllib.parse.quote(token, safe="")}:
        if secret:
            text = text.replace(secret, "[token]")
    if base:
        text = text.replace(base, "[overleaf]")
    return text


def _run_git(args: list[str], *, token: str, base: str, cwd: Path | None = None) -> bytes:
    executable = shutil.which("git")
    if not executable:
        raise PlanError("git is not available on the agent host")
    environment = dict(os.environ)
    environment.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GIT_SSH_COMMAND": "false",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    command = [
        executable,
        "-c", "credential.helper=",
        "-c", "core.askPass=",
        "--no-pager",
        *args,
    ]
    try:
        process = subprocess.run(
            command,
            cwd=None if cwd is None else str(cwd),
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        raise PlanError("git bridge operation timed out") from None
    except OSError:
        raise PlanError("git bridge operation failed to start") from None
    if process.returncode != 0:
        detail = _scrub(process.stderr, token, base).strip() or _scrub(process.stdout, token, base).strip()
        compact = detail[-300:]
        if "Authentication failed" in compact or " 401 " in compact or " 403 " in compact:
            raise PlanError("overleaf git bridge rejected authentication")
        if "does not appear to be a git repository" in compact or "not found" in compact:
            raise PlanError("overleaf project is not available on the git bridge")
        if compact:
            raise PlanError("git bridge operation failed: " + compact)
        raise PlanError("git bridge operation failed")
    return process.stdout


def _validated_branch(args: dict[str, Any]) -> str:
    branch = args.get("branch")
    if branch is None or branch == "":
        return "main"
    if not isinstance(branch, str) or not _BRANCH_PATTERN.fullmatch(branch) or ".." in branch:
        raise PlanError("branch name is invalid")
    return branch


def _validated_message(message: object) -> str:
    if (
        not isinstance(message, str) or not message.strip()
        or len(message.encode("utf-8")) > COMMIT_MESSAGE_MAX_BYTES
    ):
        raise PlanError("commit message is invalid")
    return message.strip()


def _validated_project_id(project_id: object) -> str:
    if not isinstance(project_id, str) or not _PROJECT_ID_PATTERN.fullmatch(project_id):
        raise PlanError("overleaf project id is invalid")
    return project_id


def _clone(remote: str, token: str, base: str, destination: Path, branch: str) -> None:
    _run_git(
        [
            "clone",
            "--depth", "1",
            "--single-branch",
            "--branch", branch,
            remote,
            str(destination),
        ],
        token=token,
        base=base,
    )


def _content_differs(local_payload: bytes, remote_payload: bytes) -> bool:
    """Compare managed content ignoring Windows/Unix newline style only.

    The git bridge clone stores byte-faithful blobs while hosts may hold
    CRLF variants; treating an end-line translation as a lost edit would
    block every pull on Windows. Everything else (including whitespace
    changes inside lines) still counts as a real difference."""

    if local_payload == remote_payload:
        return False
    normalize = lambda payload: payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalize(local_payload) != normalize(remote_payload)


def pull_into(project_dir: Path, args: dict[str, Any], backup=None) -> dict[str, Any]:
    base, token, allowed = _configured()
    project_id = _validated_project_id(args.get("project_id"))
    if allowed and project_id not in allowed:
        raise PlanError("overleaf project is outside the project allowlist")
    branch = _validated_branch(args)
    force = args.get("force") is True
    remote = _remote_url(base, token, project_id)
    work = Path(tempfile.mkdtemp(prefix=".company-overleaf-"))
    try:
        clone_dir = work / "repo"
        _clone(remote, token, base, clone_dir, branch)
        incoming: dict[str, bytes] = {}
        total = 0
        for path in sorted(clone_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(clone_dir).as_posix()
            if not _managed_relative(relative):
                continue
            if len(incoming) >= MAX_SYNC_FILES:
                raise PlanError("overleaf snapshot exceeds the bounded file count")
            data = path.read_bytes()
            if total + len(data) > MAX_SYNC_TOTAL:
                raise PlanError("overleaf snapshot exceeds the bounded size")
            incoming[relative] = data
            total += len(data)
        # Divergence guard: existing workspace files that differ from the
        # online snapshot are positions where a pull would overwrite local
        # edits. Fail closed and name the positions unless the caller asked
        # for an overwrite, in which case the workspace layer first snapshots
        # exactly the bytes that would be replaced.
        diverged: list[tuple[str, bytes]] = []
        local_total = 0
        for relative in sorted(incoming):
            target = project_dir.joinpath(*relative.split("/"))
            if target.is_symlink() or not target.is_file():
                continue
            size = target.stat().st_size
            if local_total + size > MAX_SYNC_TOTAL:
                raise PlanError("local workspace differences exceed the bounded size")
            local_total += size
            local_payload = target.read_bytes()
            if _content_differs(local_payload, incoming[relative]):
                diverged.append((relative, local_payload))
        checkpoint = ""
        if diverged:
            if not force:
                preview = ", ".join(relative[:64] for relative, _ in diverged[:3])
                raise PlanError(
                    f"pull would overwrite {len(diverged)} locally modified"
                    f" managed file(s) (first: {' '.join(preview.split())});"
                    " snapshot the project, or rerun with force to back up"
                    " the replaced content"
                )
            if not callable(backup):
                raise PlanError("overwrite pull requires a workspace snapshot backup")
            checkpoint = backup(diverged)
            if not isinstance(checkpoint, str) or not _CHECKPOINT_PATTERN.fullmatch(checkpoint):
                raise PlanError("workspace snapshot id is invalid")
        imported: list[str] = []
        total = 0
        for relative, data in sorted(incoming.items()):
            if len(imported) >= MAX_SYNC_FILES:
                raise PlanError("overleaf snapshot exceeds the bounded file count")
            if total + len(data) > MAX_SYNC_TOTAL:
                raise PlanError("overleaf snapshot exceeds the bounded size")
            _atomic_write(project_dir.joinpath(*relative.split("/")), data)
            imported.append(relative)
            total += len(data)
        result: dict[str, Any] = {
            "project": project_dir.name,
            "project_id": project_id,
            "files": len(imported),
            "bytes": total,
            "complete": True,
            "overwritten": len(diverged),
        }
        if checkpoint:
            result["checkpoint"] = checkpoint
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def status_of(project_dir: Path, args: dict[str, Any]) -> dict[str, Any]:
    """Read-only workspace versus online-head comparison for one project."""

    base, token, allowed = _configured()
    project_id = _validated_project_id(args.get("project_id"))
    if allowed and project_id not in allowed:
        raise PlanError("overleaf project is outside the project allowlist")
    branch = _validated_branch(args)
    remote = _remote_url(base, token, project_id)
    work = Path(tempfile.mkdtemp(prefix=".company-overleaf-"))
    try:
        clone_dir = work / "repo"
        _clone(remote, token, base, clone_dir, branch)
        head_raw = _run_git(["rev-parse", "HEAD"], token=token, base=base, cwd=clone_dir)
        online_head = (head_raw or b"").decode("ascii", errors="ignore").strip()
        if not re.fullmatch(r"[0-9a-f]{7,64}", online_head):
            raise PlanError("git bridge returned an invalid commit id")
        online: dict[str, bytes] = {}
        total_online = 0
        for path in sorted(clone_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(clone_dir).as_posix()
            if not _managed_relative(relative):
                continue
            total_online += 1
            if len(online) < MAX_SYNC_FILES:
                online[relative] = path.read_bytes()
        local: dict[str, bytes] = {}
        total_local = 0
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(project_dir).as_posix()
            if not _managed_relative(relative):
                continue
            total_local += 1
            if len(local) < MAX_SYNC_FILES:
                local[relative] = path.read_bytes()
        rows: list[dict[str, str]] = []
        for relative in sorted(set(online) | set(local)):
            if relative in online and relative not in local:
                difference = "online-only"
            elif relative not in online and relative in local:
                difference = "local-only"
            elif online[relative] != local[relative]:
                difference = "modified"
            else:
                continue
            if len(rows) < 20:
                rows.append({"path": relative, "difference": difference})
        row_limit = "workspace exceeds the bounded file count"
        if total_local > MAX_SYNC_FILES or total_online > MAX_SYNC_FILES:
            raise PlanError(row_limit)
        total = len([
            1
            for relative in set(online) | set(local)
            if relative not in online or relative not in local or online[relative] != local[relative]
        ])
        return {
            "project": project_dir.name,
            "project_id": project_id,
            "branch": branch,
            "online_head": online_head,
            "local_managed": total_local,
            "online_managed": total_online,
            "differences": rows,
            "total": total,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def push_from(project_dir: Path, files: list[tuple[str, Path]], args: dict[str, Any]) -> dict[str, Any]:
    base, token, allowed = _configured()
    project_id = _validated_project_id(args.get("project_id"))
    if allowed and project_id not in allowed:
        raise PlanError("overleaf project is outside the project allowlist")
    branch = _validated_branch(args)
    message = _validated_message(args.get("message"))
    remote = _remote_url(base, token, project_id)
    work = Path(tempfile.mkdtemp(prefix=".company-overleaf-"))
    try:
        clone_dir = work / "repo"
        _clone(remote, token, base, clone_dir, branch)
        actions: list[tuple[str, Path]] = []
        seen: set[str] = set()
        for relative, source in files:
            relative_path = relative.replace("\\", "/")
            parts = [part for part in relative_path.split("/") if part]
            if any(part in {".", ".."} for part in parts):
                raise PlanError("file path escapes the project")
            relative_path = "/".join(parts)
            if relative_path in seen or not _managed_relative(relative_path):
                continue
            seen.add(relative_path)
            if not source.read_bytes():
                continue
            if len(actions) >= MAX_SYNC_FILES:
                raise PlanError("project exceeds the bounded push size; archive manually")
            actions.append((relative_path, source))
        if not actions:
            raise PlanError("no managed latex files to push")
        for relative_path, source in actions:
            destination = clone_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            _run_git(["add", "--", relative_path], token=token, base=base, cwd=clone_dir)
        staged = _run_git(
            ["diff", "--cached", "--name-only"],
            token=token,
            base=base,
            cwd=clone_dir,
        )
        changes = sum(1 for line in staged.decode("utf-8", errors="replace").splitlines() if line.strip())
        if changes == 0:
            raise PlanError("no changes to commit; online project already matches")
        _run_git(
            [
                "-c", "user.name=company-agent",
                "-c", "user.email=company-agent@latex.invalid",
                "commit",
                "--no-gpg-sign",
                "-m", message,
            ],
            token=token,
            base=base,
            cwd=clone_dir,
        )
        head = _run_git(["rev-parse", "HEAD"], token=token, base=base, cwd=clone_dir)
        commit_sha = (head or b"").decode("ascii", errors="ignore").strip()
        if not re.fullmatch(r"[0-9a-f]{7,64}", commit_sha):
            raise PlanError("git bridge returned an invalid commit id")
        _run_git(
            ["push", "origin", "HEAD:refs/heads/" + branch],
            token=token,
            base=base,
            cwd=clone_dir,
        )
        return {
            "project": project_dir.name,
            "project_id": project_id,
            "branch": branch,
            "commit_sha": commit_sha,
            "changes": min(changes, MAX_SYNC_FILES),
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
