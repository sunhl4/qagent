"""Gates for the knowledge-registry re-approval maintenance tool.

The tool exists because an admitted knowledge document edited without
re-registration reliably blocks the whole builtin root (``stale_hash``) — the
workspace failure this batch fixed. Every refusal below is a counter-example
that must keep failing closed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def sync_module():
    spec = importlib.util.spec_from_file_location(
        "knowledge_registry_sync",
        Path(__file__).resolve().parents[1] / "scripts" / "knowledge_registry_sync.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _seal(root: Path, audiences: dict[str, str]) -> None:
    entries = [
        {"file": name, "sha256": _digest((root / name).read_bytes()),
         "audience": audience, "approved": True, "revoked": False, "expires_epoch": None}
        for name, audience in audiences.items()
    ]
    (root / "registry.json").write_text(
        json.dumps({"version": "1.0.0", "entries": entries}), encoding="utf-8")


@pytest.fixture
def drifted_root(tmp_path):
    """A seat mirroring the workspace failure: registered doc edited after admission."""

    root = tmp_path / "kb"
    root.mkdir()
    (root / "capability.md").write_text(
        "# 能力\n设备执行必须由 quantum_device_run 完成并经过人工批准。\n", encoding="utf-8")
    (root / "guide.md").write_text("# 指南\n知识检索结果必须登记准入。\n", encoding="utf-8")
    _seal(root, {"capability.md": "internal", "guide.md": "public"})
    # The deliberate post-approval edit that starves the index.
    (root / "capability.md").write_text(
        "# 能力\n设备执行必须由 quantum_device_run 完成并经过人工批准。\n"
        "云平台模拟器任务接受标准 OpenQASM-3 网络文本。\n", encoding="utf-8")
    return root


def _run_main(sync_module, argv, capsys):
    exit_code = sync_module.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured


def test_dry_run_reports_drift_without_writing(sync_module, drifted_root, capsys) -> None:
    before = (drifted_root / "registry.json").read_bytes()
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root)], capsys)
    report = json.loads(captured.out)
    assert exit_code == 1
    assert report["would_change"] is True
    assert report["committed"] is False
    changed = [row for row in report["changes"] if row["action"] == "reapproved"]
    assert [row["file"] for row in changed] == ["capability.md"]
    assert changed[0]["previous_sha256"] != changed[0]["sha256"]
    assert (drifted_root / "registry.json").read_bytes() == before


def test_write_reapproves_drift_and_restores_search(sync_module, drifted_root, capsys, monkeypatch) -> None:
    manual = json.loads((drifted_root / "registry.json").read_text())
    assert next(e["sha256"] for e in manual["entries"] if e["file"] == "capability.md") \
        != _digest((drifted_root / "capability.md").read_bytes())

    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root), "--write"], capsys)
    report = json.loads(captured.out)
    assert exit_code == 0
    assert report["committed"] is True
    assert report["applied_actions"] == 1
    sealed = sync_module._load_registry(drifted_root)
    expect = _digest((drifted_root / "capability.md").read_bytes())
    assert sealed["capability.md"]["sha256"] == expect

    # Serving behavior must follow the fresh identity, not the stale one.
    import company_agent.knowledge as knowledge

    monkeypatch.setattr(knowledge, "roots", lambda: (("builtin", drifted_root),))
    result = knowledge.search({"query": "设备执行"}, preset="lab")
    assert [row["source"] for row in result["hits"]] == ["builtin:capability.md"]
    assert result["scan"]["complete"] is True
    assert result["scan"]["reasons"] == []


def test_unregistered_file_requires_explicit_admit(sync_module, drifted_root, capsys) -> None:
    (drifted_root / "extra.md").write_text("未登记文档\n", encoding="utf-8")
    before = (drifted_root / "registry.json").read_bytes()
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root), "--write"], capsys)
    report = json.loads(captured.out)
    assert exit_code == 1
    assert report["committed"] is False
    assert any("needs explicit --admit: extra.md" in row for row in report["refusals"])
    assert (drifted_root / "registry.json").read_bytes() == before


def test_explicit_admit_defaults_to_internal_without_flipping(sync_module, drifted_root, capsys) -> None:
    (drifted_root / "extra.md").write_text("未登记文档\n", encoding="utf-8")
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root), "--write",
                      "--admit", "extra.md"], capsys)
    assert exit_code == 0
    sealed = sync_module._load_registry(drifted_root)
    assert sealed["extra.md"]["audience"] == "internal"
    assert sealed["extra.md"]["approved"] is True
    # Public entries that were never touched keep their audience.
    assert sealed["guide.md"]["audience"] == "public"


def test_admit_of_registered_file_refused(sync_module, drifted_root, capsys) -> None:
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root), "--admit", "guide.md"], capsys)
    report = json.loads(captured.out)
    assert exit_code == 1
    assert any("already admitted" in row for row in report["refusals"])


def test_drop_of_present_readable_file_refused(sync_module, drifted_root, capsys) -> None:
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root), "--write", "--drop", "guide.md"], capsys)
    report = json.loads(captured.out)
    assert exit_code == 1
    assert report["committed"] is False
    assert any("still present" in row for row in report["refusals"])


def test_drop_after_removal(sync_module, drifted_root, capsys, monkeypatch) -> None:
    (drifted_root / "guide.md").unlink()
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root), "--write", "--drop", "guide.md"], capsys)
    report = json.loads(captured.out)
    assert exit_code == 0
    assert report["committed"] is True
    sealed = sync_module._load_registry(drifted_root)
    assert "guide.md" not in sealed
    assert "capability.md" in sealed


def test_symlinked_registered_file_refused(sync_module, drifted_root, tmp_path, capsys, make_symlink) -> None:
    target = tmp_path / "outside.md"
    target.write_text("外部内容\n", encoding="utf-8")
    (drifted_root / "guide.md").unlink()
    make_symlink(target, drifted_root / "guide.md")
    exit_code, captured = _run_main(
        sync_module, ["--root", str(drifted_root)], capsys)
    report = json.loads(captured.out)
    assert exit_code == 1
    assert any("symlink" in row for row in report["refusals"])
    # The registry must be untouched even after a refused run.
    current = json.loads((drifted_root / "registry.json").read_text())
    assert {e["file"] for e in current["entries"]} == {"capability.md", "guide.md"}


def test_invalid_root_fails_closed(sync_module, tmp_path, capsys) -> None:
    missing = tmp_path / "missing"
    exit_code, _ = _run_main(sync_module, ["--root", str(missing)], capsys)
    assert exit_code == 1


def test_clean_registry_is_a_no_op(sync_module, drifted_root, capsys) -> None:
    # First write repairs the drift; the immediately following run must see
    # no pending change and succeed as a freshness gate.
    sync_module.main(["--root", str(drifted_root), "--write"])
    capsys.readouterr()
    exit_code, captured = _run_main(sync_module, ["--root", str(drifted_root)], capsys)
    report = json.loads(captured.out)
    assert exit_code == 0
    assert report["would_change"] is False
    assert report["committed"] is False
    assert [row["action"] for row in report["changes"]] == ["unchanged", "unchanged"]


def test_restored_registry_after_validator_failure(sync_module, drifted_root, monkeypatch) -> None:
    """If post-commit validation breaks, the previous bytes must come back."""

    before = (drifted_root / "registry.json").read_bytes()
    monkeypatch.setattr(sync_module, "_load_registry", lambda _root: None)
    with pytest.raises(sync_module.SyncError):
        sync_module.commit(drifted_root, {
            "changes": [{"file": "capability.md", "action": "reapproved", "sha256": "0" * 64,
                         "previous_sha256": "1" * 64}],
            "refusals": [],
            "entries": [{"file": "capability.md", "sha256": "0" * 64, "audience": "internal",
                         "approved": True, "revoked": False, "expires_epoch": None}],
        })
    assert (drifted_root / "registry.json").read_bytes() == before
