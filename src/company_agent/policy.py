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
    research_ask = policy.get("research_run_ask_presets")
    research_deny = policy.get("research_run_deny_presets")
    if (policy.get("research_run_tool") != "company_research_run"
        or policy.get("research_run_provider") != "company-research"
        or research_ask != ["lab"]
        or research_deny != ["boot", "algo", "sign"]):
        raise RuntimeError("Company Agent research run policy contract is invalid")
    if (policy.get("knowledge_note_tool") != "company_knowledge_note"
        or policy.get("knowledge_note_ask_presets") != ["lab"]
        or policy.get("knowledge_note_deny_presets") != ["boot", "algo", "sign"]
        or policy.get("sign_receipt_tool") != "company_sign_receipt"
        or policy.get("sign_receipt_allow_presets") != ["sign"]
        or policy.get("catalog_replay_tool") != "company_catalog_replay"
        or policy.get("catalog_replay_allow_presets") != ["algo", "lab"]
        or policy.get("catalog_replay_deny_presets") != ["boot", "sign"]
        or policy.get("device_window_tool") != "quantum_device_window"
        or policy.get("device_window_allow_presets") != ["algo", "lab", "sign"]
        or policy.get("device_window_deny_presets") != ["boot"]):
        raise RuntimeError("Company Agent seat policy contract is invalid")
    if (policy.get("dingtalk_reply_tool") != "company_dingtalk_reply"
        or policy.get("dingtalk_reply_provider") != "company-dingtalk"
        or policy.get("dingtalk_reply_ask_presets") != ["lab"]
        or policy.get("dingtalk_reply_deny_presets") != ["boot", "algo", "sign"]):
        raise RuntimeError("Company Agent dingtalk reply policy contract is invalid")
    grant = policy.get("session_grant")
    if (
        not isinstance(grant, dict)
        or set(grant) != {"tool", "max_calls_per_tool", "max_ttl_seconds", "tools"}
        or grant.get("tool") != "company_grant_open"
        or grant.get("max_calls_per_tool") != 20
        or grant.get("max_ttl_seconds") != 14400
        or grant.get("tools") != list(_grant_tools())
    ):
        raise RuntimeError("Company Agent session grant contract is invalid")
    return policy


def _grant_tools() -> tuple[str, ...]:
    from company_agent.grants import GRANT_TOOLS
    return GRANT_TOOLS


def _account_allows(tool: str) -> bool:
    """Narrow an already-permitted preset decision. Legacy seats stay preset-only."""

    try:
        capability = load_tools()[tool]["capability"]
    except (KeyError, RuntimeError, TypeError):
        return False
    if not isinstance(capability, str) or not capability:
        return False
    try:
        from company_agent.tenants import account_allows

        return account_allows(capability)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _with_grant(tool: str, preset: str, ask_presets: set[str], args: Mapping[str, Any]) -> Decision:
    """Ask unless this session's grant still covers the tool. A deny preset stays deny."""
    if preset not in ask_presets:
        return "deny"
    try:
        from company_agent.grants import grant_covers, handoff_pending
        if handoff_pending(tool):
            return "ask"
        if grant_covers(tool, args):
            return "allow"
    except (OSError, RuntimeError, TypeError, ValueError):
        return "ask"
    return "ask"


def _preset_decide(tool: str, preset: str, args: Mapping[str, Any] | None = None) -> Decision:
    if not isinstance(tool, str) or not tool or len(tool) > 128:
        return "deny"
    if not isinstance(preset, str) or not preset or len(preset) > 32:
        return "deny"
    if not isinstance(args, Mapping):
        raise TypeError("arguments must be an object")
    if not isinstance(args, dict):
        raise TypeError("arguments must be a JSON object")
    if preset == "sign" and tool in {"quantum_device_run", "hpc_submit", "quantum_cloud_submit"}:
        from company_agent.work_items import bound_plan_steps
        steps = bound_plan_steps()
        if steps is not None and tool not in steps:
            return "deny"
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
        return _with_grant(tool, preset, ask_presets, args)
    if tool == policy["cloud_submit_tool"]:
        cloud_ask = set(policy["cloud_submit_ask_presets"])
        if preset in set(policy["cloud_submit_deny_presets"]):
            return "deny"
        return _with_grant(tool, preset, cloud_ask, args)
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
        return _with_grant(tool, preset, set(ask_presets), args)
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
        return _with_grant(tool, preset, set(plan_ask_presets), args)
    if tool == policy.get("research_run_tool"):
        if tool != "company_research_run":
            return "deny"
        if policy.get("research_run_provider") != "company-research":
            return "deny"
        research_ask = policy.get("research_run_ask_presets") or ()
        research_deny = policy.get("research_run_deny_presets") or ()
        if not isinstance(research_ask, list) or not isinstance(research_deny, list):
            return "deny"
        if any(not isinstance(item, str) for item in (*research_ask, *research_deny)):
            return "deny"
        if set(research_ask) != {"lab"} or set(research_deny) != {"boot", "algo", "sign"}:
            return "deny"
        if preset in set(research_deny):
            return "deny"
        return _with_grant(tool, preset, set(research_ask), args)
    if tool == policy.get("dingtalk_reply_tool"):
        if tool != "company_dingtalk_reply":
            return "deny"
        if policy.get("dingtalk_reply_provider") != "company-dingtalk":
            return "deny"
        dingtalk_ask = policy.get("dingtalk_reply_ask_presets") or ()
        dingtalk_deny = policy.get("dingtalk_reply_deny_presets") or ()
        if not isinstance(dingtalk_ask, list) or not isinstance(dingtalk_deny, list):
            return "deny"
        if any(not isinstance(item, str) for item in (*dingtalk_ask, *dingtalk_deny)):
            return "deny"
        if set(dingtalk_ask) != {"lab"} or set(dingtalk_deny) != {"boot", "algo", "sign"}:
            return "deny"
        if preset in set(dingtalk_deny):
            return "deny"
        return _with_grant(tool, preset, set(dingtalk_ask), args)
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
        return _with_grant(tool, preset, hpc_ask_presets, args)
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
        return _with_grant(tool, preset, write_ask_presets, args)
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
        return _with_grant(tool, preset, cancel_ask_presets, args)
    if tool == "company_grant_open":
        return "ask" if preset in {"lab", "sign"} else "deny"
    if tool == policy.get("knowledge_note_tool"):
        if preset in set(policy.get("knowledge_note_deny_presets") or ()):
            return "deny"
        return "ask" if preset in set(policy.get("knowledge_note_ask_presets") or ()) else "deny"
    if tool == policy.get("sign_receipt_tool"):
        return "allow" if preset in set(policy.get("sign_receipt_allow_presets") or ()) else "deny"
    if tool == policy.get("catalog_replay_tool"):
        if preset in set(policy.get("catalog_replay_deny_presets") or ()):
            return "deny"
        return "allow" if preset in set(policy.get("catalog_replay_allow_presets") or ()) else "deny"
    if tool == policy.get("device_window_tool"):
        if preset in set(policy.get("device_window_deny_presets") or ()):
            return "deny"
        return "allow" if preset in set(policy.get("device_window_allow_presets") or ()) else "deny"
    return "allow"


def decide(tool: str, preset: str, args: Mapping[str, Any] | None = None) -> Decision:
    """Preset decision first. An account list can narrow allow or ask; it cannot reopen a denial."""

    decision = _preset_decide(tool, preset, args)
    if decision == "deny" or _account_allows(tool):
        return decision
    return "deny"
