from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _policy_program() -> str:
    return """
import { apply, policyDecision } from '@unitqc/company-agent-policy';
const listeners = [];
const ctx = {
  on(name, listener) { if (name === 'tools/pre-execute') listeners.push(listener); },
  tools: {},
};
apply(ctx);
const gate = listeners[0];
const downstream = { kind: 'allow', source: 'dsh' };
let thrownProceeded = false;
const run = async (name, args = {}) => await gate(
  { name, arguments: args },
  async () => downstream,
);
console.log(JSON.stringify({
  native: await run('bash', { command: 'true' }),
  unknownCompany: await run('company_unknown', {}),
  algorithm: await run('quantum_algorithm_run', {
    algorithm: 'vqe', catalog_version: 'cat_fixture', component_version: '1.0' }),
  invalidDevice: await run('quantum_device_run', { circuit_id: 'asset_wrong', shots: 8 }),
  device: await run('quantum_device_run', { circuit_id: 'circ_x', shots: 8 }),
  stage: await run('hpc_stage_file', { workspace_path: 'probe.sh', gateway_path: '/data/jobs/probe.sh' }),
  cancel: await run('hpc_job_cancel', { slurm_number: '4242' }),
  dir: await run('hpc_dir_create', { path: '/data/jobs/probe' }),
  remove: await run('hpc_file_remove', { path: '/data/jobs/probe.sh' }),
  cloud: await run('quantum_cloud_submit', { program_path: 'a.qasm3', target: 'qiskit-sim', shots: 100 }),
  latexEdit: await run('company_latex_edit', { project: 'probe', path: 'sections/method.tex',
    base_version: 'sha256:' + '0'.repeat(64), edits: [{ quote: 'abcdefgh', replacement: 'X' }] }),
  latexBatch: await run('company_latex_batch_edit', { project: 'probe', files: [
    { path: 'sections/method.tex', base_version: 'sha256:' + '0'.repeat(64),
      edits: [{ quote: 'abcdefgh', replacement: 'X' }] },
  ] }),
  latexRevert: await run('company_latex_revert', { project: 'probe', target: 'checkpoint-1' }),
  latexPush: await run('company_latex_push',
    { project: 'probe', repo: 'team-a/probe', message: 'probe push' }),
  directNative: await policyDecision('bash', {}),
  thrown: await gate(
    { name: 'quantum_device_run', arguments: { circuit_id: 'circ_x', shots: Number.NaN } },
    async () => { thrownProceeded = true; return downstream; },
  ),
  thrownProceeded,
}));
"""


def test_policy_plugin_scopes_company_contract_without_blocking_dsh_tools() -> None:
    env = os.environ.copy()
    env["COMPANY_AGENT_PYTHON"] = sys.executable
    env["COMPANY_AGENT_PYTHONPATH"] = str(ROOT / "src")
    env["COMPANY_AGENT_PROFILE"] = "company-agent"
    env["COMPANY_AGENT_PRESET"] = "lab"
    result = subprocess.run(
        ["node", "--input-type=module", "-e", _policy_program()],
        cwd=ROOT / "profiles/company-agent-minimal",
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["native"] == {"kind": "allow", "source": "dsh"}
    assert payload["directNative"] is None
    assert payload["unknownCompany"] == {"kind": "deny", "reason": "unknown Company Agent tool"}
    assert payload["algorithm"] == {"kind": "allow", "source": "dsh"}
    assert payload["invalidDevice"] == {
        "kind": "deny",
        "reason": "circuit_id has an invalid format",
    }
    assert payload["device"] == {
        "kind": "ask",
        "reason": (
            "Company Agent device execution approval: provider=ionstack-twinrun; "
            "circuit_id=circ_x; shots=8; "
            "subject=circuit:circ_x; limit=shots:8; handoff=no"
        ),
    }
    assert payload["stage"] == {
        "kind": "ask",
        "reason": (
            "Company Agent HPC file upload approval: provider=hpc-slurm-ssh; "
            "gateway_path=/data/jobs/probe.sh; workspace_path=probe.sh"
        ),
    }
    assert payload["cancel"] == {
        "kind": "ask",
        "reason": "Company Agent HPC job cancel approval: provider=hpc-slurm-ssh; slurm_number=4242",
    }
    assert payload["dir"] == {
        "kind": "ask",
        "reason": "Company Agent HPC directory create approval: provider=hpc-slurm-ssh; "
                  "path=/data/jobs/probe",
    }
    assert payload["remove"] == {
        "kind": "ask",
        "reason": "Company Agent HPC file remove approval: provider=hpc-slurm-ssh; "
                  "path=/data/jobs/probe.sh",
    }
    assert payload["cloud"] == {
        "kind": "ask",
        "reason": (
            "Company Agent cloud simulator submission approval: provider=uqc-cloud; "
            "program_path=a.qasm3; target=qiskit-sim; shots=100; "
            "subject=unset; limit=shots:100; handoff=no"
        ),
    }
    assert payload["latexEdit"] == {
        "kind": "ask",
        "reason": (
            "Company Agent latex edit approval: provider=company-latex; "
            "project=probe; path=sections/method.tex"
        ),
    }
    assert payload["latexBatch"] == {
        "kind": "ask",
        "reason": (
            "Company Agent latex batch edit approval: provider=company-latex; "
            "project=probe; files=1"
        ),
    }
    assert payload["latexRevert"] == {
        "kind": "ask",
        "reason": (
            "Company Agent latex revert approval: provider=company-latex; "
            "project=probe; target=checkpoint-1"
        ),
    }
    assert payload["latexPush"] == {
        "kind": "ask",
        "reason": "Company Agent latex push approval: provider=company-latex; "
                  "project=probe; repo=team-a/probe",
    }
    assert payload["thrown"] == {"kind": "deny", "reason": "company-agent-policy"}
    assert payload["thrownProceeded"] is False
