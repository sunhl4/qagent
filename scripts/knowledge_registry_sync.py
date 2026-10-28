#!/usr/bin/env python3
"""Re-approve the builtin knowledge registry after deliberate document updates.

The knowledge admission registry (``knowledge/registry.json``) pins sha256
digests of every admitted document. When a document is edited without
re-registration, the search layer fails closed on that root (``stale_hash``)
instead of serving content under a registered identity. This administrative
tool makes the required follow-up explicit and auditable:

- drifted digests of ALREADY ADMITTED files are re-approved by default and
  every digest change is printed (the regular maintenance case);
- unregistered documents only enter through an explicit ``--admit`` per file
  (audience ``internal``); a deliberate audience change is a governance
  decision made by editing the registry, not by this tool;
- registered files missing on disk only leave through an explicit ``--drop``;
- audience, approved, revoked and expiry flags are copied unchanged — a sync
  can never silently flip a governance decision;
- without ``--write`` nothing is committed and a pending diff exits non-zero,
  so the run doubles as a registry freshness gate;
- after a commit the bytes are re-validated through the runtime's own
  admission validator and every digest is rechecked against on-disk bytes; on
  any failure the previous registry is restored atomically.

Administrative tooling, never imported by the Agent runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from company_agent.knowledge import _TEXT_SUFFIXES, _load_registry  # noqa: E402

REGISTRY_NAME = "registry.json"
REGISTRY_VERSION = "1.0.0"
REGISTRY_LIMIT = 512
MAX_KNOWLEDGE_FILE_BYTES = 1_000_000
PATH_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")


class SyncError(RuntimeError):
    """Refusal or integrity failure that leaves the registry untouched."""


def _syntactic_relative(token: str) -> PurePosixPath:
    if "\x00" in token or "\\" in token or not PATH_TOKEN.fullmatch(token):
        raise SyncError(f"invalid knowledge path token: {token!r}")
    relative = PurePosixPath(token)
    if relative.is_absolute() or ".." in relative.parts:
        raise SyncError(f"not a relative knowledge file inside the root: {token!r}")
    for part in relative.parts:
        if part.startswith(".") or part.endswith("~"):
            raise SyncError(f"refusing directory part {part!r} of {token!r}")
    if not token.endswith(tuple(sorted(_TEXT_SUFFIXES))):
        raise SyncError(
            f"only {'/'.join(sorted(_TEXT_SUFFIXES))} files are knowledge entries: {token!r}")
    return relative


def _checked_relative(root: Path, token: str, *, require_file: bool) -> str:
    relative = _syntactic_relative(token)
    if not require_file:
        # A drop token names a registry key: a root-relative literal it must stay
        # bounded by syntax alone; the file itself may already be absent.
        return token
    target = root / Path(*relative.parts)
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise SyncError(f"knowledge path {token!r} is not available: {exc}") from exc
    if resolved.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(root):
        raise SyncError(f"not a regular knowledge file inside the root: {token!r}")
    return token


def _entry_bytes(root: Path, file_path: str) -> bytes:
    """Current on-disk bytes of a registered file, with integrity refusals."""

    target = root / Path(*PurePosixPath(file_path).parts)
    try:
        if target.is_symlink() or not target.is_file():
            raise SyncError(f"registered path is not a regular file, --drop or fix it: {file_path!r}")
        raw = target.read_bytes()
    except SyncError:
        raise
    except OSError as exc:
        raise SyncError(f"cannot read registered file {file_path!r}: {exc}") from exc
    if len(raw) > MAX_KNOWLEDGE_FILE_BYTES:
        raise SyncError(f"registered file exceeds the knowledge file budget: {file_path!r}")
    return raw


def build_plan(root: Path, admit: set[str], drop: set[str]) -> dict:
    """Diff current root state against the registry without writing anything."""

    current = _load_registry(root)
    if current is None:
        raise SyncError(f"no admission registry to sync at {REGISTRY_NAME} (legacy mode)")
    if overlap := admit & drop:
        raise SyncError(f"cannot admit and drop the same files: {sorted(overlap)}")

    changes: list[dict] = []
    refusals: list[str] = []
    kept: dict[str, dict] = {}
    on_disk: set[str] = set()
    symlinked: set[str] = set()
    try:
        discovered = sorted(root.rglob("*"))
    except OSError as exc:
        raise SyncError(f"cannot enumerate the knowledge root: {exc}") from exc
    for path in discovered:
        try:
            relative = path.relative_to(root)
        except (OSError, ValueError):
            continue  # escaped or unreadable tree: unknown content is never admitted
        if path.is_symlink():
            symlinked.add(relative.as_posix())
            continue
        if not path.is_file() or path.suffix.casefold() not in _TEXT_SUFFIXES:
            continue
        on_disk.add(relative.as_posix())

    for relative, entry in sorted(current.items()):
        if relative in drop:
            if relative in symlinked or relative not in on_disk:
                pass  # absent (or unreachable) on disk: dropping the registration is correct
            else:
                try:
                    _entry_bytes(root, relative)
                except SyncError:
                    pass  # unreadable on-disk copy cannot be kept honest; registration may leave
                else:
                    refusals.append(
                        f"file is still present and readable; remove it before --drop: {relative}")
                    continue
            changes.append({"file": relative, "action": "dropped", "previous_sha256": entry["sha256"]})
            continue
        if relative in symlinked:
            refusals.append(f"registered file is now a symlink, --drop or fix it: {relative}")
            continue
        if relative not in on_disk:
            refusals.append(f"registered file is missing on disk, needs explicit --drop: {relative}")
            continue
        try:
            raw = _entry_bytes(root, relative)
        except SyncError as exc:
            refusals.append(str(exc))
            continue
        digest = hashlib.sha256(raw).hexdigest()
        kept[relative] = {**entry, "sha256": digest}
        action = "reapproved" if digest != entry["sha256"] else "unchanged"
        row = {"file": relative, "action": action, "sha256": digest}
        if action == "reapproved":
            row["previous_sha256"] = entry["sha256"]
        changes.append(row)
    for relative in sorted(on_disk - set(current) - admit - drop):
        refusals.append(f"unregistered knowledge file needs explicit --admit: {relative}")
    for relative in sorted(admit):
        if current.get(relative) is not None:
            refusals.append(f"already admitted, refusing a silent re-audience via --admit: {relative}")
            continue
        try:
            raw = _entry_bytes(root, relative)
        except SyncError as exc:
            refusals.append(str(exc))
            continue
        if len(raw) > MAX_KNOWLEDGE_FILE_BYTES:
            refusals.append(f"file exceeds the knowledge file budget: {relative}")
            continue
        digest = hashlib.sha256(raw).hexdigest()
        kept[relative] = {"file": relative, "sha256": digest, "audience": "internal",
                          "approved": True, "revoked": False, "expires_epoch": None}
        changes.append({"file": relative, "action": "admitted", "sha256": digest})
    if len(kept) > REGISTRY_LIMIT or len(kept) != len({row["file"] for row in kept.values()}):
        raise SyncError("candidate registry would be invalid (count or uniqueness)")
    changes.sort(key=lambda row: (row["action"], row["file"]))
    return {
        "changes": changes,
        "refusals": sorted(refusals),
        "entries": [kept[key] for key in sorted(kept)],
    }


def _bytes_for(plan: dict) -> bytes:
    rows = plan["entries"]
    items = "\n".join(
        "    " + json.dumps(row, ensure_ascii=False) + ("," if index < len(rows) - 1 else "")
        for index, row in enumerate(rows)
    )
    lines = ["{", '  "version": "1.0.0",', '  "entries": [']
    if rows:
        lines.append(items)
    lines.extend(["  ]", "}"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def _swap(root: Path, payload: bytes) -> None:
    """Atomically replace registry.json with payload bytes."""

    handle, temp_name = tempfile.mkstemp(dir=root, prefix=".registry-", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(temp, root / REGISTRY_NAME)
    finally:
        temp.unlink(missing_ok=True)


def commit(root: Path, plan: dict) -> None:
    """Write the candidate bytes, verify with the runtime validator; restore on failure."""

    registry = root / REGISTRY_NAME
    previous = registry.read_bytes()
    _swap(root, _bytes_for(plan))
    problem: str | None = None
    try:
        verified = _load_registry(root)
        if verified is None or set(verified) != {row["file"] for row in plan["entries"]}:
            problem = "committed bytes fail admission validation"
        else:
            for file_path, row in verified.items():
                if hashlib.sha256(_entry_bytes(root, file_path)).hexdigest() != row["sha256"]:
                    problem = f"post-commit digest mismatch for {file_path!r}"
                    break
    except (SyncError, RuntimeError) as exc:
        problem = str(exc)
    if problem is not None:
        _swap(root, previous)
        raise SyncError(f"{problem}; previous registry restored")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "knowledge",
                        help="knowledge root holding registry.json (default: workspace builtin)")
    parser.add_argument("--admit", action="append", default=[], metavar="FILE",
                        help="explicitly admit an unregistered .md/.txt file as internal (repeatable)")
    parser.add_argument("--drop", action="append", default=[], metavar="FILE",
                        help="explicitly drop a registered file (repeatable)")
    parser.add_argument("--write", action="store_true",
                        help="commit the plan; without it just report and gate on the diff")
    args = parser.parse_args(argv)
    try:
        if args.root.is_symlink() or not args.root.is_dir():
            raise SyncError(f"--root must be an existing non-symlink directory: {args.root}")
        resolved = args.root.resolve(strict=True)
        admit = {_checked_relative(resolved, item, require_file=True) for item in args.admit}
        drop = {_checked_relative(resolved, item, require_file=False) for item in args.drop}
        plan = build_plan(resolved, admit, drop)
        pending = [row for row in plan["changes"] if row["action"] != "unchanged"]
        report = {
            "tool": "knowledge-registry-sync/1.0",
            "root": str(resolved),
            "would_change": bool(pending),
            "committed": False,
            "changes": plan["changes"],
            "refusals": plan["refusals"],
            "entry_count": len(plan["entries"]),
        }
        if plan["refusals"]:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print("sync refused; registry left untouched", file=sys.stderr)
            return 1
        if args.write and pending:
            commit(resolved, plan)
            report["committed"] = True
            report["applied_actions"] = len(pending)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if (args.write or not pending) else 1
    except SyncError as exc:
        print(f"knowledge registry sync failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"knowledge registry sync interrupted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
