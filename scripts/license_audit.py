#!/usr/bin/env python3
"""Third-party license register audit (survey P8 supply-chain review).

The register (``docs/licenses-register.json``) must cover every external
direct dependency (workspace packages, pyproject optional dependencies, tests
toolchain) plus each pinned component in ``pins.json``. Any row carrying a
forbidden SPDX family, any unregistered direct dependency, any duplicate row
and any unknown schema key fails closed with a nonzero exit. Transitive
dependency trees are deliberately out of scope of this single audit because
the release manifest already immutably digests the installed trees; a
per-package transitive lock audit is the planned follow-up (P8-A2 record).

Offline by construction: no network access, no package manager invocation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

FORBIDDEN_SPDX = (
    "AGPL-1.0-only", "AGPL-1.0-or-later", "AGPL-1.0",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "AGPL-3.0",
    "SSPL-1.0", "SSPL",
    "Elastic-License-2.0",
)
_SCOPES = {"production_runtime", "toolchain", "contract"}
_INTERNAL_PREFIXES = ("@unitqc/", "@deepseek-ai/")
_WORKSPACE_SPEC_MARKERS = ("workspace:", "file:", "link:")


def _read_json(path: Path) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"license register input is unreadable: {path.name}") from exc
    return payload


def external_direct_dependencies(workspace: Path) -> dict[str, str]:
    """Name → spec for direct external dependencies of manifest files."""
    found: dict[str, str] = {}
    for path in sorted(workspace.glob("packages/*/package.json")):
        found.update(_manifest_dependencies(path))
    for path in sorted(workspace.glob("apps/*/package.json")):
        found.update(_manifest_dependencies(path))
    found.update(_manifest_dependencies(workspace / "tests" / "ui" / "package.json"))
    found.update(_optional_python_dependencies(workspace / "pyproject.toml"))
    return {name: spec for name, spec in found.items() if name and spec}


def _manifest_dependencies(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"manifest is not an object: {path.name}")
    found: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        block = payload.get(section) or {}
        if not isinstance(block, dict):
            raise ValueError(f"manifest {section} is not an object: {path.name}")
        for name, spec in block.items():
            if isinstance(spec, str) and any(marker in spec for marker in _WORKSPACE_SPEC_MARKERS):
                continue
            if isinstance(spec, str) and name.startswith(_INTERNAL_PREFIXES):
                continue
            if isinstance(spec, str):
                found[name] = spec
    return found


def _optional_python_dependencies(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    matches = re.search(r"dev\s*=\s*\[(.*?)\]", text, flags=re.DOTALL)
    if not matches:
        return found
    for spec in re.findall(r'"([^"]+)"', matches.group(1)):
        head = re.split(r"[<>=~!]\s*", spec, maxsplit=1)[0]
        name = head.strip().strip('"').strip()
        if name:
            found[name] = spec
    return found


def _pinned_components(workspace: Path) -> dict[str, str]:
    payload = _read_json(workspace / "pins.json")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("pins.json must contain the pinned component versions")
    return {str(key): str(value) for key, value in sorted(payload.items())}


def audit(workspace: Path) -> dict[str, Any]:
    register = _read_json(workspace / "docs" / "licenses-register.json")
    if not isinstance(register, dict) or set(register) != {"version", "policy", "components"}:
        raise ValueError("license register top-level shape is invalid")
    if register["version"] != "1.0.0":
        raise ValueError("license register version is invalid")
    policy = register["policy"]
    if not isinstance(policy, dict) or set(policy) != {"forbidden_spdx", "note"}:
        raise ValueError("license register policy shape is invalid")
    forbidden = [str(item).casefold() for item in policy["forbidden_spdx"]]
    # A universal floor plus the operator register: a register cannot opt out
    # of the universally rejected families by dropping them from its own list.
    effective = sorted(set(forbidden) | {item.casefold() for item in FORBIDDEN_SPDX})
    rows = register["components"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("license register must contain components")
    components: dict[str, dict[str, Any]] = {}
    required_keys = {"name", "version", "license", "source", "scope"}
    allowed_keys = required_keys | {"notes"}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not set(row) <= allowed_keys
            or not required_keys <= set(row)
        ):
            raise ValueError("license register row shape is invalid")
        name = row["name"]
        if (
            not isinstance(name, str)
            or not name.isascii()
            or name.casefold() in {item.casefold() for item in components}
        ):
            raise ValueError("license register row names must be unique and ascii")
        if row["scope"] not in _SCOPES:
            raise ValueError(f"license register scope is invalid for {name}")
        for key in ("version", "license", "source"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f"license register {key} is invalid for {name}")
        license_text = row["license"]
        if any(marker in license_text.casefold() for marker in effective):
            raise ValueError(f"license register contains a forbidden license for {name}")
        components[name.casefold()] = row
    required = {**external_direct_dependencies(workspace), **_pinned_components(workspace)}
    missing = sorted(
        name for name in required
        if name.casefold() not in components
        and not any(alias in components for alias in (name.casefold(), name.casefold().replace("_", "-")))
    )
    if missing:
        raise ValueError(f"unregistered direct dependencies: {missing}")
    return {
        "version": "1.0.0",
        "register": str(workspace / "docs" / "licenses-register.json"),
        "components": len(components),
        "required": sorted(required),
        "scopes": sorted({row["scope"] for row in components.values()}),
        "forbidden_spdx": effective,
        "ok": True,
        "transitive_scope": (
            "release-manifest tree digests cover installed trees; "
            "per-package transitive lock audit is planned"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="license_audit")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    try:
        report = audit(Path(args.workspace).resolve())
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
