from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Mapping

from qagent.adapters.gov_store import append_jsonl, asks_path, now_iso, read_jsonl
from qagent.adapters.support import json_headers

_HTTP_FAIL = (urllib.error.URLError, TimeoutError, OSError, ValueError)


def record_ask(*, tool: str, preset: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """File-first ask notice. Webhook is optional and must not block."""
    args = args or {}
    row = {
        "ts": now_iso(),
        "tool": tool,
        "preset": preset,
        "shots": args.get("shots"),
        "status": "needs_ask",
    }
    try:
        append_jsonl(asks_path(), row)
    except OSError:
        pass
    _ping_webhook(row)
    return row


def list_asks() -> list[dict[str, Any]]:
    return read_jsonl(asks_path())


def asks_face() -> dict[str, Any]:
    rows = list_asks()
    return {"pending": len(rows), "latest_tool": (rows[-1].get("tool") if rows else "")}


def _ping_webhook(row: Mapping[str, Any]) -> None:
    url = str(os.environ.get("QAGENT_ASK_WEBHOOK") or "").strip()
    if not url:
        return
    req = urllib.request.Request(
        url,
        data=json.dumps(dict(row), ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=json_headers(url),
    )
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            resp.read(32)
    except _HTTP_FAIL:
        return
