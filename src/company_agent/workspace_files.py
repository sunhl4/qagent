"""Workspace file foundation for the WPS-suite porting (P0).

Per WPS-SUITE-PORTING ~section~6.3 the P0 slice is the shared machinery every later
slice (P1 ingestion, P2 spreadsheets, P3 docx revisions, P4.5 matter
artifacts) sits on: one path fence, one race-safe file opener and one content
fingerprint. Fail closed:

- the workspace root is an absolute, existing directory named by
  ``COMPANY_AGENT_TOOL_WORKSPACE`` (shared with workspace_reference);
- relative paths are lexical-only: no absolute forms, no backslashes, no
  ``..``/empty segments, no drive or ``~`` segments, bounded length;
- every open re-verifies the identity of the opened file object against the
  directory entry it was resolved from, so a symlink or rename swapped in
  between the two steps cannot be followed (TOCTOU);
- fingerprints stream, so bounded size is checked after, not by, the read.
"""
from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, cast

WORKSPACE_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"

MAX_PATH_BYTES = 256
DIGEST_CHUNK = 65_536
MAX_BYTES = 16_000_000
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_DIR_FD_OK = os.name == "posix"


class WorkspaceFileError(ValueError):
    """Fence, race or fingerprint failure without echoing paths outside the root."""


def root() -> Path:
    raw = str(os.environ.get(WORKSPACE_ENV) or "").strip()
    if not raw:
        raise WorkspaceFileError(f"workspace root is not configured ({WORKSPACE_ENV})")
    root_path = Path(raw)
    if not root_path.is_absolute():
        raise WorkspaceFileError("workspace root must be an absolute path")
    try:
        resolved = root_path.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise WorkspaceFileError("workspace root is not available") from exc
    if not resolved.is_dir():
        raise WorkspaceFileError("workspace root is not a directory")
    return resolved


def _lexical(relative: str | None) -> str:
    if not isinstance(relative, str) or not relative.strip():
        raise WorkspaceFileError("workspace path is invalid")
    candidate = relative.strip()
    if candidate.startswith("/") or "\\" in candidate or "\x00" in candidate:
        raise WorkspaceFileError("workspace path is invalid")
    for segment in candidate.split("/"):
        if segment in {"", ".", ".."}:
            raise WorkspaceFileError("workspace path is invalid")
        if ":" in segment or segment.startswith("~"):
            raise WorkspaceFileError("workspace path is invalid")
    if len(candidate.encode("utf-8")) > MAX_PATH_BYTES:
        raise WorkspaceFileError("workspace path is invalid")
    return candidate


def _inside(root_path: Path, resolved: Path) -> bool:
    try:
        canonical_root = root_path.resolve(strict=True)
        return resolved.is_relative_to(canonical_root) and resolved != canonical_root
    except (OSError, ValueError):
        return False


def resolve(root_value: Path, relative: str | None) -> Path:
    """Resolve ``relative`` inside ``root_value`` behind both fences.

    The lexical fence rejects escape attempts before any system call; the
    resolve fence catches symlinks or devices that already point outside the
    workspace.
    """

    candidate = root_value / _lexical(relative)
    _reject_link_components(root_value, candidate)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise WorkspaceFileError("workspace file is not available") from exc
    if not _inside(root_value, resolved):
        raise WorkspaceFileError("workspace path escapes the workspace root")
    return resolved


@contextmanager
def _owned(fd: int) -> Iterator[BinaryIO]:
    try:
        stream = os.fdopen(fd, "rb", closefd=True)
    except BaseException:
        os.close(fd)
        raise
    with stream:
        yield stream


def _refused_entry(entry: os.stat_result) -> bool:
    """True when the directory entry itself is a link instead of a regular file.

    POSIX rejects with ``O_NOFOLLOW``; Windows has no ``O_NOFOLLOW`` so the
    pre-open ``lstat`` must refuse symlinks (``S_ISLNK``) and any reparse
    point (``st_reparse_tag`` covers junctions and other link-like entries).
    """

    link = stat.S_ISLNK(entry.st_mode)
    tag = int(cast(int, getattr(entry, "st_reparse_tag", 0)))
    return link or (os.name == "nt" and tag != 0)


def _reject_link_components(root_path: Path, candidate: Path) -> None:
    """Reject symlink/reparse components, including intermediate directories."""

    try:
        relative = candidate.relative_to(root_path)
    except ValueError as exc:
        raise WorkspaceFileError("workspace path escapes the workspace root") from exc
    current = root_path
    for part in relative.parts:
        current = current / part
        try:
            entry = os.lstat(current)
        except OSError as exc:
            raise WorkspaceFileError("workspace file is not readable") from exc
        if _refused_entry(entry):
            raise WorkspaceFileError("workspace path escapes the workspace root")


def _same_identity(opened: os.stat_result, entry: os.stat_result) -> bool:
    """Compare the opened object with a fresh directory entry by identity.

    POSIX offers stable ``(st_dev, st_ino)`` pairs on both ``fstat`` and
    ``lstat``. Windows reports inconsistent ``st_dev`` values across the two
    APIs but a stable ``st_ino`` on NTFS, so ``st_ino`` carries the check;
    where ``st_ino`` is zero (FAT-style volumes) only the device is shared
    between the two paths -- the guard then degrades to device equality.
    """

    if opened.st_ino != entry.st_ino:
        return False
    if entry.st_ino:
        return os.name == "nt" or opened.st_dev == entry.st_dev
    return opened.st_dev == entry.st_dev


def open_file(root_value: Path, relative: str | None) -> Any:
    """Context manager yielding a read handle re-verified after the open.

    Race plan (TOCTOU): on POSIX the open uses ``O_NOFOLLOW`` on a
    root-relative path; Windows has neither ``dir_fd`` nor ``O_NOFOLLOW`` so
    it refuses link-like entries with a pre-open ``lstat`` instead. Either
    way the opened object is then compared with a fresh ``lstat`` of the same
    path. If the entry was swapped to a different file object -- as any
    symlink or rename race produces -- the identities disagree and the open is
    refused.
    """

    lexical = _lexical(relative)
    candidate = root_value / lexical
    if _DIR_FD_OK:
        try:
            dirs_fd = os.open(root_value, os.O_RDONLY | _CLOEXEC)
        except OSError as exc:
            raise WorkspaceFileError("workspace root is not available") from exc
    else:
        try:
            _reject_link_components(root_value, candidate)
        except WorkspaceFileError:
            raise
        except OSError as exc:
            raise WorkspaceFileError("workspace file is not readable") from exc
    try:
        try:
            if _DIR_FD_OK:
                fd = os.open(lexical, os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=dirs_fd)
            else:
                fd = os.open(candidate, os.O_RDONLY | _BINARY | _CLOEXEC)
        except (OSError, TypeError, NotImplementedError):
            raise WorkspaceFileError("workspace file is not readable") from None
        try:
            opened = os.fstat(fd)
            entry = os.lstat(candidate)
        except OSError as exc:
            os.close(fd)
            raise WorkspaceFileError("workspace file is not readable") from exc
        if not _same_identity(opened, entry):
            os.close(fd)
            raise WorkspaceFileError("workspace file identity changed during open")
    finally:
        if _DIR_FD_OK:
            os.close(dirs_fd)
    return _owned(fd)


def fingerprint(root_value: Path, relative: str | None) -> dict[str, Any]:
    """Bind a relative workspace path to its streaming sha256 and byte size."""

    resolved = resolve(root_value, relative)
    if not resolved.is_file():
        raise WorkspaceFileError("workspace path is not a file")
    bounded = resolved.relative_to(root_value).as_posix()
    digest = hashlib.sha256()
    size = 0
    with open_file(root_value, bounded) as stream:
        while True:
            chunk = stream.read(DIGEST_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    if size > MAX_BYTES:
        raise WorkspaceFileError("workspace file exceeds the bounded size")
    return {"path": bounded, "sha256": digest.hexdigest(), "bytes": int(size)}
