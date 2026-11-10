"""Current seat, grant remainder, and the names of missing configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path

from company_agent.grants import grant_view, handoff_view

_PROFILES = {"company-agent", "company-agent-minimal"}
_CHECKED = (
    "COMPANY_AGENT_GITLAB_URL",
    "COMPANY_AGENT_GITLAB_TOKEN",
    "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
    "COMPANY_QUANTUM_PLATFORM_TOKEN",
    "COMPANY_AGENT_SIMULATOR_INVOKE_URL",
    "COMPANY_AGENT_SIMULATOR_TOKEN",
    "COMPANY_AGENT_COMPILER_INVOKE_URL",
    "COMPANY_AGENT_COMPILER_TOKEN",
    "COMPANY_AGENT_DEVICE_INVOKE_URL",
    "COMPANY_AGENT_DEVICE_TOKEN",
    "COMPANY_AGENT_CLOUD_INVOKE_URL",
    "COMPANY_AGENT_CLOUD_TOKEN",
    "COMPANY_AGENT_HPC_INVOKE_URL",
    "COMPANY_AGENT_HPC_TOKEN",
    "COMPANY_AGENT_FETCH_ALLOWLIST",
    "COMPANY_AGENT_COMPUTE_ALLOW",
    "COMPANY_AGENT_RESEARCH_ROOT",
    "COMPANY_AGENT_OPEN_WPS",
)


def _executor() -> str:
    configured = str(os.environ.get("COMPANY_AGENT_RESEARCH_STATE") or "").strip()
    path = Path(configured) if configured else Path.home() / ".dsh" / "research-clock"
    record = path / "records.json"
    if not record.is_file():
        return "unset"
    try:
        payload = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "unset"
    runs = payload.get("runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return "unset"
    for item in reversed(runs):
        if isinstance(item, dict) and item.get("executor") in {"stub", "local", "handoff"}:
            return str(item["executor"])
    return "unset"


def status(preset: str) -> dict:
    profile = str(os.environ.get("COMPANY_AGENT_PROFILE") or "").strip()
    if profile not in _PROFILES:
        profile = "unset"
    missing = []
    for name in _CHECKED:
        value = str(os.environ.get(name) or "").strip()
        if name == "COMPANY_AGENT_COMPUTE_ALLOW":
            if value != "1":
                missing.append(name)
        elif not value:
            missing.append(name)
    from company_agent.receipts import unknown_submissions
    from company_agent.work_items import bound_plan_hash

    handoff = handoff_view()
    handoff["experiment_id"] = str(handoff.get("experiment_id") or "")[:64]
    handoff["next_tool"] = str(handoff.get("next_tool") or "")[:64]
    unknown = []
    for item in unknown_submissions():
        unknown.append({
            "tool": str(item.get("tool") or "")[:64],
            "business_ref": str(item.get("business_ref") or "")[:128],
        })
    return {
        "profile": profile,
        "preset": preset,
        "grant": grant_view(),
        "missing_env": missing[:32],
        "executor": _executor(),
        "handoff": handoff,
        "unknown": unknown[:8],
        "plan_hash": bound_plan_hash()[:64],
    }
