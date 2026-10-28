from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from company_agent.jsonutil import StrictJsonError, loads
from company_agent.schema import SchemaError, validate_json_schema

settings.register_profile("company", max_examples=40, derandomize=True, database=None, deadline=None)
settings.load_profile("company")
ROOT = Path(__file__).resolve().parents[1]
TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80)


@given(TEXT)
def test_unicode_roundtrips_strict_json(value):
    assert loads(json.dumps(value, ensure_ascii=False)) == value


@given(st.integers(min_value=-1000, max_value=1000))
def test_boolean_never_satisfies_numeric_schema(number):
    validate_json_schema(number, {"type": "integer"})
    for boolean in (True, False):
        with pytest.raises(SchemaError):
            validate_json_schema(boolean, {"type": "integer", "minimum": number - 1})
        with pytest.raises(SchemaError):
            validate_json_schema(number, {"const": boolean})


@given(TEXT, st.integers())
def test_duplicate_fields_fail_including_unicode_names(key, value):
    encoded = json.dumps(key)
    with pytest.raises(StrictJsonError):
        loads("{" + encoded + ":0," + encoded + ":" + str(value) + "}")


@given(st.integers(min_value=65, max_value=100))
def test_excessive_json_depth_is_bounded(depth):
    with pytest.raises(StrictJsonError):
        loads("[" * depth + "0" + "]" * depth)


@given(st.sampled_from([None, True, 3, [], {"type": "string", "unsupported": True}]))
def test_absent_optional_schema_branch_is_still_checked(child):
    with pytest.raises(SchemaError):
        validate_json_schema({}, {"type": "object", "properties": {"optional": child},
                                  "additionalProperties": False})


@given(st.lists(TEXT, max_size=8))
@settings(max_examples=15)
def test_javascript_and_python_preserve_unicode_json(values):
    program = "const v=JSON.parse(process.argv[1]); console.log(JSON.stringify(v));"
    result = subprocess.run(["node", "--input-type=module", "-e", program, json.dumps(values)],
                            capture_output=True, text=True, timeout=10, check=True)
    assert loads(result.stdout) == values


@given(st.integers(min_value=0, max_value=1000), st.integers(min_value=1, max_value=1000))
@settings(max_examples=12)
def test_schema_projection_drops_only_documented_bounds(minimum, width):
    schema = {"type": "object", "properties": {"value": {"type": "integer", "minimum": minimum,
              "maximum": minimum + width}}, "required": ["value"], "additionalProperties": False}
    uri = (ROOT / "packages/company-agent-core/src/runtime.js").as_uri()
    program = f"import {{ dshSchema }} from {json.dumps(uri)}; " \
              "console.log(JSON.stringify(dshSchema(JSON.parse(process.argv[1]))));"
    result = subprocess.run(["node", "--input-type=module", "-e", program, json.dumps(schema)],
                            capture_output=True, text=True, check=True, timeout=10)
    assert loads(result.stdout) == {"type": "object", "properties": {"value": {"type": "integer"}},
                                    "required": ["value"], "additionalProperties": False}
    with pytest.raises(SchemaError):
        validate_json_schema({"value": minimum - 1}, schema)
