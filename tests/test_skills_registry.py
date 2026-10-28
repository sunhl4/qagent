"""Architecture gates for the skill admission lifecycle (survey P1 3.3)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _verify_skills():
    spec = importlib.util.spec_from_file_location("verify_skills", ROOT / "scripts/verify_skills.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "src"))
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def verify_skills():
    return _verify_skills()


@pytest.fixture()
def mount_root(tmp_path):
    return tmp_path / "skills"


def _registry_digests() -> dict[str, str]:
    payload = json.loads((ROOT / "contracts/skills.json").read_text(encoding="utf-8"))
    return {row["name"]: row for row in payload["skills"]}


def test_sync_matches_registry_selection(verify_skills, mount_root) -> None:
    # company-agent + lab mirrors the historical binary selection.
    assert verify_skills.sync(root=mount_root, profile="company-agent", preset="lab") == 0
    assert {path.name for path in mount_root.iterdir()} == {
        "company-knowledge", "company-docs-research", "quantum-workflow",
        "company-plan",
    }
    for name, row in _registry_digests().items():
        mounted = mount_root / name / Path(row["path"]).name
        if (mount_root / name).is_dir():
            assert hashlib.sha256(mounted.read_bytes()).hexdigest() == row["sha256"]


def test_sync_composes_minimal_profile_boot(verify_skills, mount_root) -> None:
    assert verify_skills.sync(root=mount_root, profile="company-agent-minimal", preset="boot") == 0
    assert {path.name for path in mount_root.iterdir()} == {
        "company-knowledge", "company-docs-research", "company-software-development",
    }


def test_verify_passes_on_a_fresh_mount(verify_skills, mount_root) -> None:
    verify_skills.sync(root=mount_root, profile="company-agent", preset="lab")
    assert verify_skills.verify(root=mount_root, profile="company-agent", preset="lab") == 0


def test_verify_catches_stray_files(verify_skills, mount_root) -> None:
    verify_skills.sync(root=mount_root, profile="company-agent", preset="lab")
    (mount_root / "stray-notes.md").write_text("not admitted", encoding="utf-8")
    assert verify_skills.verify(root=mount_root, profile="company-agent", preset="lab") == 1


def test_verify_catches_digest_drift(verify_skills, mount_root) -> None:
    verify_skills.sync(root=mount_root, profile="company-agent", preset="lab")
    target = mount_root / "company-knowledge" / "SKILL.md"
    target.write_bytes(target.read_bytes() + b"\n<!-- drifted -->\n")
    assert verify_skills.verify(root=mount_root, profile="company-agent", preset="lab") == 1


def test_revoked_entry_never_mounts(verify_skills, mount_root, monkeypatch) -> None:
    payload = json.loads((ROOT / "contracts/skills.json").read_text(encoding="utf-8"))
    revoked_name = payload["skills"][0]["name"]
    real_load = verify_skills.load_skills

    def mutated():
        original = real_load()
        rows = dict(original)
        rows[revoked_name]["revoked"] = True
        return rows

    monkeypatch.setattr(verify_skills, "load_skills", mutated)
    assert verify_skills.sync(root=mount_root, profile="company-agent", preset="lab") == 0
    names = {path.name for path in mount_root.iterdir()}
    assert revoked_name not in names
    assert verify_skills.verify(root=mount_root, profile="company-agent", preset="lab") == 0


def test_missing_registered_file_fails_sync(verify_skills, mount_root, monkeypatch) -> None:
    source = ROOT / "skills/company-docs-research/SKILL.md"
    backup = source.with_suffix(".md.bak")
    shutil.move(str(source), str(backup))
    try:
        assert verify_skills.sync(root=mount_root, profile="company-agent", preset="lab") == 1
    finally:
        shutil.move(str(backup), str(source))
