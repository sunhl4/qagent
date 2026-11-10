"""Short local bridges: sign receipt, catalog replay, and the device window."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from company_agent.dossier import previous_metric
from company_agent.providers import ProviderError, client_by_provider
from company_agent.receipts import identity_age_seconds
from company_agent.workspace_files import WorkspaceFileError, root as workspace_root


def sign_receipt(arguments: Mapping[str, Any]) -> dict[str, Any]:
    approval_id = arguments["approval_id"]
    unknown = arguments.get("unknown") is True
    body = {
        "approval_id": approval_id,
        "asset_id": arguments.get("asset_id") if isinstance(arguments.get("asset_id"), str) else "",
        "circuit_id": arguments.get("circuit_id") if isinstance(arguments.get("circuit_id"), str) else "",
        "twin_id": arguments.get("twin_id") if isinstance(arguments.get("twin_id"), str) else "",
        "unknown": unknown,
    }
    try:
        root = workspace_root()
        folder = root / ".company-agent" / "sign-receipts"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{approval_id}.json"
        path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        relative = path.relative_to(root).as_posix()
    except (WorkspaceFileError, OSError, ValueError) as exc:
        raise ValueError("sign receipt is unavailable") from exc
    if len(relative) > 180:
        raise ValueError("sign receipt is unavailable")
    return {"ok": True, "path": relative, "unknown": unknown}


def catalog_replay(arguments: Mapping[str, Any]) -> dict[str, Any]:
    client = client_by_provider("independent-simulator")
    if not client.configured():
        raise ValueError("simulator is not configured")
    items: list[dict[str, Any]] = []
    stopped = False
    unknown = False
    for circuit_id in arguments["circuit_ids"]:
        try:
            result = client.invoke("circuit.simulate", {"circuit_id": circuit_id, "shots": 1})
        except ProviderError:
            stopped = True
            unknown = True
            break
        metric, current = _summary_metric(result)
        if metric is None or current is None:
            stopped = True
            unknown = True
            break
        previous = previous_metric(circuit_id, metric)
        items.append({
            "circuit_id": circuit_id,
            "metric": metric,
            "previous": current if previous is None else previous,
            "current": current,
        })
    return {
        "ok": True,
        "stopped": stopped,
        "unknown": unknown,
        "compared": len(items),
        "items": items,
    }


def _summary_metric(result: Mapping[str, Any]) -> tuple[str | None, float | None]:
    summary = result.get("summary")
    if isinstance(summary, dict):
        duration = summary.get("duration_ms")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            return "duration_ms", float(duration)
    shots = result.get("shots_actual")
    if isinstance(shots, int) and not isinstance(shots, bool):
        return "shots", float(shots)
    return None, None


def device_window(_arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = str(os.environ.get("COMPANY_AGENT_DEVICE_WINDOW") or "").strip()
    if not raw:
        raise ValueError("device window is unavailable")
    path = Path(raw)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("device window is unavailable") from exc
    if not isinstance(payload, dict):
        raise ValueError("device window is unavailable")
    bookable = payload.get("bookable")
    maintenance = payload.get("maintenance")
    if not isinstance(bookable, bool) or not isinstance(maintenance, bool):
        raise ValueError("device window is unavailable")
    age = identity_age_seconds()
    return {
        "bookable": bookable,
        "maintenance": maintenance,
        "identity_age_seconds": -1 if age is None else min(age, 9007199254740991),
        "identity_known": age is not None,
    }
