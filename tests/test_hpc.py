"""compute.hpc capability gates: contract, policy, and south-bound SSH adapter."""

from __future__ import annotations

import base64
import importlib
import json
import shlex
import subprocess
import threading
from http.server import ThreadingHTTPServer

import pytest

from company_agent.capabilities import list_capabilities
from company_agent.catalog import load_providers, load_tools
from company_agent.hpc_ssh import (
    AdapterError,
    handle_request,
    script_exists_result,
    ssh_target,
    status_result,
    submit_result,
)
from company_agent.invoke import invoke
from company_agent.policy import decide

QUEUE_RESULT = {
    "provider": "hpc-slurm-ssh",
    "jobs": [{"slurm_number": "101", "name": "survey", "partition": "gpu",
              "state": "RUNNING", "nodes": "1", "elapsed": "00:10"}],
    "status": "completed",
}
ENVELOPE_PROTOCOL = "company-agent-provider/1.0"
FIXTURE_REQUEST_ID = "req_" + "0" * 32


def test_hpc_contract_roster() -> None:
    tools = load_tools()
    assert {
        "hpc_queue", "hpc_job_status", "hpc_script_check", "hpc_resources",
        "hpc_file_list", "hpc_file_fetch", "hpc_stage_file",
        "hpc_job_cancel", "hpc_dir_create", "hpc_file_remove", "hpc_submit",
    } <= set(tools)
    for name in ("hpc_queue", "hpc_job_status", "hpc_script_check", "hpc_resources",
                 "hpc_file_list", "hpc_file_fetch", "hpc_stage_file", "hpc_submit"):
        row = tools[name]
        assert row["capability"] == "compute.hpc"
        assert row["input_handles"] == []
        assert row["output_handles"] == []
        assert row["parameters"]["additionalProperties"] is False
        assert row["output"]["additionalProperties"] is False
    hpc = next(item for item in list_capabilities() if item.id == "compute.hpc")
    assert hpc.kind == "compute"
    assert hpc.provider == "hpc-slurm-ssh"
    assert hpc.tools == (
        "hpc_queue", "hpc_submit", "hpc_job_status",
        "hpc_script_check", "hpc_resources",
        "hpc_file_list", "hpc_file_fetch", "hpc_stage_file",
        "hpc_job_cancel", "hpc_dir_create", "hpc_file_remove",
    )
    assert hpc.handles == ()
    assert hpc.approval == "human"


def test_compute_hpc_provider_operations_are_bound() -> None:
    providers = {row["id"]: row for row in load_providers()["providers"]}
    assert providers["hpc-slurm-ssh"] == {
        "id": "hpc-slurm-ssh",
        "kind": "compute",
        "env": "COMPANY_AGENT_HPC_INVOKE_URL",
        "token_env": "COMPANY_AGENT_HPC_TOKEN",
        "operations": ["hpc.queue", "hpc.submit", "hpc.job-status", "hpc.script-exists",
                       "hpc.resources", "hpc.file-list", "hpc.file-fetch", "hpc.stage-file",
                       "hpc.job-cancel", "hpc.dir-create", "hpc.file-remove"],
    }


@pytest.mark.parametrize(
    ("preset", "tool", "expected"),
    [
        ("boot", "hpc_queue", "deny"),
        ("boot", "hpc_job_status", "deny"),
        ("boot", "hpc_script_check", "deny"),
        ("boot", "hpc_resources", "deny"),
        ("boot", "hpc_file_list", "deny"),
        ("boot", "hpc_file_fetch", "deny"),
        ("boot", "hpc_stage_file", "deny"),
        ("boot", "hpc_job_cancel", "deny"),
        ("boot", "hpc_dir_create", "deny"),
        ("boot", "hpc_file_remove", "deny"),
        ("boot", "hpc_submit", "deny"),
        ("algo", "hpc_queue", "allow"),
        ("algo", "hpc_job_status", "allow"),
        ("algo", "hpc_resources", "allow"),
        ("algo", "hpc_file_list", "allow"),
        ("algo", "hpc_file_fetch", "allow"),
        ("algo", "hpc_script_check", "deny"),
        ("algo", "hpc_stage_file", "deny"),
        ("algo", "hpc_job_cancel", "deny"),
        ("algo", "hpc_dir_create", "deny"),
        ("algo", "hpc_file_remove", "deny"),
        ("algo", "hpc_submit", "deny"),
        ("lab", "hpc_queue", "allow"),
        ("lab", "hpc_job_status", "allow"),
        ("lab", "hpc_resources", "allow"),
        ("lab", "hpc_file_list", "allow"),
        ("lab", "hpc_file_fetch", "allow"),
        ("lab", "hpc_script_check", "allow"),
        ("lab", "hpc_stage_file", "ask"),
        ("lab", "hpc_job_cancel", "ask"),
        ("lab", "hpc_dir_create", "ask"),
        ("lab", "hpc_file_remove", "ask"),
        ("lab", "hpc_submit", "ask"),
        ("sign", "hpc_queue", "deny"),
        ("sign", "hpc_job_status", "deny"),
        ("sign", "hpc_resources", "deny"),
        ("sign", "hpc_file_list", "deny"),
        ("sign", "hpc_file_fetch", "deny"),
        ("sign", "hpc_script_check", "allow"),
        ("sign", "hpc_stage_file", "ask"),
        ("sign", "hpc_job_cancel", "ask"),
        ("sign", "hpc_dir_create", "ask"),
        ("sign", "hpc_file_remove", "ask"),
        ("sign", "hpc_submit", "ask"),
    ],
)
def test_hpc_policy_decisions_match_contract(preset, tool, expected) -> None:
    assert decide(tool, preset, {}) == expected


def test_hpc_queue_never_carries_scientific_handles() -> None:
    tools = load_tools()
    for name in ("hpc_queue", "hpc_submit"):
        row = tools[name]
        properties = row["output"]["properties"]
        assert not ({"asset_id", "circuit_id", "twin_id"} & set(properties))
    submit = tools["hpc_submit"]
    assert submit["output"]["required"] == ["provider", "slurm_number", "job_name", "state"]
    assert submit["output"]["properties"]["provider"]["const"] == "hpc-slurm-ssh"


def test_hpc_tools_fail_closed_without_provider_environment(monkeypatch) -> None:
    for name in ("COMPANY_AGENT_HPC_INVOKE_URL", "COMPANY_AGENT_HPC_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    result = invoke("hpc_queue", "lab", {})
    assert result.status == "error"
    assert result.payload is None


@pytest.fixture
def stubbed_ssh(monkeypatch):
    """Stub the ssh channel; returns a list capturing every remote command."""

    from company_agent import hpc_ssh

    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        story = getattr(fake_run, "story", {})
        return story.get(
            "result",
            subprocess.CompletedProcess(argv, 0, stdout=story.get("stdout", ""), stderr=""),
        )

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    return fake_run, calls


def test_ssh_target_is_validated(stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    target = ssh_target()
    assert target is not None and target.user == "hpc-user" and target.host == "hpc-login.internal"


def test_queue_result_parses_short_rows(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            ["ssh"], 0,
            stdout="101\tsurvey\tgpu\tRUNNING\t1\t00:10\n102\tmalformed row\t\n"
                   "103\taudit\tcpu\tR\t4\t05:20\n",
            stderr="",
        ),
    )
    result = hpc_ssh.queue_result()
    assert result == {
        "provider": "hpc-slurm-ssh",
        "jobs": [
            {"slurm_number": "101", "name": "survey", "partition": "gpu",
             "state": "RUNNING", "nodes": "1", "elapsed": "00:10"},
            {"slurm_number": "103", "name": "audit", "partition": "cpu",
             "state": "R", "nodes": "4", "elapsed": "05:20"},
        ],
        "status": "completed",
    }


def test_queue_result_fails_closed_on_squeue_failure(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 1, stdout="", stderr="denied"),
    )
    with pytest.raises(AdapterError):
        hpc_ssh.queue_result()
    monkeypatch.setattr(hpc_ssh.subprocess, "run", lambda *_a, **_k: hpc_ssh.SshResult(
        stdout="", stderr="", returncode=-1, timed_out=True))
    with pytest.raises(AdapterError):
        hpc_ssh.queue_result()


def test_submit_result_quotes_remote_command(stubbed_ssh) -> None:
    fake_run, calls = stubbed_ssh
    fake_run.story = {"stdout": "5001\n"}
    result = submit_result({
        "job_name": "oedipus-run-2", "script": "/home/u/runs/r1.sh",
        "partition": "gpu", "nodes": 2, "walltime": "04:00:00",
    })
    assert result["slurm_number"] == "5001"
    assert result["job_name"] == "oedipus-run-2"
    argv = calls[0]
    remote = argv[-1]
    # Only the SSH argv list is spawned locally; the remote command is fully quoted.
    assert argv[:1] == ["ssh"] and "-o" in argv[:4] and "BatchMode=yes" in argv[:4]
    assert remote == ("sbatch --parsable -J oedipus-run-2 -p gpu -N 2 "
                      "-t 04:00:00 /home/u/runs/r1.sh")
    # The quoting survives a strict shell round-trip without reinterpretation.
    field = shlex.split(remote)
    assert field[0:3] == ["sbatch", "--parsable", "-J"] and field[3] == "oedipus-run-2"


def test_submit_result_rejects_invalid_arguments() -> None:
    with pytest.raises(AdapterError):
        submit_result({"job_name": "demo", "script": "/tmp/../etc/x.sh"})
    with pytest.raises(AdapterError):
        submit_result({"job_name": "demo; rm", "script": "/tmp/x.sh"})
    with pytest.raises(AdapterError):
        submit_result({"job_name": "demo", "script": "relative/path.sh"})
    with pytest.raises(AdapterError):
        submit_result({"job_name": "demo", "script": "/tmp/x.sh", "nodes": 65})
    with pytest.raises(AdapterError):
        submit_result({"job_name": "demo", "script": "/tmp/x.sh", "walltime": "4 h"})


def test_job_status_result_parses_queue_row(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            ["ssh"], 0,
            stdout="5010\tcalibrate\tgpu\tRUNNING\t2\t01:30\n",
            stderr="",
        ),
    )
    result = hpc_ssh.status_result({"slurm_number": "5010"})
    assert result == {
        "provider": "hpc-slurm-ssh",
        "slurm_number": "5010",
        "name": "calibrate",
        "partition": "gpu",
        "state": "RUNNING",
        "nodes": "2",
        "elapsed": "01:30",
        "source": "queue",
    }


def test_job_status_falls_back_to_accounting_history(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    responses = [
        subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr=""),
        subprocess.CompletedProcess(["ssh"], 0, stdout="5010|COMPLETED|01:30|calibrate\n"),
    ]

    def fake_run(*_a, **_k):
        return responses.pop(0)

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    result = hpc_ssh.status_result({"slurm_number": "5010"})
    assert result == {
        "provider": "hpc-slurm-ssh",
        "slurm_number": "5010",
        "state": "COMPLETED",
        "elapsed": "01:30",
        "name": "calibrate",
        "source": "history",
    }


def test_job_status_reports_clean_not_found(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr=""),
    )
    result = hpc_ssh.status_result({"slurm_number": "9999"})
    assert result == {
        "provider": "hpc-slurm-ssh",
        "slurm_number": "9999",
        "state": "not_found",
        "source": "none",
    }


def test_job_status_fails_closed_on_sacct_failure(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    responses = [subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr="")]

    def fake_run(*_a, **_k):
        return responses.pop(0) if responses else subprocess.CompletedProcess(
            ["ssh"], 1, stdout="", stderr="sacct unavailable")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    with pytest.raises(AdapterError):
        hpc_ssh.status_result({"slurm_number": "9999"})


def test_job_status_rejects_invalid_arguments() -> None:
    with pytest.raises(AdapterError):
        status_result({"slurm_number": "5010; rm"})
    with pytest.raises(AdapterError):
        status_result({"slurm_number": "5010x"})
    with pytest.raises(AdapterError):
        status_result({})
    with pytest.raises(AdapterError):
        status_result({"slurm_number": "5010", "extra": "field"})


def test_job_status_quotes_remote_commands(stubbed_ssh) -> None:
    fake_run, calls = stubbed_ssh
    # The shared story text has no tab-separated queue fields, so the live
    # queue probe finds nothing and the lookup falls through to accounting.
    fake_run.story = {"stdout": "5010|COMPLETED|01:30|calibrate\n"}
    result = status_result({"slurm_number": "5010"})
    assert result["source"] == "history"
    squeue_command, sacct_command = (argv[-1] for argv in calls)
    assert squeue_command == "squeue -j 5010 -h -o '%.20i\t%.120j\t%.60P\t%.30T\t%.16N\t%.16M'"
    assert sacct_command == "sacct --parsable2 -n -j 5010 -o JobID%28,State%32,Elapsed%16,JobName%120"
    # The arguments survive a strict shell round-trip without reinterpretation.
    field = shlex.split(sacct_command)
    assert field[0] == "sacct" and field[1:] == ["--parsable2", "-n", "-j", "5010", "-o",
                                                "JobID%28,State%32,Elapsed%16,JobName%120"]


def test_script_check_reports_existing_file(stubbed_ssh) -> None:
    fake_run, calls = stubbed_ssh
    result = script_exists_result({"script": "/data/jobs/demo.sh"})
    assert result == {
        "provider": "hpc-slurm-ssh",
        "script": "/data/jobs/demo.sh",
        "exists": True,
    }
    argv = calls[0]
    assert argv[:1] == ["ssh"] and "BatchMode=yes" in argv[:4]
    assert argv[-1] == "test -f /data/jobs/demo.sh"


def test_script_check_reports_missing_file(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 1, stdout="", stderr=""),
    )
    result = hpc_ssh.script_exists_result({"script": "/data/jobs/demo.sh"})
    assert result["exists"] is False


def test_script_check_fails_closed_on_transport_failure(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 255, stdout="", stderr="connect refused"),
    )
    with pytest.raises(AdapterError):
        hpc_ssh.script_exists_result({"script": "/data/jobs/demo.sh"})


def test_script_check_rejects_invalid_arguments() -> None:
    with pytest.raises(AdapterError):
        script_exists_result({"script": "demo.sh"})
    with pytest.raises(AdapterError):
        script_exists_result({"script": "~/jobs/demo.sh"})
    with pytest.raises(AdapterError):
        script_exists_result({"script": "/data/../etc/x.sh"})
    with pytest.raises(AdapterError):
        script_exists_result({"script": "D:\\jobs\\demo.sh"})
    with pytest.raises(AdapterError):
        script_exists_result({})


def test_resources_result_aggregates_partitions(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            ["ssh"], 0,
            stdout="standard*|up|2|allocated|48/16/0/64\n"
                   "standard*|up|4|idle|0/128/0/128\n"
                   "gpu|up|1|mixed|8/0/8/16\n"
                   "malformed line\n"
                   "company-agent-home\t/data/home/hpc-user\n",
            stderr="",
        ),
    )
    result = hpc_ssh.resources_result()
    assert result == {
        "provider": "hpc-slurm-ssh",
        "partitions": [
            {"partition": "standard*", "availability": "up",
             "nodes_total": 6, "nodes_by_state": "allocated=2,idle=4",
             "cores_allocated": 48, "cores_idle": 144, "cores_other": 0, "cores_total": 192},
            {"partition": "gpu", "availability": "up",
             "nodes_total": 1, "nodes_by_state": "mixed=1",
             "cores_allocated": 8, "cores_idle": 0, "cores_other": 8, "cores_total": 16},
        ],
        "staging_root": "/data/home/hpc-user/company_agent",
    }


def test_resources_result_quotes_remote_command(stubbed_ssh) -> None:
    fake_run, calls = stubbed_ssh
    fake_run.story = {"stdout": "company-agent-home\t/data/home/hpc-user\n"}
    hpc_ssh_module = importlib.import_module("company_agent.hpc_ssh")
    result = hpc_ssh_module.resources_result()
    assert result["staging_root"] == "/data/home/hpc-user/company_agent"
    argv = calls[0]
    assert argv[:1] == ["ssh"] and "BatchMode=yes" in argv[:4]
    remote = argv[-1]
    assert remote.startswith("sinfo -h -o '%P|%a|%D|%t|%C'")
    assert "printf 'company-agent-home\\t%s\\n'" in remote
    assert remote.endswith("exit $sinfo_status")


@pytest.mark.parametrize(
    "home_line",
    [
        None,
        "company-agent-home\tdata/home/relative\n",
        "company-agent-home\t/data/home/../escape\n",
        "company-agent-home\t/data/home/hpc-user/\n",
        "company-agent-home\t/\n",
        "company-agent-home\t/home/with space\n",
        "company-agent-home\t/data/home/one\ncompany-agent-home\t/data/home/two\n",
    ],
)
def test_resources_result_fails_closed_without_account_home(home_line, monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    stdout = "gpu|up|1|mixed|8/0/8/16\n" + (home_line if home_line is not None else "")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 0, stdout=stdout, stderr=""),
    )
    with pytest.raises(AdapterError):
        hpc_ssh.resources_result()


def test_resources_result_fails_closed_on_sinfo_failure(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 1, stdout="", stderr="denied"),
    )
    with pytest.raises(AdapterError):
        hpc_ssh.resources_result()
    monkeypatch.setattr(hpc_ssh.subprocess, "run", lambda *_a, **_k: hpc_ssh.SshResult(
        stdout="", stderr="", returncode=-1, timed_out=True))
    with pytest.raises(AdapterError):
        hpc_ssh.resources_result()


def test_kernel_resources_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    fake_run.story = {
        "stdout": "standard*|up|2|idle|0/64/0/64\ncompany-agent-home\t/data/home/hpc-user\n"
    }
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke("hpc_resources", "algo", {})
    assert result.status == "ok", result.error
    assert result.decision == "allow"
    assert result.payload == {
        "provider": "hpc-slurm-ssh",
        "partitions": [
            {"partition": "standard*", "availability": "up",
             "nodes_total": 2, "nodes_by_state": "idle=2",
             "cores_allocated": 0, "cores_idle": 64, "cores_other": 0, "cores_total": 64},
        ],
        "staging_root": "/data/home/hpc-user/company_agent",
    }


def test_kernel_script_check_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke("hpc_script_check", "lab", {"script": "/data/jobs/demo.sh"})
    assert result.status == "ok", result.error
    assert result.decision == "allow"
    assert result.payload == {
        "provider": "hpc-slurm-ssh",
        "script": "/data/jobs/demo.sh",
        "exists": True,
    }


def test_file_list_result_parses_find_rows(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            ["ssh"], 0,
            stdout="512\t1700000000\tjob-1.sh\n102400\t1699000000\tresults.dat\n"
                   "broken row\n1\t1700000000.5\t100\tweird.txt\n",
            stderr="",
        ),
    )
    result = hpc_ssh.file_list_result({"path": "/data/jobs"})
    assert result == {
        "provider": "hpc-slurm-ssh",
        "path": "/data/jobs",
        "entries": [
            {"name": "job-1.sh", "bytes": 512, "mtime": 1700000000},
            {"name": "results.dat", "bytes": 102400, "mtime": 1699000000},
        ],
    }


def test_file_list_result_quotes_remote_command(stubbed_ssh) -> None:
    fake_run, calls = stubbed_ssh
    hpc_ssh_module = importlib.import_module("company_agent.hpc_ssh")
    fake_run.story = {"stdout": ""}
    hpc_ssh_module.file_list_result({"path": "/data/jobs"})
    argv = calls[0]
    assert argv[:1] == ["ssh"] and "BatchMode=yes" in argv[:4]
    remote = argv[-1]
    assert remote.startswith("find /data/jobs -maxdepth 1 -mindepth 1 -type f -printf '")
    assert remote.endswith("' | head -33")
    field = shlex.split(remote)
    assert field[0] == "find" and field[1] == "/data/jobs" and field[-2:] == ["head", "-33"]


def test_file_fetch_result_writes_into_workspace(monkeypatch, tmp_path) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    payload_text = "score: 0.93\nrecords: 8\n"
    encoded = base64.b64encode(payload_text.encode()).decode()
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 0, stdout=encoded, stderr=""),
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    header = base64.b64encode(str(workspace).encode()).decode()
    result = hpc_ssh.file_fetch_result({"path": "/data/jobs/result.txt"}, header)
    assert result == {
        "provider": "hpc-slurm-ssh",
        "gateway_path": "/data/jobs/result.txt",
        "saved_to": "gateway/result.txt",
        "bytes": len(payload_text.encode()),
    }
    saved = workspace / "gateway" / "result.txt"
    assert saved.is_file()
    assert saved.read_text(encoding="utf-8") == payload_text


def test_file_fetch_result_fails_closed_on_missing_remote_file(monkeypatch, tmp_path) -> None:
    """A missing remote path must not masquerade as a zero-byte fetch."""
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        status = 1 if "test -f" in argv[-1] else 0
        return subprocess.CompletedProcess(["ssh"], status, stdout="", stderr="")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    header = base64.b64encode(str(workspace).encode()).decode()
    with pytest.raises(AdapterError):
        hpc_ssh.file_fetch_result({"path": "/data/jobs/gone.txt"}, header)
    assert not (workspace / "gateway").exists()


def test_file_fetch_result_rejects_binary(monkeypatch, tmp_path) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    encoded = base64.b64encode(b"\xff\xfe\x00bad").decode()
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 0, stdout=encoded, stderr=""),
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    header = base64.b64encode(str(workspace).encode()).decode()
    with pytest.raises(AdapterError):
        hpc_ssh.file_fetch_result({"path": "/data/jobs/result.bin"}, header)
    assert not (workspace / "gateway").exists()


def test_file_fetch_result_requires_workspace(monkeypatch, tmp_path) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    with pytest.raises(AdapterError):
        hpc_ssh.file_fetch_result({"path": "/data/jobs/result.txt"}, "")


def test_stage_file_result_creates_and_skips(monkeypatch, tmp_path) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    source = tmp_path / "demo.sh"
    source.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    calls: list[tuple[str, str | None]] = []

    def fake_run(argv, **kwargs):
        remote = argv[-1]
        if remote.startswith("test -f"):
            calls.append((remote, None))
            # First run: target missing; second run: target already exists.
            returncode = 1 if len(calls) == 1 else 0
            return subprocess.CompletedProcess(argv, returncode, stdout="", stderr="")
        calls.append((remote, kwargs.get("input")))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    workspace = tmp_path
    header = base64.b64encode(str(workspace).encode()).decode()
    created = hpc_ssh.stage_file_result(
        {"workspace_path": "demo.sh", "gateway_path": "/data/jobs/demo.sh"}, header)
    assert created == {
        "provider": "hpc-slurm-ssh",
        "gateway_path": "/data/jobs/demo.sh",
        "written": True,
        "mode": "created",
        "bytes": source.stat().st_size,
    }
    assert calls[0][0] == "test -f /data/jobs/demo.sh"
    write_command, stdin_text = calls[1]
    assert write_command == "cat > /data/jobs/demo.sh"
    assert stdin_text == "#!/bin/sh\necho hi\n"
    overwritten = hpc_ssh.stage_file_result(
        {"workspace_path": "demo.sh", "gateway_path": "/data/jobs/demo.sh", "overwrite": True},
        header)
    assert overwritten["mode"] == "overwritten" and overwritten["written"] is True


def test_stage_file_result_skips_existing_without_overwrite(monkeypatch, tmp_path) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    source = tmp_path / "keep.txt"
    source.write_text("keep\n", encoding="utf-8")
    writes: list[str | None] = []

    def fake_run(argv, **kwargs):
        remote = argv[-1]
        if remote.startswith("test -f"):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        writes.append(kwargs.get("input"))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    header = base64.b64encode(str(tmp_path).encode()).decode()
    skipped = hpc_ssh.stage_file_result(
        {"workspace_path": "keep.txt", "gateway_path": "/data/jobs/keep.txt"}, header)
    assert skipped == {
        "provider": "hpc-slurm-ssh",
        "gateway_path": "/data/jobs/keep.txt",
        "written": False,
        "mode": "skipped_exists",
    }
    assert writes == []


def test_stage_file_result_rejects_invalid_sources(monkeypatch, tmp_path) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    header = base64.b64encode(str(tmp_path).encode()).decode()
    with pytest.raises(AdapterError):
        hpc_ssh.stage_file_result({"workspace_path": "missing.sh",
                                   "gateway_path": "/data/jobs/demo.sh"}, header)
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\xff\xfe")
    with pytest.raises(AdapterError):
        hpc_ssh.stage_file_result({"workspace_path": "blob.bin",
                                   "gateway_path": "/data/jobs/blob.bin"}, header)
    outside = tmp_path.parent / "outside.sh"
    outside.write_text("x\n", encoding="utf-8")
    with pytest.raises(AdapterError):
        hpc_ssh.stage_file_result({"workspace_path": str(outside),
                                   "gateway_path": "/data/jobs/x.sh"}, header)


def test_file_list_result_rejects_traversal() -> None:
    hpc_ssh_module = importlib.import_module("company_agent.hpc_ssh")
    with pytest.raises(AdapterError):
        hpc_ssh_module.file_list_result({"path": "/data/../etc"})


def test_kernel_file_list_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    fake_run.story = {"stdout": "512\t1700000000\tjob-1.sh\n"}
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke("hpc_file_list", "algo", {"path": "/data/jobs"})
    assert result.status == "ok", result.error
    assert result.decision == "allow"
    assert result.payload == {
        "provider": "hpc-slurm-ssh",
        "path": "/data/jobs",
        "entries": [{"name": "job-1.sh", "bytes": 512, "mtime": 1700000000}],
    }


def test_kernel_stage_file_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh, tmp_path) -> None:
    fake_run, _ = stubbed_ssh
    # ssh story rc0: test -f sees an existing target, so overwrite must be set.
    fake_run.story = {"stdout": ""}
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "demo.sh").write_bytes(b"#!/bin/sh\necho hi\n")
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(workspace))
    result = invoke(
        "hpc_stage_file", "lab",
        {"workspace_path": "demo.sh", "gateway_path": "/data/jobs/demo.sh", "overwrite": True},
        approved=True,
    )
    assert result.status == "ok"
    assert result.decision == "ask"
    assert result.payload == {
        "provider": "hpc-slurm-ssh",
        "gateway_path": "/data/jobs/demo.sh",
        "written": True,
        "mode": "overwritten",
        "bytes": len(b"#!/bin/sh\necho hi\n"),
    }


def test_job_cancel_result_receipt(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr=""),
    )
    result = hpc_ssh.job_cancel_result({"slurm_number": "5010"})
    assert result == {"provider": "hpc-slurm-ssh", "slurm_number": "5010", "cancelled": True}


def test_job_cancel_result_rejects_invalid_arguments() -> None:
    with pytest.raises(AdapterError):
        hpc_ssh_module = importlib.import_module("company_agent.hpc_ssh")
        hpc_ssh_module.job_cancel_result({"slurm_number": "5010; rm"})


def test_dir_create_result_receipt(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    returns = []

    def fake_run(argv, **_kwargs):
        remote = argv[-1]
        if remote.startswith("test -d"):
            is_first = len(returns) == 0
            returns.append(remote)
            return subprocess.CompletedProcess(argv, 1 if is_first else 0, stdout="", stderr="")
        returns.append(remote)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    created = hpc_ssh.dir_create_result({"path": "/data/jobs/runs"})
    assert created == {"provider": "hpc-slurm-ssh", "path": "/data/jobs/runs",
                       "created": True, "mode": "created"}
    assert returns[0] == "test -d /data/jobs/runs"
    assert returns[1] == "mkdir -p /data/jobs/runs"
    exists = hpc_ssh.dir_create_result({"path": "/data/jobs/runs"})
    assert exists == {"provider": "hpc-slurm-ssh", "path": "/data/jobs/runs",
                      "created": False, "mode": "exists"}


def test_file_remove_result_receipt(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")

    def fake_run(argv, **_kwargs):
        remote = argv[-1]
        if remote.startswith("test -f"):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    removed = hpc_ssh.file_remove_result({"path": "/data/jobs/demo.sh"})
    assert removed == {"provider": "hpc-slurm-ssh", "path": "/data/jobs/demo.sh",
                       "removed": True, "mode": "removed"}
    missing = hpc_ssh.file_remove_result({"path": "/data/jobs/gone.sh"}) if False else None
    del missing


def test_file_remove_result_skips_missing(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    removes: list[str] = []

    def fake_run(argv, **_kwargs):
        remote = argv[-1]
        if remote.startswith("test -f"):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        removes.append(remote)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(hpc_ssh.subprocess, "run", fake_run)
    skipped = hpc_ssh.file_remove_result({"path": "/data/jobs/gone.sh"})
    assert skipped == {"provider": "hpc-slurm-ssh", "path": "/data/jobs/gone.sh",
                       "removed": False, "mode": "skipped_missing"}
    assert removes == []


def test_kernel_job_cancel_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    fake_run.story = {"stdout": ""}
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke("hpc_job_cancel", "lab", {"slurm_number": "5010"}, approved=True)
    assert result.status == "ok", result.error
    assert result.decision == "ask"
    assert result.payload == {"provider": "hpc-slurm-ssh", "slurm_number": "5010", "cancelled": True}


def test_kernel_dir_create_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    # story rc0: test -d sees the directory already there, so the receipt is an
    # honest exists observation; mkdir never runs.
    fake_run.story = {"stdout": ""}
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke("hpc_dir_create", "lab", {"path": "/data/jobs/runs"}, approved=True)
    assert result.status == "ok", result.error
    assert result.decision == "ask"
    assert result.payload == {"provider": "hpc-slurm-ssh", "path": "/data/jobs/runs",
                              "created": False, "mode": "exists"}


def test_adapter_rejects_unknown_operation(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    # Operation-level rejection: unknown operations never reach the SSH bridge.
    with pytest.raises(AdapterError):
        hpc_ssh.operation_result("device.run", {})
    # Envelope-level rejection: unknown operations fail closed as invalid requests.
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    status, payload = handle_request(
        json.dumps({"protocol": ENVELOPE_PROTOCOL, "operation": "device.run",
                    "request_id": FIXTURE_REQUEST_ID, "payload": {}}).encode(),
        "Bearer hpc-token-fixture",
    )
    assert status == 400
    body = json.loads(payload)
    assert body["ok"] is False and body["error"] == "invalid request"


def test_handle_request_requires_target_configuration(monkeypatch) -> None:
    for key in ("COMPANY_AGENT_HPC_USER", "COMPANY_AGENT_HPC_HOST"):
        monkeypatch.delenv(key, raising=False)
    status, payload = handle_request(
        json.dumps({"protocol": ENVELOPE_PROTOCOL, "operation": "hpc.queue",
                    "request_id": FIXTURE_REQUEST_ID, "payload": {}}).encode(),
        None,
    )
    assert status == 503
    body = json.loads(payload)
    assert body["ok"] is False
    assert body["provider"] == "hpc-slurm-ssh"
    assert body["error"] == "hpc gateway is unavailable"


def test_handle_request_requires_bearer_token(monkeypatch) -> None:
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_USER", "hpc-user")
    monkeypatch.setenv("COMPANY_AGENT_HPC_HOST", "hpc-login.internal")
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    monkeypatch.setattr(
        hpc_ssh.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr=""),
    )
    request = json.dumps(
        {"protocol": ENVELOPE_PROTOCOL, "operation": "hpc.queue",
         "request_id": FIXTURE_REQUEST_ID, "payload": {}}
    ).encode()
    status, payload = handle_request(request, "Bearer wrong")
    assert status == 401
    status, payload = handle_request(request, "Bearer hpc-token-fixture")
    assert status == 200


@pytest.fixture
def adapter_with_token(monkeypatch, stubbed_ssh):
    """Serving adapter + stubbed ssh; the kernel invokes it through the envelope.

    The provider contract requires the shared bearer token on both sides, so
    the fixture sets ``COMPANY_AGENT_HPC_TOKEN`` for the kernel and the local
    HTTPS-bridge in the same process.
    """
    from company_agent import hpc_ssh

    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    server = ThreadingHTTPServer(("127.0.0.1", 0), hpc_ssh._Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/invoke"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_kernel_reaches_ssh_adapter_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    fake_run.story = {"stdout": "101\tsurvey\tgpu\tRUNNING\t1\t00:10\n"}
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    result = invoke("hpc_queue", "lab", {})
    assert result.status == "ok", result.error
    assert result.payload == QUEUE_RESULT
    assert result.decision == "allow"


def test_kernel_submit_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    fake_run.story = {"stdout": "5001\n"}
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke(
        "hpc_submit", "lab",
        {"job_name": "demo", "script": "/home/u/runs/r1.sh", "partition": "gpu"},
        approved=True,
    )
    assert result.status == "ok", result.error
    assert result.payload == {
        "provider": "hpc-slurm-ssh", "slurm_number": "5001",
        "job_name": "demo", "partition": "gpu", "state": "pending",
    }


def test_kernel_job_status_end_to_end(adapter_with_token, monkeypatch, stubbed_ssh) -> None:
    fake_run, _ = stubbed_ssh
    fake_run.story = {"stdout": "5010\tcalibrate\tgpu\tRUNNING\t2\t01:30\n"}
    monkeypatch.setenv("COMPANY_AGENT_HPC_INVOKE_URL", adapter_with_token)
    monkeypatch.setenv("COMPANY_AGENT_HPC_TOKEN", "hpc-token-fixture")
    result = invoke("hpc_job_status", "algo", {"slurm_number": "5010"})
    assert result.status == "ok", result.error
    assert result.decision == "allow"
    assert result.payload == {
        "provider": "hpc-slurm-ssh", "slurm_number": "5010",
        "name": "calibrate", "partition": "gpu", "state": "RUNNING",
        "nodes": "2", "elapsed": "01:30", "source": "queue",
    }


def test_hpc_invocation_arguments_take_only_contract_fields() -> None:
    result = invoke("hpc_queue", "lab", {"unexpected": "value"})
    assert result.status == "error"
    assert result.error == "unknown arguments: ['unexpected']"
    result = invoke("hpc_submit", "lab", {"job_name": "demo", "script": "relative.sh"})
    assert result.status == "error"
    assert "script must be an absolute POSIX path" in (result.error or "")
    assert "verify the file first with hpc_script_check" in (result.error or "")
