from __future__ import annotations

import json
import os
from pathlib import Path

from company_agent.capabilities import list_capabilities
from company_agent.catalog import (
    WORKSPACE_ROOT,
    _load_object,
    load_policy,
    load_presets,
    load_tools,
)
from company_agent.policy import decide

_FRAMEWORK_KEYS = {
    "runtime", "compatible_runtime_versions", "prototype", "prototype_objects",
    "official_status", "migration_mode", "executor", "connectors",
    "forbidden_worker_modes", "mandate_scopes",
}
_OBJECTS = ("source", "trigger", "eval", "mandate", "ticket", "assignment", "subscription")
_SCOPES = ("boot", "lab", "algo", "sign")
_FORBIDDEN = ("danger-full-access", "shell", "second-loop")
_MARKERS = ("danger-full-access", "dsh-tool-shell", "@deepseek-ai/dsh-superagent")


class HarnessCompatError(ValueError):
    """Raised when the harness migration contract itself is invalid."""


def _framework() -> dict:
    contract = _load_object("superagent.json")
    framework = contract.get("framework")
    connectors = framework.get("connectors") if isinstance(framework, dict) else None
    versions = framework.get("compatible_runtime_versions") if isinstance(framework, dict) else None
    if (
        contract.get("version") != "1.3.0"
        or contract.get("fail_closed") is not True
        or not isinstance(framework, dict)
        or set(framework) != _FRAMEWORK_KEYS
        or framework.get("runtime") != "deepseek-harness"
        or framework.get("prototype") != "dsh-superagent-prototype"
        or framework.get("official_status") != "unreleased"
        or framework.get("migration_mode") != "dsh-plugin-pack"
        or framework.get("executor") != "existing-dsh-session"
        or not isinstance(versions, list)
        or versions != ["0.1.5-rc.2", "0.2.1-rc.5"]
        or framework.get("prototype_objects") != list(_OBJECTS)
        or framework.get("forbidden_worker_modes") != list(_FORBIDDEN)
        or framework.get("mandate_scopes") != list(_SCOPES)
        or not isinstance(connectors, dict)
        or set(connectors) != {"github", "feishu"}
        or connectors != {"github": False, "feishu": False}
    ):
        raise HarnessCompatError("harness contract is invalid")
    return framework


def mandate_scopes() -> tuple[str, ...]:
    scopes = _framework()["mandate_scopes"]
    return tuple(scopes)


def _pins(root: Path) -> dict:
    path = root / "pins.json"
    if not path.is_file():
        raise HarnessCompatError("harness pin is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HarnessCompatError("harness pin is invalid")
    return payload


def _manifest_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HarnessCompatError("harness package manifest is invalid")
    return payload


def _scan_forbidden(root: Path) -> list[str]:
    found: list[str] = []
    for base in (root / "profiles", root / "packages"):
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if "node_modules" in path.parts or path.suffix.lower() not in {".js", ".yml", ".yaml", ".json"}:
                continue
            text = path.read_text(encoding="utf-8")
            for marker in _MARKERS:
                if marker in text:
                    found.append(f"{marker} in {path.relative_to(root).as_posix()}")
    return found


def migration_manifest() -> dict:
    """Project company capabilities onto one DSH session and the SuperAgent object model."""
    framework = _framework()
    contract = _load_object("superagent.json")
    from company_agent.super_dsh import SuperDshError, topology

    try:
        company_architecture = topology()
    except SuperDshError:
        company_architecture = {}
    root = WORKSPACE_ROOT
    pins = _pins(root)
    reasons: list[str] = []
    if not company_architecture:
        reasons.append("super-dsh architecture is invalid")
    runtime_pin = pins.get("deepseek_harness")
    if runtime_pin not in framework["compatible_runtime_versions"]:
        reasons.append("pinned DeepSeek Harness version is not in the tested set")
    runtime = _manifest_json(root / "runtime" / "package.json")
    full_profile = _manifest_json(root / "profiles" / "company-agent" / "package.json")
    if runtime.get("dependencies", {}).get("@deepseek-ai/dsh") != runtime_pin:
        reasons.append("runtime package does not match the DeepSeek Harness pin")
    if runtime.get("engines", {}).get("runtime", {}).get("version") != pins.get("dsh_node"):
        reasons.append("runtime Node version does not match the pin")
    dependencies = full_profile.get("dependencies", {})
    if dependencies.get("@deepseek-ai/dsh-subagent-codex") != pins.get("dsh_subagent_codex"):
        reasons.append("Codex subagent package does not match the pin")
    if dependencies.get("@openai/codex") != pins.get("openai_codex"):
        reasons.append("Codex package does not match the pin")
    if any("superagent" in str(name).lower() for name in dependencies):
        reasons.append("official SuperAgent package is not enabled")
    reasons.extend(_scan_forbidden(root))
    tools = load_tools()
    seen: dict[str, str] = {}
    capabilities = []
    for item in list_capabilities():
        names = list(item.tools)
        for name in names:
            if name not in tools or name in seen:
                reasons.append(f"capability tool {name} is not a single company tool")
            seen[name] = item.id
        capabilities.append({
            "id": item.id,
            "provider": item.provider,
            "approval": item.approval,
            "superagent_role": "tool-pack",
            "executor": "existing-dsh-session",
            "tools": names,
        })
    if set(seen) != set(tools):
        reasons.append("company tools are not all mapped onto SuperAgent tool packs")
    builtins = _load_object("tools.json").get("managed_builtins", [])
    builtin_names = [item.get("name") for item in builtins] if isinstance(builtins, list) else []
    if any(name in {"bash", "pwsh", "shell", "exec"} for name in builtin_names):
        reasons.append("managed shell tool is not part of the migration")
    policy = load_policy()
    presets = load_presets().get("presets", {})
    preset_report = {}
    for preset in _SCOPES:
        visible = list(presets[preset]["visible_tools"])
        if any(name not in tools for name in visible):
            reasons.append(f"preset {preset} exposes an unknown tool")
        device = decide(policy["device_tool"], preset, {})
        expected = "ask" if preset in policy["device_ask_presets"] else "deny"
        if device != expected:
            reasons.append(f"device decision for {preset} drifted")
        has_work_item = "company_work_item" in visible
        if has_work_item != (preset != "sign"):
            reasons.append(f"work-item visibility for {preset} drifted")
        preset_report[preset] = {
            "tool_count": len(visible),
            "includes_work_item": has_work_item,
            "device": device,
        }
    observed = str(os.environ.get("COMPANY_AGENT_DSH_VERSION") or "").strip()
    if observed and observed not in framework["compatible_runtime_versions"]:
        reasons.append("observed DeepSeek Harness version is not in the tested set")
    return {
        "runtime": framework["runtime"],
        "runtime_pin": runtime_pin if isinstance(runtime_pin, str) else "",
        "compatible_runtime_versions": list(framework["compatible_runtime_versions"]),
        "observed_runtime_version": observed,
        "compatible": not reasons,
        "reasons": reasons,
        "superagent_contract": contract["version"],
        "prototype": framework["prototype"],
        "prototype_objects": list(framework["prototype_objects"]),
        "official_status": framework["official_status"],
        "migration_mode": framework["migration_mode"],
        "executor": framework["executor"],
        "second_runtime": False,
        "architecture": company_architecture.get("name", ""),
        "clocks": list(company_architecture.get("clocks", [])),
        "planes": list(company_architecture.get("planes", [])),
        "connectors": dict(framework["connectors"]),
        "forbidden_worker_modes": list(framework["forbidden_worker_modes"]),
        "mandate_scopes": list(framework["mandate_scopes"]),
        "tool_count": len(tools),
        "capabilities": capabilities,
        "presets": preset_report,
    }


def harness_summary() -> dict:
    manifest = migration_manifest()
    return {
        "runtime": manifest["runtime"],
        "runtime_pin": manifest["runtime_pin"],
        "superagent_contract": manifest["superagent_contract"],
        "official_status": manifest["official_status"],
        "migration_mode": manifest["migration_mode"],
        "compatible": manifest["compatible"],
    }
