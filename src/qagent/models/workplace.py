from __future__ import annotations

from dataclasses import dataclass


def parse_llm_pool(text: str) -> list[dict[str, str]]:
    """Parse textarea lines ``name | base_url | model``. No I/O. Never invents a row."""
    rows: list[dict[str, str]] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            continue
        name, base_url, model = parts[0], parts[1], parts[2]
        if not (name and base_url and model):
            continue
        rows.append({"name": name, "base_url": base_url, "model": model})
    return rows


def resolve_llm_endpoint(
    llm_model: str,
    llm_pool: str = "",
    llm_base_url: str = "",
) -> tuple[str, str]:
    """Return ``(base_url, model)``. Pool name, then pool model, else explicit fields. Never invents."""
    model = str(llm_model or "").strip()
    base_url = str(llm_base_url or "").strip()
    if not model:
        return base_url, ""
    named: dict[str, str] | None = None
    by_model: dict[str, str] | None = None
    for entry in parse_llm_pool(llm_pool):
        if named is None and entry["name"] == model:
            named = entry
        if by_model is None and entry["model"] == model:
            by_model = entry
    hit = named or by_model
    if hit:
        return hit["base_url"], hit["model"]
    return base_url, model


@dataclass
class Workplace:
    """Local workplace. Secrets never live on this object."""

    llm_base_url: str = ""
    llm_model: str = ""
    llm_pool: str = ""
    hpc_host: str = ""
    hpc_user: str = ""
    quantum_host: str = ""
    quantum_user: str = ""
    knowledge_path: str = ""
    cloud_url: str = ""
    qdata_home: str = ""
    qchem_home: str = ""
    ionstack_home: str = ""
    has_llm_key: bool = False
    has_hpc_secret: bool = False
    has_quantum_secret: bool = False

    def ready(self) -> bool:
        return bool(self.llm_base_url.strip() and self.llm_model.strip())

    def to_public(self) -> dict[str, object]:
        return {
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_pool": self.llm_pool,
            "hpc_host": self.hpc_host,
            "hpc_user": self.hpc_user,
            "quantum_host": self.quantum_host,
            "quantum_user": self.quantum_user,
            "knowledge_path": self.knowledge_path,
            "cloud_url": self.cloud_url,
            "qdata_home": self.qdata_home,
            "qchem_home": self.qchem_home,
            "ionstack_home": self.ionstack_home,
            "has_llm_key": self.has_llm_key,
            "has_hpc_secret": self.has_hpc_secret,
            "has_quantum_secret": self.has_quantum_secret,
            "ready": self.ready(),
        }
