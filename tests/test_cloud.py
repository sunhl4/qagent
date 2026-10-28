"""Cloud SDK boundary, artifact, envelope and approval regression gates."""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from company_agent import cloud, cloud_worker
from company_agent.invoke import invoke
from company_agent.policy import decide


@pytest.mark.parametrize("preset,expected", [("boot", "deny"), ("algo", "deny"),
                                               ("lab", "ask"), ("sign", "ask")])
def test_submission_is_always_human_approved(preset, expected):
    assert decide("quantum_cloud_submit", preset, {}) == expected
    result = invoke("quantum_cloud_submit", preset,
                    {"program_path": "test.qasm", "target": "sim-fixture", "shots": 100})
    assert result.status == ("needs_ask" if expected == "ask" else "denied")


def test_workspace_artifact_is_bounded_and_regular(tmp_path, make_symlink):
    program = 'OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\n'
    (tmp_path / "test.qasm").write_text(program)
    assert cloud.read_program("test.qasm", str(tmp_path)) == program
    assert cloud.read_program(str(tmp_path / "test.qasm"), str(tmp_path)) == program
    make_symlink(tmp_path / "test.qasm", tmp_path / "link.qasm")
    make_symlink(tmp_path, tmp_path / "dir", target_is_directory=True)
    for candidate in ("../test.qasm", "/etc/passwd", "link.qasm", "dir/test.qasm", "test.txt"):
        with pytest.raises((ValueError, OSError)):
            cloud.read_program(candidate, str(tmp_path))
    for text in ("not a program", "OPENQASM 3.0;" + " " * 64000,
                 'OPENQASM 3.0; include "/etc/passwd";'):
        (tmp_path / "test.qasm").write_text(text)
        with pytest.raises(ValueError):
            cloud.read_program("test.qasm", str(tmp_path))


def test_cloud_gateway_fails_closed_without_bearer(monkeypatch):
    monkeypatch.delenv("COMPANY_AGENT_CLOUD_TOKEN", raising=False)
    assert cloud.handle_request(b"{}", None)[0] == 401
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")
    assert cloud.handle_request(b"{}", "Bearer wrong")[0] == 401


def request(operation="cloud.devices", payload=None):
    return json.dumps({"protocol": "company-agent-provider/1.0", "operation": operation,
                       "request_id": "req_" + "0" * 32, "payload": payload or {}}).encode()


def test_gateway_requires_exact_envelope(monkeypatch):
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")
    for body in (b'{"protocol":1,"protocol":2}', b"NaN", b"[]", b"{}",
                 request("device.run"), request().replace(b'"payload":', b'"extra":1,"payload":')):
        status, _ = cloud.handle_request(body, "Bearer cloud-fixture")
        assert status == 400


def test_gateway_returns_short_real_device_metadata(monkeypatch):
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")
    result = {"provider": "uqc-cloud", "devices": []}
    monkeypatch.setattr(cloud, "worker", lambda *_args: result)
    status, raw = cloud.handle_request(request(), "Bearer cloud-fixture")
    value = json.loads(raw)
    assert status == 200 and value["ok"] is True
    assert value["request_id"] == "req_" + "0" * 32
    assert value["result"] == result


def test_submit_reads_artifact_without_returning_body(monkeypatch, tmp_path):
    (tmp_path / "a.qasm").write_text("OPENQASM 3.0; qubit[1] q;")
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")
    calls = []

    def worker(operation, payload):
        calls.append((operation, payload))
        return {"provider": "uqc-cloud", "cloud_task": "task-fixture", "target": "sim-fixture",
                "state": "submitted", "shots": 100}

    monkeypatch.setattr(cloud, "worker", worker)
    payload = {"program_path": "a.qasm", "target": "sim-fixture", "shots": 100}
    workspace = base64.urlsafe_b64encode(str(tmp_path).encode()).decode()
    _, raw = cloud.handle_request(request("cloud.submit", payload), "Bearer cloud-fixture", workspace)
    assert json.loads(raw)["ok"] is True
    assert "OPENQASM" not in raw.decode() and "program_path" not in calls[0][1]
    assert calls[0][1]["program"].startswith("OPENQASM")
    payload["shots"] = 101
    _, raw = cloud.handle_request(request("cloud.submit", payload), "Bearer cloud-fixture", workspace)
    assert json.loads(raw)["ok"] is False
    assert len(calls) == 1


def test_sdk_result_metrics_normalizes_histogram():
    histogram = [[0, 480], [1, 520], [0, 0]]
    shots, items = cloud_worker.result_metrics(
        [{"datasets": {"computational_basis_histogram": histogram}}])
    assert shots == 1000
    assert items == [
        {"name": "p_1", "kind": "probability", "unit": "dimensionless", "value": 0.52},
        {"name": "p_0", "kind": "probability", "unit": "dimensionless", "value": 0.48},
    ]
    # One state also keeps a full-width label; zero-count rows never appear.
    assert cloud_worker.result_metrics([{"datasets": {"computational_basis_histogram": [[7, 1]]}}]) == (
        1, [{"name": "p_111", "kind": "probability", "unit": "dimensionless", "value": 1.0}]
    )


@pytest.mark.parametrize("raw", [
    [], "flat", [{"x": 1}], [{"datasets": {}}],
    [{"datasets": {"computational_basis_histogram": "no"}}],
    [{"datasets": {"computational_basis_histogram": [[0, 1], [2.5, 2]]}}],
    [{"datasets": {"computational_basis_histogram": [["0", 1]]}}],
    [{"datasets": {"computational_basis_histogram": [[0, 0]]}}],
    [{"datasets": {"computational_basis_histogram": [[2**64, 1]]}}],
])
def test_sdk_result_metrics_rejects_unsupported_shapes(raw):
    with pytest.raises(ValueError):
        cloud_worker.result_metrics(raw)


def test_sdk_result_reclaims_without_bulk(monkeypatch):
    histogram = [[0, 480], [1, 520]]
    client = SimpleNamespace(get_task_result=lambda task_id: [
        {"datasets": {"computational_basis_histogram": histogram}, "artiq_version": "v9.0",
         "expid": "private"}])
    result = cloud_worker.execute(client, "cloud.result", {"cloud_task": "remote-receipt"})
    assert result["cloud_task"] == "remote-receipt" and result["state"] == "completed"
    assert result["summary"]["shots"] == 1000
    assert result["summary"]["metrics"]["schema_version"] == "scientific-metrics/1.0"
    # Provenance, backend metadata and any private payload never enter the result.
    assert "artiq" not in json.dumps(result) and "expid" not in json.dumps(result)
    assert "bitstring" not in json.dumps(result).lower() and "counts" not in json.dumps(result)


def test_sdk_result_requires_bounded_interpretable_payload(monkeypatch):
    for task_result in (None, {"unexpected": "shape"}, [{"unparsed": 1}], [{"scalars": ["x" * 90000]}]):
        client = SimpleNamespace(get_task_result=lambda task_id=None, value=task_result: value)
        with pytest.raises(ValueError):
            cloud_worker.execute(client, "cloud.result", {"cloud_task": "remote-receipt"})


def test_gateway_result_flow_is_read_only(monkeypatch):
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")
    seen = []

    def worker(operation, payload):
        seen.append((operation, set(payload)))
        return {"provider": "uqc-cloud", "cloud_task": "remote-receipt", "state": "completed",
                "summary": {"status": "completed", "shots": 100,
                            "metrics": {"schema_version": "scientific-metrics/1.0",
                                        "items": [{"name": "p_0", "kind": "probability",
                                                   "unit": "dimensionless", "value": 1.0}]}}}

    monkeypatch.setattr(cloud, "worker", worker)
    _, raw = cloud.handle_request(request("cloud.result", {"cloud_task": "remote-receipt"}),
                                  "Bearer cloud-fixture")
    value = json.loads(raw)
    assert value["ok"] is True
    assert "OPENQASM" not in raw.decode() and "twin_id" not in raw.decode()
    assert seen == [("cloud.result", {"cloud_task"})]


def test_sdk_rejects_hardware_regardless_of_its_name():
    submissions = []
    client = SimpleNamespace(
        get_chips=lambda: {"sim-looking-name": {"chip_type": "hardware", "status": "online",
                                               "device_info": {"max_shots": 1000}}},
        submit_task=lambda **kwargs: submissions.append(kwargs),
    )
    with pytest.raises(ValueError):
        cloud_worker.execute(client, "cloud.submit", {"target": "sim-looking-name", "shots": 100,
                                                     "program": "unused"})
    assert submissions == []


def test_sdk_submission_happens_exactly_once():
    calls = []
    client = SimpleNamespace(
        get_chips=lambda: {"remote-sim": {"chip_type": "sim", "status": "online",
                                          "device_info": {"max_shots": 1000}}},
        submit_task=lambda **kwargs: calls.append(kwargs) or "remote-receipt",
    )
    result = cloud_worker.execute(client, "cloud.submit", {
        "target": "remote-sim", "shots": 100,
        "program": "OPENQASM 3.0; qubit[1] q; rx(pi/2) q[0];",
    })
    assert result["cloud_task"] == "remote-receipt" and len(calls) == 1
    assert "program" not in result and "twin_id" not in result


def test_normalize_inserts_rzz_definition_and_assigned_measures():
    program = ('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[2] q;\n'
               'ry(pi/2) q[0];\nrzz(pi) q[0], q[1];\nmeasure q;\n')
    rewritten = cloud_worker.normalize_program(program)
    assert "gate rzz(p0) _gate_q_0, _gate_q_1 {" in rewritten
    assert "bit[2] meas;\nmeas[0] = measure q[0];" in rewritten
    assert "meas[1] = measure q[1];" in rewritten
    assert rewritten.count("measure q[") == 2 and "measure q;" not in rewritten
    # Idempotent: a second pass must be a no-op once the dialect is present.
    assert cloud_worker.normalize_program(rewritten) == rewritten




def test_compile_lowers_standard_bell_gates_to_sdk_basis():
    program = ('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[2] q;\nbit[2] c;\n'
               'h(q[0]);\ncx q[0], q[1];\nmeasure q[0] -> c[0];\nmeasure q[1] -> c[1];\n')
    compiled = cloud_worker.compile_program(program)
    assert "h(" not in compiled and "cx " not in compiled
    assert "rx(" in compiled and "ry(" in compiled and "rzz(" in compiled
    rewritten = cloud_worker.normalize_program(compiled)
    assert "gate rzz(" in rewritten


def test_compile_rejects_dynamic_or_custom_gate_programs():
    for program in (
        'OPENQASM 3.0; qubit[1] q; if (true) { rx(pi/2) q[0]; }',
        'OPENQASM 3.0; gate custom a { rx(pi/2) a; } qubit[1] q; custom q[0];',
    ):
        with pytest.raises(ValueError):
            cloud_worker.compile_program(program)
    program = ('OPENQASM 3.0;\ninclude "stdgates.inc";\ngate rzz(p0) a, b {\n'
               '  cx a, b;\n  rz(p0) b;\n  cx a, b;\n}\nbit[2] meas;\nqubit[2] q;\n'
               'rzz(pi) q[0], q[1];\nmeas[0] = measure q[0];\n')
    assert cloud_worker.normalize_program(program) == program


def test_normalize_adds_no_definition_without_rzz_calls():
    # The definition block is added only when the program actually calls rzz;
    # standard-gate programs keep going through the same measure rewrite.
    program = 'OPENQASM 3.0;\nqubit[2] q;\nry(pi/2) q[0];\nmeasure q;\n'
    rewritten = cloud_worker.normalize_program(program)
    assert "gate rzz(" not in rewritten
    assert "bit[2] meas;\nmeas[0] = measure q[0];" in rewritten


def test_normalize_handles_meas_name_collision():
    program = ('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\n'
               'bit[1] meas;\nmeas[0] = measure q[0];\nry(pi/2) q[0];\n'
               'measure q;\n')
    rewritten = cloud_worker.normalize_program(program)
    assert "bit[1] meas_bits;\nmeas_bits[0] = measure q[0];" in rewritten


def test_sdk_failure_is_generic(monkeypatch):
    monkeypatch.setenv("COMPANY_AGENT_CLOUD_TOKEN", "cloud-fixture")

    def fail(*_args):
        raise RuntimeError("credential-value OPENQASM 3.0; full body")

    monkeypatch.setattr(cloud, "worker", fail)
    _, raw = cloud.handle_request(request(), "Bearer cloud-fixture")
    assert json.loads(raw)["error"] == "gateway operation failed"
    assert "credential-value" not in raw.decode() and "OPENQASM" not in raw.decode()


@pytest.mark.parametrize("capability", ["cloud", "hpc"])
@pytest.mark.parametrize("scenario,calls,asks", [("allow", 1, 1), ("reject", 0, 1),
                                                ("twice", 2, 2), ("deny_algo", 0, 0),
                                                ("cancel_after", 1, 1)])
def test_real_dsh_submission_approval_lifecycle(capability, scenario, calls, asks):
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.environ.get("COMPANY_AGENT_RUNTIME_DIR",
                   Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
                   / "unitqc-company-agent/dsh-runtime"))
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "DSH_TELEMETRY_MODE": "DISABLED",
           "COMPANY_AGENT_TEST_ROOT": str(root),
           "COMPANY_AGENT_TEST_MODULES": str(runtime / "node_modules/.pnpm/node_modules"),
           "COMPANY_AGENT_PROFILE": "company-agent", "COMPANY_AGENT_PRESET": "lab",
           "COMPANY_AGENT_PYTHON": sys.executable, "COMPANY_AGENT_PYTHONPATH": str(root / "src"),
           "COMPANY_AGENT_CONTRACTS_DIR": str(root / "contracts"),
           # Hermetic ledger: real-engine fixtures get a fresh turn identity and
           # receipt root per run, so termination budgets stay per-turn facts and
           # never accumulate stat across repeated test sessions.
           "COMPANY_AGENT_TURN_ID": f"fixture-{uuid.uuid4().hex[:16]}",
           "COMPANY_AGENT_RECEIPT_DIR": tempfile.mkdtemp(prefix="company-agent-fixture-"),
           "COMPANY_AGENT_FIXTURE_CAPABILITY": capability}
    completed = subprocess.run([str(runtime / "node_modules/node/bin/node"),
                                str(root / "tests/fixtures/dsh-lifecycle.mjs"), scenario],
                               env=env, cwd=root, text=True, capture_output=True, timeout=45)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert (report["calls"], report["asks"]) == (calls, asks)
    if scenario in {"allow", "twice"}:
        results = [event for event in report["results"] if event["type"] == "tool/result"]
        assert results and all(not row["data"]["message"]["content"][0]["isError"] for row in results)
    if asks:
        tool = "hpc_submit" if capability == "hpc" else "quantum_cloud_submit"
        assert all(row["toolName"] == tool for row in report["approvalRequests"])
    if scenario == "cancel_after":
        diagnostics = [json.loads(line.removeprefix("company-agent-diagnostic:"))
                       for line in completed.stderr.splitlines()
                       if line.startswith("company-agent-diagnostic:")]
        assert any(row["execution_state"] == "unknown" and row["request_id"].startswith("req_")
                   for row in diagnostics)


@pytest.mark.parametrize("operation", ["cloud.submit", "cloud.status"])
def test_worker_failure_logs_class_and_frames_only(monkeypatch, tmp_path, operation):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    def sdk_failure():
        secret = "credential-value OPENQASM 3.0; full body"
        raise RuntimeError("sdk reports " + secret)

    failure = None
    try:
        sdk_failure()
    except RuntimeError as exc:
        failure = exc
    cloud_worker._log_failure(operation, failure)
    target = tmp_path / ".cache/unitqc-company-agent/gateway-errors.log"
    text = target.read_text()
    # Only the last entry is new; earlier entries in the same file stay intact.
    entries = text.strip().split("\n\n")
    assert entries[-1].strip().splitlines()[0].endswith(f"uqc-cloud worker {operation}")
    assert "RuntimeError" in entries[-1] and "sdk_failure:" in entries[-1]
    # Error text may embed program bodies or account material: never log values.
    assert "sdk reports" not in text and "credential-value" not in text
    assert "OPENQASM" not in text
    assert entries[-1].strip().splitlines()[0].startswith("20")


def test_worker_failure_log_survives_unusable_channel(monkeypatch, tmp_path):
    # A blocked home must neither crash the worker nor corrupt prior entries.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    (tmp_path / ".cache").write_text("blocked")
    cloud_worker._log_failure("cloud.status", RuntimeError("untrusted detail"))
    assert not (tmp_path / ".cache/unitqc-company-agent/gateway-errors.log").exists()


def test_worker_failure_log_refuses_symlinked_target(monkeypatch, tmp_path, make_symlink):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    log_dir = tmp_path / ".cache/unitqc-company-agent"
    log_dir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("preserved")
    target = log_dir / "gateway-errors.log"
    make_symlink(outside, target)
    cloud_worker._log_failure("cloud.status", RuntimeError("untrusted detail"))
    assert outside.read_text() == "preserved"


def test_worker_main_reports_and_logs_sdk_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("UQC_CLOUD_HOST", raising=False)
    payload = json.dumps({"operation": "cloud.devices", "payload": {}}).encode()
    monkeypatch.setattr(cloud_worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload)))
    cloud_worker.main()
    value = json.loads(capsys.readouterr().out)
    assert value == {"ok": False, "result": None}
    log = (tmp_path / ".cache/unitqc-company-agent/gateway-errors.log").read_text()
    assert "uqc-cloud worker cloud.devices" in log and "KeyError" in log
    assert "UQC_CLOUD_HOST" not in log

