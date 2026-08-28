from __future__ import annotations

import argparse
from dataclasses import fields, is_dataclass
import json
from pathlib import Path
import sys
import types
from typing import Any, Dict, Union, get_args, get_origin, get_type_hints

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ourd.egcf.catalog import COMMON_INPUT_FIELDS, command_catalog, command_contract
from ourd.egcf.models import RECORD_TYPES, RecordMixin


JSON_VALUE_TYPES = ["object", "array", "string", "number", "boolean", "null"]


def _schema_for_annotation(annotation: Any) -> Dict[str, Any]:
    if annotation is Any:
        return {"type": JSON_VALUE_TYPES}
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is type(None):
        return {"type": "null"}
    if isinstance(annotation, type) and issubclass(annotation, RecordMixin):
        return {"$ref": f"#/$defs/{annotation.object_type}"}
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {list, tuple, set}:
        item = _schema_for_annotation(arguments[0]) if arguments else {"type": JSON_VALUE_TYPES}
        return {"type": "array", "items": item}
    if origin is dict:
        value_schema = _schema_for_annotation(arguments[1]) if len(arguments) == 2 else {"type": JSON_VALUE_TYPES}
        return {"type": "object", "additionalProperties": value_schema}
    if origin in {Union, types.UnionType}:
        schemas = [_schema_for_annotation(item) for item in arguments]
        simple_types = [item.get("type") for item in schemas if set(item) == {"type"}]
        if len(simple_types) == len(schemas) and all(isinstance(item, str) for item in simple_types):
            return {"type": simple_types}
        return {"anyOf": schemas}
    if is_dataclass(annotation):
        return {"type": "object"}
    return {"type": JSON_VALUE_TYPES}


def render_object_schema() -> str:
    definitions: Dict[str, Any] = {}
    for object_type, record_class in sorted(RECORD_TYPES.items()):
        hints = get_type_hints(record_class)
        properties = {
            item.name: _schema_for_annotation(hints.get(item.name, Any))
            for item in fields(record_class)
        }
        definitions[object_type] = {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        }
    payload = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/ourd/egcf-v1/objects.schema.json",
        "title": "EGCFv1 Canonical Object Envelope",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "object_type", "object_id", "payload"],
        "properties": {
            "schema_version": {"const": 1},
            "object_type": {"type": "string"},
            "object_id": {
                "type": "string",
                "pattern": "^[a-z0-9-]+:sha256:[a-f0-9]{64}$",
            },
            "payload": {"type": "object"},
        },
        "oneOf": [
            {
                "properties": {
                    "object_type": {"const": object_type},
                    "payload": {"$ref": f"#/$defs/{object_type}"},
                }
            }
            for object_type in sorted(RECORD_TYPES)
        ],
        "$defs": definitions,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def command_contract_catalog() -> Dict[str, Any]:
    catalog = command_catalog()
    commands: Dict[str, Any] = {}
    for namespace, verbs in catalog["namespaces"].items():
        for verb in verbs:
            command_id = f"{namespace}.{verb}@1"
            contract = command_contract(namespace, verb)
            commands[command_id] = {
                "aliases": sorted(
                    alias for alias, target in catalog["aliases"].items() if target == command_id
                ),
                "required_inputs": contract["input_schema"]["required"],
                "preconditions": contract["preconditions"],
                "postconditions": contract["postconditions"],
                "invariants": contract["invariants"],
                "evidence_requirements": contract["evidence_requirements"],
                "settings": contract["settings"],
            }
    output_schema = command_contract("capability", "list")["output_schema"]
    return {
        "schema_version": 1,
        "authority": "ourd.egcf.catalog.command_contract",
        "input_field_schemas": COMMON_INPUT_FIELDS,
        "output_envelope_schema": output_schema,
        "commands": commands,
    }


def render_contract_catalog() -> str:
    return json.dumps(command_contract_catalog(), indent=2, sort_keys=True) + "\n"


def render_markdown_reference() -> str:
    payload = command_contract_catalog()
    lines = [
        "# EGCFv1 Generated Command Contracts",
        "",
        "This file is generated by `tools/generate_egcf_reference.py`. Do not edit it manually.",
        "",
        "| Command | Capability | Risk | Approval | Rollback | Required Inputs | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for command_id, contract in payload["commands"].items():
        settings = contract["settings"]
        required = ", ".join(f"`{item}`" for item in contract["required_inputs"]) or "none"
        evidence = ", ".join(f"`{item}`" for item in contract["evidence_requirements"])
        lines.append(
            f"| `{command_id}` | `{settings['level']}` | `{settings['risk']}` | "
            f"`{settings['approval']}` | `{settings['rollback']}` | {required} | {evidence} |"
        )
    lines.extend(
        [
            "",
            "Every input property has an explicit JSON type, unknown fields fail closed, and every",
            "definition carries preconditions, postconditions, invariants, and evidence requirements.",
            "",
        ]
    )
    return "\n".join(lines)


GENERATED = {
    Path("schemas/egcf-v1/objects.schema.json"): render_object_schema,
    Path("commands/v1/contracts.json"): render_contract_catalog,
    Path("docs/EGCFV1_GENERATED_REFERENCE.md"): render_markdown_reference,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic EGCFv1 schemas and references")
    parser.add_argument("--check", action="store_true", help="fail if checked-in generated files differ")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    failures = []
    for relative_path, renderer in GENERATED.items():
        target = args.output_root / relative_path
        expected = renderer()
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != expected:
                failures.append(relative_path.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8")
    if failures:
        print(json.dumps({"ok": False, "stale": failures}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "checked": args.check, "files": [str(item) for item in GENERATED]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
