from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from company_agent.catalog import load_policy, load_presets, load_tools
from company_agent.contracts import Decision


def _policy_contract() -> dict[str, Any]:
    policy = load_policy()
    if policy.get("fail_closed") is not True:
        raise RuntimeError("Company Agent policy contract must be fail-closed")
    if policy.get("forbidden_tools") != ["cal_edit", "shuttle_write", "cordis_define", "cordis_run"]:
        raise RuntimeError("Company Agent policy forbidden tool contract is invalid")
    if policy.get("device_tool") != "quantum_device_run":
        raise RuntimeError("Company Agent policy device tool contract is invalid")
    if (policy.get("cloud_submit_tool") != "quantum_cloud_submit"
        or policy.get("cloud_submit_provider") != "uqc-cloud"
        or policy.get("cloud_submit_ask_presets") != ["lab", "sign"]
        or policy.get("cloud_submit_deny_presets") != ["boot", "algo"]
        or policy.get("cloud_submission") != {
            "target_scope": "simulators_only", "artifact_scope": "workspace_openqasm_file",
            "automatic_retries": 0,
        }):
        raise RuntimeError("Company Agent policy cloud submission contract is invalid")
    if policy.get("hpc_submit_tool") != "hpc_submit":
        raise RuntimeError("Company Agent policy HPC submit tool contract is invalid")
    latex_write = policy.get("latex_write_tools")
    if (not isinstance(latex_write, list) or any(not isinstance(item, str) for item in latex_write)
        or len(latex_write) != 6
        or sorted(latex_write) != [
            "company_latex_batch_edit", "company_latex_edit",
            "company_latex_issue_note", "company_latex_overleaf_push",
            "company_latex_push", "company_latex_revert",
        ]
        or policy.get("latex_write_provider") != "company-latex"
        or policy.get("latex_write_ask_presets") != ["lab", "sign"]
        or policy.get("latex_write_deny_presets") != ["boot", "algo"]):
        raise RuntimeError("Company Agent latex write policy contract is invalid")
    plan_write = policy.get("plan_write_tools")
    if (not isinstance(plan_write, list) or any(not isinstance(item, str) for item in plan_write)
        or len(plan_write) != 4
        or sorted(plan_write) != [
            "company_plan_issue_create", "company_plan_issue_write",
            "company_plan_milestone_create", "company_plan_note_create",
        ]
        or policy.get("plan_write_provider") != "company-plan"
        or policy.get("plan_write_ask_presets") != ["lab", "sign"]
        or policy.get("plan_write_deny_presets") != ["boot", "algo"]):
        raise RuntimeError("Company Agent plan write policy contract is invalid")
    return policy


def decide(tool: str, preset: str, args: Mapping[str, Any] | None = None) -> Decision:
    if not isinstance(tool, str) or not tool or len(tool) > 128:
        return "deny"
    if not isinstance(preset, str) or not preset or len(preset) > 32:
        return "deny"
    if not isinstance(args, Mapping):
        raise TypeError("arguments must be an object")
    if not isinstance(args, dict):
        raise TypeError("arguments must be a JSON object")
    del args
    try:
        if tool not in load_tools():
            return "deny"
        presets = load_presets().get("presets", {})
    except RuntimeError:
        return "deny"
    if not isinstance(presets, dict) or set(presets) != {"boot", "lab", "algo", "sign"}:
        return "deny"
    if preset not in presets:
        return "deny"
    preset_row = presets[preset]
    if not isinstance(preset_row, dict):
        return "deny"
    visible_raw = preset_row.get("visible_tools", [])
    if not isinstance(visible_raw, list) or any(not isinstance(item, str) for item in visible_raw):
        return "deny"
    visible = set(visible_raw)
    if len(visible) != len(visible_raw):
        return "deny"
    if tool not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "quantum_device_run" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "quantum_device_run" not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "hpc_submit" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "hpc_submit" not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "quantum_cloud_submit" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "quantum_cloud_submit" not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "hpc_stage_file" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "hpc_stage_file" not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "hpc_job_cancel" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "hpc_job_cancel" not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "hpc_dir_create" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "hpc_dir_create" not in visible:
        return "deny"
    if preset in {"boot", "algo"} and "hpc_file_remove" in visible:
        return "deny"
    if preset in {"lab", "sign"} and "hpc_file_remove" not in visible:
        return "deny"
    if preset == "boot" and "hpc_queue" in visible:
        return "deny"
    try:
        policy = _policy_contract()
    except RuntimeError:
        return "deny"
    ask_contract = policy.get("device_ask_presets")
    deny_contract = policy.get("device_deny_presets")
    if not isinstance(ask_contract, list) or not isinstance(deny_contract, list):
        return "deny"
    if set(ask_contract) != {"lab", "sign"}:
        return "deny"
    if set(deny_contract) != {"boot", "algo"}:
        return "deny"
    forbidden_raw = policy.get("forbidden_tools", [])
    if not isinstance(forbidden_raw, list) or any(not isinstance(item, str) for item in forbidden_raw):
        return "deny"
    if tool in set(forbidden_raw):
        return "deny"
    if tool == policy.get("device_tool"):
        if tool != "quantum_device_run":
            return "deny"
        if (
            policy.get("device_provider") != "ionstack-twinrun"
            or policy.get("device_provenance") != "qccd-twin"
        ):
            return "deny"
        ask_raw = policy.get("device_ask_presets") or ()
        deny_raw = policy.get("device_deny_presets") or ()
        if not isinstance(ask_raw, list) or not isinstance(deny_raw, list):
            return "deny"
        if any(not isinstance(item, str) for item in (*ask_raw, *deny_raw)):
            return "deny"
        ask_presets = set(ask_raw)
        deny_presets = set(deny_raw)
        if preset in deny_presets:
            return "deny"
        return "ask" if preset in ask_presets else "deny"
    if tool == policy["cloud_submit_tool"]:
        return "ask" if preset in policy["cloud_submit_ask_presets"] else "deny"
    if tool in set(policy.get("latex_write_tools") or ()):
        ask_presets = policy.get("latex_write_ask_presets") or ()
        deny_presets = policy.get("latex_write_deny_presets") or ()
        if (
            any(not isinstance(item, str) for item in (*ask_presets, *deny_presets))
            or set(ask_presets) != {"lab", "sign"}
            or set(deny_presets) != {"boot", "algo"}
        ):
            return "deny"
        if preset in deny_presets:
            return "deny"
        return "ask" if preset in ask_presets else "deny"
    if tool in set(policy.get("plan_write_tools") or ()):
        plan_ask_presets = policy.get("plan_write_ask_presets") or ()
        plan_deny_presets = policy.get("plan_write_deny_presets") or ()
        if (
            any(not isinstance(item, str) for item in (*plan_ask_presets, *plan_deny_presets))
            or set(plan_ask_presets) != {"lab", "sign"}
            or set(plan_deny_presets) != {"boot", "algo"}
        ):
            return "deny"
        if preset in plan_deny_presets:
            return "deny"
        return "ask" if preset in plan_ask_presets else "deny"
    if tool == policy.get("hpc_submit_tool"):
        if tool != "hpc_submit":
            return "deny"
        if policy.get("hpc_submit_provider") != "hpc-slurm-ssh":
            return "deny"
        hpc_ask_raw = policy.get("hpc_submit_ask_presets") or ()
        hpc_deny_raw = policy.get("hpc_submit_deny_presets") or ()
        if not isinstance(hpc_ask_raw, list) or not isinstance(hpc_deny_raw, list):
            return "deny"
        if any(not isinstance(item, str) for item in (*hpc_ask_raw, *hpc_deny_raw)):
            return "deny"
        hpc_ask_presets = set(hpc_ask_raw)
        hpc_deny_presets = set(hpc_deny_raw)
        if preset in hpc_deny_presets:
            return "deny"
        return "ask" if preset in hpc_ask_presets else "deny"
    if tool == policy.get("hpc_file_write_tool") or tool in {"hpc_dir_create", "hpc_file_remove"}:
        if tool not in {"hpc_stage_file", "hpc_dir_create", "hpc_file_remove"}:
            return "deny"
        if policy.get("hpc_file_write_provider") != "hpc-slurm-ssh":
            return "deny"
        write_ask_raw = policy.get("hpc_file_write_ask_presets") or ()
        write_deny_raw = policy.get("hpc_file_write_deny_presets") or ()
        if not isinstance(write_ask_raw, list) or not isinstance(write_deny_raw, list):
            return "deny"
        if any(not isinstance(item, str) for item in (*write_ask_raw, *write_deny_raw)):
            return "deny"
        write_ask_presets = set(write_ask_raw)
        write_deny_presets = set(write_deny_raw)
        if preset in write_deny_presets:
            return "deny"
        return "ask" if preset in write_ask_presets else "deny"
    if tool == policy.get("hpc_job_cancel_tool"):
        if tool != "hpc_job_cancel":
            return "deny"
        if policy.get("hpc_job_cancel_provider") != "hpc-slurm-ssh":
            return "deny"
        cancel_ask_raw = policy.get("hpc_job_cancel_ask_presets") or ()
        cancel_deny_raw = policy.get("hpc_job_cancel_deny_presets") or ()
        if not isinstance(cancel_ask_raw, list) or not isinstance(cancel_deny_raw, list):
            return "deny"
        if any(not isinstance(item, str) for item in (*cancel_ask_raw, *cancel_deny_raw)):
            return "deny"
        cancel_ask_presets = set(cancel_ask_raw)
        cancel_deny_presets = set(cancel_deny_raw)
        if preset in cancel_deny_presets:
            return "deny"
        return "ask" if preset in cancel_ask_presets else "deny"
    return "allow"
