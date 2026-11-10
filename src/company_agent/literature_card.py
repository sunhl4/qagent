"""Draft a later experiment card from a local val_loss reproduction.

The draft keeps the metric and the change path, opens a new experiment id and
idempotency key, and leaves the reproduced-baseline checkbox unset. Compile
omits the idempotency key; the later approved call keeps it. Training time is
not copied.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from company_agent.literature import LiteratureError

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PATH = re.compile(r"^[A-Za-z0-9_./-]{1,120}$")
_MARKERS = ("secret", "token", "password", "prompt", "credential", "api_key")
_LOCAL_RESOURCES = frozenset({"cpu", "gpu"})


def draft_scale_card(
    local: Mapping[str, Any],
    *,
    experiment_id: str,
    idempotency_key: str,
    hypothesis: str,
    falsifier: str,
) -> dict[str, Any]:
    """Return one new card. It does not run, submit, or mark a baseline reproduced."""

    if local.get("primary_metric") != "val_loss":
        raise LiteratureError("scale card requires a val_loss baseline")
    if local.get("resource_type") not in _LOCAL_RESOURCES:
        raise LiteratureError("scale card must start from a local baseline")
    if local.get("baseline_reproduced") is not True:
        raise LiteratureError("scale card requires a reproduced local baseline")
    local_experiment = _ident(local.get("experiment_id"), "experiment_id")
    if _ID.fullmatch(experiment_id) is None or experiment_id == local_experiment:
        raise LiteratureError("scale card needs a new experiment id")
    local_key = local.get("idempotency_key")
    if local_key is not None and _ident(local_key, "idempotency_key") == idempotency_key:
        raise LiteratureError("scale card needs a new idempotency key")
    if _ID.fullmatch(idempotency_key) is None:
        raise LiteratureError("scale card needs a new idempotency key")
    local_hypothesis = _text(local.get("hypothesis"), "hypothesis", 240)
    hypothesis_text = _text(hypothesis, "hypothesis", 240)
    if hypothesis_text.casefold() == local_hypothesis.casefold():
        raise LiteratureError("scale card needs a new hypothesis")
    changed = _path(local.get("changed_path"))
    metric = _metric(local.get("baseline_metric"))
    direction = local.get("direction")
    if direction not in {"minimize", "maximize"}:
        raise LiteratureError("direction is invalid")
    card: dict[str, Any] = {
        "tenant_id": _ident(local.get("tenant_id"), "tenant_id"),
        "task_id": _ident(local.get("task_id"), "task_id"),
        "experiment_id": experiment_id,
        "idempotency_key": idempotency_key,
        "hypothesis": hypothesis_text,
        "falsifier": _text(falsifier, "falsifier", 240),
        "baseline_name": _text(local.get("baseline_name"), "baseline_name", 80),
        "baseline_source": _text(local.get("baseline_source"), "baseline_source", 80),
        "baseline_metric": metric,
        "baseline_reproduced": False,
        "changed_path": changed,
        "primary_metric": "val_loss",
        "direction": direction,
        "resource_type": "hpc",
        "max_cost": _money(local.get("max_cost")),
        "max_attempts": _attempts(local.get("max_attempts")),
    }
    project = local.get("project_id")
    if project not in (None, ""):
        card["project_id"] = _ident(project, "project_id")
    if "min_seeds" in local and local.get("min_seeds") is not None:
        card["min_seeds"] = _seeds(local.get("min_seeds"))
    return card


def _text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise LiteratureError(f"{field} is invalid")
    text = value.strip()
    if not text or len(text) > limit or any(marker in text.casefold() for marker in _MARKERS):
        raise LiteratureError(f"{field} is invalid")
    return text


def _ident(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value.strip()) is None:
        raise LiteratureError(f"{field} is invalid")
    return value.strip()


def _path(value: object) -> str:
    if not isinstance(value, str):
        raise LiteratureError("changed_path is invalid")
    text = value.strip()
    if _PATH.fullmatch(text) is None or ".." in text or text.startswith("/"):
        raise LiteratureError("changed_path is invalid")
    return text


def _metric(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise LiteratureError("baseline metric is invalid")
    if not -1_000_000 <= float(value) <= 1_000_000:
        raise LiteratureError("baseline metric is invalid")
    return value


def _money(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LiteratureError("research cost is invalid")
    if not 1 <= value <= 100_000:
        raise LiteratureError("research cost is invalid")
    return value


def _attempts(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
        raise LiteratureError("max_attempts is invalid")
    return value


def _seeds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in {1, 2, 3}:
        raise LiteratureError("min_seeds is invalid")
    return value
