from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["allow", "deny", "ask"]
SlotStatus = Literal["empty", "implemented", "passing"]


@dataclass(frozen=True)
class Slot:
    id: str
    phase: str
    status: SlotStatus
    title: str
    fill: str
    review: str = ""
    note: str = ""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    slot: str
    schema_file: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class EvalCase:
    id: str
    phase: str
    status: SlotStatus
    preset: str
    slot: str
    prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    invoke_tool: str | None = None
    invoke_args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductEvalCase:
    """Q-01 product cases. Not loaded by load_eval_cases() (E01–E21 stay isolated)."""

    id: str
    kind: str
    status: str
    phase: str
    preset: str
    prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    qagent_must: list[str] = field(default_factory=list)
    qagent_must_not: list[str] = field(default_factory=list)
    codex_baseline: str = "may_fail"
    assertions: list[dict[str, Any]] = field(default_factory=list)
