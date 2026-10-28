"""P8-A3 per-package license scan over installed trees (supply chain)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "license_tree_audit", ROOT / "scripts" / "license_tree_audit.py")


def module() -> Any:
    loaded = importlib.util.module_from_spec(MODULE_SPEC)
    MODULE_SPEC.loader.exec_module(loaded)
    return loaded


def _pkg(root: Path, name: str, license_text: str | None) -> None:
    directory = root / name.rsplit("/", 1)[-1]
    manifest = directory / "package.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"name": name, "version": "1.0.0"}
    if license_text is not None:
        payload["license"] = license_text
    manifest.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "docs").mkdir(parents=True)
    policy = {"forbidden_spdx": ["AGPL-3.0-only"], "note": "逐项登记"}
    (workspace / "docs" / "licenses-register.json").write_text(
        json.dumps({"version": "1.0.0", "policy": policy, "components": []}),
        encoding="utf-8",
    )
    (workspace / "pins.json").write_text(json.dumps({"p": "1"}), encoding="utf-8")
    return workspace


def test_real_tree_scan_is_clean_and_counts_internal_rows() -> None:
    report = module().audit(ROOT)
    assert report["ok"] is True
    assert report["scanned"] > 50
    label_gender = {label: row["skipped_internal"] for label, row in report["trees"].items()}
    assert label_gender["company-agent"] >= 1
    assert label_gender["ui"] == 0
    assert all("AGPL" not in family for family in report["licenses"])
    assert "MIT" in "".join(report["licenses"])


def test_nested_embedded_manifests_are_not_package_roots(workspace: Path) -> None:
    tree = workspace / "profiles" / "company-agent" / "node_modules"
    _pkg(tree / "@deepseek-ai", "@deepseek-ai/dsh", None)  # internal row, no license
    nested = tree / "@deepseek-ai" / "dsh" / "locales"
    nested.mkdir(parents=True, exist_ok=True)
    nested.joinpath("package.json").write_text(
        json.dumps({}), encoding="utf-8")  # an embedded blob without identity
    nested_deep = nested / "v4"
    nested_deep.mkdir(parents=True, exist_ok=True)
    nested_deep.joinpath("package.json").write_text(
        json.dumps({}), encoding="utf-8")
    report = module().audit(workspace)
    assert report["trees"]["company-agent"]["packages"] == 1
    assert report["trees"]["company-agent"]["skipped_internal"] == 1


def test_internal_rows_may_omit_license_external_rows_fail_closed(
    workspace: Path,
) -> None:
    tree = workspace / "profiles" / "company-agent" / "node_modules"
    _pkg(tree / "@deepseek-ai", "@deepseek-ai/cordis", None)  # company rows may omit
    _pkg(tree / "@unitqc", "@unitqc/company-agent-core", "UNLICENSED")  # internal row
    report = module().audit(workspace)
    company_tree = report["trees"]["company-agent"]
    assert company_tree["packages"] == 2
    assert company_tree["skipped_internal"] == 2
    external = tree / "external-pkg"
    external.mkdir(parents=True, exist_ok=True)
    external.joinpath("package.json").write_text(
        json.dumps({"name": "external-pkg", "version": "1.0.0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="without declared license"):
        module().audit(workspace)


def test_forbidden_family_fails_closed(workspace: Path) -> None:
    tree = workspace / "tests" / "ui" / "node_modules"
    _pkg(tree, "bad-pkg", "AGPL-3.0-or-later AND MIT")
    with pytest.raises(ValueError, match="forbidden license family"):
        module().audit(workspace)


def test_overview_walk_skips_missing_trees(workspace: Path) -> None:
    workspace = workspace / "isolated"
    (workspace / "docs").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "licenses-register.json").write_text(
        json.dumps({"version": "1.0.0", "policy": {"forbidden_spdx": ["AGPL-3.0-only"],
                                                   "note": "n"}, "components": []}),
        encoding="utf-8")
    (workspace / "pins.json").write_text(json.dumps({"p": "1"}), encoding="utf-8")
    report = module().audit(workspace)
    assert report["ok"] is True
    assert all(row["packages"] == 0 for row in report["trees"].values())


def test_cli_contract_and_error_contract() -> None:
    result = module().main([])
    assert result == 0
    assert module().audit  # module surface exists
