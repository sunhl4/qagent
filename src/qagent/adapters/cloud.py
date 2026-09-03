from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qagent.adapters.contracts import CONTRACTS

URL_FIELDS = (
    "qdata_url",
    "qchem_url",
    "twin_url",
    "hub_url",
)
ENV_FOR_FIELD = {
    "qdata_url": "QAGENT_QDATA_URL",
    "qchem_url": "QAGENT_QCHEM_URL",
    "twin_url": "QAGENT_TWIN_URL",
    "hub_url": "QAGENT_ALGO_HUB_URL",
}
_LAB_QDATA = "http://127.0.0.1:8787"
_LAB_TWIN = "http://127.0.0.1:8765"


def cloud_company_path() -> Path:
    raw = os.environ.get("QAGENT_CLOUD_FILE")
    return Path(raw) if raw else CONTRACTS / "cloud" / "company.json"


def load_cloud_company() -> dict[str, str]:
    """Public company endpoints. Empty string means unpublished. Never invents localhost."""
    path = cloud_company_path()
    if not path.is_file():
        return {key: "" for key in URL_FIELDS}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {key: "" for key in URL_FIELDS}
    if not isinstance(raw, dict):
        return {key: "" for key in URL_FIELDS}
    out: dict[str, str] = {}
    for key in URL_FIELDS:
        value = str(raw.get(key) or "").strip()
        if "\n" in value or "\r" in value:
            value = ""
        out[key] = value.rstrip("/")
    return out


def _workplace_url(field: str) -> str:
    try:
        from qagent.adapters.workplace_store import WorkplaceStore
    except ImportError:
        return ""
    row = WorkplaceStore().load()[0]
    return str(getattr(row, field, "") or "").strip().rstrip("/")


def _home_set(env_name: str) -> bool:
    if (os.environ.get(env_name) or "").strip():
        return True
    home_field = {
        "QAGENT_QDATA_HOME": "qdata_home",
        "QAGENT_QCHEM_HOME": "qchem_home",
        "QAGENT_IONSTACK_HOME": "ionstack_home",
    }.get(env_name)
    if not home_field:
        return False
    try:
        from qagent.adapters.workplace_store import WorkplaceStore
    except ImportError:
        return False
    row = WorkplaceStore().load()[0]
    return bool(str(getattr(row, home_field, "") or "").strip())


def resolve_cloud_url(field: str) -> str:
    """env > workplace > company.json. Empty is unpublished, not 127.0.0.1."""
    if field not in ENV_FOR_FIELD:
        raise KeyError(field)
    env_name = ENV_FOR_FIELD[field]
    raw = (os.environ.get(env_name) or "").strip()
    if raw:
        return raw.rstrip("/")
    workplace = _workplace_url(field)
    if workplace:
        return workplace
    return load_cloud_company().get(field) or ""


def qdata_url() -> str | None:
    resolved = resolve_cloud_url("qdata_url")
    if resolved:
        return resolved
    if _home_set("QAGENT_QDATA_HOME"):
        return _LAB_QDATA
    return None


def qchem_url() -> str | None:
    resolved = resolve_cloud_url("qchem_url")
    return resolved or None


def twin_url() -> str | None:
    resolved = resolve_cloud_url("twin_url")
    if resolved:
        return resolved
    if _home_set("QAGENT_IONSTACK_HOME"):
        return _LAB_TWIN
    return None


def hub_url() -> str | None:
    resolved = resolve_cloud_url("hub_url")
    return resolved or None


def apply_cloud_env() -> dict[str, str]:
    """Fill empty process env from workplace then company.json. Never set QAGENT_CLOUD_URL."""
    applied: dict[str, str] = {}
    for field, env_name in ENV_FOR_FIELD.items():
        if (os.environ.get(env_name) or "").strip():
            continue
        value = resolve_cloud_url(field)
        if not value:
            continue
        os.environ[env_name] = value
        applied[env_name] = value
    return applied


def cloud_status() -> dict[str, Any]:
    """Honest reachability labels. Does not mint handles."""
    return {
        "qdata_url": qdata_url() or "",
        "qchem_url": qchem_url() or "",
        "twin_url": twin_url() or "",
        "hub_url": hub_url() or "",
        "qdata": "configured" if qdata_url() else "not_configured",
        "qchem": "configured" if qchem_url() else "not_configured",
        "twin": "configured" if twin_url() else "not_configured",
        "hub": "configured" if hub_url() else "not_configured",
    }
