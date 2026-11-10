from __future__ import annotations

import json

import pytest

from company_agent.catalog import load_presets, load_tools
from company_agent.cli import main


def test_doctor_reports_model_and_contract_providers(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_DSH_VERSION", raising=False)
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
        "COMPANY_DINGTALK_APP_KEY",
        "COMPANY_DINGTALK_APP_SECRET",
        "COMPANY_DINGTALK_ROBOT_CODE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "platform", "simulator", "compiler", "device", "compute", "cloud", "model",
        "managed_builtins", "local_model_route", "relay_model_route",
        "knowledge_governance", "skills_governance", "tenants_governance", "receipts",
        "harness", "dingtalk",
    }
    assert payload["harness"]["compatible"] is True
    assert payload["harness"]["official_status"] == "unreleased"
    assert payload["harness"]["migration_mode"] == "dsh-plugin-pack"
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
    assert payload["managed_builtins"] == {"enabled": True, "count": 9}
    assert payload["local_model_route"]["token_env"] == "COMPANY_AGENT_LOCAL_MODEL_TOKEN"
    assert payload["dingtalk"]["configured"] is False
    assert payload["dingtalk"]["app_key_env"] == "COMPANY_DINGTALK_APP_KEY"
    assert payload["dingtalk"]["app_secret_env"] == "COMPANY_DINGTALK_APP_SECRET"
    assert payload["dingtalk"]["robot_code_env"] == "COMPANY_DINGTALK_ROBOT_CODE"


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
    assert payload == {"decision": "deny", "error": "circuit_id has an invalid format", "handoff": False}

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
    assert json.loads(capsys.readouterr().out) == {"decision": "ask", "error": None, "handoff": False}


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
    assert [row["name"] for row in tools] == list(load_tools())
    assert "company_shell" not in {row["name"] for row in tools}
    assert "company_run_dossier" in {row["name"] for row in tools}
    assert tools[0]["name"] == "company_work_item"
    assert tools[-1]["name"] == "company_dingtalk_reply"


def test_tools_command_filters_by_preset(capsys) -> None:
    assert main(["tools", "--preset", "boot"]) == 0
    boot = {row["name"] for row in json.loads(capsys.readouterr().out)}
    assert boot == {
        "company_capabilities",
        "company_work_item",
        "company_session_status",
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
        "company_office_review_table",
        "company_office_files",
        "company_office_fix",
        "company_office_surface",
        "company_portal_open",
        "company_dingtalk_inbox",
    }
    assert main(["tools", "--preset", "lab"]) == 0
    lab = {row["name"] for row in json.loads(capsys.readouterr().out)}
    assert boot == set(load_presets()["presets"]["boot"]["model_tools"])
    assert lab == set(load_presets()["presets"]["lab"]["model_tools"])
    assert "company_shell" not in boot
    assert "company_shell" not in lab
    assert "company_office_edit" not in load_presets()["presets"]["algo"]["visible_tools"]
    assert "quantum_algorithm_catalog" in lab
    assert "quantum_algorithm_run" in lab
    assert "quantum_cloud_submit" in lab
    assert "quantum_device_run" in lab
    assert "hpc_submit" in lab
    assert "company_grant_open" in lab
    assert "company_dingtalk_inbox" in lab
    assert "company_dingtalk_reply" in lab
    assert "company_dingtalk_reply" not in boot
    assert main(["tools", "--preset", "sign"]) == 0
    sign = {row["name"] for row in json.loads(capsys.readouterr().out)}
    assert sign == {
        "company_capabilities",
        "company_session_status",
        "company_grant_open",
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
        "quantum_cloud_result_page",
        "quantum_device_identity",
        "quantum_device_run",
        "company_work_item",
        "company_sign_receipt",
        "quantum_device_window",
    }


def test_seat_path_reads_dossier_draft_receipt_and_window(monkeypatch, tmp_path) -> None:
    from company_agent.dossier import remember
    from company_agent.invoke import invoke
    from company_agent.receipts import record_outcome

    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:seat-path")
    monkeypatch.delenv("COMPANY_AGENT_DEVICE_WINDOW", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_SIMULATOR_INVOKE_URL", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_SIMULATOR_TOKEN", raising=False)
    paper = tmp_path / "literature" / "demo1"
    paper.mkdir(parents=True)
    (paper / "formula-ledger.json").write_text(
        json.dumps({"entries": [{"anchor": "eq:energy", "ledger_id": "F1"}]}),
        encoding="utf-8",
    )
    draft = invoke("company_literature_draft_card", "lab", {"paper_id": "demo1"})
    assert draft.status == "ok"
    assert draft.payload["baseline_reproduced"] is False
    assert draft.payload["idempotency_key"] == ""
    assert "eq:energy" in draft.payload["anchors"]
    remember(
        "quantum_cloud_submit",
        {"catalog_version": "cat"},
        {"cloud_task": "task-1", "component_id": "demo"},
    )
    found = invoke("company_run_dossier", "lab", {"cloud_task": "task-1"})
    assert found.status == "ok"
    assert found.payload["count"] == 1
    assert found.payload["items"][0]["cloud_task"] == "task-1"
    assert "OPENQASM" not in json.dumps(found.payload)
    receipt = invoke(
        "company_sign_receipt",
        "sign",
        {"approval_id": "appr1", "unknown": True},
    )
    assert receipt.status == "ok"
    assert receipt.payload["unknown"] is True
    assert (tmp_path / receipt.payload["path"]).is_file()
    window = invoke("quantum_device_window", "algo", {})
    assert window.status == "error"
    replay = invoke(
        "company_catalog_replay",
        "algo",
        {"catalog_version": "cat", "circuit_ids": ["circ_a"]},
    )
    assert replay.status == "error"
    record_outcome(
        {
            "version": "1.0",
            "event": "provider",
            "tool": "quantum_cloud_submit",
            "operation": "cloud.submit",
            "request_id": "req_" + "a" * 32,
            "contract_digest": "sha256:" + ("a" * 64),
            "elapsed_ms": 1,
            "status": "error",
            "error_category": "timeout",
            "execution_state": "unknown",
        }
    )
    board = invoke("company_session_status", "lab", {})
    assert board.status == "ok"
    assert any(item["tool"] == "quantum_cloud_submit" for item in board.payload["unknown"])
    assert "COMPANY_AGENT_SIMULATOR_INVOKE_URL" in board.payload["missing_env"]


def test_tools_command_rejects_unknown_preset(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["tools", "--preset", "unknown"])
    assert caught.value.code == 2
    assert "unknown preset" in capsys.readouterr().err
