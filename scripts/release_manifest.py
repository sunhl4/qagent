#!/usr/bin/env python3
"""Create and verify fail-closed manifests for operator-managed releases."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

FORMAT = "company-agent-release-manifest/1"
ATTESTATION_FORMAT = "company-agent-release-attestation/1"
TRUST_FORMAT = "company-agent-release-trust/1"
MANAGED_ROOTS = ("contracts", "src", "packages", "profiles", "skills", "knowledge")
CONTRACT_NAMES = (
    "tools", "results", "providers", "capabilities", "policy", "presets", "templates", "skills", "tenants")
MANAGED_FILES = (
    "package.json",
    "pins.json",
    "pyproject.toml",
    "runtime/package.json",
    "runtime/pnpm-lock.yaml",
    "runtime/python-dev.in",
    "runtime/python-dev.lock",
    "scripts/dsh-cli.mjs",
    "scripts/release_manifest.py",
    "scripts/verify_acceptance.py",
    "scripts/acceptance_pytest.py",
    "scripts/verify_manual_evidence.py",
    "scripts/verify_skills.py",
    "scripts/compliance_gate.py",
    "scripts/probe_model_service.py",
    "scripts/start_runtime.sh",
)
RUNTIME_FILES = (
    ("runtime/node", "node_modules/node/bin/node", True),
    ("runtime/dsh-entry", "node_modules/@deepseek-ai/dsh/lib/bin.js", True),
    ("runtime/dsh-package", "node_modules/@deepseek-ai/dsh/package.json", False),
)
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000


class ManifestError(RuntimeError):
    """A release input failed a closed safety or integrity check."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ManifestError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _validate_json(value: Any) -> None:
    """Bound decoded input, including values accepted by Python's JSON extensions."""
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ManifestError("JSON structure exceeds budget")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ManifestError("JSON keys must be strings")
            pending.extend((entry, depth + 1) for pair in item.items() for entry in pair)
        elif isinstance(item, list):
            pending.extend((entry, depth + 1) for entry in item)
        elif isinstance(item, str):
            item.encode("utf-8", errors="strict")
        elif item is None or isinstance(item, bool):
            continue
        elif isinstance(item, (int, float)):
            if not math.isfinite(item) or abs(item) > 9_007_199_254_740_991:
                raise ManifestError("invalid JSON number")
        else:
            raise ManifestError("invalid JSON type")


def _reject_constant(_value: str) -> None:
    raise ManifestError("nonfinite JSON number")


def load_json(path: Path) -> Any:
    """Read only a bounded regular file; never block on a pipe or follow a leaf link."""
    try:
        path = Path(path)
        flags = os.O_RDONLY
        # O_NOFOLLOW and O_NONBLOCK do not exist on Windows; there the leaf-link
        # fence is the pre-open symlink check plus the regular-file fstat below.
        if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
            raise ManifestError("invalid bounded JSON file")
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
                raise ManifestError("JSON file exceeds budget or is nonregular")
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ManifestError("JSON file exceeds budget")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates, parse_constant=_reject_constant
        )
        _validate_json(value)
        return value
    except (OSError, UnicodeError, ValueError, RecursionError, OverflowError, ManifestError) as exc:
        raise ManifestError("invalid bounded JSON file") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise ManifestError("value is not bounded canonical JSON") from exc


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ManifestError(f"could not hash file: {path.name}") from exc
    return "sha256:" + digest.hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def contract_digest(root: Path) -> str:
    contracts = root / "contracts"
    digest = hashlib.sha256()
    for stem in CONTRACT_NAMES:
        name = f"{stem}.json"
        path = contracts / name
        if not path.is_file() or path.is_symlink():
            raise ManifestError(f"missing regular contract: {name}")
        try:
            parsed = load_json(path)
        except ManifestError as exc:
            raise ManifestError(f"invalid contract: {name}") from exc
        content = canonical_bytes(parsed)
        digest.update(name.encode("ascii") + b"\0" + content + b"\0")
    return "sha256:" + digest.hexdigest()


def lock_digest(root: Path) -> str:
    paths = (
        root / "runtime/package.json",
        root / "runtime/pnpm-lock.yaml",
        root / "runtime/python-dev.in",
        root / "runtime/python-dev.lock",
        root / "profiles/company-agent/pnpm-lock.yaml",
        root / "profiles/company-agent-minimal/pnpm-lock.yaml",
    )
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.is_symlink():
            raise ManifestError(f"missing regular lock input: {relative}")
        digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return "sha256:" + digest.hexdigest()


def _canonical_root(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ManifestError(f"{label} must be absolute")
    if path.is_symlink():
        raise ManifestError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ManifestError(f"{label} is unavailable") from exc
    if not resolved.is_dir():
        raise ManifestError(f"{label} must be a directory")
    return resolved


def _relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ManifestError("manifest paths must be non-empty POSIX relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ManifestError(f"non-canonical manifest path: {value!r}")
    return path


def _beneath(root: Path, relative: PurePosixPath, *, allow_symlinks: bool = False) -> Path:
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ManifestError(f"manifest path is unavailable: {relative}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestError(f"manifest path escapes release root: {relative}") from exc
    if not allow_symlinks and resolved != candidate.absolute():
        raise ManifestError(f"symlink is not allowed in managed path: {relative}")
    return resolved


def _validate_ancestors(root: Path, path: Path, *, immutable: bool) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ManifestError("managed path escapes its root") from exc
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ManifestError(f"unsafe managed directory: {current.relative_to(root)}")
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o022:
            raise ManifestError(f"managed directory is group/world writable: {current.relative_to(root)}")
        if immutable and mode & 0o222:
            raise ManifestError(f"managed directory is writable: {current.relative_to(root)}")


def _entry(
    root: Path,
    path: Path,
    *,
    executable: bool,
    immutable: bool,
    logical_path: str | None = None,
    expected_real_path: str | None = None,
) -> dict[str, Any]:
    relative = logical_path or path.relative_to(root).as_posix()
    _relative(relative)
    requested = path if logical_path is not None else root.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = requested.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ManifestError(f"managed path is unavailable or escapes its root: {relative}") from exc
    if expected_real_path is not None and str(resolved) != expected_real_path:
        raise ManifestError(f"managed real path changed: {relative}")
    info = resolved.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ManifestError(f"managed entry is not a regular file: {relative}")
    _validate_ancestors(root, resolved, immutable=immutable)
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o022:
        raise ManifestError(f"managed file is group/world writable: {relative}")
    if immutable and mode & 0o222:
        raise ManifestError(f"managed file remains writable: {relative}")
    execute_bits = mode & 0o111
    if executable and execute_bits != 0o111:
        raise ManifestError(f"managed executable must have mode 0555 or 0755: {relative}")
    if not executable and execute_bits:
        raise ManifestError(f"non-executable managed file has execute bits: {relative}")
    return {
        "path": relative,
        **({"name": relative} if logical_path is not None else {}),
        "real_path": str(resolved),
        "sha256": sha256_file(resolved),
        "mode": f"{mode:04o}",
        "size": info.st_size,
        "executable": executable,
    }


def _walk_error(_error: OSError) -> None:
    raise ManifestError("managed tree could not be fully scanned")


def source_paths(root: Path, *, immutable: bool = False) -> list[Path]:
    paths: list[Path] = []
    for relative in MANAGED_ROOTS:
        managed = root / relative
        if not managed.is_dir() or managed.is_symlink():
            raise ManifestError(f"missing regular managed root: {relative}")
        managed_mode = stat.S_IMODE(managed.lstat().st_mode)
        if managed_mode & (0o222 if immutable else 0o022):
            raise ManifestError(f"managed root is writable: {relative}")
        for base, directories, names in os.walk(managed, followlinks=False, onerror=_walk_error):
            directories[:] = sorted(
                name for name in directories if name not in {"node_modules", "__pycache__"}
            )
            for directory in directories:
                child = Path(base) / directory
                if child.is_symlink():
                    raise ManifestError(f"symlink in managed root: {child.relative_to(root)}")
                if stat.S_IMODE(child.lstat().st_mode) & (0o222 if immutable else 0o022):
                    raise ManifestError("managed directory is writable")
            for name in sorted(names):
                path = Path(base) / name
                if path.is_symlink():
                    raise ManifestError(f"symlink in managed root: {path.relative_to(root)}")
                paths.append(path)
    for relative in MANAGED_FILES:
        paths.append(root / relative)
    unique = {path.relative_to(root).as_posix(): path for path in paths}
    return [unique[name] for name in sorted(unique)]


def runtime_paths(runtime_root: Path) -> list[tuple[str, Path, bool]]:
    return [(name, runtime_root / relative, executable) for name, relative, executable in RUNTIME_FILES]


def runtime_tree_digest(runtime_root: Path, *, immutable: bool) -> str:
    """Bind all dependency bytes, modes and symlink targets, not just the entrypoint."""
    entries = []
    tree = runtime_root / "node_modules"
    if tree.is_symlink() or not tree.is_dir():
        raise ManifestError("runtime dependency root must be a regular directory")
    for base, directories, files in os.walk(tree, followlinks=False, onerror=_walk_error):
        for name in sorted(directories + files):
            path = Path(base) / name
            info = path.lstat()
            relative = path.relative_to(runtime_root).as_posix()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                try:
                    resolved = path.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise ManifestError("runtime dependency link is unavailable") from exc
                if not resolved.is_relative_to(tree):
                    raise ManifestError("runtime dependency symlink escapes managed tree")
                entries.append([relative, "link", os.readlink(path)])
            elif stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
                if mode & (0o222 if immutable else 0o022):
                    raise ManifestError("runtime dependency is writable")
                entries.append(
                    [relative, f"{mode:04o}", sha256_file(path) if path.is_file() else "directory"]
                )
            else:
                raise ManifestError("runtime contains a nonregular dependency")
    if stat.S_IMODE(tree.stat().st_mode) & (0o222 if immutable else 0o022):
        raise ManifestError("runtime dependency root is writable")
    return sha256_bytes(canonical_bytes(sorted(entries)))


def profile_dependency_digests(root: Path, *, immutable: bool) -> dict[str, str | None]:
    """Cover each installed profile dependency tree; production requires both trees."""
    result: dict[str, str | None] = {}
    for name in ("company-agent", "company-agent-minimal"):
        profile = root / "profiles" / name
        if (profile / "node_modules").is_symlink():
            raise ManifestError("profile dependency root must not be a symlink")
        if not (profile / "node_modules").exists():
            if immutable:
                raise ManifestError("production profile dependencies are missing")
            result[name] = None
        else:
            result[name] = runtime_tree_digest(profile, immutable=immutable)
    return result


def host_python_identity() -> dict[str, str]:
    """Bind the fixed OS interpreter; its standard library remains an OS trust prerequisite."""
    python = Path("/usr/bin/python3").resolve(strict=True)
    if not python.is_file() or python.stat().st_mode & 0o022:
        raise ManifestError("managed OS Python is unavailable or unsafe")
    return {
        "real_path": str(python),
        "sha256": sha256_file(python),
        "version": _probe([str(python), "-I", "--version"], "Python"),
    }


def _probe(command: list[str], label: str) -> str:
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ManifestError(f"{label} version probe failed") from exc
    value = result.stdout.strip()
    if result.returncode != 0 or "\n" in value or not value:
        raise ManifestError(f"{label} version probe failed")
    return value


def probe_versions(root: Path, runtime_root: Path) -> dict[str, str]:
    pins = load_json(root / "pins.json")
    if not isinstance(pins, dict):
        raise ManifestError("pins.json must be an object")
    expected_node = pins.get("dsh_node")
    expected_dsh = pins.get("deepseek_harness")
    if not isinstance(expected_node, str) or not isinstance(expected_dsh, str):
        raise ManifestError("runtime version pins are missing")
    node = _beneath(runtime_root, _relative("node_modules/node/bin/node"), allow_symlinks=True)
    dsh_package = _beneath(
        runtime_root,
        _relative("node_modules/@deepseek-ai/dsh/package.json"),
        allow_symlinks=True,
    )
    actual_node = _probe([str(node), "--version"], "Node").removeprefix("v")
    actual_dsh = _probe(
        [
            str(node),
            "-e",
            "const f=require('node:fs');const p=JSON.parse(f.readFileSync(process.argv[1],'utf8'));"
            "if(typeof p.version!=='string')process.exit(3);process.stdout.write(p.version)",
            str(dsh_package),
        ],
        "DSH",
    )
    if actual_node != expected_node:
        raise ManifestError(f"Node version mismatch: expected {expected_node}, got {actual_node}")
    if actual_dsh != expected_dsh:
        raise ManifestError(f"DSH version mismatch: expected {expected_dsh}, got {actual_dsh}")
    return {"node": actual_node, "dsh": actual_dsh}


def build_manifest(root: Path, runtime_root: Path, *, immutable: bool) -> dict[str, Any]:
    root = _canonical_root(root, "release root")
    runtime_root = _canonical_root(runtime_root, "runtime root")
    if immutable:
        for candidate, label in ((root, "release root"), (runtime_root, "runtime root")):
            if stat.S_IMODE(candidate.lstat().st_mode) & 0o222:
                raise ManifestError(f"{label} is writable")
    source = [
        _entry(root, path, executable=False, immutable=immutable)
        for path in source_paths(root, immutable=immutable)
    ]
    runtime_entries = []
    for name, path, executable in runtime_paths(runtime_root):
        row = _entry(runtime_root, path, executable=executable, immutable=immutable, logical_path=name)
        runtime_entries.append(row)
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "release_root": str(root),
        "runtime_root": str(runtime_root),
        "managed_roots": list(MANAGED_ROOTS),
        "managed_files": list(MANAGED_FILES),
        "source_entries": source,
        "runtime_entries": runtime_entries,
        "runtime_tree_digest": runtime_tree_digest(runtime_root, immutable=immutable),
        "python_identity": host_python_identity(),
        "profile_dependency_digests": profile_dependency_digests(root, immutable=immutable),
        "contract_digest": contract_digest(root),
        "lock_digest": lock_digest(root),
        "versions": probe_versions(root, runtime_root),
        "immutable_required": immutable,
    }
    manifest["content_digest"] = sha256_bytes(
        canonical_bytes(
            {
                "source": [[row["path"], row["sha256"]] for row in source],
                "runtime": [[row["name"], row["sha256"]] for row in runtime_entries],
            }
        )
    )
    return manifest


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ManifestError(f"invalid {label} fields")
    return value


def _validate_entry_shape(row: Any, *, runtime: bool) -> dict[str, Any]:
    expected = {"path", "real_path", "sha256", "mode", "size", "executable"}
    if runtime:
        expected.add("name")
    row = _exact_keys(row, expected, "manifest entry")
    if (
        not isinstance(row["real_path"], str)
        or not SHA256.fullmatch(row["sha256"] if isinstance(row["sha256"], str) else "")
        or not isinstance(row["mode"], str)
        or not re.fullmatch(r"[0-7]{4}", row["mode"])
        or isinstance(row["size"], bool)
        or not isinstance(row["size"], int)
        or row["size"] < 0
        or not isinstance(row["executable"], bool)
    ):
        raise ManifestError("invalid manifest entry value")
    _relative(row["path"])
    if runtime and (not isinstance(row["name"], str) or not row["name"]):
        raise ManifestError("invalid runtime entry name")
    return row


def verify_manifest(
    manifest_path: Path,
    *,
    expected_root: Path | None = None,
    expected_runtime: Path | None = None,
    require_immutable: bool = False,
    attestation_path: Path | None = None,
    trust_path: Path | None = None,
) -> dict[str, Any]:
    # Authentication applies to this exact decoded manifest, before any executable
    # version probe. Never reload it between checking its signature and its bytes.
    if (attestation_path is None) != (trust_path is None):
        raise ManifestError("attestation and trust config must be supplied together")
    if not manifest_path.is_absolute() or manifest_path.is_symlink():
        raise ManifestError("manifest path must be absolute and not a symlink")
    manifest_real = manifest_path.resolve(strict=True)
    manifest_info = manifest_real.lstat()
    if not stat.S_ISREG(manifest_info.st_mode) or manifest_info.st_mode & 0o022:
        raise ManifestError("manifest must be a protected regular file")
    manifest = _exact_keys(
        load_json(manifest_real),
        {
            "format",
            "release_root",
            "runtime_root",
            "managed_roots",
            "managed_files",
            "source_entries",
            "runtime_entries",
            "contract_digest",
            "lock_digest",
            "versions",
            "immutable_required",
            "content_digest",
            "runtime_tree_digest",
            "python_identity",
            "profile_dependency_digests",
        },
        "manifest",
    )
    if manifest["format"] != FORMAT:
        raise ManifestError("unsupported manifest format")
    if manifest["managed_roots"] != list(MANAGED_ROOTS) or manifest["managed_files"] != list(MANAGED_FILES):
        raise ManifestError("managed path policy mismatch")
    if not isinstance(manifest["immutable_required"], bool):
        raise ManifestError("invalid immutable_required value")
    immutable = require_immutable or manifest["immutable_required"]
    if require_immutable and not manifest["immutable_required"]:
        raise ManifestError("production requires an immutable release manifest")
    if not isinstance(manifest["release_root"], str) or not isinstance(manifest["runtime_root"], str):
        raise ManifestError("invalid manifest roots")
    root = _canonical_root(Path(manifest["release_root"]), "release root")
    runtime_root = _canonical_root(Path(manifest["runtime_root"]), "runtime root")
    if expected_root is not None and root != _canonical_root(expected_root, "expected release root"):
        raise ManifestError("release root does not match launcher root")
    if expected_runtime is not None and runtime_root != _canonical_root(
        expected_runtime, "expected runtime root"
    ):
        raise ManifestError("runtime root does not match launcher runtime")
    if attestation_path is not None and trust_path is not None:
        verify_attestation(manifest, attestation_path, trust_path)
    if immutable:
        for candidate, label in ((root, "release root"), (runtime_root, "runtime root")):
            if stat.S_IMODE(candidate.lstat().st_mode) & 0o222:
                raise ManifestError(f"{label} is writable")
    source_rows = manifest["source_entries"]
    runtime_rows = manifest["runtime_entries"]
    if not isinstance(source_rows, list) or not isinstance(runtime_rows, list):
        raise ManifestError("manifest entries must be arrays")
    source_rows = [_validate_entry_shape(row, runtime=False) for row in source_rows]
    runtime_rows = [_validate_entry_shape(row, runtime=True) for row in runtime_rows]
    if any(not row["real_path"].startswith(str(root) + os.sep) for row in source_rows):
        raise ManifestError("source real path is outside release root")
    if any(not row["real_path"].startswith(str(runtime_root) + os.sep) for row in runtime_rows):
        raise ManifestError("runtime real path is outside runtime root")
    source_names = [row["path"] for row in source_rows]
    actual_source_names = [
        path.relative_to(root).as_posix() for path in source_paths(root, immutable=immutable)
    ]
    if source_names != sorted(set(source_names)) or source_names != actual_source_names:
        raise ManifestError("managed source additions or deletions detected")
    expected_runtime_names = [name for name, _path, _executable in runtime_paths(runtime_root)]
    runtime_names = [row["name"] for row in runtime_rows]
    if runtime_names != expected_runtime_names or len(runtime_names) != len(set(runtime_names)):
        raise ManifestError("runtime entry set mismatch")
    for row in source_rows:
        actual = _entry(
            root,
            root / row["path"],
            executable=row["executable"],
            immutable=immutable,
            expected_real_path=row["real_path"],
        )
        if actual != row:
            raise ManifestError(f"managed source mismatch: {row['path']}")
    expected_runtime_rows = []
    for name, path, executable in runtime_paths(runtime_root):
        row = next(item for item in runtime_rows if item["name"] == name)
        actual = _entry(
            runtime_root,
            path,
            executable=executable,
            immutable=immutable,
            logical_path=name,
            expected_real_path=row["real_path"],
        )
        expected_runtime_rows.append(actual)
    if expected_runtime_rows != runtime_rows:
        raise ManifestError("managed runtime content mismatch")
    if manifest["runtime_tree_digest"] != runtime_tree_digest(runtime_root, immutable=immutable):
        raise ManifestError("runtime dependency tree mismatch")
    if manifest["profile_dependency_digests"] != profile_dependency_digests(root, immutable=immutable):
        raise ManifestError("profile dependency tree mismatch")
    if manifest["python_identity"] != host_python_identity():
        raise ManifestError("managed OS Python identity mismatch")
    if manifest["contract_digest"] != contract_digest(root):
        raise ManifestError("contract digest mismatch")
    if manifest["lock_digest"] != lock_digest(root):
        raise ManifestError("lock digest mismatch")
    if manifest["versions"] != probe_versions(root, runtime_root):
        raise ManifestError("runtime version metadata mismatch")
    content_digest = sha256_bytes(
        canonical_bytes(
            {
                "source": [[row["path"], row["sha256"]] for row in source_rows],
                "runtime": [[row["name"], row["sha256"]] for row in runtime_rows],
            }
        )
    )
    if manifest["content_digest"] != content_digest:
        raise ManifestError("content digest mismatch")
    return manifest


def _secret_from_trust(trust: dict[str, Any]) -> bytes:
    encoded = trust["hmac_sha256_key_hex"]
    if not isinstance(encoded, str) or not re.fullmatch(r"[0-9a-f]{64,256}", encoded) or len(encoded) % 2:
        raise ManifestError("invalid trust key")
    return bytes.fromhex(encoded)


def verify_attestation(manifest: dict[str, Any], attestation_path: Path, trust_path: Path) -> dict[str, Any]:
    release_root = _canonical_root(Path(manifest["release_root"]), "release root")
    runtime_root = _canonical_root(Path(manifest["runtime_root"]), "runtime root")
    for path, label in ((attestation_path, "attestation"), (trust_path, "trust config")):
        if not path.is_absolute() or path.is_symlink():
            raise ManifestError(f"{label} path must be absolute and not a symlink")
        resolved = path.resolve(strict=True)
        if any(resolved.is_relative_to(root) for root in (release_root, runtime_root)):
            raise ManifestError(f"{label} must be external to release and runtime roots")
        info = resolved.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ManifestError(f"{label} must be an operator-private regular file")
    trust = _exact_keys(load_json(trust_path), {"format", "key_id", "hmac_sha256_key_hex"}, "trust config")
    if (
        trust["format"] != TRUST_FORMAT
        or not isinstance(trust["key_id"], str)
        or not KEY_ID.fullmatch(trust["key_id"])
    ):
        raise ManifestError("invalid trust config")
    attestation = _exact_keys(
        load_json(attestation_path),
        {"format", "key_id", "manifest_sha256", "release_root", "runtime_root", "signature"},
        "attestation",
    )
    if (
        attestation["format"] != ATTESTATION_FORMAT
        or attestation["key_id"] != trust["key_id"]
        or attestation["manifest_sha256"] != manifest_digest(manifest)
        or attestation["release_root"] != manifest["release_root"]
        or attestation["runtime_root"] != manifest["runtime_root"]
        or not isinstance(attestation["signature"], str)
        or not re.fullmatch(r"hmac-sha256:[0-9a-f]{64}", attestation["signature"])
    ):
        raise ManifestError("attestation linkage is invalid")
    signed = {key: value for key, value in attestation.items() if key != "signature"}
    expected = (
        "hmac-sha256:"
        + hmac.new(_secret_from_trust(trust), canonical_bytes(signed), hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, attestation["signature"]):
        raise ManifestError("attestation signature is invalid")
    return attestation


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ManifestError("output must be a new absolute path")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        raise ManifestError("output parent must be a regular directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _print_result(status: str, **fields: Any) -> None:
    print(json.dumps({"status": status, **fields}, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="create a new manifest")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--runtime-root", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--immutable", action="store_true")
    verify = subparsers.add_parser("verify", help="verify a manifest")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--root", type=Path)
    verify.add_argument("--runtime-root", type=Path)
    verify.add_argument("--require-immutable", action="store_true")
    verify.add_argument("--attestation", type=Path)
    verify.add_argument("--trust-config", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            manifest = build_manifest(args.root, args.runtime_root, immutable=args.immutable)
            _write_new_json(args.output, manifest)
            _print_result(
                "created",
                manifest_sha256=manifest_digest(manifest),
                contract_digest=manifest["contract_digest"],
                lock_digest=manifest["lock_digest"],
                immutable=manifest["immutable_required"],
            )
            return 0
        manifest = verify_manifest(
            args.manifest,
            expected_root=args.root,
            expected_runtime=args.runtime_root,
            require_immutable=args.require_immutable,
            attestation_path=args.attestation,
            trust_path=args.trust_config,
        )
        attested = args.attestation is not None
        _print_result(
            "verified",
            manifest_sha256=manifest_digest(manifest),
            contract_digest=manifest["contract_digest"],
            lock_digest=manifest["lock_digest"],
            immutable=manifest["immutable_required"],
            operator_attested=attested,
        )
        return 0
    except (ManifestError, OSError, RuntimeError, ValueError, TypeError):
        print("release verification failed: invalid or unavailable release inputs", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
