"""Strict local HTTP gateway dispatch shared by the SSH and cloud adapters."""
from __future__ import annotations

import hmac
import json
import os
import re
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from company_agent.contracts import PROVIDER_PROTOCOL
from company_agent.jsonutil import loads

MAX_REQUEST_BYTES = 256_000
REQUEST_ID = re.compile(r"req_[0-9a-f]{32}")


def response(provider: str, request_id: str, *, result=None, error: str | None = None) -> bytes:
    value = {"protocol": PROVIDER_PROTOCOL, "ok": error is None,
             "provider": provider, "request_id": request_id}
    value["result" if error is None else "error"] = result if error is None else error
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def dispatch(body: bytes, authorization: str | None, *, provider: str, token_env: str,
             operations: set[str], execute: Callable, workspace: str = "") -> tuple[int, bytes]:
    token = os.environ.get(token_env, "").strip()
    if not token or not authorization or not hmac.compare_digest(
        authorization.encode(), f"Bearer {token}".encode()
    ):
        return 401, response(provider, "", error="unauthorized")
    try:
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("request size")
        envelope = loads(body.decode("utf-8"))
        if (not isinstance(envelope, dict)
            or set(envelope) != {"protocol", "operation", "request_id", "payload"}
            or envelope["protocol"] != PROVIDER_PROTOCOL
            or not isinstance(envelope["request_id"], str)
            or not REQUEST_ID.fullmatch(envelope["request_id"])
            or not isinstance(envelope["operation"], str)
            or envelope["operation"] not in operations
            or not isinstance(envelope["payload"], dict)):
            raise ValueError("envelope")
    except (ValueError, TypeError, UnicodeError):
        return 400, response(provider, "", error="invalid request")
    try:
        result = execute(envelope["operation"], envelope["payload"], workspace)
        data = response(provider, envelope["request_id"], result=result)
        if len(data) > 64_000:
            raise ValueError("result size")
        return 200, data
    except Exception as exc:
        _log_failure(provider, envelope["request_id"], envelope["operation"], exc)
        # Never propagate SDK/SSH errors, paths, environment values or program text.
        return 200, response(provider, envelope["request_id"], error="gateway operation failed")


def _log_failure(provider: str, request_id: str, operation: str, exc: BaseException) -> None:
    """Operator-facing diagnosis: exception class + bounded traceback, never values."""
    try:
        log_dir = Path(os.environ.get(
            "XDG_CACHE_HOME", str(Path(os.environ.get("HOME", "/tmp")) / ".cache")
        )) / "unitqc-company-agent"
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = log_dir / "gateway-errors.log"
        if target.exists() and target.is_symlink():
            return
        entries = traceback.format_exception_only(type(exc), exc)
        for _frame in traceback.extract_tb(exc.__traceback__):
            entries.append(f"  {_frame.name}:{_frame.lineno}")
        entries = entries[-8:]
        request = f"{datetime.now(UTC).isoformat()} {provider} {request_id} {operation}\n"
        with open(target, "a", encoding="utf-8") as stream:
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), 0o600)
            stream.write(request + "".join(entries) + "\n")
    except OSError:
        pass


def handler(callback):
    class Handler(BaseHTTPRequestHandler):
        server_version = "company-agent-access/1.0"
        sys_version = ""

        def do_POST(self):  # noqa: N802
            if self.path != "/invoke":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_REQUEST_BYTES:
                self.send_error(400)
                return
            self.connection.settimeout(35)
            status, body = callback(self.rfile.read(length), self.headers.get("Authorization"),
                                    self.headers.get("X-Company-Workspace", ""))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    return Handler
