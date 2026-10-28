from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

from company_agent.catalog import load_tools

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("company-agent", "company-agent-minimal")


def _os_env() -> dict[str, str]:
    """Hermetic env that still carries OS-critical variables for Node.

    On Windows, replacing the environment wholesale drops ``SystemRoot``,
    and Node aborts at init (``ncrypto::CSPRNG``) without it. The PATH passed
    to the child never affects how ``node`` itself is resolved.
    """

    env = {"PATH": os.environ.get("PATH", "")}
    for name in ("SystemRoot", "windir", "SYSTEMDRIVE", "COMPUTERNAME"):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _run_node(profile: str, program: str, *, preset: str | None = None) -> subprocess.CompletedProcess[str]:
    env = _os_env() | {
        "COMPANY_AGENT_PYTHON": sys.executable,
        "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
        "COMPANY_AGENT_PROFILE": profile,
        # Probe runs stay hermetic: each invocation gets a fresh receipt/ledger
        # root and turn identity, so termination budgets never accumulate across
        # test sessions (device_runs etc. are per-turn facts, not global ones).
        "COMPANY_AGENT_RECEIPT_DIR": tempfile.mkdtemp(prefix="company-agent-probe-"),
        "COMPANY_AGENT_TURN_ID": f"probe-{uuid.uuid4().hex[:16]}",
    }
    if preset is not None:
        env["COMPANY_AGENT_PRESET"] = preset
    return subprocess.run(
        ["node", "--input-type=module", "-e", program],
        cwd=ROOT / "profiles" / profile,
        env=env,
        # Children emit UTF-8 (JS/Python both pass through the file encoding);
        # decoding with the console code page would stall on Chinese payload
        # facts depending on where a failing byte pair lands.
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_hpc_plugin_registers_preset_visible_hpc_tools_only() -> None:
    # The plugin itself only forwards the compute.hpc roster; the preset catalog filter
    # decides visibility. Verify through the plugin entry point.
    register_program = """
import('@unitqc/company-agent-hpc').then(async (plugin) => {
  const names = [];
  plugin.apply({ tools: { register: (row) => names.push(row.name) } });
  console.log(JSON.stringify(names));
});
"""
    for profile, preset, expected in (
        ("company-agent", "lab", [
            "hpc_queue", "hpc_submit", "hpc_job_status", "hpc_script_check",
            "hpc_resources", "hpc_file_list", "hpc_file_fetch", "hpc_stage_file",
            "hpc_job_cancel", "hpc_dir_create", "hpc_file_remove",
        ]),
        ("company-agent", "algo", [
            "hpc_queue", "hpc_job_status", "hpc_resources", "hpc_file_list", "hpc_file_fetch",
        ]),
        ("company-agent", "sign", ["hpc_submit", "hpc_script_check", "hpc_stage_file",
                                   "hpc_job_cancel", "hpc_dir_create", "hpc_file_remove"]),
        ("company-agent", "boot", []),
    ):
        result = _run_node(profile, register_program, preset=preset)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == expected
    # The plugin mounts in the minimal profile, where its presets only reach the
    # read-only probes.
    for preset, expected_names in (("boot", []), ("algo", [
            "hpc_queue", "hpc_job_status", "hpc_resources", "hpc_file_list", "hpc_file_fetch",
    ])):
        result = _run_node("company-agent-minimal", register_program, preset=preset)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == expected_names


def test_latex_plugin_registers_preset_visible_company_latex_tools_only() -> None:
    # The preset catalog filter also decides company.latex visibility: the full
    # roster in lab, the read-only probes in algo, none in boot/sign. The minimal
    # profile reaches the same read-only probes through its algo preset.
    register_program = """
import('@unitqc/company-agent-latex').then(async (plugin) => {
  const names = [];
  plugin.apply({ tools: { register: (row) => names.push(row.name) } });
  console.log(JSON.stringify(names));
});
"""
    read_only = ["company_latex_structure", "company_latex_read", "company_latex_check"]
    for profile, preset, expected in (
        ("company-agent", "lab", [
            "company_latex_structure", "company_latex_read", "company_latex_edit",
            "company_latex_batch_edit", "company_latex_check", "company_latex_compile",
            "company_latex_diff", "company_latex_checkpoint", "company_latex_revert",
            "company_latex_pull", "company_latex_push",
            "company_latex_overleaf_pull", "company_latex_overleaf_push",
            "company_latex_overleaf_status", "company_latex_issue_note",
        ]),
        ("company-agent", "algo", read_only),
        ("company-agent", "sign", []),
        ("company-agent", "boot", []),
        ("company-agent-minimal", "algo", read_only),
        ("company-agent-minimal", "boot", []),
    ):
        result = _run_node(profile, register_program, preset=preset)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == expected


def test_plugins_import_from_clean_profile_dependency_graph() -> None:
    expected = {
        "company-agent": ("policy", "core", "quantum", "hpc", "device", "latex", "office", "plan"),
        "company-agent-minimal": ("policy", "core", "quantum", "hpc", "latex", "office"),
    }
    for profile, packages in expected.items():
        for package in packages:
            name = f"@unitqc/company-agent-{package}"
            result = _run_node(
                profile,
                f"import({json.dumps(name)}).then(m => console.log(m.name))",
                preset="lab" if profile == "company-agent" else "boot",
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == f"company-agent-{package}"


def test_core_runtime_reads_python_contract_catalog() -> None:
    result = _run_node(
        "company-agent",
        (
            "import('@unitqc/company-agent-core/runtime')"
            ".then(m => console.log(JSON.stringify(m.toolCatalog())))"
        ),
        preset="lab",
    )
    assert result.returncode == 0, result.stderr
    tools = json.loads(result.stdout)
    assert len(tools) == 59
    assert "quantum_algorithm_catalog" in {row["name"] for row in tools}
    assert tools[0]["name"] == "company_capabilities"
    # The lab-filtered catalog follows the preset's visible_tools order, whose
    # final entry is now the portal open fact (full-contract order ends with
    # company_fetch; see test_cli).
    assert tools[-1]["name"] == "company_portal_open"
    assert all(row["output"]["additionalProperties"] is False for row in tools)
    runtime = (ROOT / "packages/company-agent-core/src/runtime.js").read_text()
    assert "CLI_TIMEOUT_MS" in runtime
    assert "maxBuffer" in runtime
    assert "Buffer.byteLength(output" in runtime
    assert "ETIMEDOUT" in runtime
    assert "spawn(command.executable, command.args" in runtime
    assert "for (const key of Object.keys(env))" in runtime
    assert "env.PYTHONPATH = configured" in runtime
    assert '"--args", "-"' in runtime
    assert "child.stdin.end(stdin)" in runtime
    assert 'env.COMPANY_AGENT_APPROVAL_CONTEXT = "dsh"' in runtime
    assert "export async function authorize" in runtime
    # The bridge passes the turn identity to the adapter after the budget batch;
    # the pin follows the call prefix so neither shape drifts silently.
    assert 'await invoke(name, args, decision === "ask", exec?.signal' in runtime
    assert "schema: dshSchema(outputSchema)" in runtime
    assert "additionalProperties: true" not in runtime
    assert 'signal?.addEventListener("abort", onAbort' in runtime


@pytest.mark.parametrize(
    ("profile", "preset"),
    [
        ("company-agent", "boot"),
        ("company-agent", "lab"),
        ("company-agent", "algo"),
        ("company-agent", "sign"),
        ("company-agent-minimal", "boot"),
        ("company-agent-minimal", "algo"),
    ],
)
def test_registered_local_tools_execute_through_python(profile: str, preset: str) -> None:
    program = """
import { registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const tools = new Map();
registerCapabilityTools({ tools: { register: (row) => tools.set(row.name, row) } },
  ['company.workflow', 'company.knowledge']);
const capabilities = await tools.get('company_capabilities').execute({}, {});
const results = { capabilities };
if (tools.has('company_knowledge_search')) {
  results.knowledge = await tools.get('company_knowledge_search').execute({ query: '设备执行' }, {});
  results.workflow = await tools.get('company_workflow_validate').execute({ steps: [{
    id: 'inspect', capability: 'company.workflow', tool: 'company_capabilities'
  }] }, {});
}
console.log(JSON.stringify(results));
"""
    result = _run_node(profile, program, preset=preset)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["capabilities"]["capabilities"]) == 13
    if preset != "sign":
        assert payload["knowledge"]["query"] == "设备执行"
        assert payload["knowledge"]["hits"]
        assert payload["workflow"]["valid"] is True


def test_registered_schemas_match_every_python_contract() -> None:
    program = """
import { dshSchema, registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const rows = [];
registerCapabilityTools({ tools: { register: (row) => rows.push({
  name: row.name, parameters: row.parameters, output: row.output.schema
}) } }, ['company.workflow', 'company.knowledge', 'company.algorithm', 'company.asset',
  'quantum.simulation', 'quantum.compilation', 'quantum.device', 'compute.cloud', 'compute.hpc',
  'company.latex', 'company.office', 'company.plan', 'company.portal']);
console.log(JSON.stringify(rows));
"""
    result = _run_node("company-agent", program, preset="lab")
    assert result.returncode == 0, result.stderr
    registered = {row["name"]: row for row in json.loads(result.stdout)}
    contracts = load_tools()
    assert set(registered) == set(contracts)
    stripped = {
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
    }

    def projection(schema: dict) -> dict:
        projected = {}
        for key, value in schema.items():
            if key in stripped:
                continue
            if key == "properties":
                projected[key] = {name: projection(child) for name, child in value.items()}
            elif key in {"items", "additionalProperties"} and isinstance(value, dict):
                projected[key] = projection(value)
            else:
                projected[key] = value
        return projected

    for name, contract in contracts.items():
        assert registered[name]["parameters"] == projection(contract["parameters"])
        assert registered[name]["output"] == projection(contract["output"])


@pytest.mark.parametrize("profile", PROFILES)
def test_registered_workflow_accepts_static_arguments(profile: str) -> None:
    result = _run_node(
        profile,
        """
import { registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const tools = new Map();
registerCapabilityTools({ tools: { register: (row) => tools.set(row.name, row) } }, ['company.workflow']);
const result = await tools.get('company_workflow_validate').execute({ steps: [
  { id: 'algorithm', capability: 'company.algorithm', tool: 'quantum_algorithm_run',
    produces: ['asset_id', 'circuit_id'], arguments: {
      catalog_version: 'cat_fixture', component_version: '1.0',
      algorithm: 'test', parameters: { iterations: 2 } } },
  { id: 'device', capability: 'quantum.device', tool: 'quantum_device_run', needs: ['circuit_id'],
    produces: ['twin_id'], arguments: { shots: 8 } }
] }, {});
console.log(JSON.stringify(result));
""",
        preset="lab" if profile == "company-agent" else "boot",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["steps"][-1]["approval"] == "human"
    assert payload["produces"] == ["asset_id", "circuit_id", "twin_id"]


def test_registered_tool_keeps_full_argument_validation() -> None:
    result = _run_node(
        "company-agent-minimal",
        """
import { registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const tools = [];
registerCapabilityTools({ tools: { register: (row) => tools.push(row) } }, ['company.knowledge']);
await tools[0].execute({ query: 'x'.repeat(1001) }, {});
""",
        preset="boot",
    )
    assert result.returncode != 0
    assert "query must have at most 1000 characters" in result.stderr


def test_device_bridge_waits_for_dsh_approval() -> None:
    result = _run_node(
        "company-agent",
        """
import { authorize, invoke, registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const args = { circuit_id: 'circ_ui_test', shots: 8 };
const preflight = await authorize('quantum_device_run', args);
const beforeApproval = await invoke('quantum_device_run', args);
const tools = [];
registerCapabilityTools({ tools: { register: (row) => tools.push(row) } }, ['quantum.device']);
// This invokes the handler at the DSH post-approval boundary, with no provider configured.
let afterApproval;
try { await tools.find((row) => row.name === 'quantum_device_run').execute(args, {}); }
catch (error) { afterApproval = error.message; }
console.log(JSON.stringify({ preflight, beforeApproval, afterApproval }));
""",
        preset="lab",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["preflight"]["decision"] == "ask"
    assert payload["beforeApproval"]["status"] == "needs_ask"
    assert payload["afterApproval"] == "quantum_device_run: COMPANY_AGENT_DEVICE_INVOKE_URL is not configured"


def test_dsh_schema_projection_keeps_structure_and_strips_unsupported_keywords() -> None:
    program = """
import { dshSchema } from '@unitqc/company-agent-core/runtime';
console.log(JSON.stringify(dshSchema({
  type: 'object',
  required: ['id'],
  properties: {
    id: { type: 'string', pattern: '^asset_.+$', minLength: 1, maxLength: 256 },
    rows: { type: 'array', maxItems: 8, items: { type: 'integer', minimum: 1 } },
  },
  additionalProperties: false,
})));
"""
    result = _run_node("company-agent-minimal", program, preset="boot")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "rows": {"type": "array", "items": {"type": "integer"}},
        },
        "additionalProperties": False,
    }


def test_dsh_schema_projection_accepts_open_object_contracts() -> None:
    program = """
import { dshSchema } from '@unitqc/company-agent-core/runtime';
console.log(JSON.stringify(dshSchema({
  type: 'object',
  properties: {},
  maxProperties: 64,
  additionalProperties: true,
})));
"""
    result = _run_node("company-agent-minimal", program, preset="boot")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }


def test_dsh_schema_projection_rejects_required_without_properties() -> None:
    program = """
import { dshSchema } from '@unitqc/company-agent-core/runtime';
dshSchema({ type: 'object', required: ['id'], additionalProperties: true });
"""
    result = _run_node("company-agent-minimal", program, preset="boot")
    assert result.returncode != 0
    assert "properties must be explicit" in result.stderr


def test_core_runtime_filters_registered_catalog_by_preset() -> None:
    program = (
        "import('@unitqc/company-agent-core/runtime')"
        ".then(m => console.log(JSON.stringify(m.toolCatalog().map(row => row.name))))"
    )
    boot = _run_node("company-agent-minimal", program, preset="boot")
    assert boot.returncode == 0, boot.stderr
    assert json.loads(boot.stdout) == [
        "company_capabilities",
        "company_knowledge_search",
        "company_fetch",
        "company_table_profile",
        "company_workspace_reference",
        "company_workflow_validate",
        "company_analysis_render",
        "company_office_analyze",
        "company_office_create",
        "company_portal_open",
    ]
    sign = _run_node("company-agent", program, preset="sign")
    assert sign.returncode == 0, sign.stderr
    assert json.loads(sign.stdout) == [
        "company_capabilities",
        "company_analysis_render",
        "quantum_asset_get",
        "quantum_asset_metrics",
        "quantum_cloud_devices",
        "quantum_cloud_submit",
        "quantum_cloud_status",
        "quantum_cloud_result",
        "hpc_submit",
        "hpc_script_check",
        "hpc_stage_file",
        "hpc_job_cancel",
        "hpc_dir_create",
        "hpc_file_remove",
        "quantum_device_identity",
        "quantum_device_run",
    ]


def test_capability_registration_allows_known_capability_hidden_by_preset() -> None:
    program = """
import { registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const names = [];
const ctx = { tools: { register: (row) => names.push(row.name) } };
registerCapabilityTools(ctx, ['company.algorithm']);
console.log(JSON.stringify(names));
"""
    result = _run_node("company-agent-minimal", program, preset="boot")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_capability_registration_rejects_unknown_capability() -> None:
    program = """
import { registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const ctx = { tools: { register: () => {} } };
registerCapabilityTools(ctx, ['company.unknown']);
"""
    result = _run_node("company-agent-minimal", program, preset="boot")
    assert result.returncode != 0
    assert "catalog has unknown capabilities" in result.stderr


def test_core_runtime_rejects_relative_pythonpath_override() -> None:
    env = _os_env() | {
        "COMPANY_AGENT_PYTHONPATH": "relative/src",
        "COMPANY_AGENT_PYTHON": "/usr/bin/python3",
        "COMPANY_AGENT_PROFILE": "company-agent-minimal",
        "COMPANY_AGENT_PRESET": "boot",
    }
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import('@unitqc/company-agent-core/runtime').then(m => m.validate('company_capabilities', {}))",
        ],
        cwd=ROOT / "profiles/company-agent-minimal",
        env=env,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "COMPANY_AGENT_PYTHONPATH must be an absolute path" in result.stderr


def test_core_runtime_rejects_relative_python_override() -> None:
    env = _os_env() | {
        "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
        "COMPANY_AGENT_PYTHON": "python3",
        "COMPANY_AGENT_PROFILE": "company-agent-minimal",
        "COMPANY_AGENT_PRESET": "boot",
    }
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import('@unitqc/company-agent-core/runtime').then(m => m.validate('company_capabilities', {}))",
        ],
        cwd=ROOT / "profiles/company-agent-minimal",
        env=env,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "COMPANY_AGENT_PYTHON must be an absolute path" in result.stderr


def test_core_runtime_rejects_non_json_arguments() -> None:
    program = """
import { validate } from '@unitqc/company-agent-core/runtime';
const value = {}; value.self = value;
await validate('company_capabilities', value);
"""
    result = _run_node("company-agent-minimal", program, preset="boot")
    assert result.returncode != 0
    assert "arguments must be JSON serializable" in result.stderr


def test_minimal_runtime_rejects_device_presets() -> None:
    for preset in ("lab", "sign"):
        result = _run_node(
            "company-agent-minimal",
            "import('@unitqc/company-agent-core/runtime').then(m => m.toolCatalog())",
            preset=preset,
        )
        assert result.returncode != 0
        assert f"preset {preset} is not allowed" in result.stderr


def test_core_runtime_requires_explicit_preset() -> None:
    result = _run_node(
        "company-agent-minimal",
        "import('@unitqc/company-agent-core/runtime').then(m => m.toolCatalog())",
    )
    assert result.returncode != 0
    assert "COMPANY_AGENT_PRESET is required" in result.stderr


def test_core_runtime_rejects_unknown_preset() -> None:
    result = _run_node(
        "company-agent-minimal",
        "import('@unitqc/company-agent-core/runtime').then(m => m.toolCatalog())",
        preset="unknown",
    )
    assert result.returncode != 0
    assert "preset unknown is not allowed for profile company-agent-minimal" in result.stderr


@pytest.mark.parametrize("schema", [
    {"type": "string", "format": "uuid"},
    {"type": "object", "properties": None, "additionalProperties": False},
    {"type": "array", "items": None},
    {"type": "string", "oneOf": [{"type": "string"}]},
])
def test_dsh_schema_rejects_unsupported_contracts(schema: dict) -> None:
    result = _run_node(
        "company-agent-minimal",
        "import { dshSchema } from '@unitqc/company-agent-core/runtime'; "
        f"dshSchema({json.dumps(schema)});",
        preset="boot",
    )
    assert result.returncode != 0


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-0", "undefined"])
def test_bridge_rejects_lossy_json_arguments(value: str) -> None:
    result = _run_node(
        "company-agent-minimal",
        "import { validate } from '@unitqc/company-agent-core/runtime'; "
        "await validate('quantum_algorithm_run', { catalog_version: 'cat_fixture', "
        "component_version: '1.0', algorithm: 'fixture', "
        f"parameters: {{ value: {value} }} }});",
        preset="boot",
    )
    assert result.returncode != 0
    assert "arguments must be JSON serializable" in result.stderr


def test_registered_output_render_enforces_short_result_budget() -> None:
    result = _run_node(
        "company-agent-minimal",
        """
import { registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const rows = [];
registerCapabilityTools({ tools: { register: row => rows.push(row) } }, ['company.workflow']);
rows[0].output.render({}, { text: 'x'.repeat(64001) });
""",
        preset="boot",
    )
    assert result.returncode != 0
    assert "rendered result exceeded maximum size" in result.stderr


def test_plugins_have_no_repository_layout_imports() -> None:
    for path in (ROOT / "packages").glob("company-agent-*/src/*.js"):
        text = path.read_text(encoding="utf-8")
        assert "../../../" not in text
        assert "/seams/" not in text
