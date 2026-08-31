from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from qagent.models.handles import FOREIGN_PROVENANCE, HANDLE_TWIN, HANDLES

SCHEMA_HANDOFF = "qagent.handoff/v1"
PRESET_BOOT = "boot"
INTENT_CAP = 240
TWIN_RUN_TOOL = "ionstack_twin_run"

KIND_FORGED_TWIN = "forged_twin"
KIND_NO_EVIDENCE = "no_evidence"
KIND_LEAK = "leak"
KIND_FOREIGN_TWIN = "foreign_qccd_twin"

LEAK_KEYS = frozenset(
    {
        "pauli_terms",
        "bitstrings",
        "rows",
        "counts_full",
        "cal",
        "calibration",
        "shuttle",
        "ms_matrix",
    }
)
POOLS = ("policy", "provenance", "b3", "handles", "short_output")
# E23 is reserved empty by L1-03-pl. Governance five-pool is E28–E32.
GOV_EVAL_IDS = ("E28", "E29", "E30", "E31", "E32")
BOOT_TOOLS = (
    "qagent_list_engines",
    "qagent_pin_circuit",
    "qccd_docs_search",
    "ionstack_twin_identity",
)


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    message: str
    pool: str


@dataclass(frozen=True)
class Handoff:
    schema: str
    source_preset: str
    target_preset: str
    handles: Mapping[str, str]
    intent: str
    unresolved: tuple[str, ...] = ()
    handoff_id: str = ""
    source_session: str = ""

    def to_public(self) -> dict[str, Any]:
        handles = {key: self.handles[key] for key in HANDLES if self.handles.get(key)}
        row: dict[str, Any] = {
            "schema": self.schema,
            "source_preset": self.source_preset,
            "target_preset": self.target_preset,
            "handles": handles,
            "intent": self.intent,
            "unresolved": list(self.unresolved),
        }
        if self.handoff_id:
            row["handoff_id"] = self.handoff_id
        if self.source_session:
            row["source_session"] = self.source_session
        return row


def compact_intent(text: str, cap: int = INTENT_CAP) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= cap:
        return clean
    return clean[: cap - 1] + "…"


def only_handles(raw: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in HANDLES:
        value = str((raw or {}).get(key) or "").strip()
        if value:
            out[key] = value
    return out


def extra_handle_keys(raw: Mapping[str, Any] | None) -> tuple[str, ...]:
    return tuple(sorted(key for key in (raw or {}) if key not in HANDLES))


def b3_block(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    block = payload.get("b3")
    if isinstance(block, Mapping):
        return block
    return payload


def leak_paths(payload: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in LEAK_KEYS:
                found.append(path)
            found.extend(leak_paths(value, path))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            found.extend(leak_paths(value, f"{prefix}[{index}]"))
    return found


def may_carry_twin(tool: str) -> bool:
    return tool == TWIN_RUN_TOOL


def foreign_provenance(value: Any) -> bool:
    return value in FOREIGN_PROVENANCE or value == "pennylane"


def payload_has_twin(payload: Mapping[str, Any]) -> bool:
    if HANDLE_TWIN in payload:
        return True
    for value in payload.values():
        if isinstance(value, Mapping) and payload_has_twin(value):
            return True
    return False
