from __future__ import annotations

import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from company_agent.invoke import invoke


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    provider = "uniqon"
    result: dict = {"asset_id": "asset_test", "summary": {"status": "completed"}}
    last_authorization: str | None = None
    response_request_id: str | None = None
    response_status = 200
    response_error = ""
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        self.__class__.requests.append(request)
        self.__class__.last_authorization = self.headers.get("Authorization")
        if self.response_status == 200:
            response = {
                "protocol": "company-agent-provider/1.0",
                "ok": True,
                "provider": self.provider,
                "request_id": self.response_request_id
                if self.response_request_id is not None
                else request["request_id"],
                "result": self.result,
            }
        else:
            response = {"error": self.response_error}
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


@pytest.fixture(autouse=True)
def reset_handler(monkeypatch) -> None:
    Handler.provider = "uniqon"
    Handler.result = {"asset_id": "asset_test", "summary": {"status": "completed"}}
    Handler.last_authorization = None
    Handler.response_request_id = None
    Handler.response_status = 200
    Handler.response_error = ""
    Handler.requests = []
    for name in (
        "COMPANY_QUANTUM_PLATFORM_TOKEN",
        "COMPANY_AGENT_SIMULATOR_TOKEN",
        "COMPANY_AGENT_COMPILER_TOKEN",
        "COMPANY_AGENT_DEVICE_TOKEN",
    ):
        monkeypatch.setenv(name, "test-provider-token")


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


@pytest.mark.parametrize(
    ("tool", "provider", "url_env", "arguments", "output", "approved"),
    [
        (
            "quantum_algorithm_run",
            "uniqon",
            "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
            {
                "catalog_version": "cat_fixture",
                "component_version": "1.0",
                "algorithm": "test",
                "parameters": {"iterations": 2},
            },
            {"asset_id": "asset_test"},
            False,
        ),
        (
            "quantum_asset_get",
            "uniqon",
            "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
            {"asset_id": "asset_test"},
            {},
            False,
        ),
        (
            "quantum_asset_metrics",
            "uniqon",
            "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
            {"asset_id": "asset_test"},
            {
                "status": "completed",
                "summary": {"metrics": {"schema_version": "scientific-metrics/1.0", "items": []}},
            },
            False,
        ),
        (
            "quantum_circuit_export",
            "uniqon",
            "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
            {"asset_id": "asset_test"},
            {"circuit_id": "circ_test"},
            False,
        ),
        (
            "quantum_simulate",
            "independent-simulator",
            "COMPANY_AGENT_SIMULATOR_INVOKE_URL",
            {"circuit_id": "circ_test", "shots": 8},
            {"provenance": "independent-simulator"},
            False,
        ),
        (
            "quantum_compile_estimate",
            "independent-compiler",
            "COMPANY_AGENT_COMPILER_INVOKE_URL",
            {"circuit_id": "circ_test"},
            {"provenance": "independent-compiler", "makespan_ns": 1},
            False,
        ),
        (
            "quantum_device_identity",
            "ionstack-twinrun",
            "COMPANY_AGENT_DEVICE_INVOKE_URL",
            {},
            {"provider": "ionstack-twinrun"},
            False,
        ),
        (
            "quantum_device_run",
            "ionstack-twinrun",
            "COMPANY_AGENT_DEVICE_INVOKE_URL",
            {"circuit_id": "circ_test", "shots": 8},
            {"twin_id": "twin_test", "provenance": "qccd-twin"},
            True,
        ),
    ],
)
def test_provider_accepts_contract_summary(
    monkeypatch, provider_url, tool, provider, url_env, arguments, output, approved
) -> None:
    Handler.provider = provider
    Handler.result = {**output, "summary": {"status": "completed", "duration_ms": 1}}
    monkeypatch.setenv(url_env, provider_url)
    result = invoke(tool, "lab", arguments, approved=approved)
    assert result.status == "ok", result.error
    assert result.payload == Handler.result


@pytest.mark.parametrize("count", [0, 1, 32])
def test_asset_list_returns_existing_asset_references(monkeypatch, provider_url, count) -> None:
    Handler.result = {
        "assets": [
            {"asset_id": f"asset_existing_{index}", "label": "Existing asset", "kind": "result"}
            for index in range(count)
        ]
    }
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_asset_list", "lab", {})
    assert result.status == "ok", result.error
    assert result.payload == Handler.result


@pytest.mark.parametrize(
    "asset_id", ["asset_", "circ_wrong", "asset_has space", "asset_中文", "asset_" + "x" * 251]
)
def test_asset_list_rejects_malformed_references(monkeypatch, provider_url, asset_id) -> None:
    Handler.result = {"assets": [{"asset_id": asset_id}]}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_asset_list", "lab", {})
    assert result.status == "error"
    assert result.payload is None
    assert "asset_id" in result.error


@pytest.mark.parametrize(
    "payload",
    [
        {"assets": [{"asset_id": "asset_ok", "circuit_id": "circ_hidden"}]},
        {"assets": [{"asset_id": "asset_ok", "twin_id": "twin_hidden"}]},
        {"assets": [{"asset_id": "asset_ok", "summary": {"asset_id": "asset_hidden"}}]},
        {"assets": [{"asset_id": "asset_ok"}] * 33},
        {"assets": [{"label": "missing reference"}]},
    ],
)
def test_asset_list_fails_closed_for_invalid_rows(monkeypatch, provider_url, payload) -> None:
    Handler.result = payload
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke("quantum_asset_list", "lab", {})
    assert result.status == "error"
    assert result.payload is None


def test_asset_metrics_feed_analysis_template_without_new_handles(
    monkeypatch, provider_url,
) -> None:
    """The managed template consumes the fetched platform table as snapshot data; the
    chain stays provider-tool-first with only the registered handle vocabulary."""

    Handler.provider = "uniqon"
    Handler.result = {
        "status": "completed",
        "summary": {
            "status": "completed",
            "duration_ms": 5.0,
            "metrics": {"schema_version": "scientific-metrics/1.0", "items": [
                {"name": "fidelity", "kind": "probability", "value": 0.8812, "unit": "dimensionless"},
                {"name": "wall_time", "kind": "objective", "value": 330.5, "unit": "second"},
                {"name": "circuits", "kind": "count", "value": 6, "unit": "count"},
            ]},
        },
    }
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    fetched = invoke("quantum_asset_metrics", "lab", {"asset_id": "asset_test"})
    assert fetched.status == "ok", fetched.error
    assert set(fetched.payload) == {"status", "summary"}
    assert fetched.payload["summary"]["metrics"]["schema_version"] == "scientific-metrics/1.0"
    audit = invoke("company_analysis_render", "lab", {
        "template": "metric-summary", "metrics": fetched.payload["summary"]["metrics"],
    })
    assert audit.status == "ok" and audit.payload["status"] == "complete"
    assert {chart["unit"] for chart in audit.payload["charts"]} == {"count", "dimensionless", "second"}


def test_asset_metrics_rejects_unregistered_input_and_bad_table(
    monkeypatch, provider_url,
) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    Handler.provider = "uniqon"
    bad = invoke("quantum_asset_metrics", "lab", {"asset_id": "circ_wrong_prefix"})
    assert bad.status == "error" and "asset_id" in bad.error
    # The tool output contract pins the metric table schema: an upstream table
    # with a wrong schema_version fails closed at the provider boundary — it
    # must never reach the model or a downstream template.
    Handler.result = {
        "status": "completed",
        "summary": {"metrics": {"schema_version": "wrong/1.0", "items": []}},
    }
    mismatched = invoke("quantum_asset_metrics", "lab", {"asset_id": "asset_test"})
    assert mismatched.status == "error"
    assert mismatched.payload is None


def test_asset_list_exception_does_not_apply_to_other_operations(monkeypatch, provider_url) -> None:
    Handler.result = {"asset_id": "asset_top", "assets": [{"asset_id": "asset_hidden"}]}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "test"},
    )
    assert result.status == "error"
    assert "forbidden or oversized result data" in result.error


def test_platform_provider_rejects_forbidden_science_fields(monkeypatch, provider_url) -> None:
    Handler.provider = "uniqon"
    Handler.result = {
        "asset_id": "asset_test",
        "summary": {"status": "completed"},
        "pauli_terms": ["forbidden"],
    }
    Handler.last_authorization = None
    Handler.response_request_id = None
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "secret-token")
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert result.payload is None
    assert "forbidden or oversized result data" in str(result.error)
    assert Handler.last_authorization == "Bearer secret-token"


def test_provider_rejects_unknown_result_fields(monkeypatch, provider_url) -> None:
    Handler.result = {"asset_id": "asset_test", "summary": {"status": "completed"}, "debug": "leak"}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert "unknown fields" in str(result.error)
    assert "debug" not in str(result.error)


def test_provider_rejects_wrong_result_types(monkeypatch, provider_url) -> None:
    Handler.result = {"asset_id": "asset_test", "summary": "not-an-object"}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert "result.summary must be an object" in str(result.error)


def test_simulator_cannot_mint_twin_id(monkeypatch, provider_url) -> None:
    Handler.provider = "independent-simulator"
    Handler.result = {"provenance": "independent-simulator", "twin_id": "twin_forged"}
    Handler.response_request_id = None
    monkeypatch.setenv("COMPANY_AGENT_SIMULATOR_INVOKE_URL", provider_url)
    result = invoke("quantum_simulate", "lab", {"circuit_id": "circ_x", "shots": 8})
    assert result.status == "error"
    assert "not allowed to return twin_id" in str(result.error)


def test_simulator_cannot_hide_nested_twin_id(monkeypatch, provider_url) -> None:
    Handler.provider = "independent-simulator"
    Handler.result = {
        "provenance": "independent-simulator",
        "summary": {"twin_id": "twin_forged"},
    }
    monkeypatch.setenv("COMPANY_AGENT_SIMULATOR_INVOKE_URL", provider_url)
    result = invoke("quantum_simulate", "lab", {"circuit_id": "circ_x", "shots": 8})
    assert result.status == "error"
    assert "nested twin_id" in str(result.error)


def test_approved_device_requires_twin_provenance(monkeypatch, provider_url) -> None:
    Handler.provider = "ionstack-twinrun"
    Handler.result = {"twin_id": "twin_x", "provenance": "qccd-twin", "shots_actual": 8}
    Handler.response_request_id = None
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", provider_url)
    result = invoke("quantum_device_run", "lab", {"circuit_id": "circ_x", "shots": 8}, approved=True)
    assert result.status == "ok"
    assert result.payload and result.payload["twin_id"] == "twin_x"


def test_compiler_rejects_non_finite_or_negative_makespan(monkeypatch, provider_url) -> None:
    Handler.provider = "independent-compiler"
    monkeypatch.setenv("COMPANY_AGENT_COMPILER_INVOKE_URL", provider_url)
    for makespan in (True, -1, math.inf, math.nan):
        Handler.result = {"provenance": "independent-compiler", "makespan_ns": makespan}
        result = invoke("quantum_compile_estimate", "lab", {"circuit_id": "circ_x"})
        assert result.status == "error"
        assert "finite non-negative makespan_ns" in str(result.error) or "non-finite JSON number" in str(
            result.error
        )


def test_provider_requires_matching_request_id(monkeypatch, provider_url) -> None:
    Handler.provider = "uniqon"
    Handler.result = {"asset_id": "asset_test"}
    Handler.response_request_id = "req_wrong"
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert "request_id mismatch" in str(result.error)


def test_provider_rejects_duplicate_envelope_fields(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def duplicate_field_envelope(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = (
            '{"protocol":"company-agent-provider/1.0","ok":true,'
            '"provider":"uniqon","provider":"ionstack-twinrun",'
            f'"request_id":{json.dumps(request["request_id"])},'
            '"result":{"asset_id":"asset_test"}}'
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = duplicate_field_envelope
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "duplicate JSON field" in str(result.error)


def test_provider_rejects_credential_shaped_envelope_field(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def credential_field(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": True,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "result": {"asset_id": "asset_test"},
                "token": "leaked-value",
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = credential_field
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "credential-shaped envelope fields" in str(result.error)
    assert "leaked-value" not in str(result.error)


def test_provider_rejects_unknown_envelope_fields(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def extra_field_envelope(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": True,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "result": {"asset_id": "asset_test"},
                "debug": "not allowed",
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = extra_field_envelope
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "unknown envelope fields" in str(result.error)


def test_provider_rejects_misleading_content_type(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def misleading_content_type(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": True,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "result": {"asset_id": "asset_test"},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; note=application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = misleading_content_type
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "non-JSON content type" in str(result.error)


def test_provider_rejects_oversized_response(monkeypatch, provider_url) -> None:
    Handler.result = {"asset_id": "asset_test", "summary": "x" * 1_000_001}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert "response is too large" in str(result.error)


def test_provider_rejects_malformed_handle(monkeypatch, provider_url) -> None:
    Handler.result = {"asset_id": "wrong-prefix"}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert "asset_id has an invalid format" in str(result.error)


def test_provider_rejects_empty_handle_with_format_error(monkeypatch, provider_url) -> None:
    Handler.result = {"asset_id": ""}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert result.error == "asset_id has an invalid format"


def test_provider_authentication_failure_is_sanitized(monkeypatch, provider_url) -> None:
    Handler.response_status = 401
    Handler.response_error = "token secret-token rejected"
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "secret-token")
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert result.error == "provider platform rejected authentication"
    assert "secret-token" not in str(result.error)


def test_provider_http_error_does_not_echo_credentials(monkeypatch, provider_url) -> None:
    Handler.response_status = 500
    Handler.response_error = "provider token leaked-value failed"
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert result.error == "provider platform returned HTTP 500"
    assert "leaked-value" not in str(result.error)


def test_provider_rejects_error_in_success_envelope(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def mixed_envelope(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": True,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "error": "ambiguous",
                "result": {"asset_id": "asset_test"},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = mixed_envelope
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "error data in a success envelope" in str(result.error)


def test_provider_rejects_result_in_error_envelope(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def mixed_envelope(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": False,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "error": "failed",
                "result": {"asset_id": "asset_must_not_use"},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = mixed_envelope
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "result data in an error envelope" in str(result.error)


def test_provider_rejects_non_string_error_field(monkeypatch, provider_url) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    original = Handler.do_POST

    def invalid_error(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": False,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "error": {"message": "failed"},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = invalid_error
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert "invalid error field" in str(result.error)


def test_provider_http_error_does_not_echo_urls(monkeypatch, provider_url) -> None:
    Handler.response_status = 500
    Handler.response_error = "failed at https://internal.example/private"
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert result.error == "provider platform returned HTTP 500"
    assert "internal.example" not in str(result.error)


def test_provider_error_envelope_never_echoes_arbitrary_remote_text(monkeypatch, provider_url) -> None:
    Handler.provider = "uniqon"
    Handler.result = {"asset_id": "asset_test"}
    Handler.response_status = 200
    Handler.response_error = ""
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)

    original = Handler.do_POST

    def error_envelope(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        raw = json.dumps(
            {
                "protocol": "company-agent-provider/1.0",
                "ok": False,
                "provider": "uniqon",
                "request_id": request["request_id"],
                "error": "private-fixture-value",
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    Handler.do_POST = error_envelope
    try:
        result = invoke(
            "quantum_algorithm_run",
            "lab",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
    finally:
        Handler.do_POST = original
    assert result.status == "error"
    assert result.error == "provider platform failed"
    assert "private-fixture-value" not in str(result.error)


def test_provider_error_is_bounded_and_sanitized(monkeypatch, provider_url) -> None:
    Handler.response_status = 500
    Handler.response_error = "x" * 600
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    )
    assert result.status == "error"
    assert result.error == "provider platform returned HTTP 500"


@pytest.mark.parametrize("message", ["private-fixture-value", "OPENQASM 3.0; qubit q;", "设备底层详情"])
def test_provider_http_errors_never_echo_arbitrary_remote_text(monkeypatch, provider_url, message) -> None:
    Handler.response_status = 500
    Handler.response_error = message
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "fixture"},
    )
    assert result.error == "provider platform returned HTTP 500"
    assert result.payload is None


@pytest.mark.parametrize(
    "summary",
    [
        {"apiKey": "private-fixture"},
        {"accessToken": "private-fixture"},
        {"provenance": "qccd-twin"},
        {"text": "OPENQASM 3.0; qubit q;"},
        {f"metric{index}": "x" * 4000 for index in range(34)},
    ],
)
def test_provider_result_boundaries_fail_closed_end_to_end(monkeypatch, provider_url, summary) -> None:
    Handler.result = {"asset_id": "asset_fixture", "summary": summary}
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "fixture"},
    )
    assert result.status == "error"
    assert result.payload is None
    assert len(Handler.requests) == 1 and Handler.requests[0]["operation"] == "algorithm.run"
    assert "forbidden or oversized" in result.error


def test_local_validation_error_never_echoes_credential_shaped_argument_name() -> None:
    result = invoke(
        "quantum_algorithm_run",
        "lab",
        {
            "catalog_version": "cat_fixture",
            "component_version": "1.0",
            "algorithm": "vqe",
            "authorization_secret": "leaked-value",
        },
    )
    assert result.status == "error"
    assert result.error == "invalid tool arguments"
    assert "leaked-value" not in str(result.error)


def test_device_identity_requires_contract_fields(monkeypatch, provider_url) -> None:
    Handler.provider = "ionstack-twinrun"
    Handler.result = {"status": "ready"}
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", provider_url)
    result = invoke("quantum_device_identity", "lab", {})
    assert result.status == "error"
    assert "result.provider is required" in str(result.error)


def test_device_identity_cannot_mint_twin(monkeypatch, provider_url) -> None:
    Handler.provider = "ionstack-twinrun"
    Handler.result = {"twin_id": "twin_forged", "provenance": "qccd-twin"}
    Handler.response_request_id = None
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", provider_url)
    result = invoke("quantum_device_identity", "lab", {})
    assert result.status == "error"
    assert "may only return twin_id from device.run" in str(result.error)


@pytest.mark.parametrize("device", [False, True])
def test_known_credential_echo_is_rejected_end_to_end(monkeypatch, provider_url, capsys, device):
    secret = "synthetic-provider-secret-echo-regression"
    if device:
        Handler.provider = "ionstack-twinrun"
        Handler.result = {"twin_id": "twin_fixture", "provenance": "qccd-twin", "status": secret}
        monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", provider_url)
        monkeypatch.setenv("COMPANY_AGENT_DEVICE_TOKEN", secret)
        result = invoke("quantum_device_run", "lab", {"circuit_id": "circ_fixture", "shots": 1},
                        approved=True)
    else:
        Handler.result = {"asset_id": "asset_fixture", "status": secret}
        monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", provider_url)
        monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", secret)
        result = invoke("quantum_algorithm_run", "lab", {
            "algorithm": "fixture", "component_version": "1.0", "catalog_version": "cat_fixture",
        })
    captured = capsys.readouterr()
    assert result.status == "error" and result.payload is None
    assert len(Handler.requests) == 1
    assert secret not in str(result) + captured.out + captured.err
    events = [json.loads(line.split(":", 1)[1]) for line in captured.err.splitlines()]
    if device:
        assert events[-1]["execution_state"] == "unknown"
        assert events[-1]["request_id"] == Handler.requests[0]["request_id"]
