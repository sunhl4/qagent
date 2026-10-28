"""P3-B3 bounded workspace file reference binding (company_workspace_reference)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from company_agent.invoke import invoke
from company_agent.workspace_reference import WORKSPACE_ENV, ReferenceError, reference


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv(WORKSPACE_ENV, str(root))
    return root


def test_reference_requires_a_configured_workspace(monkeypatch) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    with pytest.raises(ReferenceError) as caught:
        reference({"path": "notes.md"})
    assert "workspace root is not configured" in str(caught.value)


def test_reference_binds_text_file_metadata(workspace: Path) -> None:
    target = workspace / "notes.md"
    target.write_bytes(b"hello\nworkspace\n")
    result = reference({"path": "notes.md"})
    assert result == {
        "path": "notes.md",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "bytes": 16,
        "lines": 2,
        "kind": "text",
        "truncated": False,
        "trust": "untrusted_reference_data",
    }


def test_reference_counts_nested_paths_and_lfless_tail(workspace: Path) -> None:
    nested = workspace / "data" / "2026" / "log.txt"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"a\nb\nc")  # no trailing newline, three lines
    result = reference({"path": "data/2026/log.txt"})
    assert result["path"] == "data/2026/log.txt"
    assert result["lines"] == 3
    assert result["kind"] == "text"


def test_reference_classifies_binary_as_binary(workspace: Path) -> None:
    payload = bytes(range(256)) * 32
    (workspace / "blob.bin").write_bytes(payload)
    result = reference({"path": "blob.bin"})
    assert result["kind"] == "binary" and result["lines"] == 0
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["truncated"] is False


def test_reference_oversize_file_binds_partial(workspace: Path) -> None:
    payload = b"a\n" * 1_200_000  # 2.4MB > digest budget
    (workspace / "big.log").write_bytes(payload)
    result = reference({"path": "big.log"})
    assert result["truncated"] is True
    assert result["sha256"] == ""
    assert result["kind"] == "text"
    assert result["lines"] == 1_200_000
    assert result["bytes"] == len(payload)


def test_reference_rejects_escapes_and_missing_targets(workspace: Path, make_symlink) -> None:
    outside = workspace.parent / "outside.txt"
    outside.write_bytes(b"x\n")
    make_symlink(outside, workspace / "escape.md")
    (workspace / "folder").mkdir()
    for args in (
        {"path": "../outside.txt"},
        {"path": "/etc/passwd"},
        {"path": "missing.md"},
        {"path": "folder"},  # a directory, not a file
        {"path": "escape.md"},
    ):
        with pytest.raises(ReferenceError):
            reference(args)


def test_reference_requires_object_arguments(monkeypatch) -> None:
    monkeypatch.setenv(WORKSPACE_ENV, "/tmp/isolated-workspace-check")
    with pytest.raises((TypeError, ValueError, ReferenceError)):
        reference({"path": "x.md", "extra": 1})


def test_invoke_wires_reference_and_marks_untrusted(workspace: Path, monkeypatch, capsys) -> None:
    import os

    from company_agent import budget

    (workspace / "hello.txt").write_bytes(b"hi\n")
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", "reference-check")
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", "operator@corp.example.com")
    try:
        result = invoke("company_workspace_reference", "lab", {"path": "hello.txt"})
        assert result.status == "ok"
        assert result.payload["trust"] == "untrusted_reference_data"
        denied = invoke("company_workspace_reference", "sign", {"path": "hello.txt"})
        assert denied.status == "denied"
        assert budget.counts()["invocations"] == 1
    finally:
        budget.reset("reference-check")
        os.environ.pop("COMPANY_AGENT_SUBJECT", None)
