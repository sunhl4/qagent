"""Desktop seat uses the shipped standard preset and keeps company policy."""
from __future__ import annotations

from pathlib import Path

from company_agent.catalog import load_tools
from company_agent.policy import decide

ROOT = Path(__file__).resolve().parents[1]
HARNESS = Path(r"D:\Yaozheng\deepseek-harness")
DESKTOP = ROOT / "desktop/profile/cordis.patch.yml"
STANDARD = HARNESS / "packages/bundle/web-app/presets/standard.patch.yml"


def test_desktop_patch_selects_standard_without_duplicate_host_tools() -> None:
    text = DESKTOP.read_text(encoding="utf-8")
    assert "default: standard" in text
    assert "- id: preset-standard\n  disabled: true" not in text
    for name in ("preset-ptc", "preset-minimal", "preset-cordis", "preset-company-agent"):
        assert f"- id: {name}\n  disabled: true" in text
    for name in ("tool-fs", "tool-fs-search", "tool-web", "tool-todo", "tool-present", "tool-skill"):
        assert f"- id: {name}\n" not in text
    assert "COMPANY_AGENT_SKILL_ROOT" in text
    assert "includeDefaultRoots: false" not in text
    assert "permissionMode: never" in text
    assert "tool-subagent-codex" in text
    assert "disabled: true" in text.split("- id: tool-subagent-codex", 1)[1].split("- id:", 1)[0]


def test_shipped_standard_preset_still_has_the_native_seat() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    for name in (
        "tool-bash",
        "tool-pwsh",
        "tool-jobs",
        "compaction-basic",
        "tool-subagent",
        "plan-mode",
        "tool-goal",
        "tool-ask-user",
    ):
        assert f"id: {name}" in text
    web = text.split("id: tool-web", 1)[1].split("id: present", 1)[0]
    assert "fetch: true" in web


def test_lab_still_asks_and_boot_still_denies_submission() -> None:
    assert decide("hpc_submit", "lab", {}) == "ask"
    assert decide("quantum_device_run", "lab", {}) == "ask"
    assert decide("hpc_submit", "boot", {}) == "deny"
    assert decide("quantum_device_run", "boot", {}) == "deny"
    assert decide("company_grant_open", "lab", {}) == "ask"
    assert "company_shell" not in load_tools()
    for preset in ("boot", "lab", "algo", "sign"):
        assert decide("company_shell", preset, {}) == "deny"
        assert decide("hpc_submit", preset, {}) == ("ask" if preset in {"lab", "sign"} else "deny")
        assert decide("quantum_cloud_submit", preset, {}) == ("ask" if preset in {"lab", "sign"} else "deny")
        assert decide("quantum_device_run", preset, {}) == ("ask" if preset in {"lab", "sign"} else "deny")
    assert decide("company_office_edit", "algo", {}) == "deny"
    assert decide("company_sign_receipt", "sign", {}) == "allow"
    assert decide("company_sign_receipt", "lab", {}) == "deny"
    assert decide("company_catalog_replay", "algo", {}) == "allow"
    assert decide("company_catalog_replay", "boot", {}) == "deny"
    assert decide("quantum_device_window", "algo", {}) == "allow"
    assert decide("quantum_device_window", "boot", {}) == "deny"
    assert decide("company_knowledge_note", "lab", {}) == "ask"
    assert decide("company_knowledge_note", "algo", {}) == "deny"
