from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qagent.adapters.contracts import ROOT
from qagent.models.workplace import Workplace, resolve_llm_endpoint

_PUBLIC_KEYS = (
    "llm_base_url",
    "llm_model",
    "llm_pool",
    "hpc_host",
    "hpc_user",
    "quantum_host",
    "quantum_user",
    "knowledge_path",
    "cloud_url",
    "qdata_home",
    "qchem_home",
    "ionstack_home",
    "qdata_url",
    "qchem_url",
    "twin_url",
    "hub_url",
)
SECRET_KEYS = ("llm_api_key", "hpc_secret", "quantum_secret")
_SECRET_KEYS = SECRET_KEYS
_DSH_HOME_ENV = (
    ("qdata_home", "QAGENT_QDATA_HOME"),
    ("qchem_home", "QAGENT_QCHEM_HOME"),
    ("ionstack_home", "QAGENT_IONSTACK_HOME"),
    ("knowledge_path", "QAGENT_KNOWLEDGE_PATH"),
    ("qdata_url", "QAGENT_QDATA_URL"),
    ("qchem_url", "QAGENT_QCHEM_URL"),
    ("twin_url", "QAGENT_TWIN_URL"),
    ("hub_url", "QAGENT_ALGO_HUB_URL"),
)
_DSH_FORBIDDEN_KEYS = frozenset({"QAGENT_CLOUD_URL", "hpc_secret", "quantum_secret"})


def workplace_path() -> Path:
    raw = os.environ.get("QAGENT_WORKPLACE_FILE")
    return Path(raw) if raw else ROOT / ".qagent" / "workplace.json"


def secrets_path() -> Path:
    raw = os.environ.get("QAGENT_SECRETS_FILE")
    return Path(raw) if raw else ROOT / ".qagent" / "secrets.json"


def dsh_env_path() -> Path:
    raw = os.environ.get("QAGENT_DSH_ENV_FILE")
    return Path(raw) if raw else ROOT / ".qagent" / "dsh.env"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return raw if isinstance(raw, dict) else {}


def _write_json(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, mode)


def _public_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: raw[key] for key in _PUBLIC_KEYS if key in raw}


def _existing_dsh_env(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    if not path.is_file():
        return rows
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in _DSH_FORBIDDEN_KEYS:
            continue
        rows[key] = value
    return rows


def _lock_secrets_file() -> None:
    path = secrets_path()
    if path.is_file():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


class WorkplaceStore:
    """Local workplace + secrets. Never logs secret values."""

    def load(self) -> tuple[Workplace, dict[str, str]]:
        public = _public_fields(_read_json(workplace_path()))
        _lock_secrets_file()
        secrets = {key: str(value) for key, value in _read_json(secrets_path()).items() if key in _SECRET_KEYS and value}
        row = Workplace(
            **{key: str(public.get(key) or "") for key in _PUBLIC_KEYS},
            has_llm_key=bool(secrets.get("llm_api_key")),
            has_hpc_secret=bool(secrets.get("hpc_secret")),
            has_quantum_secret=bool(secrets.get("quantum_secret")),
        )
        return row, secrets

    def local_auth_headers(self) -> dict[str, str]:
        """Bearer token for southbound job HTTP. Caller must not return this to the model."""
        hidden = self.load()[1]
        token = hidden.get("hpc_secret") or hidden.get("quantum_secret") or ""
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def save(self, public: dict[str, Any], secrets_patch: dict[str, str] | None = None) -> Workplace:
        current, secrets = self.load()
        visible = {key: value for key, value in dict(public or {}).items() if key not in _SECRET_KEYS}
        merged = current.to_public()
        for key in _PUBLIC_KEYS:
            if key in visible and visible[key] is not None:
                merged[key] = str(visible[key]).strip()
        base_url, model = resolve_llm_endpoint(
            str(merged.get("llm_model") or ""),
            str(merged.get("llm_pool") or ""),
            str(merged.get("llm_base_url") or ""),
        )
        merged["llm_base_url"] = base_url
        merged["llm_model"] = model
        _write_json(workplace_path(), {key: merged[key] for key in _PUBLIC_KEYS})
        for key in _SECRET_KEYS:
            incoming = (secrets_patch or {}).get(key)
            if incoming:
                secrets[key] = incoming
        _write_json(secrets_path(), secrets)
        self.write_dsh_env(
            str(merged.get("llm_base_url") or ""),
            secrets.get("llm_api_key", ""),
            model=str(merged.get("llm_model") or ""),
            qdata_home=str(merged.get("qdata_home") or ""),
            qchem_home=str(merged.get("qchem_home") or ""),
            ionstack_home=str(merged.get("ionstack_home") or ""),
            knowledge_path=str(merged.get("knowledge_path") or ""),
            qdata_url=str(merged.get("qdata_url") or ""),
            qchem_url=str(merged.get("qchem_url") or ""),
            twin_url=str(merged.get("twin_url") or ""),
            hub_url=str(merged.get("hub_url") or ""),
        )
        return self.load()[0]

    def write_dsh_env(
        self,
        base_url: str,
        api_key: str,
        *,
        model: str = "",
        qdata_home: str = "",
        qchem_home: str = "",
        ionstack_home: str = "",
        knowledge_path: str = "",
        qdata_url: str = "",
        qchem_url: str = "",
        twin_url: str = "",
        hub_url: str = "",
    ) -> None:
        path = dsh_env_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = _existing_dsh_env(path)
        base_url = str(base_url or "").strip() or existing.get("DEEPSEEK_BASE_URL", "")
        api_key = str(api_key or "").strip() or existing.get("DEEPSEEK_API_KEY", "")
        model = str(model or "").strip() or existing.get("DEEPSEEK_MODEL", "")
        homes = {
            "qdata_home": qdata_home,
            "qchem_home": qchem_home,
            "ionstack_home": ionstack_home,
            "knowledge_path": knowledge_path,
            "qdata_url": qdata_url,
            "qchem_url": qchem_url,
            "twin_url": twin_url,
            "hub_url": hub_url,
        }
        lines = []
        if base_url:
            lines.append(f"DEEPSEEK_BASE_URL={base_url}")
        if api_key:
            lines.append(f"DEEPSEEK_API_KEY={api_key}")
        if model:
            lines.append(f"DEEPSEEK_MODEL={model}")
        for field, env_name in _DSH_HOME_ENV:
            value = str(homes.get(field) or "").strip()
            if value and env_name not in _DSH_FORBIDDEN_KEYS:
                lines.append(f"{env_name}={value}")
        kept = []
        for line in lines:
            key = line.split("=", 1)[0]
            if key in _DSH_FORBIDDEN_KEYS or line.endswith("="):
                continue
            kept.append(line)
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        os.chmod(path, 0o600)
