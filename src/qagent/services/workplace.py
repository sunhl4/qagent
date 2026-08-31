from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Any

from qagent.adapters.support import json_headers
from qagent.adapters.workplace_store import SECRET_KEYS, WorkplaceStore
from qagent.models.workplace import Workplace, resolve_llm_endpoint
from qagent.services.engines import list_engines, list_reserved_engines

_HOME_ENV = {
    "qdata_home": "QAGENT_QDATA_HOME",
    "qchem_home": "QAGENT_QCHEM_HOME",
    "ionstack_home": "QAGENT_IONSTACK_HOME",
}
_CLOUD_ENV = "QAGENT_CLOUD_URL"
_SECRET_FIELDS = frozenset(SECRET_KEYS)
_HTTP_FAIL = (urllib.error.URLError, TimeoutError, OSError, ValueError)


def load_workplace() -> Workplace:
    return WorkplaceStore().load()[0]


def secrets() -> dict[str, str]:
    return WorkplaceStore().load()[1]


def save_workplace(public: dict[str, Any], secrets_patch: dict[str, str] | None = None) -> Workplace:
    row = WorkplaceStore().save(public, secrets_patch)
    apply_env(row)
    return row


def cloud_url(row: Workplace | None = None) -> str:
    """Public settings URL only. Empty means cloud is not configured."""
    current = row or load_workplace()
    return str(current.cloud_url or "").strip()


def apply_env(row: Workplace | None = None) -> None:
    """Push homes, public cloud URL, and LLM endpoint into process env.

    ``cloud_url`` mirrors to ``QAGENT_CLOUD_URL`` (not a secret; GET may show
    it). Empty cloud unsets the env var. Never written to ``dsh.env``.
    ``llm_api_key`` may be mirrored to ``DEEPSEEK_API_KEY`` so dsh / the local
    model client can authenticate. ``hpc_secret`` and ``quantum_secret`` stay
    in the store — never env, never status JSON, never a dsh prompt.
    """
    current = row or load_workplace()
    for field, env_name in _HOME_ENV.items():
        value = str(getattr(current, field) or "").strip()
        if value:
            os.environ[env_name] = value
    if current.knowledge_path:
        os.environ["QAGENT_KNOWLEDGE_PATH"] = current.knowledge_path
    url = cloud_url(current)
    if url:
        os.environ[_CLOUD_ENV] = url
    else:
        os.environ.pop(_CLOUD_ENV, None)
    hidden = secrets()
    base_url, model = resolve_llm_endpoint(
        current.llm_model, current.llm_pool, current.llm_base_url
    )
    if base_url:
        os.environ["DEEPSEEK_BASE_URL"] = base_url
    if model:
        os.environ["DEEPSEEK_MODEL"] = model
    llm_key = hidden.get("llm_api_key")
    if llm_key:
        os.environ["DEEPSEEK_API_KEY"] = llm_key


def probe_cloud(row: Workplace | None = None) -> dict[str, Any]:
    """Honest cloud reachability. Empty is not a job. Dead URL is an error.

    Never ``status=done``. Never ``twin_id``. Not a tool; same names stay.
    """
    url = cloud_url(row)
    if not url:
        return {"configured": False, "status": "not_configured"}
    req = urllib.request.Request(url, method="GET", headers=json_headers(url))
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            resp.read(64)
    except _HTTP_FAIL as exc:
        raise RuntimeError(f"cloud HTTP is not reachable ({url})") from exc
    return {"configured": True, "status": "reachable"}


def job_auth_headers() -> dict[str, str]:
    """Southbound job HTTP only. Do not put this mapping in status or dsh prompt."""
    return WorkplaceStore().local_auth_headers()


def workplace_status() -> dict[str, Any]:
    row = load_workplace()
    apply_env(row)
    public = row.to_public()
    llm_model = str(public.get("llm_model") or "")
    return _without_secret_values(
        {
            "workplace": public,
            "ready": row.ready(),
            "next_model": llm_model if row.ready() else "",
            "add_pack": "contracts/engines/HOW_TO_ADD.md",
            "engines": [
                {
                    "id": pack.id,
                    "kind": pack.kind,
                    "label": pack.label,
                    "status": pack.status,
                    "vibe": pack.vibe,
                }
                for pack in list_engines()
            ],
            "reserved_engines": [
                {
                    "id": pack.id,
                    "kind": pack.kind,
                    "label": pack.label,
                    "status": pack.status,
                    "vibe": pack.vibe,
                }
                for pack in list_reserved_engines()
            ],
        }
    )


def _secret_values() -> frozenset[str]:
    return frozenset(value for value in secrets().values() if value)


def _without_secret_values(payload: Any) -> Any:
    return _scrub(payload, _secret_values())


def _scrub(payload: Any, values: frozenset[str]) -> Any:
    if isinstance(payload, dict):
        return {
            key: _scrub(value, values)
            for key, value in payload.items()
            if key not in _SECRET_FIELDS
        }
    if isinstance(payload, list):
        return [_scrub(item, values) for item in payload]
    if isinstance(payload, str) and values:
        text = payload
        for secret in values:
            if secret and secret in text:
                text = text.replace(secret, "")
        return text
    return payload
