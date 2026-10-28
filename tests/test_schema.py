from __future__ import annotations

import pytest

from company_agent.schema import SchemaError, validate_json_schema


def test_schema_rejects_unsupported_keywords() -> None:
    with pytest.raises(SchemaError, match="unsupported schema keywords"):
        validate_json_schema("x", {"type": "string", "format": "uuid"})


def test_schema_rejects_malformed_schema_metadata() -> None:
    with pytest.raises(SchemaError, match="required must be a unique array of strings"):
        validate_json_schema({}, {"type": "object", "required": "id"})
    with pytest.raises(SchemaError, match="description must be a string"):
        validate_json_schema("x", {"type": "string", "description": 1})
    with pytest.raises(SchemaError, match="properties must be an object"):
        validate_json_schema({}, {"type": "object", "properties": []})
    with pytest.raises(SchemaError, match="items must be an object schema"):
        validate_json_schema([], {"type": "array", "items": []})
    with pytest.raises(SchemaError, match="additionalProperties must be a boolean or object schema"):
        validate_json_schema(
            {},
            {"type": "object", "properties": {}, "additionalProperties": "yes"},
        )
    with pytest.raises(SchemaError, match="maxItems must be a non-negative integer"):
        validate_json_schema([], {"type": "array", "maxItems": -1})
    with pytest.raises(SchemaError, match="minimum must be a finite number"):
        validate_json_schema(1, {"type": "integer", "minimum": True})
    with pytest.raises(SchemaError, match="pattern is invalid"):
        validate_json_schema("x", {"type": "string", "pattern": "["})
    with pytest.raises(SchemaError, match="validation keywords without a type"):
        validate_json_schema({}, {"properties": {}})
    with pytest.raises(SchemaError, match="incompatible with object type"):
        validate_json_schema({}, {"type": "object", "minItems": 1})
    with pytest.raises(SchemaError, match="required references unknown property"):
        validate_json_schema(
            {},
            {
                "type": "object",
                "required": ["id"],
                "properties": {},
                "additionalProperties": False,
            },
        )
    with pytest.raises(SchemaError, match="enum must contain unique JSON values"):
        validate_json_schema("x", {"type": "string", "enum": ["x", "x"]})


def test_schema_requires_explicit_properties() -> None:
    with pytest.raises(SchemaError, match="properties must be explicit"):
        validate_json_schema({}, {"type": "object", "additionalProperties": True})


def test_schema_accepts_explicit_bounded_open_objects() -> None:
    schema = {"type": "object", "properties": {}, "maxProperties": 2, "additionalProperties": True}
    validate_json_schema({"algorithm": "test", "parameters": {"iterations": 2}}, schema)
    with pytest.raises(SchemaError, match="at most 2 properties"):
        validate_json_schema({"a": 1, "b": 2, "c": 3}, schema)


def test_schema_requires_explicit_additional_properties() -> None:
    with pytest.raises(SchemaError, match="additionalProperties must be explicit"):
        validate_json_schema({}, {"type": "object", "properties": {}})


def test_schema_rejects_unknown_nested_fields() -> None:
    schema = {
        "type": "object",
        "properties": {
            "row": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            }
        },
        "additionalProperties": False,
    }
    with pytest.raises(SchemaError, match="value.row has unknown fields"):
        validate_json_schema({"row": {"name": "ok", "secret": "bad"}}, schema)


def test_schema_rejects_boolean_as_number() -> None:
    with pytest.raises(SchemaError, match="must be a number"):
        validate_json_schema(True, {"type": "number"})


def test_schema_enforces_patterns_constants_and_bounds() -> None:
    schema = {
        "type": "object",
        "required": ["id", "provider", "shots"],
        "properties": {
            "id": {"type": "string", "pattern": "^asset_.+$"},
            "provider": {"type": "string", "const": "company"},
            "shots": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "additionalProperties": False,
    }
    validate_json_schema({"id": "asset_x", "provider": "company", "shots": 3}, schema)
    with pytest.raises(SchemaError, match="invalid format"):
        validate_json_schema({"id": "wrong", "provider": "company", "shots": 3}, schema)
    with pytest.raises(SchemaError, match="must equal"):
        validate_json_schema({"id": "asset_x", "provider": "other", "shots": 3}, schema)
    with pytest.raises(SchemaError, match="must be <= 10"):
        validate_json_schema({"id": "asset_x", "provider": "company", "shots": 11}, schema)


def test_schema_enforces_unique_array_items() -> None:
    validate_json_schema(
        ["asset_id", "circuit_id"],
        {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
    )
    with pytest.raises(SchemaError, match="must contain unique items"):
        validate_json_schema(
            ["asset_id", "asset_id"],
            {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        )
