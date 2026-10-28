"""company.workflow bounded workspace file reference binding (P3 context slice).

The tool encodes the file-reference half of the「会话、消息、文件引用」
work package: it binds exactly one file inside the mounted workspace root
(``COMPANY_AGENT_TOOL_WORKSPACE``) to a metadata record — sha256, byte size,
line count and a text/binary classification — without returning any file
content. Reads before binds reopen the bounded-read problem (H39): a
reference record has an explicit read path, an explicit byte budget and an
explicit truncated marker so partial binds cannot pass as complete.
Workspace-gated and fail closed: no root, relative-path escapes, missing
files, directories and symlinks out of the root all refuse. Files are
untrusted reference data; the trust marker is constant. This module never
imports the contract kernel and creates no model, session or tool loops.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

WORKSPACE_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"

MAX_DIGEST_BYTES = 2_000_000
MAX_SNIFF_BYTES = 4096
_TEXT_SUFFIXES = {".md", ".txt", ".csv", ".log", ".yaml", ".yml", ".toml", ".json", ".py", ".tex"}


class ReferenceError(ValueError):
    """Bounded reference failure without echoing paths outside the workspace."""


def _root() -> Path:
    raw = str(os.environ.get(WORKSPACE_ENV) or "").strip()
    if not raw:
        raise ReferenceError(f"workspace root is not configured ({WORKSPACE_ENV})")
    root = Path(raw)
    if not root.is_absolute():
        raise ReferenceError("workspace root must be an absolute path")
    try:
        resolved = root.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ReferenceError("workspace root is not available") from exc
    if not resolved.is_dir():
        raise ReferenceError("workspace root is not a directory")
    return resolved


def _target(root: Path, raw: object) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ReferenceError("workspace reference path is invalid")
    relative = raw.strip()
    if relative.startswith("/") or "\\" in relative or "\x00" in relative:
        raise ReferenceError("workspace reference path is invalid")
    if any(segment in {"", ".."} for segment in relative.split("/")):
        raise ReferenceError("workspace reference path is invalid")
    if len(relative.encode("utf-8")) > 256:
        raise ReferenceError("workspace reference path is invalid")
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ReferenceError("workspace reference is not available") from exc
    try:
        inside = resolved.is_relative_to(root)
    except (OSError, ValueError):
        inside = False
    if not inside or resolved == root:
        raise ReferenceError("workspace reference escapes the workspace root")
    if not resolved.is_file():
        raise ReferenceError("workspace reference is not a file")
    return resolved


def reference(args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise TypeError("workspace reference arguments must be a JSON object")
    unknown = set(args) - {"path"}
    if unknown:
        raise ValueError(f"workspace reference has unknown fields: {sorted(unknown)}")
    root = _root()
    resolved = _target(root, args.get("path"))
    relative = ""
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:  # pragma: no cover — _target already guarantees containment
        raise ReferenceError("workspace reference escapes the workspace root") from exc
    size = resolved.stat().st_size
    if size < 0 or size > 16_000_000:
        raise ReferenceError("workspace reference exceeds the bounded size")
    truncated = size > MAX_DIGEST_BYTES
    with resolved.open("rb") as handle:
        head = handle.read(MAX_SNIFF_BYTES + 1)
    suffix = resolved.suffix.casefold()
    if suffix in _TEXT_SUFFIXES:
        kind = "text"
    else:
        try:
            kind = "text" if b"\x00" not in head else "binary"
            if kind == "text":
                head.decode("utf-8")
        except UnicodeError:
            kind = "binary"
    digest = ""
    if not truncated:
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    lines = 0
    if kind == "text":
        with resolved.open("rb") as handle:
            counted = 0
            last = b""
            while True:
                chunk = handle.read(65_536)
                if not chunk:
                    break
                counted += chunk.count(b"\n")
                last = chunk[-1:]
            if last and last != b"\n":
                counted += 1
        lines = counted
    return {
        "path": relative,
        "sha256": digest,
        "bytes": int(size),
        "lines": int(lines),
        "kind": kind,
        "truncated": truncated,
        "trust": "untrusted_reference_data",
    }
