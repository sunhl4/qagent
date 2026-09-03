from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qagent.adapters.contracts import ROOT

STORE_ROOT = ROOT / ".qagent" / "store"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def ephemeral_roots() -> list[Path]:
    roots = [Path(tempfile.gettempdir()).resolve()]
    for raw in ("/tmp", "/var/tmp", "/private/tmp"):
        path = Path(raw)
        try:
            roots.append(path.resolve())
        except OSError:
            roots.append(path)
    return roots


def is_ephemeral_dir(raw: str | Path) -> bool:
    text = str(raw)
    if not text:
        return False
    lowered = text.lower()
    if "mkdtemp" in lowered:
        return True
    path = Path(text)
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    parts = set(resolved.parts)
    if "var" in parts and "folders" in parts:
        return True
    for root in ephemeral_roots():
        if resolved == root or root in resolved.parents:
            return True
        if text == str(root) or text.startswith(str(root) + os.sep):
            return True
    return False


def resolve_user_store(args: dict[str, Any] | None = None) -> Path:
    args = args or {}
    raw = args.get("data_dir") or args.get("store_dir") or os.environ.get("QAGENT_DATA_DIR")
    if raw and is_ephemeral_dir(raw):
        raise ValueError("data_dir must be a persistent user store, not a temporary directory")
    if raw:
        path = Path(str(raw))
        path.mkdir(parents=True, exist_ok=True)
        return path
    STORE_ROOT.mkdir(parents=True, exist_ok=True)
    return STORE_ROOT


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def json_headers(url: str) -> dict[str, str]:
    """JSON Accept plus job Bearer only when the URL is not loopback."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if is_loopback_url(url):
        return headers
    from qagent.adapters.workplace_store import WorkplaceStore

    extra = WorkplaceStore().local_auth_headers()
    if extra:
        headers.update(extra)
    return headers


def http_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 1.5,
) -> dict[str, Any]:
    from qagent.adapters.cloud import twin_url

    base = twin_url()
    if not base:
        raise OSError("twin URL is not configured")
    target = f"{base}{path}"
    req = urllib.request.Request(
        target,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method=method,
        headers=json_headers(target),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise ValueError("twin HTTP response must be an object")
    return parsed


def try_http_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        return http_json(method, path, body)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def http_json_url(
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 1.5,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method=method,
        headers=json_headers(url),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise ValueError("HTTP response must be an object")
    return parsed


def try_http_json_url(
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        return http_json_url(url, method, body)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return None
