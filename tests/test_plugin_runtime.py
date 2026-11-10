from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

from company_agent.catalog import load_presets, load_tools

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("company-agent", "company-agent-minimal")


def _os_env() -> dict[str, str]:
    """Hermetic env that still carries OS-critical variables for Node.

    On Windows, replacing the environment wholesale drops ``SystemRoot``,
    and Node aborts at init (``ncrypto::CSPRNG``) without it. The PATH passed
    to the child never affects how ``node`` itself is resolved.
    """

    env = {"PATH": os.environ.get("PATH", "")}
    for name in (
        "SystemRoot", "windir", "SYSTEMDRIVE", "COMPUTERNAME",
        "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH",
    ):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _run_node(
    profile: str,
    program: str,
    *,
    preset: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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
    if extra_env:
        env.update(extra_env)
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
        ("company-agent", "lab", ["hpc_submit", "hpc_job_status"]),
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
    minimal_text = (ROOT / "profiles/company-agent-minimal/cordis.patch.yml").read_text(encoding="utf-8")
    minimal_manifest = (ROOT / "profiles/company-agent-minimal/package.json").read_text(encoding="utf-8")
    for name in ("company-agent-quantum", "company-agent-hpc", "company-agent-plan", "company-agent-research"):
        assert name not in minimal_text
        assert name not in minimal_manifest


def test_latex_plugin_registers_preset_visible_company_latex_tools_only() -> None:
    # model_tools hides LaTeX from the model. Host invoke still sees the visible set.
    register_program = """
import('@unitqc/company-agent-latex').then(async (plugin) => {
  const names = [];
  plugin.apply({ tools: { register: (row) => names.push(row.name) } });
  console.log(JSON.stringify(names));
});
"""
    for profile, preset, expected in (
        ("company-agent", "lab", []),
        ("company-agent", "algo", []),
        ("company-agent", "sign", []),
        ("company-agent", "boot", []),
        ("company-agent-minimal", "algo", []),
        ("company-agent-minimal", "boot", []),
    ):
        result = _run_node(profile, register_program, preset=preset)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == expected


def test_literature_plugin_registers_preset_visible_tools_only() -> None:
    register_program = """
import('@unitqc/company-agent-literature').then(async (plugin) => {
  const names = [];
  plugin.apply({ tools: { register: (row) => names.push(row.name) } });
  console.log(JSON.stringify(names));
});
"""
    lab = [
        "company_literature_search", "company_literature_fetch",
        "company_literature_index", "company_literature_draft_card",
    ]
    algo = ["company_literature_search", "company_literature_index", "company_literature_draft_card"]
    for profile, preset, expected in (
        ("company-agent", "lab", lab),
        ("company-agent", "algo", algo),
        ("company-agent", "boot", []),
        ("company-agent", "sign", []),
        ("company-agent-minimal", "algo", algo),
        ("company-agent-minimal", "boot", []),
    ):
        result = _run_node(profile, register_program, preset=preset)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == expected


def test_seat_plugin_runs_literature_and_scale_handoff(tmp_path: Path) -> None:
    """The DSH tool handler is what the seat calls. Literature uses the session directory."""
    import shutil

    from company_agent.literature_card import draft_scale_card

    workspace = tmp_path / "seat"
    workspace.mkdir()
    shutil.copytree(ROOT / "tests" / "fixtures" / "literature", workspace / "paper")
    (workspace / "search.json").write_text(
        json.dumps({"records": [{"paper_id": "demo1", "source": "arxiv", "year": 2024}]}),
        encoding="utf-8",
    )
    local = {
        "tenant_id": "team-a",
        "experiment_id": "exp-local",
        "task_id": "task-local",
        "project_id": "proj-1",
        "hypothesis": "warmup lowers validation loss",
        "falsifier": "the metric does not improve",
        "baseline_name": "recorded",
        "baseline_source": "internal",
        "baseline_metric": 1.0,
        "baseline_reproduced": True,
        "baseline_train_time_seconds": 3600,
        "changed_path": "src/train/scheduler.py",
        "primary_metric": "val_loss",
        "direction": "minimize",
        "resource_type": "cpu",
        "max_cost": 1,
        "max_attempts": 1,
        "idempotency_key": "local-1",
    }
    draft = draft_scale_card(
        local,
        experiment_id="exp-scale",
        idempotency_key="scale-1",
        hypothesis="more nodes keep the same validation loss",
        falsifier="the metric moves outside tolerance",
    )
    human = {**draft, "baseline_reproduced": True}
    program = """
import { markApprovalCard, registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const tools = new Map();
registerCapabilityTools({ tools: { register: (row) => tools.set(row.name, row) } },
  ['company.literature', 'company.research']);
const workspace = process.env.PROBE_WORKSPACE;
const seated = { agent: { id: 'seat-probe', session: { header: { id: 'seat-probe', cwd: workspace } } } };
let missing = '';
try {
  await tools.get('company_literature_search').execute(
    { query: 'synthetic source', fixture: 'search.json' }, {});
} catch (error) {
  missing = String(error.message || error);
}
const search = await tools.get('company_literature_search').execute(
  { query: 'synthetic source', fixture: 'search.json' }, seated);
const fetched = await tools.get('company_literature_fetch').execute(
  { paper_id: 'demo1', fixture: 'paper' }, seated);
const indexed = await tools.get('company_literature_index').execute(
  { paper_id: 'demo1' }, seated);
const compiled = await tools.get('company_research_compile').execute(
  JSON.parse(process.env.PROBE_COMPILE), seated);
markApprovalCard(seated);
const ran = await tools.get('company_research_run').execute(
  JSON.parse(process.env.PROBE_RUN), seated);
console.log(JSON.stringify({ missing, search, fetched, indexed, compiled, ran }));
"""
    result = _run_node(
        "company-agent",
        program,
        preset="lab",
        extra_env={
            "PROBE_WORKSPACE": str(workspace),
            "PROBE_COMPILE": json.dumps(
                {key: value for key, value in human.items() if key != "idempotency_key"},
            ),
            "PROBE_RUN": json.dumps(human),
            "COMPANY_AGENT_RESEARCH_STATE": str(tmp_path / "clock"),
            "COMPANY_AGENT_WORK_ITEM_DB": str(tmp_path / "work.sqlite3"),
        },
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "company_literature_search" in payload["missing"]
    assert payload["search"]["exhaustive"] is False
    assert payload["search"]["paper_ids"] == ["demo1"]
    assert payload["fetched"]["paper_id"] == "demo1"
    assert payload["indexed"]["clock_admitted"] is False
    assert payload["indexed"]["platform_metric_eligible"] is False
    assert "\\approx" not in json.dumps(payload["indexed"])
    assert payload["compiled"]["approval_required"] is True
    assert payload["ran"]["next_tool"] == "hpc_submit"
    assert payload["ran"]["approval_still_required"] is True
    assert "baseline_train_time_seconds" not in draft


def test_plugins_import_from_clean_profile_dependency_graph() -> None:
    expected = {
        "company-agent": ("policy", "core", "quantum", "hpc", "device", "latex", "office", "plan", "research", "literature"),
        "company-agent-minimal": ("policy", "core", "latex", "office", "literature"),
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
    assert len(tools) == 25
    assert "company_shell" not in {row["name"] for row in tools}
    assert "quantum_algorithm_catalog" in {row["name"] for row in tools}
    assert tools[0]["name"] == "company_session_status"
    # The lab catalog follows the preset model_tools order.
    assert tools[-1]["name"] == "company_dingtalk_reply"
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
    assert 'await invoke(name, args, approved, exec?.signal' in runtime
    assert 'decision === "ask" && approvalCardShown(exec)' in runtime
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
    assert len(payload["capabilities"]["capabilities"]) == 16
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
  'company.latex', 'company.office', 'company.plan', 'company.portal', 'company.research',
  'company.literature', 'company.dingtalk']);
console.log(JSON.stringify(rows));
"""
    result = _run_node("company-agent", program, preset="lab")
    assert result.returncode == 0, result.stderr
    registered = {row["name"]: row for row in json.loads(result.stdout)}
    contracts = load_tools()
    assert "company_shell" not in contracts
    assert "company_shell" not in registered
    assert set(registered) == set(load_presets()["presets"]["lab"]["model_tools"])
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

    for name, row in registered.items():
        contract = contracts[name]
        assert row["parameters"] == projection(contract["parameters"])
        assert row["output"] == projection(contract["output"])


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
import { authorize, invoke, markApprovalCard, registerCapabilityTools } from '@unitqc/company-agent-core/runtime';
const args = { circuit_id: 'circ_ui_test', shots: 8 };
const preflight = await authorize('quantum_device_run', args);
const beforeApproval = await invoke('quantum_device_run', args);
const tools = [];
registerCapabilityTools({ tools: { register: (row) => tools.push(row) } }, ['quantum.device']);
// This invokes the handler at the DSH post-approval boundary, with no provider configured.
const approved = {};
markApprovalCard(approved);
let afterApproval;
try { await tools.find((row) => row.name === 'quantum_device_run').execute(args, approved); }
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
    ]
    sign = _run_node("company-agent", program, preset="sign")
    assert sign.returncode == 0, sign.stderr
    assert json.loads(sign.stdout) == [
        "company_capabilities",
        "company_session_status",
        "company_grant_open",
        "company_analysis_render",
        "quantum_asset_get",
        "quantum_asset_metrics",
        "quantum_cloud_devices",
        "quantum_cloud_submit",
        "quantum_cloud_status",
        "quantum_cloud_result",
        "quantum_cloud_result_page",
        "hpc_submit",
        "hpc_script_check",
        "hpc_stage_file",
        "hpc_job_cancel",
        "hpc_dir_create",
        "hpc_file_remove",
        "quantum_device_identity",
        "quantum_device_run",
        "company_work_item",
        "company_sign_receipt",
        "quantum_device_window",
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
rows[0].output.render({}, { text: 'x'.repeat(140000) });
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
