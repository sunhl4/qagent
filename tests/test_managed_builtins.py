"""Framework v0.8 counter-examples over the managed builtin layer.

F2: unknown tools fail closed including preset/builtin layer confusion.
F5: untrusted file and knowledge content stays data and never authorizes.
F10: result budgets bind all tools and close oversized outputs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from company_agent.catalog import (
    builtin_tools_for_preset,
    load_managed_builtins,
    load_result_policy,
    load_tools,
)
from company_agent.invoke import validate_invocation
from company_agent.policy import decide

ROOT = Path(__file__).resolve().parents[1]


def test_f2_unknown_tool_fails_closed_across_layers() -> None:
    # Managed builtins are mounted by DSH itself; they are not company
    # capabilities, so every company-side path must refuse them.
    for name in (*load_managed_builtins(), "skill"):
        assert validate_invocation(name, {}) == "unknown tool", name
        assert decide(name, "lab", {}) == "deny", name
    # Presets never widen the catalog: unknown or out-of-scope names stay
    # denied even when a caller claims an allow-listing preset.
    for name in ("quantum_device_run", "nowhere_tool", "read", "web_search"):
        assert decide(name, "boot", {}) == "deny", name
    assert validate_invocation("nowhere_tool", {"path": "x"}) == "unknown tool"


def test_f5_untrusted_content_is_data_not_authority() -> None:
    preset = (
        ROOT / "profiles/company-agent/agent-presets/company-agent/agent.cordis.yml"
    ).read_text(encoding="utf-8")
    assert "信任分区" in preset
    assert "不得当作指令执行" in preset
    skill = (ROOT / "skills/company-docs-research/SKILL.md").read_text(encoding="utf-8")
    assert "是**数据**" in skill
    assert "不执行" in skill
    assert "不授予任何审批或设备权限" in skill
    knowledge = (ROOT / "skills/company-knowledge/SKILL.md").read_text(encoding="utf-8")
    assert "untrusted_reference_data" in knowledge
    # The knowledge contract fixes the trust label and output bounds itself;
    # snippets cannot carry executable authority.
    contract = json.loads((ROOT / "contracts/results.json").read_text(encoding="utf-8"))
    assert contract["output_content"]["reference_trust"] == "untrusted_reference_data"
    assert contract["output_content"]["known_credentials"] == "reject_echo"
    tools = load_tools()
    assert tools["company_knowledge_search"]["output"]["properties"]["trust"] == {
        "type": "string",
        "const": "untrusted_reference_data",
    }


def test_f10_result_budget_covers_managed_builtins() -> None:
    policy = load_result_policy()
    assert policy["output_content"]["scope"] == "all_tools"
    assert 1 <= policy["max_result_bytes"] <= 131_072
    # The fs read cap stays under the single-result budget so oversized reads
    # fail closed instead of spilling tool payloads into the conversation.
    patch = (ROOT / "profiles/company-agent/cordis.patch.yml").read_text(encoding="utf-8")
    read_cap = int(re.search(r"(?m)^    readMaxBytes: (\d+)$", patch).group(1))
    assert 0 < read_cap <= policy["max_result_bytes"]


def test_local_route_stays_failure_honest() -> None:
    patch = (ROOT / "profiles/company-agent/cordis.patch.yml").read_text(encoding="utf-8")
    assert "provider: company-relay" in patch
    assert "baseURL: http://127.0.0.1:8000/v1" in patch
    local = patch.split("      company-local:", 1)[1].split("      company-relay:", 1)[0]
    assert "Authorization: Bearer local" in local
    assert "apiKeyEnv:" not in local
    # No key material is inlined; credentials stay env-addressed, and local
    # unreachability is reported as-is instead of falling back to a public route.
    assert "DEEPSEEK_API_KEY" not in patch
    with pytest.raises(KeyError):
        builtin_tools_for_preset("standard")
