#!/usr/bin/env python3
"""Pick the next reviewed development candidate from catalog and history.

Kept and discarded ids are finished. The next item is the highest priority
item still open. An empty list means the reviewed catalog is exhausted.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_LEDGER_DECISION = re.compile(r"`([a-z0-9-]+)`\s+(keep|discard)\b")
_PUBLIC_FIELDS = ("id", "hypothesis", "cost", "kind", "status", "allowed_paths", "edits")


def _decision(row: dict[str, Any]) -> str:
    decision = row.get("decision")
    if isinstance(decision, dict):
        return str(decision.get("action") or "")
    if isinstance(decision, str):
        return decision
    return str(row.get("action") or "")


def _ledger_ids(text: str) -> set[str]:
    return {match.group(1) for match in _LEDGER_DECISION.finditer(text)}


def propose_from_history(
    history: list[dict[str, Any]],
    catalog: dict[str, Any],
    ledger_text: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    done = {item for item in _ledger_ids(ledger_text)}
    for row in history:
        if _decision(row) in {"keep", "discard"}:
            identifier = str(row.get("candidate_id") or row.get("id") or "")
            if identifier:
                done.add(identifier)
    pending: list[dict[str, Any]] = []
    for item in catalog.get("candidates", []):
        if not isinstance(item, dict):
            continue
        if item.get("decision") in {"keep", "discard"}:
            done.add(str(item.get("id") or ""))
        if str(item.get("id") or "") not in done:
            pending.append(item)
    pending.sort(key=lambda item: (-int(item.get("priority", 0)), str(item.get("id"))))
    if not pending:
        return [], {"next": None, "reason": "requires_new_review", "remaining": []}
    chosen = pending[0]
    public = {key: chosen[key] for key in _PUBLIC_FIELDS if key in chosen}
    diagnosis = {
        "next": public.get("id"),
        "reason": public.get("hypothesis"),
        "remaining": [str(item.get("id")) for item in pending],
    }
    return [public], diagnosis


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose the next development candidate")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--history", default="")
    parser.add_argument("--ledger", default="")
    args = parser.parse_args(argv)
    history_path = Path(args.history) if args.history else None
    history = []
    if history_path is not None and history_path.is_file():
        loaded = json.loads(history_path.read_text(encoding="utf-8"))
        history = loaded if isinstance(loaded, list) else []
    ledger_path = Path(args.ledger) if args.ledger else None
    ledger_text = ""
    if ledger_path is not None and ledger_path.is_file():
        ledger_text = ledger_path.read_text(encoding="utf-8")
    catalog = _read_json(Path(args.catalog), {"candidates": []})
    if not isinstance(catalog, dict):
        raise ValueError("catalog must be an object")
    chosen, diagnosis = propose_from_history(history, catalog, ledger_text)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(chosen, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    diagnosis_path = output.with_name("diagnosis.json")
    diagnosis_path.write_text(
        json.dumps(diagnosis, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(diagnosis.get("reason") or "requires_new_review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
