"""Turn experiment-card cells into one compile call.

Office tools already read the table. This module accepts those cell values and
does not open a workbook. The research plugin does not open xlsx either.
"""

from __future__ import annotations

import re
from typing import Any

from company_agent.research_clock import compile_spec

_REQUIRED = (
    "tenant_id",
    "experiment_id",
    "task_id",
    "hypothesis",
    "falsifier",
    "baseline_name",
    "baseline_source",
    "baseline_metric",
    "baseline_reproduced",
    "changed_path",
    "primary_metric",
    "direction",
    "resource_type",
    "max_cost",
    "max_attempts",
)
_OPTIONAL = ("project_id", "baseline_train_time_seconds", "min_seeds")
_FIELDS = set(_REQUIRED) | set(_OPTIONAL)
_BOOL = {"true": True, "false": False, "是": True, "否": False}
_DIRECTIONS = {"minimize", "maximize"}
_RESOURCES = {"cpu", "gpu", "hpc", "qpu", "cloud"}
_METRIC = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PATH = re.compile(r"^[A-Za-z0-9_./-]{1,120}$")
_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class CardError(ValueError):
    """The cell table is not a compile input."""


def cells_to_args(rows: object) -> dict[str, Any]:
    if isinstance(rows, str) or not isinstance(rows, list) or not rows:
        raise CardError("experiment card cells are required")
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"field", "value"}:
            raise CardError("each cell needs field and value")
        field = row["field"]
        value = row["value"]
        if not isinstance(field, str) or field not in _FIELDS:
            raise CardError("unknown experiment card field")
        if not isinstance(value, str):
            raise CardError("experiment card values stay text until compile")
        if ".xlsx" in value.casefold():
            raise CardError("experiment card does not open xlsx")
        if field in found:
            raise CardError("duplicate experiment card field")
        found[field] = value.strip()
    if any(name not in found or found[name] == "" for name in _REQUIRED):
        raise CardError("experiment card is incomplete")
    args: dict[str, Any] = {}
    for field, value in found.items():
        if value == "" and field in _OPTIONAL:
            continue
        args[field] = _coerce(field, value)
    return args


def compile_cells(rows: object) -> dict[str, Any]:
    """Compile the cells. A failed compile does not start a run."""
    return compile_spec(cells_to_args(rows))


def _coerce(field: str, value: str) -> Any:
    if field in {"tenant_id", "experiment_id", "task_id", "project_id"}:
        if _IDENT.fullmatch(value) is None:
            raise CardError(f"{field} is invalid")
        return value
    if field in {"hypothesis", "falsifier", "baseline_name", "baseline_source"}:
        if not value or len(value) > (240 if field in {"hypothesis", "falsifier"} else 80):
            raise CardError(f"{field} is invalid")
        return value
    if field == "baseline_reproduced":
        if value.casefold() not in _BOOL and value not in _BOOL:
            raise CardError("baseline_reproduced is invalid")
        return _BOOL.get(value, _BOOL[value.casefold()])
    if field == "baseline_metric":
        return _number(value, field)
    if field == "baseline_train_time_seconds":
        number = _number(value, field)
        if number <= 0:
            raise CardError(f"{field} is invalid")
        return number
    if field == "min_seeds":
        number = _integer(value, field)
        if number not in {1, 2, 3}:
            raise CardError(f"{field} is invalid")
        return number
    if field == "changed_path":
        if _PATH.fullmatch(value) is None or ".." in value:
            raise CardError("changed_path is invalid")
        return value
    if field == "primary_metric":
        if _METRIC.fullmatch(value) is None:
            raise CardError("primary_metric is invalid")
        return value
    if field == "direction":
        if value not in _DIRECTIONS:
            raise CardError("direction is invalid")
        return value
    if field == "resource_type":
        if value not in _RESOURCES:
            raise CardError("resource_type is invalid")
        return value
    if field == "max_cost":
        number = _integer(value, field)
        if number < 1 or number > 100_000:
            raise CardError("max_cost is invalid")
        return number
    if field == "max_attempts":
        number = _integer(value, field)
        if number < 1 or number > 20:
            raise CardError("max_attempts is invalid")
        return number
    raise CardError("unknown experiment card field")


def _number(value: str, field: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise CardError(f"{field} is invalid") from exc
    if number != number or abs(number) > 1_000_000:
        raise CardError(f"{field} is invalid")
    return number


def _integer(value: str, field: str) -> int:
    if not value.isdigit():
        raise CardError(f"{field} is invalid")
    return int(value)
