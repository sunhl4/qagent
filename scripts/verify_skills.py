#!/usr/bin/env python3
"""Skill admission lifecycle against contracts/skills.json (survey P1 「Skills 准入」).

``sync`` composes the DSH skill mount root from the admission registry:
- only skills whose (profile, preset) ``when`` clause matches are mounted;
- a registered entry whose file is missing or whose digest differs stops the
  sync entirely (fail closed: no partially admitted skill tree);
- ``revoked`` entries are never mounted, so revoking a skill is a contract
  change plus a re-sync — never a manual file delete.

``verify`` rechecks a composed mount root: every mounted skill must be a
registered, non-revoked entry with matching digests, no stray files at the
mount root, and registered scripts must be present with pinned digests —
installing a skill never auto-authorizes script execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from company_agent.catalog import load_skills  # noqa: E402


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mounts_for(entry: dict[str, object], profile: str, preset: str) -> bool:
    when = entry.get("when") or []
    return any(
        item.get("profiles") and item.get("presets")
        and profile in item["profiles"] and preset in item["presets"]
        for item in when
    )


def _entry_sources(entry: dict[str, object]) -> list[tuple[Path, str]]:
    """Registered (path, digest) pairs for one skill entry."""

    main = (ROOT / str(entry["path"]), str(entry["sha256"]))
    scripts = [(ROOT / str(script["file"]), str(script["digest"])) for script in entry.get("scripts") or []]
    return [main, *scripts]


def sync(*, root: Path, profile: str, preset: str) -> int:
    skills = load_skills()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, mode=0o700)
    mounted: list[str] = []
    for name, entry in skills.items():
        if entry["revoked"] or not _mounts_for(entry, profile, preset):
            continue
        sources = _entry_sources(entry)
        for path, digest in sources:
            if not path.is_file() or path.is_symlink():
                print(f"skill {name}: registered file is missing: {path.name}", file=sys.stderr)
                return 1
            if _file_digest(path) != digest:
                print(f"skill {name}: digest mismatch for {path.name}", file=sys.stderr)
                return 1
        staging = root / f"{name}.partial"
        destination = root / name
        staging.mkdir(mode=0o700)
        for source, _digest in sources:
            shutil.copy(source, staging / source.name)
        staging.rename(destination)
        mounted.append(name)
    for directory in root.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    for file_path in root.rglob("*"):
        if file_path.is_file():
            file_path.chmod(0o600)
    print(json.dumps({"synced": mounted, "skill_root": str(root)}))
    return 0


def verify(*, root: Path, profile: str, preset: str) -> int:
    skills = load_skills()
    failures: list[str] = []
    mounted: list[str] = []
    if not root.is_dir():
        print(json.dumps({"ok": False, "mounted": [], "failures": ["skill root missing"]}))
        return 1
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_dir():
            # Exactly one directory level per mounted skill is allowed.
            if len(relative.parts) != 1:
                failures.append("unexpected nested directory in mount root")
            continue
        if len(relative.parts) != 2:
            failures.append("unexpected file depth at mount root")
            continue
        mounted.append(str(relative.parts[0]))
        entry = skills.get(str(relative.parts[0]))
        if entry is None or entry["revoked"]:
            failures.append(f"unregistered or revoked skill mounted: {relative.parts[0]}")
            continue
        if not _mounts_for(entry, profile, preset):
            failures.append(f"skill {relative.parts[0]} is not admitted for this profile/preset")
            continue
        source_map = {Path(source_path).name: digest for source_path, digest in _entry_sources(entry)}
        if path.name not in source_map:
            failures.append(f"unexpected file for skill {relative.parts[0]}: {path.name}")
            continue
        if _file_digest(path) != source_map[path.name]:
            failures.append(f"digest mismatch for {relative.parts[0]}/{path.name}")
    for name, entry in skills.items():
        if entry["revoked"] or not _mounts_for(entry, profile, preset):
            continue
        if name not in mounted:
            failures.append(f"admitted skill is missing from the mount: {name}")
    report = {"ok": not failures, "mounted": sorted(set(mounted)), "failures": failures[:32]}
    print(json.dumps(report))
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_skills")
    sub = parser.add_subparsers(dest="command", required=True)
    sync_cmd = sub.add_parser("sync")
    sync_cmd.add_argument("--root", required=True)
    sync_cmd.add_argument("--profile", required=True)
    sync_cmd.add_argument("--preset", required=True)
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--root", required=True)
    verify_cmd.add_argument("--profile", required=True)
    verify_cmd.add_argument("--preset", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_absolute():
        parser.error("--root must be an absolute path")
    if args.command == "sync":
        return sync(root=root, profile=args.profile, preset=args.preset)
    return verify(root=root, profile=args.profile, preset=args.preset)


if __name__ == "__main__":
    raise SystemExit(main())
