from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qagent.models.types import EvalCase, ProductEvalCase, Slot, ToolSpec

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_slots() -> list[Slot]:
    raw = load_json(CONTRACTS / "slots.json")
    return [
        Slot(
            id=s["id"],
            phase=s["phase"],
            status=s["status"],
            title=s["title"],
            fill=s["fill"],
            review=s.get("review", ""),
            note=s.get("note", ""),
        )
        for s in raw["slots"]
    ]


def load_presets() -> dict[str, Any]:
    return load_json(CONTRACTS / "presets.json")


def load_policy() -> dict[str, Any]:
    return load_json(CONTRACTS / "policy.json")


def load_tool_catalog() -> list[ToolSpec]:
    catalog = load_json(CONTRACTS / "tools" / "catalog.json")
    out: list[ToolSpec] = []
    for row in catalog["tools"]:
        schema_path = CONTRACTS / "tools" / row["schema"]
        out.append(
            ToolSpec(
                name=row["name"],
                slot=row["slot"],
                schema_file=row["schema"],
                schema=load_json(schema_path),
            )
        )
    return out


def load_engine_catalog() -> dict:
    return load_json(CONTRACTS / "engines" / "catalog.json")


def load_company() -> dict:
    return load_json(CONTRACTS / "company.json")


def load_gov() -> dict:
    return load_json(CONTRACTS / "gov.json")


def load_port_catalog() -> dict:
    return load_json(CONTRACTS / "ports.json")


def load_eval_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    for path in sorted((CONTRACTS / "eval").glob("E*.json")):
        raw = load_json(path)
        cases.append(
            EvalCase(
                id=raw["id"],
                phase=raw["phase"],
                status=raw["status"],
                preset=raw["preset"],
                slot=raw["slot"],
                prompt=raw["prompt"],
                allowed_tools=list(raw.get("allowed_tools") or []),
                assertions=list(raw.get("assertions") or []),
                invoke_tool=raw.get("invoke_tool"),
                invoke_args=dict(raw.get("invoke_args") or {}),
            )
        )
    return cases


def load_product_eval_cases() -> list[ProductEvalCase]:
    cases: list[ProductEvalCase] = []
    for path in sorted((CONTRACTS / "eval").glob("Q-*.json")):
        raw = load_json(path)
        cases.append(
            ProductEvalCase(
                id=raw["id"],
                kind=str(raw.get("kind") or ""),
                status=str(raw.get("status") or "draft"),
                phase=str(raw.get("phase") or "G3"),
                preset=str(raw.get("preset") or "lab"),
                prompt=str(raw.get("prompt") or ""),
                allowed_tools=list(raw.get("allowed_tools") or []),
                qagent_must=list(raw.get("qagent_must") or []),
                qagent_must_not=list(raw.get("qagent_must_not") or []),
                codex_baseline=str(raw.get("codex_baseline") or "may_fail"),
                assertions=list(raw.get("assertions") or []),
            )
        )
    return cases
