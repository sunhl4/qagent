"""Exercise the actual administrative pytest wrapper in tiny isolated repositories."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("acceptance_evidence", ROOT / "scripts/verify_acceptance.py")
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)


def repository(tmp_path: Path, test: str, *, conftest: str = "", addopts: str = "") -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    shutil.copyfile(ROOT / "scripts/acceptance_pytest.py", tmp_path / "scripts/acceptance_pytest.py")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nmarkers=['platform_compatibility: external']\n"
        f"addopts={json.dumps(addopts)}\n"
    )
    (tmp_path / "tests/test_local.py").write_text(test)
    (tmp_path / "tests/test_external.py").write_text(
        "import pytest\n@pytest.mark.platform_compatibility\ndef test_external():\n"
        "    raise AssertionError('external test must not run')\n"
    )
    if conftest:
        (tmp_path / "tests/conftest.py").write_text(conftest)
    return tmp_path / "pytest.json"


def run(tmp_path: Path, evidence: Path, *, overrides: dict | None = None):
    result = subprocess.run(
        [sys.executable, str(tmp_path / "scripts/acceptance_pytest.py"), "--report", str(evidence)],
        cwd=tmp_path, env={**os.environ, **(overrides or {}), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=30, check=False,
    )
    row = {"check": "tests", "status": "passed" if result.returncode == 0 else "failed",
           "exit_code": result.returncode}
    return ACCEPTANCE._test_evidence(row, evidence)


def test_fixed_scope_ignores_environment_and_config_selection(tmp_path):
    evidence = repository(tmp_path, "def test_local():\n    pass\n", addopts="--collect-only -k absent")
    result = run(tmp_path, evidence, overrides={
        "PYTEST_ADDOPTS": "--collect-only -k absent", "PYTEST_PLUGINS": "nonexistent_private_plugin",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0",
    })
    assert result["status"] == "passed"
    assert result["counts"] == {"passed": 1, "failed": 0, "skipped": 0, "deselected": 1}
    assert result["selection"]["complete"] is True


@pytest.mark.parametrize("mutation", ["collect_only", "remove", "skip", "xfail", "fail", "empty_file"])
def test_zero_partial_skipped_and_failed_runs_never_pass(tmp_path, mutation):
    test = "def test_local():\n    pass\n"
    conftest = ""
    if mutation == "collect_only":
        conftest = "def pytest_configure(config):\n    config.option.collectonly = True\n"
    elif mutation == "remove":
        conftest = "def pytest_collection_modifyitems(items):\n    items[:] = []\n"
    elif mutation == "skip":
        test = "import pytest\n@pytest.mark.skip(reason='private')\ndef test_local():\n    pass\n"
    elif mutation == "xfail":
        test = "import pytest\n@pytest.mark.xfail(reason='private')\ndef test_local():\n    assert False\n"
    elif mutation == "fail":
        test = ("import pytest\n@pytest.mark.parametrize('value',['private-input'])\n"
                "def test_local(value):\n    assert False, 'secret assertion'\n")
    evidence = repository(tmp_path, test, conftest=conftest)
    if mutation == "empty_file":
        (tmp_path / "tests/test_empty.py").write_text("# accidentally empty test module\n")
    result = run(tmp_path, evidence)
    assert result["status"] != "passed"
    assert "private" not in json.dumps(result) and "secret assertion" not in json.dumps(result)
    if mutation == "skip":
        assert result["status"] == "blocked" and result["reason"] == "tests_skipped"
    if mutation == "fail":
        assert result["failed_tests"] == ["tests/test_local.py::test_local"]


@pytest.mark.parametrize("mutation", ["count_bool", "counts_zero", "selection", "malformed", "missing"])
def test_structured_evidence_validation_is_fail_closed(tmp_path, mutation):
    evidence = repository(tmp_path, "def test_local():\n    pass\n")
    assert run(tmp_path, evidence)["status"] == "passed"
    value = json.loads(evidence.read_text())
    if mutation == "count_bool":
        value["counts"]["passed"] = True
    elif mutation == "counts_zero":
        value["counts"]["passed"] = 0
    elif mutation == "selection":
        value["selection"]["expected_excluded"] = 2
    evidence.write_text("{}" if mutation == "malformed" else json.dumps(value))
    if mutation == "missing":
        evidence.unlink()
    row = {"check": "tests", "status": "passed", "exit_code": 0}
    assert ACCEPTANCE._test_evidence(row, evidence)["status"] == "failed"
