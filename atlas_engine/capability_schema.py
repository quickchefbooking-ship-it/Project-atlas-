"""Fail-closed validator for the bounded JSON Schema subset used by capabilities."""
from __future__ import annotations

import math
from typing import Any, Mapping


_SUPPORTED = {
    "type", "properties", "required", "additionalProperties", "items",
    "enum", "const", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems",
    "uniqueItems", "description", "title", "default",
}
_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "null": type(None),
}


def _matches_type(value: Any, expected: str) -> bool:
    if expected not in _TYPES:
        raise ValueError(f"Unsupported JSON Schema type: {expected}")
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float) and math.isfinite(value)
    if expected == "boolean":
        return type(value) is bool
    return isinstance(value, _TYPES[expected])


def validate_json_value(value: Any, schema: Mapping[str, Any], *, path: str = "$") -> None:
    """Validate data against a deliberately small schema subset; unknown keywords fail closed."""
    if not isinstance(schema, Mapping) or schema.get("type") not in _TYPES:
        raise ValueError(f"{path}: schema must declare a supported type")
    unsupported = set(schema) - _SUPPORTED
    if unsupported:
        raise ValueError(f"{path}: unsupported schema keywords: {', '.join(sorted(unsupported))}")
    expected = schema["type"]
    if not _matches_type(value, expected):
        raise ValueError(f"{path}: expected {expected}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: value is not an allowed enum member")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: value does not match const")

    if expected == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", ())
        if not isinstance(properties, Mapping) or not isinstance(required, (list, tuple)):
            raise ValueError(f"{path}: invalid object schema")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"{path}: missing required properties: {', '.join(missing)}")
        additional = schema.get("additionalProperties", True)
        if additional is False:
            extras = set(value) - set(properties)
            if extras:
                raise ValueError(f"{path}: undeclared properties: {', '.join(sorted(extras))}")
        elif additional is not True:
            raise ValueError(f"{path}: additionalProperties must be boolean")
        for key, item in value.items():
            if key in properties:
                validate_json_value(item, properties[key], path=f"{path}.{key}")

    elif expected == "array":
        items_schema = schema.get("items")
        if items_schema is not None:
            for index, item in enumerate(value):
                validate_json_value(item, items_schema, path=f"{path}[{index}]")
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path}: array is shorter than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path}: array exceeds maxItems")
        if schema.get("uniqueItems") is True:
            try:
                if len({repr(item) for item in value}) != len(value):
                    raise ValueError(f"{path}: array items must be unique")
            except TypeError as exc:
                raise ValueError(f"{path}: array uniqueness cannot be checked") from exc

    elif expected == "string":
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path}: string exceeds maxLength")

    elif expected in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path}: number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path}: number exceeds maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path}: number is not above exclusiveMinimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise ValueError(f"{path}: number is not below exclusiveMaximum")
