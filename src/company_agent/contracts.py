from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["allow", "ask", "deny"]
Status = Literal["ok", "error", "needs_ask", "denied"]
CapabilityKind = Literal[
    "platform", "simulator", "compiler", "device", "compute", "cloud", "knowledge", "workflow"
]

HANDLES = ("asset_id", "circuit_id", "twin_id")
PROVIDER_PROTOCOL = "company-agent-provider/1.0"
HANDLE_PREFIXES = {"asset_id": "asset_", "circuit_id": "circ_", "twin_id": "twin_"}


@dataclass(frozen=True)
class Capability:
    id: str
    kind: CapabilityKind
    provider: str
    contract_version: str
    tools: tuple[str, ...]
    handles: tuple[str, ...] = ()
    approval: Literal["none", "human"] = "none"
    provenance: str = ""


@dataclass(frozen=True)
class ToolContract:
    name: str
    capability: str
    operation: str
    description: str
    parameters: Mapping[str, Any]
    forbidden_output_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class Invocation:
    tool: str
    decision: Decision
    status: Status
    payload: Mapping[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    capability: str
    tool: str
    needs: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    approval: Literal["none", "human"] = "none"
    arguments: Mapping[str, Any] = field(default_factory=dict)
    bindings: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
