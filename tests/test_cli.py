from __future__ import annotations

import json

import pytest

from company_agent.cli import main


def test_doctor_reports_model_and_contract_providers(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    for name in (
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
        "COMPANY_QUANTUM_PLATFORM_TOKEN",
        "COMPANY_AGENT_SIMULATOR_INVOKE_URL",
        "COMPANY_AGENT_SIMULATOR_TOKEN",
        "COMPANY_AGENT_COMPILER_INVOKE_URL",
        "COMPANY_AGENT_COMPILER_TOKEN",
        "COMPANY_AGENT_DEVICE_INVOKE_URL",
        "COMPANY_AGENT_DEVICE_TOKEN",
        "COMPANY_AGENT_HPC_INVOKE_URL",
        "COMPANY_AGENT_HPC_TOKEN",
        "COMPANY_AGENT_CLOUD_INVOKE_URL",
        "COMPANY_AGENT_CLOUD_TOKEN",
        "COMPANY_AGENT_LOCAL_MODEL_TOKEN",
        "COMPANY_RELAY_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "platform", "simulator", "compiler", "device", "compute", "cloud", "model",
        "managed_builtins", "local_model_route", "relay_model_route",
        "knowledge_governance", "skills_governance", "tenants_governance", "receipts",
    }
    assert payload["tenants_governance"] == {
        "regime": "legacy-single-user", "configured": False, "valid": False,
        "entries": 0, "subjects": 0, "approved_services": 0,
    }
    assert all(
        payload[name]["configured"] is False
        for name in ("platform", "simulator", "compiler", "device", "compute", "cloud", "model")
    )
    assert payload["local_model_route"] == {
        "token_env": "COMPANY_AGENT_LOCAL_MODEL_TOKEN",
        "token_configured": False,
    }
    assert payload["relay_model_route"] == {
        "token_env": "COMPANY_RELAY_API_KEY",
        "token_configured": False,
    }
    assert payload["model"]["env"] == "DEEPSEEK_API_KEY"
    assert payload["platform"]["token_env"] == "COMPANY_QUANTUM_PLATFORM_TOKEN"
    assert payload["managed_builtins"] == {"enabled": True, "count": 7}
    assert payload["local_model_route"]["token_env"] == "COMPANY_AGENT_LOCAL_MODEL_TOKEN"


def test_cli_rejects_non_object_arguments(capsys) -> None:
    try:
        main(["decide", "--tool", "company_capabilities", "--args", "[]"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("CLI accepted a non-object --args value")
    assert "must hold a JSON object" in capsys.readouterr().err


def test_validate_command_preflights_arguments_without_provider(capsys) -> None:
    assert (
        main(
            [
                "validate",
                "--tool",
                "quantum_device_run",
                "--args",
                '{"circuit_id":"asset_wrong","shots":8}',
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"valid": False, "error": "circuit_id has an invalid format"}

    assert (
        main(
            [
                "validate",
                "--tool",
                "quantum_device_run",
                "--args",
                '{"circuit_id":"circ_x","shots":8}',
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"valid": True, "error": None}


def test_authorize_command_combines_preflight_and_policy(capsys) -> None:
    assert (
        main(
            [
                "authorize",
                "--tool",
                "quantum_device_run",
                "--preset",
                "lab",
                "--args",
                '{"circuit_id":"asset_wrong","shots":8}',
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"decision": "deny", "error": "circuit_id has an invalid format"}

    assert (
        main(
            [
                "authorize",
                "--tool",
                "quantum_device_run",
                "--preset",
                "lab",
                "--args",
                '{"circuit_id":"circ_x","shots":8}',
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"decision": "ask", "error": None}


def test_cli_reads_arguments_from_standard_input(monkeypatch, capsys) -> None:
    class FakeStdin:
        class Buffer:
            @staticmethod
            def read(_size):
                return b'{"catalog_version":"cat_fixture","component_version":"1.0","algorithm":"vqe"}'

        buffer = Buffer()

    monkeypatch.setattr("company_agent.cli.sys.stdin", FakeStdin())
    assert main(["validate", "--tool", "quantum_algorithm_run", "--args", "-"]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True, "error": None}


def test_cli_rejects_forged_approval_context(monkeypatch, capsys) -> None:
    monkeypatch.delenv("COMPANY_AGENT_APPROVAL_CONTEXT", raising=False)
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "invoke",
                "--tool",
                "quantum_device_run",
                "--preset",
                "lab",
                "--args",
                '{"circuit_id":"circ_x","shots":8}',
                "--approved",
            ]
        )
    assert caught.value.code == 2
    assert "reserved for the DSH approval lifecycle" in capsys.readouterr().err


def test_cli_rejects_duplicate_json_fields(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "validate",
                "--tool",
                "quantum_simulate",
                "--args",
                '{"circuit_id":"circ_x","shots":8,"shots":9}',
            ]
        )
    assert caught.value.code == 2
    assert "duplicate JSON field 'shots'" in capsys.readouterr().err


def test_cli_rejects_non_finite_json_number(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "validate",
                "--tool",
                "quantum_simulate",
                "--args",
                '{"circuit_id":"circ_x","shots":NaN}',
            ]
        )
    assert caught.value.code == 2
    assert "non-finite JSON number" in capsys.readouterr().err


def test_tools_command_exposes_contract_catalog(capsys) -> None:
    assert main(["tools"]) == 0
    tools = json.loads(capsys.readouterr().out)
    assert len(tools) == 71
    assert "quantum_algorithm_catalog" in {row["name"] for row in tools}
    assert tools[0]["name"] == "company_work_item"
    assert tools[-1]["name"] == "company_office_deliver"


def test_tools_command_filters_by_preset(capsys) -> None:
    assert main(["tools", "--preset", "boot"]) == 0
    boot = {row["name"] for row in json.loads(capsys.readouterr().out)}
    assert boot == {
        "company_capabilities",
        "company_work_item",
        "company_knowledge_search",
        "company_fetch",
        "company_table_profile",
        "company_workspace_reference",
        "company_workflow_validate",
        "company_analysis_render",
        "company_office_analyze",
        "company_office_create",
        "company_office_compare",
        "company_office_edit",
        "company_office_validate",
        "company_office_chart",
        "company_office_matter",
        "company_office_audit",
        "company_office_pptx",
        "company_office_convert",
        "company_office_open",
        "company_office_compute",
        "company_office_deliver",
        "company_portal_open",
    }
    assert main(["tools", "--preset", "lab"]) == 0
    lab = {row["name"] for row in json.loads(capsys.readouterr().out)}
    assert "quantum_algorithm_catalog" in lab
    assert "quantum_algorithm_run" in lab
    assert "quantum_cloud_submit" in lab
    assert main(["tools", "--preset", "sign"]) == 0
    sign = {row["name"] for row in json.loads(capsys.readouterr().out)}
    assert sign == {
        "company_capabilities",
        "company_analysis_render",
        "quantum_asset_get",
        "quantum_asset_metrics",
        "hpc_submit",
        "hpc_script_check",
        "hpc_stage_file",
        "hpc_job_cancel",
        "hpc_dir_create",
        "hpc_file_remove",
        "quantum_cloud_devices",
        "quantum_cloud_submit",
        "quantum_cloud_status",
        "quantum_cloud_result",
        "quantum_device_identity",
        "quantum_device_run",
    }


def test_tools_command_rejects_unknown_preset(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["tools", "--preset", "unknown"])
    assert caught.value.code == 2
    assert "unknown preset" in capsys.readouterr().err
