from __future__ import annotations

import io
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from company_agent import catalog, diagnostics
from company_agent.invoke import _validate_output, invoke
from company_agent.providers import ProviderClient, ProviderError

ROOT = Path(__file__).resolve().parents[1]


def test_summary_contracts_are_closed_and_versioned() -> None:
    schemas = [
        row["output"]["properties"]["summary"]
        for row in catalog.load_tools().values()
        if "summary" in row["output"]["properties"]
    ]
    assert len(schemas) == 11
    for schema in schemas:
        assert schema["additionalProperties"] is False
        if "metrics" in schema["properties"]:
            metrics = schema["properties"]["metrics"]
            assert metrics["additionalProperties"] is False
            expected_items = 64 if "omitted_states" in schema["properties"] else 8
            assert metrics["properties"]["items"]["maxItems"] == expected_items
        assert schema["properties"]["duration_ms"]["minimum"] == 0
    versions = {row["id"]: row["contract_version"] for row in catalog.load_capabilities()["capabilities"]}
    assert versions["company.algorithm"] == "company.algorithm/2.0"
    assert all(
        version.endswith("/2.0")
        for capability_id, version in versions.items()
        if capability_id != "company.algorithm"
    )


@pytest.mark.parametrize(
    "summary",
    [
        {"unknown": "ordinary-looking-private-text"},
        {"metrics": {"value": 2}},
        {"status": "custom-status"},
        {"duration_ms": True},
        {"duration_ms": -1},
        {"duration_ms": 1_000_000_001},
        {"qubits": 0},
        {"gate_count": 1.5},
    ],
)
def test_closed_algorithm_summary_rejects_unknown_or_invalid_data(summary) -> None:
    with pytest.raises(ProviderError):
        _validate_output("quantum_algorithm_run", {"asset_id": "asset_fixture", "summary": summary})


def test_summary_fields_are_operation_specific() -> None:
    _validate_output(
        "quantum_algorithm_run",
        {
            "asset_id": "asset_fixture",
            "summary": {"qubits": 2, "gate_count": 0, "duration_ms": 0.5},
        },
    )
    with pytest.raises(ProviderError):
        _validate_output(
            "quantum_simulate",
            {
                "provenance": "independent-simulator",
                "summary": {"qubits": 2},
            },
        )


@pytest.fixture
def contract_copy(tmp_path, monkeypatch):
    root = tmp_path / "contracts"
    shutil.copytree(ROOT / "contracts", root)
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", str(root))
    return root


def test_snapshot_is_immutable_scoped_and_content_addressed(contract_copy) -> None:
    with catalog.contract_snapshot() as snapshot:
        first = snapshot.digest
        with pytest.raises(TypeError):
            snapshot.documents["tools.json"] = b"{}"
        tools = catalog.load_tools()
        tools["company_capabilities"]["description"] = "mutated"
        assert catalog.load_tools()["company_capabilities"]["description"] != "mutated"
        path = contract_copy / "tools.json"
        value = json.loads(path.read_text())
        value["tools"][0]["description"] += " updated"
        path.write_text(json.dumps(value))
        with pytest.raises(RuntimeError, match="changed before dispatch"):
            catalog.verify_snapshot_current()
    with catalog.contract_snapshot() as snapshot:
        assert snapshot.digest != first
    (contract_copy / "results.json").write_text("broken")
    assert invoke("company_capabilities", "lab", {}).status == "error"


def test_snapshot_reads_each_file_once_per_local_invocation(monkeypatch) -> None:
    reads = []
    original = catalog.read_json

    def read(path):
        reads.append(path.name)
        return original(path)

    monkeypatch.setattr(catalog, "read_json", read)
    assert invoke("company_capabilities", "lab", {}).status == "ok"
    # tools, results, providers, capabilities, policy, presets, templates,
    # skills, tenants, budgets, superagent (once per invocation after the
    # first snapshot build).
    assert len(reads) == len(set(reads)) == 11
    assert invoke("company_capabilities", "lab", {}).status == "ok"
    assert len(reads) == 22


def diagnostic_event():
    return {
        "version": "1.0",
        "event": "provider",
        "tool": "quantum_device_run",
        "operation": "device.run",
        "request_id": "req_" + "a" * 32,
        "contract_digest": catalog.current_contract_digest(),
        "elapsed_ms": 0,
        "status": "started",
        "execution_state": "dispatched",
        "error_category": "none",
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("tool", "quantum_unknown"),
        ("operation", "algorithm.run"),
        ("request_id", "private"),
        ("elapsed_ms", True),
        ("elapsed_ms", 2**53),
        ("status", {}),
        ("request_id", ""),
    ],
)
def test_diagnostic_metadata_is_strict(key, value) -> None:
    event = diagnostic_event()
    event[key] = value
    with pytest.raises(ValueError):
        diagnostics.encode(event)


def test_logging_failure_does_not_replace_local_result(monkeypatch) -> None:
    class Broken(io.StringIO):
        def write(self, value):
            raise BrokenPipeError("closed")

    monkeypatch.setattr(diagnostics.sys, "stderr", Broken())
    assert invoke("company_capabilities", "lab", {}).status == "ok"


def test_device_timeout_is_unknown_and_not_retried(monkeypatch, capsys) -> None:
    calls = []

    def timeout(request, **kwargs):
        calls.append(request)
        raise TimeoutError("private transport detail")

    monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", "http://127.0.0.1:30001/invoke")
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_TOKEN", "fixture")
    monkeypatch.setattr("company_agent.providers._OPENER.open", timeout)
    client = ProviderClient(
        "device",
        "COMPANY_AGENT_DEVICE_INVOKE_URL",
        "ionstack-twinrun",
        token_env="COMPANY_AGENT_DEVICE_TOKEN",
        allow_twin_id=True,
    )
    with pytest.raises(ProviderError, match="outcome unknown; do not retry automatically; request_id=req_"):
        client.invoke("device.run", {"circuit_id": "circ_fixture", "shots": 1})
    assert len(calls) == 1
    events = [
        json.loads(line.removeprefix(diagnostics.PREFIX)) for line in capsys.readouterr().err.splitlines()
    ]
    assert [event["execution_state"] for event in events if event["event"] == "provider"] == [
        "dispatched",
        "unknown",
    ]
    assert events[-1]["error_category"] == "timeout"
    assert events[0]["request_id"] == events[-1]["request_id"]
    assert "private" not in json.dumps(events)


@pytest.mark.parametrize("fault", ["disconnect", "invalid_json", "bad_summary"])
def test_loopback_device_bad_response_is_unknown_once(monkeypatch, capsys, fault):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(request["request_id"])
            if fault == "disconnect":
                self.close_connection = True
                return
            raw = (
                b"invalid-json"
                if fault == "invalid_json"
                else json.dumps(
                    {
                        "protocol": "company-agent-provider/1.0",
                        "ok": True,
                        "provider": "ionstack-twinrun",
                        "request_id": request["request_id"],
                        "result": {
                            "twin_id": "twin_fixture",
                            "provenance": "qccd-twin",
                            "summary": {"unknown": "private fixture detail"},
                        },
                    }
                ).encode()
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", f"http://127.0.0.1:{server.server_port}/invoke")
        monkeypatch.setenv("COMPANY_AGENT_DEVICE_TOKEN", "fixture")
        try:
            result = invoke(
                "quantum_device_run", "lab", {"circuit_id": "circ_fixture", "shots": 1}, approved=True
            )
        finally:
            server.shutdown()
            thread.join(timeout=3)
    assert result.status == "error" and len(calls) == 1
    assert result.error.removeprefix("device execution ") == (
        "outcome unknown; do not retry automatically; request_id="
        + calls[0]
        + "; query status and do not resubmit"
    )
    events = [
        json.loads(line.removeprefix(diagnostics.PREFIX)) for line in capsys.readouterr().err.splitlines()
    ]
    assert [event["execution_state"] for event in events if event["event"] == "provider"] == [
        "dispatched",
        "unknown",
    ]
    assert events[-1]["error_category"] == ("transport" if fault == "disconnect" else "invalid_result")
    assert "private" not in json.dumps(events)


def test_changed_contract_before_dispatch_never_calls_provider(contract_copy, monkeypatch):
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://127.0.0.1:30001/invoke")
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "fixture")
    monkeypatch.setattr("company_agent.providers._OPENER.open", lambda *a, **k: pytest.fail("dispatched"))
    original = catalog.verify_snapshot_current

    def change_then_check():
        path = contract_copy / "results.json"
        path.write_text("broken")
        original()

    monkeypatch.setattr("company_agent.providers.verify_snapshot_current", change_then_check)
    assert (
        invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "fixture"},
        ).status
        == "error"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operations", "device.identity device.run"),
        ("operations", ["device.run", "device.run"]),
        ("operations", ["device.identity", "device.run", "device.other"]),
        ("operations", [None]),
        ("token_env", []),
        ("token_env", ""),
        ("env", "bad value"),
    ],
)
def test_bad_unused_provider_contract_blocks_all_dispatch(contract_copy, monkeypatch, field, value):
    path = contract_copy / "providers.json"
    payload = json.loads(path.read_text())
    payload["providers"][-1][field] = value
    path.write_text(json.dumps(payload))
    monkeypatch.setattr("company_agent.providers._OPENER.open", lambda *a, **k: pytest.fail("dispatched"))
    assert (
        invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "fixture"},
        ).status
        == "error"
    )
    assert invoke("company_capabilities", "lab", {}).status == "error"


def test_contract_final_component_symlink_fails_closed(contract_copy, make_symlink):
    path = contract_copy / "results.json"
    target = contract_copy.parent / "external.json"
    path.rename(target)
    make_symlink(target, path)
    assert invoke("company_capabilities", "lab", {}).status == "error"


def test_unavailable_diagnostic_channel_blocks_network(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", "http://127.0.0.1:30001/invoke")
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_TOKEN", "fixture")
    monkeypatch.setattr("company_agent.providers.emit", lambda event: False)
    monkeypatch.setattr("company_agent.providers._OPENER.open", lambda *a, **k: pytest.fail("dispatched"))
    client = ProviderClient(
        "device",
        "COMPANY_AGENT_DEVICE_INVOKE_URL",
        "ionstack-twinrun",
        token_env="COMPANY_AGENT_DEVICE_TOKEN",
        allow_twin_id=True,
    )
    with pytest.raises(ProviderError, match="unavailable before dispatch"):
        client.invoke("device.run", {"circuit_id": "circ_fixture", "shots": 1})
