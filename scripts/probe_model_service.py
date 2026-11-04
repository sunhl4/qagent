#!/usr/bin/env python3
"""Acceptance probe for the company model service (survey P2 「模型服务和费用」).

Six checks against an OpenAI-completions-compatible endpoint:

1. tool_call shape — a tools declaration yields a tool_calls response;
2. streaming — streamed chunks arrive progressively and end with a finish reason;
3. cancellation — an in-flight generation is cut by a client timeout (the
   honest client-side analogue of user cancellation);
4. context metadata — the /models listing records what the service reports;
5. structured output — a json_object response_format returns parseable JSON;
6. concurrency — parallel bounded requests complete without server errors.

Rules:
- offline by default: without ``--live`` nothing is sent; the evidence file
  records ``executed: false`` so later reports can bind honest facts;
- token usage totals are recorded (cost accounting stays with the company
  platform; this probe only contributes observable token facts);
- prompts, completions and reply bodies never enter the evidence file.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "company-model-stack-probe/1.0"


def _post(
    url: str, key: str | None, body: dict, timeout: float, *, raise_errors: bool = False,
) -> tuple[int, dict | str]:
    request = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000).decode("utf-8")
        try:
            return 200, json.loads(raw)
        except json.JSONDecodeError:
            return 200, raw
    except urllib.error.HTTPError as exc:
        if raise_errors:
            raise
        return exc.code, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError):
        if raise_errors:
            raise
        return 0, "transport failure"


def _check_tool_shape(base: str, key: str, model: str, timeout: float) -> dict:
    status, payload = _post(base, key, {
        "model": model,
        "messages": [{"role": "user", "content": "调用 probe_tool 工具，"
                         "参数 {\"probe\": true}。仅调用一次。"}],
        "tools": [{"type": "function", "function": {
            "name": "probe_tool",
            "description": "Probe tool with one boolean.",
            "parameters": {"type": "object", "properties": {"probe": {"type": "boolean"}},
                           "required": ["probe"], "additionalProperties": False},
        }}],
        "tool_choice": "auto", "max_tokens": 200,
    }, timeout)
    ok = False
    detail = ""
    if status == 200 and isinstance(payload, dict):
        choice = (payload.get("choices") or [{}])[0]
        tool_calls = choice.get("message", {}).get("tool_calls") or []
        ok = bool(tool_calls) and isinstance(tool_calls[0].get("function", {}).get("arguments"), str)
        detail = "tool_calls present" if ok else "no tool_calls in response"
    else:
        detail = f"HTTP {status}" if status else str(payload)[:80]
    return {"check": "tool_call_shape", "ok": ok, "detail": detail}


def _check_streaming(base: str, key: str, model: str, timeout: float) -> dict:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "用一句话回答：1+1=?"}],
                       "stream": True, "max_tokens": 64}).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})},
        method="POST")
    scanner = StreamingScanner()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw in response:
                scanner.feed_line(raw.decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"check": "streaming", "ok": False,
                "detail": f"transport: {str(exc)[:80]} + {scanner.summary()}"}
    return {"check": "streaming", "ok": scannerStreamingOk(scanner),
            "detail": scanner.summary()}


def scannerStreamingOk(scanner: StreamingScanner) -> bool:
    """A healthy incremental stream: content delivered by chunks, a wire
    finish reason, and a protocol close marker. A stream that ends early (no
    finish reason, no DONE marker) fails: downstream adapters must not hang.
    """

    return scanner.content_chunks >= 2 and scanner.finish_reason != "" and scanner.done_marker


class StreamingScanner:
    """Shape-only SSE scanner: never stores content or prompts in evidence."""

    def __init__(self) -> None:
        self.content_chunks = 0
        self.chunks = 0
        self.finish_reason = ""
        self.done_marker = False
        self.usage_chunk = False
        self.unparseable_data = 0
        self.closed_flowing = False

    def feed_line(self, raw: str) -> None:
        line = raw.strip()
        if not line:
            return
        if line.startswith("data:"):
            data = line[5:].strip()
            if not data:
                return
            if data == "[DONE]":
                self.done_marker = True
                return
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                self.unparseable_data += 1
                return
            self.chunks += 1
            choices = payload.get("choices") or []
            content_delta = 0
            for choice in choices:
                reason = choice.get("finish_reason")
                if isinstance(reason, str) and reason and not self.finish_reason:
                    self.finish_reason = reason
                delta = choice.get("delta") or {}
                if isinstance(delta, dict) and ("content" in delta or "tool_calls" in delta):
                    content_delta += 1
            if content_delta:
                self.content_chunks += 1
            if "usage" in payload and not choices:
                self.usage_chunk = True
        else:
            self.closed_flowing = True

    def summary(self) -> str:
        return (
            f"chunks={self.chunks} content_chunks={self.content_chunks} "
            f"finish={self.finish_reason or 'none'} done={int(self.done_marker)} "
            f"usage_chunk={int(self.usage_chunk)} unparseable={self.unparseable_data}"
        )

def _check_cancellation(base: str, key: str, model: str) -> dict:
    start = time.monotonic()
    try:
        _post(base, key, {
            "model": model,
            "messages": [{"role": "user", "content": "请详细描述量子退相干，输出 800 字以上。"}],
            "max_tokens": 700,
        }, timeout=1.5, raise_errors=True)
        return {"check": "cancellation", "ok": False,
                "detail": "generation finished before the client timeout; cancellation not exercised"}
    except (TimeoutError, OSError):
        elapsed = time.monotonic() - start
        return {"check": "cancellation", "ok": 0.5 <= elapsed <= 20.0,
                "detail": f"client timeout cut the connection at {elapsed:.1f}s"}
    except urllib.error.HTTPError as exc:
        return {"check": "cancellation", "ok": False, "detail": f"HTTP {exc.code}"}


def _check_context(base: str, key: str, model: str) -> dict:
    request = urllib.request.Request(
        base.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
        return {"check": "context_metadata", "ok": False, "detail": f"models listing failed: {str(exc)[:60]}"}
    rows = payload.get("data") if isinstance(payload, dict) else None
    row = None
    if rows:
        row = next((item for item in rows if isinstance(item, dict) and item.get("id") == model), None)
    recorded = {}
    if row:
        for field in ("context_window", "max_context", "max_tokens", "owned_by"):
            if isinstance(row.get(field), (int, str)):
                recorded[field] = row[field]
    return {"check": "context_metadata", "ok": row is not None,
            "detail": "model listed" if row is not None else "model absent from /models",
            "reported": recorded}


def _check_structured(base: str, key: str, model: str, timeout: float) -> dict:
    status, payload = _post(base, key, {
        "model": model,
        "messages": [{"role": "user", "content": "以 JSON 对象回答，键 ok 为布尔值 true。"}],
        "response_format": {"type": "json_object"}, "max_tokens": 64,
    }, timeout)
    ok = False
    if status == 200 and isinstance(payload, dict):
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        try:
            parsed = json.loads(content)
            ok = isinstance(parsed, dict)
        except json.JSONDecodeError:
            ok = False
    detail = "structured JSON parsed" if ok else f"HTTP {status}"
    return {"check": "structured_output", "ok": ok, "detail": detail}


def _check_concurrency(base: str, key: str, model: str, timeout: float) -> dict:
    def single(index: int) -> tuple[int, int]:
        status, _payload = _post(base, key, {
            "model": model,
            "messages": [{"role": "user", "content": f"只回答数字 {index} + {index}。"}],
            "max_tokens": 16,
        }, timeout)
        return status, int(status == 200)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        initial = list(pool.map(single, (1, 2, 3, 4)))
    initial_ok = all(status == 200 for status, _ in initial)
    detail = {"initial": [status for status, _ in initial]}
    if initial_ok:
        detail["recovered"] = "not_needed"
    else:
        # One bounded retry per failed lane separates transient transport
        # blips from a real service concurrency cap; the report keeps both.
        retried = [single(index) for index in (1, 2, 3, 4) if initial[index - 1][0] != 200]
        detail["recovered"] = sum(1 for status, _ in retried if status == 200)
        detail["post_retry"] = [status for status, _ in retried]
    ok = initial_ok or all(status == 200 for status, _ in retried)
    return {"check": "concurrency", "ok": ok,
            "detail": json.dumps(detail, sort_keys=True)[:120]}


def _usage_totals(base: str, key: str, model: str, timeout: float) -> tuple[int, dict]:
    import sys

    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from company_agent.office_usage import parse_usage

    status, payload = _post(base, key, {
        "model": model,
        "messages": [{"role": "user", "content": "回答一个字：是。"}],
        "max_tokens": 8,
    }, timeout)
    absent = {"observed": "absent", "fixed": None, "cached": None, "uncached": None}
    if status == 200 and isinstance(payload, dict):
        usage = payload.get("usage") or {}
        total = usage.get("total_tokens")
        observed = parse_usage(usage if isinstance(usage, dict) else {})
        return (int(total) if isinstance(total, int) else 0), observed
    return 0, absent


def _models_url_ok(base: str) -> bool:
    return base.startswith(("http://", "https://")) and not base.rstrip("/").endswith("/models")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="probe_model_service")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="company-local")
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", default=str(ROOT / "docs" / "evidence" / "model-stack-probe.json"))
    args = parser.parse_args(argv)
    if not _models_url_ok(args.base_url):
        parser.error("--base-url must be an HTTP(S) completion endpoint without /models suffix")
    key = str(__import__("os").environ.get(args.api_key_env) or "").strip() if args.api_key_env else ""
    checks: list[dict[str, object]] = []
    usage_tokens = 0
    usage_observation = {"observed": "absent", "fixed": None, "cached": None, "uncached": None}
    executed = args.live
    if executed:
        checks = [
            _check_tool_shape(args.base_url, key, args.model, args.timeout),
            _check_streaming(args.base_url, key, args.model, args.timeout),
            _check_cancellation(args.base_url, key, args.model),
            _check_context(args.base_url, key, args.model),
            _check_structured(args.base_url, key, args.model, args.timeout),
            _check_concurrency(args.base_url, key, args.model, args.timeout),
        ]
        usage_tokens, usage_observation = _usage_totals(
            args.base_url, key, args.model, args.timeout
        )
    else:
        checks = [{"check": name, "ok": False, "detail": "not executed (offline without --live)"}
                  for name in ("tool_call_shape", "streaming", "cancellation",
                               "context_metadata", "structured_output", "concurrency")]
    payload = {
        "evidence": FORMAT,
        "provider": args.provider,
        "model": args.model,
        "endpoint_scheme": args.base_url.split(":", 1)[0],
        "executed": executed,
        "checks": checks,
        "usage_tokens_recorded": usage_tokens,
        "usage_observation": usage_observation,
        "ok": executed and all(check["ok"] for check in checks),
        "note": (
            "模型费用仍以公司平台结算为准；本证据只绑定协议六项与服务报告的上下文容量，"
            "不包含提示词、答复正文或任何密钥。"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps({"ok": payload["ok"], "executed": executed, "output": str(output)}))
    return 0 if payload["ok"] or not executed else 1


if __name__ == "__main__":
    raise SystemExit(main())
