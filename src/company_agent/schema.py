from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

_OBJECT_KEYWORDS = {"properties", "required", "additionalProperties", "minProperties", "maxProperties"}
_ARRAY_KEYWORDS = {"items", "minItems", "maxItems", "uniqueItems"}
_STRING_KEYWORDS = {"minLength", "maxLength", "pattern"}
_NUMBER_KEYWORDS = {"minimum", "maximum"}
_VALIDATION_KEYWORDS = _OBJECT_KEYWORDS | _ARRAY_KEYWORDS | _STRING_KEYWORDS | _NUMBER_KEYWORDS
_COMMON_KEYWORDS = {
    "type", "const", "enum", "title", "description", "default", "deprecated", "readOnly", "writeOnly",
}
_TYPE_KEYWORDS = {
    "object": _OBJECT_KEYWORDS,
    "array": _ARRAY_KEYWORDS,
    "string": _STRING_KEYWORDS,
    "number": _NUMBER_KEYWORDS,
    "integer": _NUMBER_KEYWORDS,
    "boolean": set(),
    "null": set(),
}
_MAX_SCHEMA_DEPTH = 32


class SchemaError(ValueError):
    """One JSON value or schema violates the supported contract subset."""


def _join(path: str, part: object) -> str:
    return f"{path}.{part}" if path else str(part)


def _json_identity(value: Any, depth: int = 0) -> tuple:
    """JSON equality distinguishes booleans from numbers, but not 1 from 1.0."""

    if depth > _MAX_SCHEMA_DEPTH:
        raise SchemaError("JSON value exceeds maximum nesting depth")
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise SchemaError("JSON value must be finite")
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_json_identity(item, depth + 1) for item in value))
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return ("object", tuple((key, _json_identity(value[key], depth + 1)) for key in sorted(value)))
    raise SchemaError("value must be JSON")


def _bounds(schema: Mapping[str, Any], low: str, high: str, path: str, *, numeric: bool = False) -> None:
    for label in (low, high):
        if label not in schema:
            continue
        bound = schema[label]
        if numeric:
            if (
                not isinstance(bound, (int, float)) or isinstance(bound, bool)
                or (isinstance(bound, float) and not math.isfinite(bound))
            ):
                raise SchemaError(f"{path}.{label} must be a finite number")
        elif not isinstance(bound, int) or isinstance(bound, bool) or bound < 0:
            raise SchemaError(f"{path}.{label} must be a non-negative integer")
    if low in schema and high in schema and schema[low] > schema[high]:
        raise SchemaError(f"{path} has inconsistent {low}/{high} bounds")


def validate_schema_definition(schema: Mapping[str, Any], *, path: str = "value", depth: int = 0) -> None:
    """Validate every branch, including optional properties absent from the value."""

    if depth > _MAX_SCHEMA_DEPTH:
        raise SchemaError(f"{path} schema exceeds maximum nesting depth")
    if not isinstance(schema, Mapping):
        raise SchemaError(f"{path} schema must be an object")
    if len(schema) > 64:
        raise SchemaError(f"{path} schema contains too many keywords")
    unknown = set(schema) - _COMMON_KEYWORDS - _VALIDATION_KEYWORDS
    if unknown:
        raise SchemaError(f"{path} uses unsupported schema keywords: {sorted(unknown)}")
    for annotation in ("title", "description"):
        if annotation in schema and not isinstance(schema[annotation], str):
            raise SchemaError(f"{path}.{annotation} must be a string")
    for flag in ("deprecated", "readOnly", "writeOnly"):
        if flag in schema and not isinstance(schema[flag], bool):
            raise SchemaError(f"{path}.{flag} must be a boolean")
    if "required" in schema and (
        not isinstance(schema["required"], list)
        or any(not isinstance(item, str) for item in schema["required"])
        or len(schema["required"]) != len(set(schema["required"]))
    ):
        raise SchemaError(f"{path}.required must be a unique array of strings")
    for annotation in ("const", "default"):
        if annotation in schema:
            try:
                _json_identity(schema[annotation])
            except SchemaError as exc:
                raise SchemaError(f"{path}.{annotation} must be a JSON value") from exc
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not enum:
            raise SchemaError(f"{path}.enum must be a non-empty array")
        identities = [_json_identity(item) for item in enum]
        if len(identities) != len(set(identities)):
            raise SchemaError(f"{path}.enum must contain unique JSON values")
    expected = schema.get("type")
    if "type" in schema and not isinstance(expected, str):
        raise SchemaError(f"{path}.type must be a string")
    if expected is None:
        if set(schema) & _VALIDATION_KEYWORDS:
            raise SchemaError(f"{path} uses validation keywords without a type")
        return
    if expected not in _TYPE_KEYWORDS:
        raise SchemaError(f"{path} uses unsupported schema type {expected!r}")
    if set(schema) & (_VALIDATION_KEYWORDS - _TYPE_KEYWORDS[expected]):
        raise SchemaError(f"{path} uses keywords incompatible with {expected} type")
    if expected == "object":
        if "properties" not in schema:
            raise SchemaError(f"{path}.properties must be explicit")
        properties = schema["properties"]
        if not isinstance(properties, Mapping):
            raise SchemaError(f"{path}.properties must be an object")
        if "additionalProperties" not in schema:
            raise SchemaError(f"{path}.additionalProperties must be explicit")
        additional = schema["additionalProperties"]
        if not isinstance(additional, (bool, Mapping)):
            raise SchemaError(f"{path}.additionalProperties must be a boolean or object schema")
        for field in schema.get("required", []):
            if field not in properties:
                raise SchemaError(f"{path}.required references unknown property {field!r}")
        _bounds(schema, "minProperties", "maxProperties", path)
        for field, child in properties.items():
            if not isinstance(field, str):
                raise SchemaError(f"{path}.properties names must be strings")
            validate_schema_definition(child, path=_join(path, field), depth=depth + 1)
        if isinstance(additional, Mapping):
            validate_schema_definition(additional, path=f"{path}.additionalProperties", depth=depth + 1)
    elif expected == "array":
        _bounds(schema, "minItems", "maxItems", path)
        if "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
            raise SchemaError(f"{path}.uniqueItems must be a boolean")
        if "items" not in schema:
            raise SchemaError(f"{path}.items must be explicit")
        if not isinstance(schema["items"], Mapping):
            raise SchemaError(f"{path}.items must be an object schema")
        validate_schema_definition(schema["items"], path=f"{path}.items", depth=depth + 1)
    elif expected == "string":
        _bounds(schema, "minLength", "maxLength", path)
        if "pattern" in schema:
            if not isinstance(schema["pattern"], str):
                raise SchemaError(f"{path}.pattern must be a string")
            try:
                re.compile(schema["pattern"])
            except re.error as exc:
                raise SchemaError(f"{path}.pattern is invalid") from exc
    elif expected in {"number", "integer"}:
        _bounds(schema, "minimum", "maximum", path, numeric=True)


def validate_json_schema(value: Any, schema: Mapping[str, Any], *, path: str = "value") -> None:
    """Validate the bounded JSON Schema subset used by Company Agent contracts."""

    validate_schema_definition(schema, path=path)
    _validate_value(value, schema, path)


def _validate_value(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if "const" in schema and _json_identity(value) != _json_identity(schema["const"]):
        raise SchemaError(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and _json_identity(value) not in {_json_identity(item) for item in schema["enum"]}:
        raise SchemaError(f"{path} must be one of {schema['enum']!r}")
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise SchemaError(f"{path} must be an object with string keys")
        if len(value) > 10_000:
            raise SchemaError(f"{path} contains too many properties")
        properties = schema["properties"]
        for field in schema.get("required", []):
            if field not in value:
                raise SchemaError(f"{_join(path, field)} is required")
        additional = schema["additionalProperties"]
        unknown = set(value) - set(properties)
        if unknown and additional is False:
            raise SchemaError(f"{path} has unknown fields: {sorted(unknown)}")
        _validate_size(len(value), schema, "minProperties", "maxProperties", path, "properties")
        for field, item in value.items():
            child = properties.get(field, additional)
            if isinstance(child, Mapping):
                _validate_value(item, child, _join(path, field))
    elif expected == "array":
        if not isinstance(value, list):
            raise SchemaError(f"{path} must be an array")
        if len(value) > 10_000:
            raise SchemaError(f"{path} contains too many items")
        _validate_size(len(value), schema, "minItems", "maxItems", path, "items")
        if schema.get("uniqueItems") is True:
            identities = [_json_identity(item) for item in value]
            if len(identities) != len(set(identities)):
                raise SchemaError(f"{path} must contain unique items")
        for index, item in enumerate(value):
            _validate_value(item, schema["items"], _join(path, index))
    elif expected == "string":
        if not isinstance(value, str):
            raise SchemaError(f"{path} must be a string")
        if len(value.encode("utf-8")) > 100_000:
            raise SchemaError(f"{path} is too long")
        _validate_size(len(value), schema, "minLength", "maxLength", path, "characters", verb="have")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise SchemaError(f"{path} has an invalid format")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise SchemaError(f"{path} must be a boolean")
    elif expected in {"number", "integer"}:
        valid_type = isinstance(value, int) if expected == "integer" else isinstance(value, (int, float))
        if not valid_type or isinstance(value, bool):
            article = "an" if expected == "integer" else "a"
            raise SchemaError(f"{path} must be {article} {expected}")
        if isinstance(value, int) and value.bit_length() > 4096:
            raise SchemaError(f"{path} is too large")
        if isinstance(value, float):
            if not math.isfinite(value):
                raise SchemaError(f"{path} must be finite")
            if value == 0.0 and math.copysign(1.0, value) < 0:
                raise SchemaError(f"{path} must not be negative zero")
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(f"{path} must be <= {schema['maximum']}")
    elif expected == "null" and value is not None:
        raise SchemaError(f"{path} must be null")


def _validate_size(
    size: int, schema: Mapping[str, Any], low: str, high: str, path: str, unit: str, *, verb: str = "contain",
) -> None:
    if low in schema and size < schema[low]:
        raise SchemaError(f"{path} must {verb} at least {schema[low]} {unit}")
    if high in schema and size > schema[high]:
        raise SchemaError(f"{path} must {verb} at most {schema[high]} {unit}")


def schema_types(schema: Mapping[str, Any]) -> Sequence[str]:
    """Return nested type names for contract linting tests."""

    validate_schema_definition(schema)
    found: list[str] = []

    def visit(node: Mapping[str, Any]) -> None:
        if isinstance(node.get("type"), str):
            found.append(node["type"])
        for child in node.get("properties", {}).values():
            visit(child)
        for key in ("additionalProperties", "items"):
            if isinstance(node.get(key), Mapping):
                visit(node[key])

    visit(schema)
    return tuple(found)
