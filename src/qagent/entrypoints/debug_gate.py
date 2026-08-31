from __future__ import annotations

import hmac
import os
from collections.abc import Mapping

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def debug_token() -> str:
    return os.environ.get("QAGENT_SHELL_TOKEN", "")


def approved_allowed(headers: Mapping[str, str] | None, requested: bool) -> bool:
    """HTTP may not open TwinRun unless a process-local approve token matches."""
    if not requested:
        return True
    token = debug_token()
    if not token:
        return False
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    given = (
        headers.get("x-qagent-debug-token")
        or headers.get("x-qagent-approve-token")
        or ""
    )
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        given = auth[7:].strip() or given
    return hmac.compare_digest(token, given)


def bind_allowed(host: str) -> bool:
    """Empty host is not loopback: HTTPServer(('', port)) listens on all interfaces."""
    name = str(host or "").strip()
    if name in _LOOPBACK:
        return True
    return bool(debug_token())
