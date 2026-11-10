"""Session grants, jailed local commands, and longer scientific pages."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from company_agent import budget, cloud
from company_agent.cloud_results import read_page, store_table
from company_agent.grants import _locked, _path, grant_view
from company_agent.hpc_ssh import (
    AdapterError,
    _validated_path_argument,
    _validated_script_arguments,
    _validated_submit_arguments,
)
from company_agent.invoke import invoke
from company_agent.shell_run import ShellError, run as run_shell
from company_agent.latex_workspace import _engine_log_errors
from company_agent.policy import decide
from company_agent.providers import ProviderClient, ProviderError
from company_agent.sanitize import has_forbidden_output

ROOT = Path(__file__).resolve().parents[1]


def test_grant_covers_one_session_then_returns_to_ask(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:grant-session")
    opened = invoke(
        "company_grant_open",
        "lab",
        {
            "tools": ["hpc_job_cancel", "quantum_device_run", "hpc_submit", "quantum_cloud_submit"],
            "max_calls": 1,
            "ttl_seconds": 60,
            "subject": {
                "kind": "experiment",
                "id": "exp-grant",
                "resource": "hpc",
                "limit_kind": "node_hours",
                "limit": 1,
            },
        },
        approved=True,
    )
    assert opened.status == "ok"
    assert opened.payload["max_calls"] == 1
    assert decide("hpc_job_cancel", "lab", {}) == "allow"
    assert decide("quantum_device_run", "boot", {}) == "deny"
    assert decide("hpc_submit", "algo", {}) == "deny"
    assert decide("quantum_cloud_submit", "boot", {}) == "deny"
    consumed = invoke("hpc_job_cancel", "lab", {"slurm_number": "12"})
    assert consumed.decision == "allow"
    assert decide("hpc_job_cancel", "lab", {}) == "ask"
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:other-session")
    assert decide("quantum_device_run", "lab", {}) == "ask"


def test_budget_refusal_does_not_spend_a_grant(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:grant-budget")
    opened = invoke(
        "company_grant_open",
        "lab",
        {"tools": ["hpc_job_cancel"], "max_calls": 1, "ttl_seconds": 60},
        approved=True,
    )
    assert opened.status == "ok"

    def refuse(tool, wait=False):
        raise budget.BudgetError("over budget")

    monkeypatch.setattr(budget, "precheck", refuse)
    result = invoke("hpc_job_cancel", "lab", {"slurm_number": "12"})
    assert result.status == "error"
    remaining = {row["name"]: row["remaining"] for row in grant_view()["tools"]}
    assert remaining["hpc_job_cancel"] == 1


def test_grant_lock_releases_only_its_own_token(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:grant-lock")
    path = _path("dsh:grant-lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    lock.write_bytes(b"other-process")
    stale = time.time() - 30
    os.utime(lock, (stale, stale))
    with _locked(path):
        assert lock.read_bytes() != b"other-process"
    assert not lock.exists()


def test_unmarked_ask_is_not_an_approval() -> None:
    runtime = (ROOT / "packages/company-agent-core/src/runtime.js").read_text(encoding="utf-8")
    policy = (ROOT / "packages/company-agent-policy/src/index.js").read_text(encoding="utf-8")
    assert 'const approved = decision === "ask" && approvalCardShown(exec);' in runtime
    assert "markApprovalCard(exec)" in policy
    assert "clearApprovalCard(exec)" in policy
    program = """
import { approvalCardShown, clearApprovalCard, markApprovalCard } from "@unitqc/company-agent-core/runtime";
const exec = { name: "hpc_submit" };
clearApprovalCard(exec);
if (approvalCardShown(exec)) throw new Error("marked before a card");
const approvedWithoutCard = approvalCardShown(exec) && true;
if (approvedWithoutCard) throw new Error("ask without a card was approved");
markApprovalCard(exec);
if (!approvalCardShown(exec)) throw new Error("card was not marked");
if (approvalCardShown({ name: "hpc_submit" })) throw new Error("card mark leaked");
clearApprovalCard(exec);
if (approvalCardShown(exec)) throw new Error("card mark survived");
console.log("ok");
"""
    env = {"PATH": os.environ.get("PATH", "")}
    for name in ("SystemRoot", "windir", "SYSTEMDRIVE"):
        if name in os.environ:
            env[name] = os.environ[name]
    result = subprocess.run(
        ["node", "--input-type=module", "-e", program],
        cwd=ROOT / "profiles" / "company-agent",
        env=env,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_shell_allowlist_stays_inside_the_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("COMPANY_AGENT_TOKEN", "super-secret-value")
    monkeypatch.setenv("SSH_AUTH_SOCK", "secret-agent-socket")
    script = tmp_path / "show.py"
    script.write_text(
        "import os\n"
        "print(os.environ.get('COMPANY_AGENT_TOKEN', ''))\n"
        "print(os.environ.get('SSH_AUTH_SOCK', ''))\n"
        "print('ran')\n",
        encoding="utf-8",
    )
    ran = run_shell({"argv": ["python", "show.py"], "timeout_seconds": 20})
    assert ran["ok"] is True
    assert "ran" in ran["stdout"]
    assert "super-secret-value" not in ran["stdout"]
    assert "secret-agent-socket" not in ran["stdout"]
    for argv in (
        ["python", "-c", "print(1)"],
        ["python", "-cprint(1)"],
        ["node", "--eval=console.log(1)"],
        ["npm", "run", "test", "--prefix", "pkg"],
        ["pytest", "-c", "pytest.ini"],
        ["git", "diff", "--no-index", "a.txt", "b.txt"],
        ["git", "push"],
        ["curl", "https://example.test"],
    ):
        with pytest.raises(ShellError, match="not allowed"):
            run_shell({"argv": argv})
    with pytest.raises(ShellError, match="refused"):
        run_shell({"argv": ["python", "C:/outside.py"]})
    for preset in ("boot", "lab", "algo", "sign"):
        assert decide("company_shell", preset, {}) == "deny"
    assert "tool-bash" not in (ROOT / "profiles/company-agent/cordis.patch.yml").read_text(encoding="utf-8")
    assert "tool-pwsh" not in (ROOT / "profiles/company-agent/cordis.patch.yml").read_text(encoding="utf-8")


def test_forbidden_result_keys_still_fail() -> None:
    for key in ("bitstrings", "cal", "shuttle", "pauli_terms", "circuit_body", "secret", "counts_full"):
        assert has_forbidden_output({key: "x"})
    assert has_forbidden_output({"summary": {"circuit": "OPENQASM 3.0; qubit q;"}})


def test_cloud_result_page_reads_only_one_window(tmp_path, monkeypatch) -> None:
    items = [
        {"name": f"p_{index}", "kind": "probability", "unit": "dimensionless", "value": 0.01}
        for index in range(40)
    ]
    relative = store_table(str(tmp_path), "task-1", 1000, items)
    digest = hashlib.sha256(b"task-1").hexdigest()
    assert relative == f".company-agent/results/{digest}.json"
    assert json.loads((tmp_path / relative).read_text(encoding="utf-8"))["cloud_task"] == "task-1"
    page = read_page(str(tmp_path), "task-1", 0, 32)
    assert page["shots"] == 1000
    assert len(page["items"]) == 32
    assert page["omitted_states"] == 8
    assert "bitstrings" not in json.dumps(page)
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    shown = invoke("quantum_cloud_result_page", "lab", {"cloud_task": "task-1", "offset": 32, "limit": 16})
    assert shown.status == "ok"
    assert len(shown.payload["items"]) == 8
    assert shown.payload["omitted_states"] == 0


def test_cloud_task_ids_do_not_share_a_probability_file(tmp_path) -> None:
    store_table(str(tmp_path), "a.b", 10, [])
    store_table(str(tmp_path), "a_b", 10, [])
    dotted = read_page(str(tmp_path), "a.b", 0, 1)
    underscored = read_page(str(tmp_path), "a_b", 0, 1)
    assert dotted["artifact_path"] != underscored["artifact_path"]
    assert dotted["cloud_task"] == "a.b"
    assert underscored["cloud_task"] == "a_b"
    assert (tmp_path / dotted["artifact_path"]).is_file()
    assert (tmp_path / underscored["artifact_path"]).is_file()


def test_cloud_result_writes_the_workspace_table(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_INVOKE_URL", "http://127.0.0.1:9/invoke")
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    captured = {}

    def opener(request, timeout=None):
        captured["workspace"] = request.headers.get("X-company-workspace")
        raise TimeoutError("stop before the network")

    monkeypatch.setattr("company_agent.providers._OPENER.open", opener)
    client = ProviderClient(
        "cloud",
        "COMPANY_AGENT_CLOUD_INVOKE_URL",
        "uqc-cloud",
        token_env="COMPANY_AGENT_CLOUD_TOKEN",
    )
    with pytest.raises(ProviderError):
        client.invoke("cloud.result", {"cloud_task": "task-1"})
    assert base64.urlsafe_b64decode(captured["workspace"]) == str(tmp_path).encode()

    def worker(operation, payload):
        return {
            "provider": "uqc-cloud",
            "cloud_task": payload["cloud_task"],
            "state": "completed",
            "summary": {
                "status": "completed",
                "shots": 100,
                "metrics": {
                    "schema_version": "scientific-metrics/1.0",
                    "items": [{"name": "p_0", "kind": "probability", "unit": "dimensionless", "value": 1.0}],
                },
            },
        }

    monkeypatch.setattr(cloud, "worker", worker)
    body = json.dumps({
        "protocol": "company-agent-provider/1.0",
        "operation": "cloud.result",
        "request_id": "req_" + "0" * 32,
        "payload": {"cloud_task": "a.b"},
    }).encode()
    encoded = base64.urlsafe_b64encode(str(tmp_path).encode()).decode()
    status, raw = cloud.handle_request(body, "Bearer cloud-fixture", encoded)
    assert status == 200
    value = json.loads(raw)
    relative = value["result"]["summary"]["artifact_path"]
    stored = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    assert stored["cloud_task"] == "a.b"
    assert (tmp_path / relative).is_file()


def test_session_status_names_missing_configuration_without_values(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:status-session")
    monkeypatch.setenv("COMPANY_AGENT_GITLAB_TOKEN", "secret-token")
    monkeypatch.delenv("COMPANY_AGENT_GITLAB_URL", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_SIMULATOR_INVOKE_URL", raising=False)
    result = invoke("company_session_status", "algo", {})
    assert result.status == "ok"
    assert result.payload["preset"] == "algo"
    assert result.payload["executor"] in {"stub", "local", "handoff", "unset"}
    assert "COMPANY_AGENT_GITLAB_URL" in result.payload["missing_env"]
    assert "COMPANY_AGENT_SIMULATOR_INVOKE_URL" in result.payload["missing_env"]
    assert "secret-token" not in json.dumps(result.payload)


def test_hpc_path_error_names_the_staging_prefix() -> None:
    with pytest.raises(AdapterError, match=r"staging_root prefix is .*/company_agent"):
        _validated_path_argument({"path": "relative"}, "path")
    with pytest.raises(AdapterError, match=r"invalid submit arguments; staging_root prefix is"):
        _validated_submit_arguments({"job_name": "job", "script": "relative"})
    with pytest.raises(AdapterError, match=r"invalid script arguments; staging_root prefix is"):
        _validated_script_arguments({"script": "relative"}, "script")


def test_latex_log_keeps_more_than_eight_errors() -> None:
    text = "\n".join(f"main.tex:{index}: undefined control sequence" for index in range(1, 41))
    rows = _engine_log_errors(text)
    assert len(rows) == 32


def test_desktop_menu_uses_the_standard_preset() -> None:
    text = (ROOT / "desktop/profile/cordis.patch.yml").read_text(encoding="utf-8")
    assert "default: standard" in text
    assert "- id: preset-standard\n  disabled: true" not in text
    for name in ("preset-ptc", "preset-minimal", "preset-cordis", "preset-company-agent"):
        assert f"- id: {name}\n  disabled: true" in text
    for name in ("tool-fs", "tool-fs-search", "tool-web", "tool-todo", "tool-present", "tool-skill"):
        assert f"- id: {name}\n" not in text
