"""P0 workspace file foundation: fence, TOCTOU-safe open, fingerprint."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from company_agent.workspace_files import (
    WORKSPACE_ENV,
    WorkspaceFileError,
    fingerprint,
    open_file,
    resolve,
    root,
)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv(WORKSPACE_ENV, str(root))
    return root


def _symlink_supported(directory: Path) -> bool:
    probe = directory / "_probe_link"
    try:
        os.symlink("_probe_target", probe)
    except (OSError, NotImplementedError):
        return False
    finally:
        if probe.exists() or probe.is_symlink():
            os.unlink(probe)
    return True


def test_root_requires_a_configured_absolute_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    with pytest.raises(WorkspaceFileError):
        root()
    monkeypatch.setenv(WORKSPACE_ENV, str(tmp_path / "missing"))
    with pytest.raises(WorkspaceFileError):
        root()
    relative_root = tmp_path / "workspace"
    relative_root.mkdir()
    monkeypatch.setenv(WORKSPACE_ENV, relative_root.name)
    with pytest.raises(WorkspaceFileError):
        root()


@pytest.mark.parametrize(
    "relative",
    [
        "../outside.md",
        "a/../outside.md",
        "/etc/passwd",
        "a\\b.md",
        "a:/b.md",
        "~/notes.md",
        "a//b.md",
        "./notes.md",
        "notes/",
        "",
        " ",
        None,
        "x" * 257,
    ],
)
def test_lexical_fence_rejects_every_escape_shape(workspace: Path, relative) -> None:
    with pytest.raises(WorkspaceFileError):
        resolve(workspace, relative)


def test_resolve_rejects_root_itself(workspace: Path) -> None:
    with pytest.raises(WorkspaceFileError):
        resolve(workspace, "..")


def test_resolve_rejects_symlinks_out_of_the_root(workspace: Path) -> None:
    if not _symlink_supported(workspace):
        pytest.skip("symlink creation is not permitted on this account")
    outside = workspace.parent / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = workspace / "doomed.md"
    os.symlink(outside, link)
    with pytest.raises(WorkspaceFileError):
        resolve(workspace, "doomed.md")


def test_fingerprint_binds_path_to_streamed_sha256(workspace: Path) -> None:
    payload = b"alpha\nbeta\n" + b"x" * (65_536 * 2 + 7)
    target = workspace / "notes" / "big.md"
    target.parent.mkdir()
    target.write_bytes(payload)
    result = fingerprint(workspace, "notes/big.md")
    assert result == {
        "path": "notes/big.md",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def test_fingerprint_refreshes_after_file_change(workspace: Path) -> None:
    import company_agent.workspace_files as wf

    wf.MAX_BYTES = 64
    target = workspace / "small.md"
    target.write_bytes(b"a" * 100)
    with pytest.raises(WorkspaceFileError):
        fingerprint(workspace, "small.md")
    target.write_bytes(b"tiny")
    assert fingerprint(workspace, "small.md")["bytes"] == 4


def test_fingerprint_refuses_directories_and_missing_files(workspace: Path) -> None:
    (workspace / "adir").mkdir()
    with pytest.raises(WorkspaceFileError):
        fingerprint(workspace, "adir")
    with pytest.raises(WorkspaceFileError):
        fingerprint(workspace, "missing.md")


def test_open_file_refuses_a_swapped_in_symlink(workspace: Path) -> None:
    if not _symlink_supported(workspace):
        pytest.skip("symlink creation is not permitted on this account")
    outside = workspace.parent / "outside.bin"
    outside.write_bytes(b"draft payload that must not be readable via the fence")
    link = workspace / "swap.md"
    os.symlink(outside, link)
    try:
        with open_file(workspace, "swap.md"):
            raise AssertionError("symlinked entry must not open")
    except WorkspaceFileError as caught:
        assert "identity" in str(caught) or "readable" in str(caught)


def test_open_file_reads_the_verified_file(workspace: Path) -> None:
    target = workspace / "real.md"
    target.write_bytes(b"verified-bytes")
    with open_file(workspace, "real.md") as stream:
        assert stream.read() == b"verified-bytes"


def test_identity_guard_refuses_disagreeing_post_open_stat(workspace: Path, monkeypatch) -> None:
    """Deterministic TOCTOU check without winning an actual race.

    The guard must refuse whenever the opened file object and a fresh
    ``lstat`` disagree. Exercised directly by substituting the post-open
    ``lstat`` with one of a different file object, exactly what a successful
    symlink/rename race would produce.
    """

    import company_agent.workspace_files as wf

    target = workspace / "victim.md"
    target.write_bytes(b"real-bytes")
    decoy = workspace / "decoy.bin"
    decoy.write_bytes(b"decoy-bytes")

    real_lstat = os.lstat
    decoy_stat = decoy_stat = decoy.lstat()

    def rigged_lstat(path, *args, **kwargs):
        if str(path) == str(target):
            return decoy_stat
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(wf.os, "lstat", rigged_lstat)
    with pytest.raises(WorkspaceFileError) as caught, open_file(workspace, "victim.md"):
        pass
    monkeypatch.setattr(wf.os, "lstat", real_lstat)
    with open_file(workspace, "victim.md") as stream:
        assert stream.read() == b"real-bytes"
    assert "identity" in str(caught)


def test_open_file_yields_the_fresh_content_after_honest_replacement(workspace: Path) -> None:
    target = workspace / "victim.md"
    target.write_bytes(b"first")
    with open_file(workspace, "victim.md") as stream:
        assert stream.read() == b"first"
    target.write_bytes(b"second")
    with open_file(workspace, "victim.md") as stream:
        assert stream.read() == b"second"
