from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_acceptance", ROOT / "scripts/verify_acceptance.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def test_default_acceptance_runs_local_only(monkeypatch, capsys):
    monkeypatch.setattr(acceptance, "local_checks", lambda: [{"check": "fixture", "status": "passed"}])
    monkeypatch.setattr(acceptance, "real_checks", lambda _: pytest.fail("real mode invoked"))
    assert acceptance.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "local" and report["external_acceptance"] == "blocked"


def test_real_preflight_reports_missing_conditions_without_network(monkeypatch, capsys):
    for key in ["DEEPSEEK_API_KEY", *[key for pair in acceptance.PROVIDERS.values() for key in pair]]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("company_agent.providers.ProviderClient.invoke", lambda *a: pytest.fail("network"))
    monkeypatch.setattr(acceptance.subprocess, "run", lambda *a, **k: pytest.fail("runtime launched"))
    assert acceptance.main(["--mode", "real", "--launch"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert all(row["status"] == "blocked" for row in report["checks"])
    assert report["device_approval"] == "per_call_in_dsh_only"


def test_configured_real_services_are_not_claimed_passed(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture")
    for url, token in acceptance.PROVIDERS.values():
        monkeypatch.setenv(url, "http://127.0.0.1:30001/invoke")
        monkeypatch.setenv(token, "fixture")
    rows = acceptance.real_checks(Namespace(asset_id="asset_fixture", circuit_id="circ_fixture",
                                            algorithm="fixture"))
    assert all(row["status"] == "passed" for row in rows if row["check"].endswith("configuration"))
    assert all(row["status"] == "blocked" for row in rows if row["check"].endswith("service"))


def test_offline_environment_removes_external_configuration(monkeypatch):
    for key in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COMPANY_AGENT_APPROVAL_CONTEXT",
                *[key for pair in acceptance.PROVIDERS.values() for key in pair]]:
        monkeypatch.setenv(key, "private")
    environment = acceptance.offline_environment()
    assert "private" not in environment.values()
    assert environment["COMPANY_AGENT_CONTRACTS_DIR"] == str(ROOT / "contracts")


def test_local_missing_runtime_blocks_all_gates(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANY_AGENT_RUNTIME_DIR", str(tmp_path))
    # Dev-dependency detection is ambient by design; pin this test to a fully
    # provisioned interpreter so the missing-runtime shape is checked exactly.
    monkeypatch.setattr(acceptance.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(acceptance, "run_gate", lambda *a: pytest.fail("gate ran without runtime"))
    assert acceptance.local_checks() == [{"check": "dsh_runtime", "status": "blocked",
                                          "reason": "run_bootstrap_dsh"}]


def test_local_missing_dev_dependency_blocks_gates_with_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANY_AGENT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(acceptance.importlib.util, "find_spec",
                        lambda name: None if name == "build" else object())
    monkeypatch.setattr(acceptance, "run_gate",
                        lambda *a: pytest.fail("gate ran with missing dev dependency"))
    assert acceptance.local_checks() == [
        {"check": "dsh_runtime", "status": "blocked", "reason": "run_bootstrap_dsh"},
        {"check": "dependency_build", "status": "blocked", "reason": "install_runtime_python_dev_lock"},
    ]


def test_real_launch_uses_isolated_existing_entry_without_approval(monkeypatch, capsys):
    # Stub the launcher: this verifies entry wiring without starting a real-service session.
    monkeypatch.setattr(acceptance, "real_checks", lambda _: [
        {"check": "model_configuration", "status": "passed"},
        {"check": "test_assets", "status": "passed"},
        {"check": "device_service", "status": "blocked"},
    ])
    monkeypatch.setenv("COMPANY_AGENT_APPROVAL_CONTEXT", "dsh")
    calls = []

    def launcher(command, **kwargs):
        calls.append(command)
        assert command == ["bash", str(ROOT / "scripts/start_runtime.sh")]
        env = kwargs["env"]
        assert "COMPANY_AGENT_APPROVAL_CONTEXT" not in env
        assert env["COMPANY_AGENT_PRESET"] == "lab"
        assert env["COMPANY_AGENT_PROFILE"] == "company-agent"
        home = Path(env["COMPANY_AGENT_DSH_HOME"])
        assert home.resolve() != ROOT.resolve()
        assert (home / "profiles/company-agent/package.json").is_file()
        assert (home / "profiles/company-agent/node_modules/@unitqc/company-agent-core").exists()
        assert 0 < int(env["COMPANY_AGENT_DSH_PORT"]) <= 65535
        return Namespace(returncode=0)

    monkeypatch.setattr(acceptance.subprocess, "run", launcher)
    assert acceptance.main(["--mode", "real", "--launch", "--asset-id", "asset_fixture",
                            "--circuit-id", "circ_fixture", "--algorithm", "fixture"]) == 2
    assert len(calls) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == report["external_acceptance"] == "blocked"


def test_unstructured_success_cannot_pass_test_gate(monkeypatch):
    class Process:
        returncode = 0

        def communicate(self, timeout):
            return "private fixture diagnostics\n999 passed in 1s", None

    monkeypatch.setattr(acceptance.subprocess, "Popen", lambda *a, **k: Process())
    result = acceptance.run_gate("tests", ["fixture"])
    assert result["status"] == "failed" and result["reason"] == "invalid_test_evidence"
    assert result["scope"] == "agent_single_repository"
    expected_markers = ["platform_compatibility", "latex_toolchain"]
    if acceptance.os.name == "nt":
        expected_markers.append("posix_permissions")
    assert result["excluded_markers"] == expected_markers
    assert result["counts"] == {"passed": 0, "failed": 0, "skipped": 0, "deselected": 0}
    assert "private" not in json.dumps(result)


def test_offline_environment_removes_pytest_selection_and_plugins(monkeypatch):
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST", "PYTEST_DEBUG",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD"):
        monkeypatch.setenv(key, "private")
    environment = acceptance.offline_environment()
    assert {key: value for key, value in environment.items() if key.startswith("PYTEST_")} == {
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    assert environment["PYTHONNOUSERSITE"] == "1"


def test_launch_requires_explicit_real_mode():
    with pytest.raises(SystemExit) as caught:
        acceptance.main(["--launch"])
    assert caught.value.code == 2


@pytest.mark.parametrize("option", ["--asset-id", "--circuit-id", "--algorithm"])
def test_real_entry_rejects_untrusted_test_identifiers(option):
    with pytest.raises(SystemExit) as caught:
        acceptance.main(["--mode", "real", option, "../unsafe"])
    assert caught.value.code == 2
