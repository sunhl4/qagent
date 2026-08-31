from __future__ import annotations

from dataclasses import dataclass, field

STATUS_RESERVED = "reserved"
STATUS_NATIVE = "native"
STATUS_WIRED = "wired"


@dataclass(frozen=True)
class EnginePack:
    id: str
    kind: str
    label: str
    status: str
    tools: list[str] = field(default_factory=list)
    identity_fields: list[str] = field(default_factory=list)
    vibe: str = ""
    home: str | None = None
