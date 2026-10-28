"""Offline regression for the model-service probe's SSE/HTTP semantics.

The six-point probe must be deterministic in what it accepts: a healthy
incremental stream ends with a wire finish reason and a ``[DONE]`` marker; a
stream closed early, an HTTP error, or a non-JSON body is a failure. Shapes
only — no content from the fake server enters any assertion text beyond keys.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location(
        "probe_model_service", ROOT / "scripts/probe_model_service.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sse_frame(deltas: list[str], finish: str | None, done: bool) -> bytes:
    frames = ["data: " + json.dumps({"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]})]
    for piece in deltas:
        frames.append("data: " + json.dumps({
            "choices": [{"delta": {"content": piece}, "finish_reason": None}],
        }))
    if finish:
        frames.append("data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": finish}]}))
    if done:
        frames.append("data: [DONE]")
    return ("\n\n".join(frames) + "\n\n").encode("utf-8")


class FakeHandler(BaseHTTPRequestHandler):
    status_code = 200
    body: bytes = b""

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(self.__class__.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.__class__.body)))
        self.end_headers()
        self.wfile.write(self.__class__.body)

    def log_message(self, *_args) -> None:
        return


@pytest.fixture()
def fake_provider() -> ...:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    thread.join(timeout=2)


def _run_check(probe, fake_provider, body: bytes, status: int = 200) -> dict:
    FakeHandler.body = body
    FakeHandler.status_code = status
    return probe._check_streaming(fake_provider, None, "fixture-model", 8.0)


def test_healthy_stream_passes_with_finish_and_done(probe, fake_provider) -> None:
    body = _sse_frame(["part-a", "part-b", "part-c"], "stop", done=True)
    result = _run_check(probe, fake_provider, body)
    assert result["ok"] is True
    assert "finish=stop" in result["detail"] and "done=1" in result["detail"]
    assert "unparseable=0" in result["detail"]


def test_content_without_finish_fails(probe, fake_provider) -> None:
    result = _run_check(probe, fake_provider, _sse_frame(["answer", " two"], None, done=True))
    assert result["ok"] is False
    assert "finish=none" in result["detail"]


def test_truncated_stream_without_done_fails(probe, fake_provider) -> None:
    result = _run_check(probe, fake_provider, _sse_frame(["写", "到一般"], "stop", done=False))
    assert result["ok"] is False
    assert "content_chunks=2" in result["detail"]


def test_final_usage_chunk_does_not_break_scan(probe, fake_provider) -> None:
    body = _sse_frame(["回", "答"], "stop", done=False)
    usage = json.dumps({"choices": [], "usage": {"total_tokens": 9}})
    body += ("data: " + usage + "\n\n").encode("utf-8")
    body += b"data: [DONE]\n\n"
    result = _run_check(probe, fake_provider, body)
    assert result["ok"] is True
    assert "usage_chunk=1" in result["detail"]


def test_error_body_fails_without_content_chunks(probe, fake_provider) -> None:
    result = _run_check(
        probe, fake_provider,
        json.dumps({"error": {"message": "unauthorized"}}).encode("utf-8"), status=401)
    assert result["ok"] is False


def test_tool_call_shape_requires_tool_calls(probe, fake_provider) -> None:
    FakeHandler.body = json.dumps({"choices": [{"message": {"role": "assistant"}}]}).encode("utf-8")
    FakeHandler.status_code = 200
    without = probe._check_tool_shape(fake_provider, None, "fixture-model", 8.0)
    assert without["ok"] is False
    FakeHandler.body = json.dumps({"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"type": "function", "function": {"name": "probe_tool", "arguments": "{\"probe\":true}"}}
    ]}}]}).encode("utf-8")
    with_calls = probe._check_tool_shape(fake_provider, None, "fixture-model", 8.0)
    assert with_calls["ok"] is True


def test_structured_output_parses_and_rejects_free_text(probe, fake_provider) -> None:
    FakeHandler.body = json.dumps({"choices": [{"message": {"content": "{\"ok\": true}"}}]}).encode("utf-8")
    FakeHandler.status_code = 200
    assert probe._check_structured(fake_provider, None, "fixture-model", 8.0)["ok"] is True
    FakeHandler.body = json.dumps({"choices": [{"message": {"content": "不是 json"}}]}).encode("utf-8")
    assert probe._check_structured(fake_provider, None, "fixture-model", 8.0)["ok"] is False


def test_concurrency_records_recoveries_and_keeps_hard_failures(probe, monkeypatch) -> None:
    """Retried lanes recover past transient blips; persistent failures stay red."""

    def lane(body: dict, prompt_template: str) -> int:
        content = prompt_template.format(index=body["messages"][0]["content"])
        del content
        return 0

    attempts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}

    def flaky(base, key, body, timeout, *, raise_errors=False):
        # body is the request payload mapping ({"messages": [...]}); the lane
        # number rides in the prompt tail ("只回答数字 1 + 1。").
        content = body["messages"][0]["content"]
        index = int(content.rsplit("数字 ", 1)[1].split()[0])
        attempts[index] += 1
        return (200, {}) if attempts[index] > 1 else (500, "HTTP 500")

    monkeypatch.setattr(probe, "_post", flaky)
    assert probe._check_concurrency(
        "http://fixture/v1", None, "fixture-model", 8.0)["ok"] is True

    attempts.clear()
    attempts.update({1: 0, 2: 0, 3: 0, 4: 0})
    stubbed = 0

    def stubborn(base, key, body, timeout, *, raise_errors=False):
        nonlocal stubbed
        content = body["messages"][0]["content"]
        index = int(content.rsplit("数字 ", 1)[1].split()[0])
        stubbed += 1
        if index == 1:
            return 500, "HTTP 500"
        return 200, {}

    monkeypatch.setattr(probe, "_post", stubborn)
    result = probe._check_concurrency("http://fixture/v1", None, "fixture-model", 8.0)
    assert result["ok"] is False
    detail = json.loads(result["detail"])
    assert detail["initial"][0] == 500
    assert detail["post_retry"] == [500]


def test_offline_run_leaves_evidence_executed_false(probe, tmp_path) -> None:
    output = tmp_path / "evidence.json"
    assert probe.main([
        "--base-url", "http://127.0.0.1:9", "--model", "fixture-model",
        "--output", str(output),
    ]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["executed"] is False
    assert payload["ok"] is False
    assert {check["check"] for check in payload["checks"]} == {
        "tool_call_shape", "streaming", "cancellation", "context_metadata",
        "structured_output", "concurrency",
    }
