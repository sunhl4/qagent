from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from company_agent.invoke import invoke


class Handler(BaseHTTPRequestHandler):
    provider = "uniqon"
    result: dict = {}
    last_request: dict | None = None
    response_request_id: str | None = None
    response_status = 200

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        self.__class__.last_request = request
        response = {
            "protocol": "company-agent-provider/1.0",
            "ok": True,
            "provider": self.provider,
            "request_id": self.response_request_id
            if self.response_request_id is not None
            else request["request_id"],
            "result": self.result,
        }
        raw = json.dumps(response).encode()
        self.send_response(self.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args) -> None:
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return


def algorithm_entry(algorithm_id: str, **overrides) -> dict:
    row = {
        "id": algorithm_id,
        "version": "0.1",
        "kind": "solver",
        "maturity": "reference",
        "runnable": True,
        "description": f"Platform component {algorithm_id}.",
        "parameters": [
            {
                "name": "iterations",
                "type": "integer",
                "required": False,
                "description": "Optional iteration bound.",
            }
        ],
    }
    row.update(overrides)
    return row


def catalog_result(*ids: str, complete: bool = True, catalog_version: str = "cat_1", **extra) -> dict:
    payload = {
        "catalog_version": catalog_version,
        "provider": "uniqon",
        "algorithms": [algorithm_entry(item) for item in ids],
        "complete": complete,
    }
    payload.update(extra)
    return payload


@pytest.fixture(autouse=True)
def reset_handler(monkeypatch) -> None:
    Handler.provider = "uniqon"
    Handler.result = catalog_result()
    Handler.last_request = None
    Handler.response_request_id = None
    Handler.response_status = 200
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "test-provider-token")


@pytest.fixture
def provider_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/invoke"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_empty_catalog_is_accepted(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result()
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "ok", result.error
    assert result.payload == Handler.result
    assert Handler.last_request["operation"] == "algorithm.catalog"
    assert Handler.last_request["payload"] == {}


def test_catalog_forwards_query_limit_and_cursor(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha", complete=False, next_cursor="cursor_2")
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    arguments = {"query": "alpha", "limit": 8, "cursor": "cursor_1"}
    result = invoke("quantum_algorithm_catalog", "lab", arguments)
    assert result.status == "ok", result.error
    assert Handler.last_request["operation"] == "algorithm.catalog"
    assert Handler.last_request["payload"] == arguments
    assert result.payload["next_cursor"] == "cursor_2"
    assert result.payload["complete"] is False


def test_new_platform_algorithm_is_discoverable_without_agent_code_change(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    Handler.result = catalog_result("existing_algo")
    first = invoke("quantum_algorithm_catalog", "lab", {})
    assert first.status == "ok", first.error
    assert [row["id"] for row in first.payload["algorithms"]] == ["existing_algo"]

    Handler.result = catalog_result("existing_algo", "new_algo", catalog_version="cat_2")
    second = invoke("quantum_algorithm_catalog", "lab", {"query": "new"})
    assert second.status == "ok", second.error
    assert [row["id"] for row in second.payload["algorithms"]] == ["existing_algo", "new_algo"]
    assert second.payload["catalog_version"] == "cat_2"

    Handler.result = {"asset_id": "asset_new_algo", "summary": {"status": "completed"}}
    run = invoke(
        "quantum_algorithm_run",
        "lab",
        {"component_version": "1.0", "algorithm": "new_algo", "catalog_version": "cat_2"},
    )
    assert run.status == "ok", run.error
    assert Handler.last_request["operation"] == "algorithm.run"
    assert Handler.last_request["payload"]["algorithm"] == "new_algo"
    assert run.payload["asset_id"] == "asset_new_algo"


def test_platform_component_ids_and_plugin_ids_are_framework_identities(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    Handler.result = catalog_result(
        "qai.fidelity-kernel",
        "solver.qaoa",
        "solver.vqe",
    )
    discovered = invoke("quantum_algorithm_catalog", "lab", {"query": "solver"})
    assert discovered.status == "ok", discovered.error
    assert [row["id"] for row in discovered.payload["algorithms"]] == [
        "qai.fidelity-kernel",
        "solver.qaoa",
        "solver.vqe",
    ]
    assert all(
        row["maturity"] in {"reference", "experimental", "production"}
        for row in discovered.payload["algorithms"]
    )
    assert all(row["runnable"] is True for row in discovered.payload["algorithms"])

    Handler.result = {"asset_id": "asset_solver_vqe", "summary": {"status": "completed"}}
    run = invoke(
        "quantum_algorithm_run",
        "lab",
        {"component_version": "1.0", "catalog_version": "cat_fixture", "algorithm": "solver.vqe"},
    )
    assert run.status == "ok", run.error
    assert Handler.last_request["payload"]["algorithm"] == "solver.vqe"


def test_catalog_may_include_non_runnable_platform_components(monkeypatch, provider_url) -> None:
    Handler.result = {
        "catalog_version": "cat_1",
        "provider": "uniqon",
        "algorithms": [
            algorithm_entry(
                "numpy.statevector.estimator",
                kind="estimator",
                runnable=False,
                description="Exact or independent Pauli binomial CPU.",
                parameters=[],
            )
        ],
        "complete": True,
    }
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "ok", result.error
    assert result.payload["algorithms"][0]["runnable"] is False
    assert result.payload["algorithms"][0]["id"] == "numpy.statevector.estimator"


def test_catalog_rejects_duplicate_identifiers(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha")
    Handler.result["algorithms"].append(algorithm_entry("alpha"))
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert result.payload is None
    assert "duplicate" in result.error


def test_catalog_rejects_unsorted_identifiers(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("vqe", "qaoa")
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert "deterministic" in result.error


def test_catalog_rejects_wrong_provider(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha")
    Handler.result["provider"] = "independent-simulator"
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert result.payload is None


def test_complete_catalog_rejects_next_cursor(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha", complete=True, next_cursor="cursor_2")
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert "next_cursor" in result.error


def test_partial_catalog_requires_next_cursor(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha", complete=False)
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert "next_cursor" in result.error


def test_catalog_rejects_forbidden_science_fields(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha")
    Handler.result["pauli_terms"] = ["forbidden"]
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert result.payload is None
    assert "forbidden or oversized result data" in result.error


def test_catalog_missing_token_is_honest(monkeypatch, provider_url) -> None:
    monkeypatch.delenv("COMPANY_QUANTUM_PLATFORM_TOKEN", raising=False)
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_algorithm_catalog", "lab", {})
    assert result.status == "error"
    assert result.payload is None
    assert Handler.last_request is None
    assert "token" not in str(result.error).casefold()


def test_catalog_is_denied_outside_lab_and_algo(monkeypatch, provider_url) -> None:
    Handler.result = catalog_result("alpha")
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    for preset in ("boot", "sign"):
        result = invoke("quantum_algorithm_catalog", preset, {})
        assert result.status == "denied"
        assert result.payload is None
    assert Handler.last_request is None
