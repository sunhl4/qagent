import json

from company_agent.cli import main
from company_agent.harness_compat import migration_manifest


def test_manifest_keeps_company_tools_on_one_harness_session() -> None:
    manifest = migration_manifest()
    names = [name for row in manifest["capabilities"] for name in row["tools"]]
    assert manifest["compatible"] is True
    assert manifest["reasons"] == []
    assert manifest["runtime"] == "deepseek-harness"
    assert manifest["runtime_pin"] == "0.1.5-rc.2"
    assert manifest["compatible_runtime_versions"] == ["0.1.5-rc.2", "0.2.1-rc.5"]
    assert manifest["second_runtime"] is False
    assert manifest["architecture"] == "company-super-dsh"
    assert manifest["planes"] == ["control", "execution", "platform"]
    assert manifest["official_status"] == "unreleased"
    assert manifest["executor"] == "existing-dsh-session"
    assert manifest["connectors"] == {"github": False, "feishu": False}
    assert "danger-full-access" in manifest["forbidden_worker_modes"]
    assert len(names) == len(set(names)) == manifest["tool_count"]
    assert manifest["presets"]["lab"]["device"] == "ask"
    assert manifest["presets"]["sign"]["device"] == "ask"
    assert manifest["presets"]["boot"]["device"] == "deny"
    assert manifest["presets"]["algo"]["device"] == "deny"
    assert manifest["presets"]["sign"]["includes_work_item"] is False
    assert manifest["presets"]["lab"]["includes_work_item"] is True


def test_unknown_harness_version_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_DSH_VERSION", "9.9.9")
    manifest = migration_manifest()
    assert manifest["compatible"] is False
    assert manifest["observed_runtime_version"] == "9.9.9"
    assert "observed DeepSeek Harness version is not in the tested set" in manifest["reasons"]


def test_harness_command_reports_the_migration_manifest(capsys) -> None:
    assert main(["harness"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["compatible"] is True
    assert payload["superagent_contract"] == "1.3.0"
    assert payload["architecture"] == "company-super-dsh"
    assert payload["clocks"] == ["agent", "platform"]
    assert payload["planes"] == ["control", "execution", "platform"]
    assert payload["migration_mode"] == "dsh-plugin-pack"


def test_doctor_rejects_an_untested_harness_version(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("COMPANY_AGENT_DSH_VERSION", "9.9.9")
    assert main(["doctor"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["harness"]["compatible"] is False
