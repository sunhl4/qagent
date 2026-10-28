from __future__ import annotations

import json
import math
from typing import Any


class StrictJsonError(ValueError):
    """JSON is syntactically valid-looking but violates the strict wire contract."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise StrictJsonError(f"non-finite JSON number {value!r} is not allowed")


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise StrictJsonError("non-finite JSON number is not allowed")
    return result


def _validate_unicode(value: Any) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise StrictJsonError("JSON input exceeds maximum nesting depth")
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise StrictJsonError("JSON strings must contain valid Unicode") from exc
        elif isinstance(item, dict):
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def loads(value: str | bytes | bytearray) -> Any:
    """Reject duplicate fields, non-finite numbers and malformed Unicode."""

    if not isinstance(value, (str, bytes, bytearray)):
        raise StrictJsonError("JSON input must be text or bytes")
    try:
        result = json.loads(value, object_pairs_hook=_object, parse_constant=_constant, parse_float=_float)
    except RecursionError as exc:
        raise StrictJsonError("JSON input exceeds maximum nesting depth") from exc
    _validate_unicode(result)
    return result
