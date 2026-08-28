from __future__ import annotations

from dataclasses import MISSING, fields
from typing import Any, Dict, Type

from .errors import SchemaError
from .models import RECORD_TYPES, RecordMixin


FORBIDDEN_DEFINITION_FIELDS = {
    "callback",
    "callable",
    "executor",
    "function",
    "handler",
    "subprocess",
}


def validate_record_payload(object_type: str, payload: Dict[str, Any]) -> None:
    record_class = RECORD_TYPES.get(object_type)
    if record_class is None:
        raise SchemaError(f"unknown EGCF object type: {object_type}")
    if not isinstance(payload, dict):
        raise SchemaError(f"{object_type} payload must be an object")
    definitions = {item.name: item for item in fields(record_class)}
    unknown = sorted(set(payload) - set(definitions))
    if unknown:
        raise SchemaError(f"unknown {object_type} fields: {unknown}")
    missing = sorted(
        item.name
        for item in definitions.values()
        if item.default is MISSING
        and item.default_factory is MISSING
        and item.name not in payload
    )
    if missing:
        raise SchemaError(f"missing {object_type} fields: {missing}")
    if object_type == "command-definition":
        forbidden = sorted(FORBIDDEN_DEFINITION_FIELDS.intersection(payload))
        if forbidden:
            raise SchemaError(f"command definitions cannot reference executors: {forbidden}")


def construct_record(object_type: str, payload: Dict[str, Any]) -> RecordMixin:
    validate_record_payload(object_type, payload)
    record_class: Type[RecordMixin] = RECORD_TYPES[object_type]
    return record_class(**payload)


def validate_json_value(schema: Dict[str, Any], value: Any, path: str = "$input") -> None:
    if isinstance(value, dict) and "$from" in value:
        unknown = sorted(set(value) - {"$from", "path", "default"})
        if unknown:
            raise SchemaError(f"{path} reference has unknown fields: {unknown}")
        if not isinstance(value.get("$from"), str):
            raise SchemaError(f"{path} reference $from must be string")
        if "path" in value and not (
            isinstance(value["path"], list)
            and all(isinstance(item, (str, int)) for item in value["path"])
        ):
            raise SchemaError(f"{path} reference path must be an array of strings or integers")
        return
    expected = schema.get("type")
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }
    expected_types = expected if isinstance(expected, list) else [expected]
    expected_types = [item for item in expected_types if item in type_map]
    if expected_types:
        matches = False
        for expected_type in expected_types:
            python_type = type_map[expected_type]
            if expected_type in {"integer", "number"} and isinstance(value, bool):
                continue
            if isinstance(value, python_type):
                matches = True
                break
        if not matches:
            label = expected_types[0] if len(expected_types) == 1 else f"one of {expected_types}"
            raise SchemaError(f"{path} must be {label}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{path} must be one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        raise SchemaError(f"{path} must equal {schema['const']!r}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        if missing:
            raise SchemaError(f"{path} is missing required fields: {missing}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise SchemaError(f"{path} has unknown fields: {unknown}")
        for key, item in value.items():
            if key in properties and properties[key]:
                validate_json_value(properties[key], item, f"{path}.{key}")
    if isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            validate_json_value(schema["items"], item, f"{path}[{index}]")
