import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_minimal_profile_physically_omits_device_plugin() -> None:
    text = (ROOT / "profiles/company-agent-minimal/cordis.patch.yml").read_text()
    manifest = (ROOT / "profiles/company-agent-minimal/package.json").read_text()
    bootstrap = (ROOT / "scripts/bootstrap_dsh.sh").read_text()
    start = (ROOT / "scripts/start_runtime.sh").read_text()
    assert "company-agent-device" not in text
    assert "company-agent-device" not in manifest
    assert '"patchReload":"startup"' in manifest
    assert '"private":true' in manifest
    assert "includeShippedRoot: false" in text
    assert "includeUserRoot: false" in text
    assert "COMPANY_AGENT_PRESET_ROOT" in text
    assert 'rm -rf "${profile_dir}/node_modules/@unitqc/company-agent-device"' in bootstrap
    assert 'rm -rf -- "${DSH_HOME}/profiles"' in bootstrap
    assert "COMPANY_AGENT_DSH_HOME" in bootstrap
    assert "COMPANY_AGENT_DSH_HOME" in start
    assert "runtime paths must be absolute" in start
    assert "runtime paths must be absolute" in bootstrap
    assert "runtime roots must not be symlinks" in start
    assert "runtime roots must not be symlinks" in bootstrap
    assert 'rm -rf -- "${presets_root}"' in start
    assert 'rm -rf -- "${skills_dst}"' in start
    assert "COMPANY_AGENT_SKILL_ROOT" in start
    assert 'export COMPANY_AGENT_PROFILE="${PROFILE}"' in start
    assert "COMPANY_AGENT_PYTHON must be an absolute executable path" in start
    assert 'export COMPANY_AGENT_CONTRACTS_DIR="${ROOT}/contracts"' in start
    assert "unset COMPANY_AGENT_APPROVAL_CONTEXT" in start
    assert "umask 077" in start
    assert "umask 077" in bootstrap
    assert 'chmod 700 "${DSH_HOME}"' in start
    assert "runtime.env" not in start


def test_bootstrap_creates_home_before_setting_permissions() -> None:
    bootstrap = (ROOT / "scripts/bootstrap_dsh.sh").read_text()
    assert bootstrap.index('mkdir -p "${DSH_HOME}" "${RUNTIME}"') < bootstrap.index(
        'chmod 700 "${DSH_HOME}" "${RUNTIME}"'
    )


def test_ci_keeps_source_tree_free_of_installation_artifacts() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert 'pip install -e ".[dev]"' not in workflow
    assert "--require-hashes -r runtime/python-dev.lock" in workflow
    assert "scripts/verify_acceptance.py" in workflow


def test_profile_presets_keep_composition_and_metadata_in_their_own_files() -> None:
    for profile, expected_name in (
        ("company-agent", "Company Agent"),
        ("company-agent-minimal", "Company Agent Minimal"),
    ):
        preset = ROOT / f"profiles/{profile}/agent-presets/company-agent"
        composition = preset / "agent.cordis.yml"
        metadata = preset / "preset.yml"
        composition_text = composition.read_text(encoding="utf-8")
        assert composition_text.lstrip().startswith("- id:")
        assert "@deepseek-ai/dsh-persona" in composition_text
        assert "@deepseek-ai/dsh-skill-filesystem" not in composition_text
        assert "@deepseek-ai/dsh-tool-skill" not in composition_text
        assert "name: Company Agent\n" not in composition_text
        metadata_text = metadata.read_text(encoding="utf-8")
        assert f"name: {expected_name}" in metadata_text
        assert "description:" in metadata_text
        assert not metadata_text.lstrip().startswith("[")


def test_company_skills_publish_required_frontmatter() -> None:
    names = {
        "company-knowledge",
        "company-docs-research",
        "company-office-matter",
        "company-software-development",
        "quantum-workflow",
        "company-plan",
    }
    for name in names:
        text = (ROOT / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        frontmatter = text.split("---\n", 2)[1]
        assert re.search(rf"(?m)^name:\s*{re.escape(name)}\s*$", frontmatter)
        assert re.search(r"(?m)^description:\s*\S", frontmatter)


def test_full_profile_hardens_codex() -> None:
    text = (ROOT / "profiles/company-agent/cordis.patch.yml").read_text()
    preset = (ROOT / "profiles/company-agent/agent-presets/company-agent/agent.cordis.yml").read_text()
    assert "permissionMode: never" in text
    assert "inheritsParentContext: false" in text
    assert "tool-subagent-codex" not in text
    assert "subagent_codex" not in preset
    assert not re.search(r"(?m)^\s*name:\s*['\"]?@unitqc/company-agent-device", preset)
    assert "company-agent-device" in text
    assert "includeShippedRoot: false" in text
    assert "includeUserRoot: false" in text
    assert "COMPANY_AGENT_PRESET_ROOT" in text
    assert "COMPANY_AGENT_SKILL_ROOT" in text
    assert "skill-filesystem" in text
    assert "tool-skill" in text
    assert '"patchReload":"startup"' in (ROOT / "profiles/company-agent/package.json").read_text()
    assert "dsh-cli.mjs" in (ROOT / "scripts/start_runtime.sh").read_text()
    assert "node_modules/node/bin/node" in (ROOT / "scripts/start_runtime.sh").read_text()
    assert 'NODE_PACKAGE_VERSION="22.22.0"' in (ROOT / "scripts/bootstrap_dsh.sh").read_text()
    assert 'PNPM_VERSION="12.5.1"' in (ROOT / "scripts/bootstrap_dsh.sh").read_text()
    assert "invalid COMPANY_AGENT_PRESET" in (ROOT / "scripts/start_runtime.sh").read_text()
    assert "COMPANY_AGENT_DSH_PORT must be an integer" in (ROOT / "scripts/start_runtime.sh").read_text()
    assert (
        "company-agent-minimal only supports boot or algo presets"
        in (ROOT / "scripts/start_runtime.sh").read_text()
    )


def test_runtime_lock_matches_declared_pins() -> None:
    pins = json.loads((ROOT / "pins.json").read_text())
    runtime = json.loads((ROOT / "runtime/package.json").read_text())
    lock = (ROOT / "runtime/pnpm-lock.yaml").read_text()
    assert runtime["dependencies"]["@deepseek-ai/dsh"] == pins["deepseek_harness"]
    assert runtime["engines"]["runtime"]["version"] == pins["dsh_node"]
    assert f"specifier: {pins['deepseek_harness']}" in lock
    assert f"specifier: runtime:{pins['dsh_node']}" in lock
    bootstrap = (ROOT / "scripts/bootstrap_dsh.sh").read_text()
    assert f'PNPM_VERSION="{pins["pnpm"]}"' in bootstrap
    assert "--frozen-lockfile" in bootstrap


def test_dsh_plugins_register_contract_catalog() -> None:
    core = (ROOT / "packages/company-agent-core/src/index.js").read_text()
    runtime = (ROOT / "packages/company-agent-core/src/runtime.js").read_text()
    quantum = (ROOT / "packages/company-agent-quantum/src/index.js").read_text()
    device = (ROOT / "packages/company-agent-device/src/index.js").read_text()
    for text in (core, quantum, device):
        assert "registerCapabilityTools" in text
    assert 'runCliSync(["tools", "--preset", configuredPreset()])' in runtime
    assert 'runCliSync(["tools"])' in runtime
    assert not (ROOT / "seams").exists()


def test_dsh_plugins_are_plain_javascript_runtime_artifacts() -> None:
    for package in ("policy", "core", "quantum", "device", "latex"):
        manifest = (ROOT / f"packages/company-agent-{package}/package.json").read_text()
        assert '"private": true' in manifest
        assert "src/index.js" in manifest
        assert (ROOT / f"packages/company-agent-{package}/src/index.js").is_file()
        assert not (ROOT / f"packages/company-agent-{package}/src/index.ts").exists()


def test_dsh_plugins_only_register_and_bridge() -> None:
    for path in (ROOT / "packages").glob("*/src/index.js"):
        text = path.read_text()
        assert "fetch(" not in text
        assert "company_quantum" not in text
    policy = (ROOT / "packages/company-agent-policy/src/index.js").read_text()
    assert "policyDecision" in policy
    assert 'startsWith("company_")' in policy
    assert 'startsWith("quantum_")' in policy
    assert "return next()" in policy
    assert "tools.guard" not in policy


def test_profile_reenables_managed_builtins_by_full_row_override() -> None:
    """Web bundle disables model tool rows; the patch layer must restate the
    whole row with an explicit `disabled: false`, otherwise the disabled flag
    from the web layer survives and the tool stays out of the catalog."""
    text = (ROOT / "profiles/company-agent/cordis.patch.yml").read_text(encoding="utf-8")

    def row(id: str) -> str:
        blocks = re.split(r"(?m)^- id: ", text)
        assert blocks[0].lstrip() == "" or "insert:" in blocks[0] or "patch" in blocks[0]
        body = next(block for block in blocks[1:] if block.splitlines()[0].strip() == id)
        return body

    for name in ("tool-fs", "tool-fs-search", "tool-web", "skill-filesystem", "tool-skill"):
        body = row(name)
        assert re.search(r"(?m)^  disabled: false$", body), name
    assert "readMaxBytes: 51200" in row("tool-fs")
    assert "sampleOverCapGlobResults: false" in row("tool-fs-search")
    assert "fetch: false" in row("tool-web")
    assert "str_replace_editor" not in text
    for shell in ("tool-bash", "tool-pwsh"):
        with pytest.raises(StopIteration):
            row(shell)


def test_profile_mounts_company_local_model_route_and_default() -> None:
    text = (ROOT / "profiles/company-agent/cordis.patch.yml").read_text(encoding="utf-8")
    preset = (ROOT / "profiles/company-agent/agent-presets/company-agent/agent.cordis.yml").read_text()
    assert "providers:" in text and "company-local:" in text
    assert "baseURL: http://127.0.0.1:8000/v1" in text
    assert "api: openai-completions" in text
    assert "- id: deepseek-chat" in text
    assert "COMPANY_AGENT_LOCAL_MODEL_TOKEN" in text
    assert "apiKeyEnv: COMPANY_AGENT_LOCAL_MODEL_TOKEN" not in text
    assert "company-relay:" in text
    relay = text.split("      company-relay:", 1)[1].split("\n# 默认模型路由", 1)[0]
    # Snapshot of the complete authorized discovery response, 2026-10-22.
    # These are model IDs, not scientific algorithm/component IDs.
    assert re.findall(r"^          - id: (.+)$", relay, re.MULTILINE) == [
        "yaozheng-GLM-5.3-Flash", "gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna",
        "codex-auto-review",
    ]
    assert "displayName: Company Relay (公司中转)" in relay
    assert "baseURL: http://192.168.110.150:4000/v1" in text
    assert "apiKeyEnv: COMPANY_RELAY_API_KEY" in text
    assert "COMPANY_RELAY_API_KEY" in (
        (ROOT / "src/company_agent/cli.py").read_text()
    )
    default_block = text.split("- id: agent-default-model", 1)[1].split("- id: ", 1)[0]
    assert "provider: company-local" in default_block
    assert "model: deepseek-chat" in default_block
    assert "COMPANY_AGENT_LOCAL_MODEL_TOKEN" in (
        (ROOT / "src/company_agent/cli.py").read_text()
    )
    assert "信任分区" in preset
    assert "quantum_device_run" in preset


def test_start_runtime_syncs_skills_from_registry() -> None:
    start = (ROOT / "scripts/start_runtime.sh").read_text()
    assert 'rm -rf -- "${skills_dst}"' in start
    # The mount root is composed by the admission registry, then rechecked.
    assert 'verify_skills.py" sync' in start
    assert 'verify_skills.py" verify' in start
    verify = (ROOT / "scripts/verify_dsh_profiles.py").read_text()
    assert "load_skills()" in verify
    # The registry is the single admission record; docs-research must be admitted.
    registry = json.loads((ROOT / "contracts/skills.json").read_text(encoding="utf-8"))
    assert any(row["name"] == "company-docs-research" for row in registry["skills"])
