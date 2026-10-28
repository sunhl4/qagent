#!/usr/bin/env python3
"""Per-package license scan over the installed dependency trees (P8-A3).

P8-A2 introduced the register and the direct-dependency coverage audit. This
script extends the supply-chain review one level deeper: every installed
``package.json`` inside the profile node_modules trees and the tests
toolchain tree contributes its declared license, and none of them may carry
a forbidden family from the register policy floor. Internal workspace
packages (``@unitqc/*``) and company-registry packages (``@deepseek-ai/*``)
may omit the license field because their terms live in the internal register
rows; anything else without a declared license fails closed.

Offline by construction: file reads only, bounded enumeration.

The universal FORBIDDEN_SPDX floor matches ``scripts/license_audit.py`` and
cannot be relaxed by the register on its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

FORBIDDEN_SPDX = (
    "AGPL-1.0-only", "AGPL-1.0-or-later", "AGPL-1.0",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "AGPL-3.0",
    "SSPL-1.0", "SSPL",
    "Elastic-License-2.0",
)

_INTERNAL_NAME_PREFIXES = ("@unitqc/", "@deepseek-ai/")
_TREES = (
    "profiles/company-agent/node_modules",
    "profiles/company-agent-minimal/node_modules",
    "tests/ui/node_modules",
)
_MAX_PACKAGES = 4096
_MAX_MANIFEST_BYTES = 262_144
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/-]{0,63}$")
_NAME_PATTERN = re.compile(r"^(@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]{0,127}$")


def _normalize_license(payload: Any) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, bool) or payload in {"", "\x00"}:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        types = payload.get("type")
        if isinstance(types, list):
            return " OR ".join(str(item) for item in types)
        return None
    if isinstance(payload, list):
        return " OR ".join(str(item) for item in payload)
    return ""


def _read_register(workspace: Path) -> dict[str, Any]:
    payload = json.loads((workspace / "docs" / "licenses-register.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"version", "policy", "components"}:
        raise ValueError("license register top-level shape is invalid")
    policy = payload.get("policy") or {}
    forbidden = policy.get("forbidden_spdx") or []
    if not isinstance(forbidden, list):
        raise ValueError("license register policy shape is invalid")
    return payload


def audit(workspace: Path) -> dict[str, Any]:
    register = _read_register(workspace)
    forbidden = sorted(set(
        str(item).casefold() for item in (register["policy"]["forbidden_spdx"] or ())
    ) | {item.casefold() for item in FORBIDDEN_SPDX})
    findings: list[dict[str, Any]] = []
    trees: dict[str, dict[str, int]] = {}
    licenses: dict[str, int] = {}
    scanned = 0
    for relative in _TREES:
        tree = workspace / relative
        label = relative.split("/")[1]
        if not tree.is_dir():
            trees[label] = {"packages": 0, "skipped_internal": 0}
            continue
        count = 0
        skipped_internal = 0
        for root, directories, files in os.walk(tree):
            directories[:] = [name for name in directories if name != ".jsii"]
            # Only real package roots participate: a manifest counts when its
            # containing directory is directly under a node_modules folder or
            # under a scope folder inside node_modules. Nested package files
            # (bundled sub-package json blobs) are not registry packages.
            parts = Path(root).parts
            parent = parts[-2] if len(parts) >= 2 else ""
            grand = parts[-3] if len(parts) >= 3 else ""
            is_package_root = (
                "package.json" in files
                and (
                    parent == "node_modules"
                    or (parent.startswith("@") and grand == "node_modules")
                )
            )
            if not is_package_root:
                continue
            if count >= _MAX_PACKAGES:
                raise ValueError(f"installed tree {label} exceeds the bounded package count")
            manifest = Path(root) / "package.json"
            raw = manifest.read_bytes()[:_MAX_MANIFEST_BYTES + 1]
            if len(raw) > _MAX_MANIFEST_BYTES:
                raise ValueError(f"installed manifest is too large under {label}")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f"installed manifest is invalid under {label}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"installed manifest is not an object under {label}")
            name = str(payload.get("name") or "")
            version = str(payload.get("version") or "")
            if not _NAME_PATTERN.fullmatch(name) or not _VERSION_PATTERN.fullmatch(version):
                raise ValueError(f"installed manifest identity is invalid under {label}: {name}")
            count += 1
            scanned += 1
            license_text = _normalize_license(payload.get("license"))
            if license_text and ("UNLICENSED" not in license_text.strip().upper()):
                for marker in forbidden:
                    if marker in license_text.casefold():
                        raise ValueError(
                            f"forbidden license family {marker} in {name}@{version}"
                        )
                licenses[license_text[:64]] = licenses.get(license_text[:64], 0) + 1
                findings.append({
                    "name": name, "version": version,
                    "digest": hashlib.sha256(raw).hexdigest()[:16],
                    "license": license_text[:64],
                })
            elif not any(name.startswith(prefix) for prefix in _INTERNAL_NAME_PREFIXES):
                # Only internal/company rows may omit the license declaration.
                raise ValueError(f"installed package without declared license: {name}@{version}")
            else:
                skipped_internal += 1
        trees[label] = {"packages": count, "skipped_internal": skipped_internal}
    return {
        "version": "1.0.0",
        "trees": trees,
        "scanned": scanned,
        "licenses": dict(sorted(licenses.items(), key=lambda row: (-row[1], row[0]))),
        "forbidden_spdx": forbidden,
        "ok": True,
        "register": str(workspace / "docs" / "licenses-register.json"),
        "note": (
            "per-package installed-tree scan; the register stays authoritative "
            "for the direct-dependency policy (P8-A2) and the floors merge"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="license_tree_audit")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    try:
        report = audit(Path(args.workspace).resolve())
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:200]}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
