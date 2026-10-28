"""P8-A2 license register audit: coverage, forbidden families and fail-closed shapes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "license_audit.py"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _ok_register() -> dict:
    return {
        "version": "1.0.0",
        "policy": {"forbidden_spdx": ["AGPL-3.0-only"], "note": "逐项登记"},
        "components": [
            {"name": "deepseek_harness", "version": "0.1", "license": "proprietary (company)",
             "source": "company registry", "scope": "production_runtime"},
            {"name": "dsh_node", "version": "22", "license": "MIT", "source": "nodejs.org",
             "scope": "production_runtime"},
            {"name": "pnpm", "version": "12", "license": "MIT", "source": "packageManager",
             "scope": "toolchain"},
            {"name": "openai_codex", "version": "0", "license": "Apache-2.0", "source": "upstream",
             "scope": "production_runtime"},
            {"name": "dsh_subagent_codex", "version": "0", "license": "proprietary (company)",
             "source": "company registry", "scope": "production_runtime"},
            {"name": "provider_protocol", "version": "x/1", "license": "internal (company doc)",
             "source": "pins.json", "scope": "contract"},
            {"name": "jsdom", "version": "x", "license": "MIT", "source": "npm", "scope": "toolchain"},
            {"name": "pytest", "version": "9", "license": "MIT", "source": "pyproject", "scope": "toolchain"},
            {"name": "ruff", "version": "0", "license": "MIT", "source": "pyproject", "scope": "toolchain"},
            {"name": "build", "version": "1", "license": "MIT", "source": "pyproject", "scope": "toolchain"},
            {"name": "hypothesis", "version": "6", "license": "MPL-2.0", "source": "pyproject",
             "scope": "toolchain"},
        ],
    }


def _fixture_workspace(workspace_dir: Path, register: dict) -> Path:
    workspace = workspace_dir
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "docs" / "licenses-register.json", register)
    _write(workspace / "pins.json", {"deepseek_harness": "0.1", "dsh_node": "22", "pnpm": "12",
                                     "openai_codex": "0", "dsh_subagent_codex": "0",
                                     "provider_protocol": "x/1"})
    _write(workspace / "packages" / "company-agent-core" / "package.json",
           {"dependencies": {}})
    _write(workspace / "tests" / "ui" / "package.json",
           {"devDependencies": {"jsdom": "^24"}})
    (workspace / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["pytest>=9", "ruff>=0.9", "build>=1", "hypothesis>=6"]\n',
        encoding="utf-8",
    )
    return workspace


def _run(workspace: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AUDIT), "--workspace", str(workspace)],
        capture_output=True, text=True, timeout=120,
    )


def test_real_repository_audit_passes_and_binds_digest_free_data() -> None:
    result = _run(ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "pytest" in payload["required"] and "deepseek_harness" in payload["required"]
    assert set(payload["scopes"]) == {"production_runtime", "toolchain", "contract"}


def test_unregistered_direct_dependency_fails_closed(tmp_path) -> None:
    register = _ok_register()
    register["components"] = [row for row in register["components"] if row["name"] != "jsdom"]
    result = _run(_fixture_workspace(tmp_path / "ws", register))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "unregistered" in str(payload["error"]) and "jsdom" in str(payload["error"])


@pytest.mark.parametrize("license_text", [
    "AGPL-3.0-or-later",
    "MIT / SSPL-1.0 dual",
    "Elastic-License-2.0",
])
def test_forbidden_license_family_fails_closed(tmp_path, license_text) -> None:
    register = _ok_register()
    register["components"][1]["license"] = license_text
    result = _run(_fixture_workspace(tmp_path, register))
    assert result.returncode == 1
    assert "forbidden license" in str(json.loads(result.stdout)["error"])


def test_schema_drift_duplicate_and_missing_fields_fail_closed(tmp_path) -> None:
    workspaces: dict[str, Path] = {}
    duplicate = _ok_register()
    duplicate["components"].append(
        {"name": "JSdom", "version": "y", "license": "MIT", "source": "npm", "scope": "toolchain"},
    )
    workspaces["duplicate"] = _fixture_workspace(tmp_path / "duplicate", duplicate)
    unknown_key = _ok_register()
    unknown_key["components"][0]["extra"] = 1
    workspaces["unknown-key"] = _fixture_workspace(tmp_path / "unknown-key", unknown_key)
    broken_top = _ok_register()
    broken_top["unknown"] = 1
    workspaces["broken-top"] = _fixture_workspace(tmp_path / "broken-top", broken_top)
    bad_version = _ok_register()
    bad_version["version"] = "9.9"
    workspaces["bad-version"] = _fixture_workspace(tmp_path / "bad-version", bad_version)
    for label, workspace in workspaces.items():
        result = _run(workspace)
        assert result.returncode == 1, (label, result.stdout, result.stderr)
