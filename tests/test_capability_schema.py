import pytest

from atlas_engine.capability_schema import validate_json_value


def test_validates_nested_object_and_array():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 2, "maxLength": 20},
            "limits": {
                "type": "array", "minItems": 1,
                "items": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
        "required": ["query", "limits"],
        "additionalProperties": False,
    }
    validate_json_value({"query": "Atlas", "limits": [1, 5]}, schema)


@pytest.mark.parametrize("value", [
    {"query": "x", "limits": [1]},
    {"query": "valid", "limits": [0]},
    {"query": "valid", "limits": [11]},
    {"query": "valid", "limits": [1], "admin": True},
    {"limits": [1]},
])
def test_rejects_invalid_nested_capability_input(value):
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 2},
            "limits": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 10}},
        },
        "required": ["query", "limits"],
        "additionalProperties": False,
    }
    with pytest.raises(ValueError):
        validate_json_value(value, schema)


def test_boolean_is_not_accepted_as_integer():
    with pytest.raises(ValueError, match="expected integer"):
        validate_json_value(True, {"type": "integer"})


def test_unknown_schema_keyword_fails_closed():
    with pytest.raises(ValueError, match="unsupported schema keywords"):
        validate_json_value("hello", {"type": "string", "pattern": ".*"})


def test_enum_and_const_are_enforced():
    validate_json_value("read_only", {"type": "string", "enum": ["read_only", "local_write"]})
    with pytest.raises(ValueError):
        validate_json_value("external_write", {"type": "string", "enum": ["read_only"]})
    with pytest.raises(ValueError):
        validate_json_value(2, {"type": "integer", "const": 1})
