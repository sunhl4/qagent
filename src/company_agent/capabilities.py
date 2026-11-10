from __future__ import annotations

from company_agent.catalog import load_capabilities
from company_agent.contracts import Capability


def _parse_capabilities(rows: object) -> tuple[Capability, ...]:
    if not isinstance(rows, list):
        raise RuntimeError("capability contract is invalid")
    try:
        capabilities = tuple(
            Capability(
                id=str(row["id"]),
                kind=row["kind"],
                provider=str(row["provider"]),
                contract_version=str(row["contract_version"]),
                tools=tuple(str(item) for item in row.get("tools") or ()),
                handles=tuple(str(item) for item in row.get("handles") or ()),
                approval=row.get("approval", "none"),
                provenance=str(row.get("provenance") or ""),
            )
            for row in rows
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("capability contract is invalid") from exc
    identities = [item.id for item in capabilities]
    if not all(identities) or len(identities) != len(set(identities)):
        raise RuntimeError("capability contract is invalid")
    expected_kinds = {
        "company.algorithm": "platform",
        "company.asset": "platform",
        "quantum.simulation": "simulator",
        "quantum.compilation": "compiler",
        "quantum.device": "device",
        "compute.cloud": "cloud",
        "compute.hpc": "compute",
        "company.knowledge": "knowledge",
        "company.workflow": "workflow",
        "company.latex": "document",
        "company.office": "document",
        "company.plan": "plan",
        "company.portal": "portal",
        "company.research": "research",
        "company.literature": "literature",
        "company.dingtalk": "channel",
        "company.workflow": "workflow",
        "company.latex": "document",
        "company.plan": "plan",
        "company.office": "document",
    }
    if any(item.kind != expected_kinds.get(item.id) for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    if {item.id for item in capabilities} != {
        "company.algorithm",
        "company.asset",
        "quantum.simulation",
        "quantum.compilation",
        "quantum.device",
        "compute.cloud",
        "compute.hpc",
        "company.knowledge",
        "company.workflow",
        "company.latex",
        "company.office",
        "company.plan",
        "company.portal",
        "company.research",
        "company.literature",
        "company.dingtalk",
    }:
        raise RuntimeError("capability contract is invalid")
    if any(item.approval not in {"none", "human"} for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    if any(len(item.tools) != len(set(item.tools)) for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    if any(len(item.handles) != len(set(item.handles)) for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    if any(set(item.handles) - {"asset_id", "circuit_id", "twin_id"} for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    if any(not item.provider or len(item.provider) > 128 for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    if any(not item.contract_version or len(item.contract_version) > 128 for item in capabilities):
        raise RuntimeError("capability contract is invalid")
    return capabilities


def list_capabilities() -> tuple[Capability, ...]:
    return _parse_capabilities(load_capabilities().get("capabilities") or [])


def capability(capability_id: str) -> Capability:
    if not isinstance(capability_id, str) or not capability_id or len(capability_id) > 128:
        raise KeyError("invalid capability id")
    for item in list_capabilities():
        if item.id == capability_id:
            return item
    raise KeyError(f"unknown capability {capability_id!r}")
