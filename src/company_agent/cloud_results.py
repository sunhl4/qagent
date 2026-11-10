"""Workspace copies of cloud probability tables. The model sees one page."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_TASK = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_DEFAULT_LIMIT = 32
_MAX_LIMIT = 64


class CloudResultError(ValueError):
    """The stored probability table cannot be read."""


def _task_file(task: str) -> str:
    if not isinstance(task, str) or not _TASK.fullmatch(task):
        raise CloudResultError("cloud task is invalid")
    return hashlib.sha256(task.encode("utf-8")).hexdigest() + ".json"


def _root(workspace: str) -> Path | None:
    if not workspace:
        return None
    root = Path(workspace)
    if not root.is_absolute() or not root.is_dir():
        return None
    resolved = root.resolve()
    if resolved.is_symlink():
        return None
    return resolved


def artifact_relative(task: str) -> str:
    return f".company-agent/results/{_task_file(task)}"


def _destination(root: Path, task: str) -> Path:
    relative = artifact_relative(task)
    destination = (root / relative).resolve()
    if root != destination and root not in destination.parents:
        raise CloudResultError("result artifact path is invalid")
    if destination.is_symlink() or destination.parent.is_symlink():
        raise CloudResultError("result artifact path is invalid")
    return destination


def limit_of(value: object, default: int = _DEFAULT_LIMIT) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_LIMIT:
        raise CloudResultError("result page limit is invalid")
    return value


def store_table(workspace: str, task: str, shots: int, items: list) -> str:
    """Write the full table. Returns a workspace-relative path, or empty when there is no workspace."""
    root = _root(workspace)
    if root is None:
        return ""
    destination = _destination(root, task)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cloud_task": task, "shots": shots, "items": items}
    temporary = destination.with_suffix(".tmp")
    if temporary.is_symlink():
        raise CloudResultError("result artifact path is invalid")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(destination)
    return artifact_relative(task)


def read_page(workspace: str, task: str, offset: int = 0, limit: int | None = None) -> dict:
    root = _root(workspace)
    if root is None:
        raise CloudResultError("result artifact unavailable")
    page_limit = limit_of(limit)
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 256:
        raise CloudResultError("result page offset is invalid")
    destination = _destination(root, task)
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise CloudResultError("result artifact unavailable") from exc
    if not isinstance(payload, dict) or payload.get("cloud_task") != task:
        raise CloudResultError("result artifact unavailable")
    items = payload.get("items")
    shots = payload.get("shots")
    if not isinstance(items, list) or isinstance(shots, bool) or not isinstance(shots, int):
        raise CloudResultError("result artifact unavailable")
    page = items[offset:offset + page_limit]
    return {
        "cloud_task": task,
        "offset": offset,
        "limit": page_limit,
        "shots": shots,
        "omitted_states": max(0, len(items) - offset - len(page)),
        "artifact_path": artifact_relative(task),
        "items": page,
    }
