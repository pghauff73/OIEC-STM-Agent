from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any, Mapping

from ourd.egcf.models import CommandDefinition

from .commands import CommandRequest, safe_default_modifiers
from .read_models import ReadOnlyEGCFRepository


FORBIDDEN_SHELL_PATTERN = re.compile(r"[;&|<>`$]|\$\(|\n|\r")


@dataclass(frozen=True)
class SemanticTerminalCommand:
    command_id: str
    inputs: Mapping[str, Any]
    capability_level: str
    risk: str
    approval_policy: str
    read_only: bool

    def request(self) -> CommandRequest:
        modifiers = safe_default_modifiers()
        if self.capability_level in {"C0", "C1"}:
            modifiers["dry_run"] = False
        elif self.capability_level == "C2":
            modifiers["dry_run"] = False
            modifiers["simulate"] = True
        return CommandRequest(
            command_id=self.command_id,
            inputs=dict(self.inputs),
            modifiers=modifiers,
        )


def parse_semantic_command(
    repository: ReadOnlyEGCFRepository,
    text: str,
) -> SemanticTerminalCommand:
    raw = text.strip()
    if not raw:
        raise ValueError("semantic command is empty")
    if FORBIDDEN_SHELL_PATTERN.search(raw):
        raise ValueError("shell metacharacters are not accepted by the semantic terminal")
    json_start = raw.find("{")
    if json_start >= 0:
        command_text = raw[:json_start].strip()
        input_text = raw[json_start:].strip()
    else:
        command_text = raw
        input_text = ""
    parts = shlex.split(command_text)
    if not parts:
        raise ValueError("semantic command is empty")
    first = parts.pop(0)
    if "." in first:
        command_name = first
    else:
        if not parts:
            raise ValueError("expected '<namespace> <verb> [JSON]' or '<command-id> [JSON]'")
        command_name = f"{first}.{parts.pop(0)}"
    definitions = [
        record
        for record in repository.list("command-definition", active_only=True)
        if isinstance(record, CommandDefinition)
        and command_name in {record.command_id, f"{record.namespace}.{record.name}", *record.aliases}
    ]
    if not definitions:
        raise ValueError(f"unknown semantic command: {command_name}")
    definitions.sort(key=lambda item: (item.version, item.object_id), reverse=True)
    definition = definitions[0]
    if not input_text:
        inputs: Mapping[str, Any] = {}
    else:
        try:
            parsed = json.loads(input_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"inputs must be one JSON object: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("semantic command inputs must be a JSON object")
        inputs = parsed
    capability_level = str(definition.capability_query.get("level", "C0"))
    return SemanticTerminalCommand(
        command_id=definition.command_id,
        inputs=inputs,
        capability_level=capability_level,
        risk=definition.risk_policy,
        approval_policy=definition.approval_policy,
        read_only=capability_level in {"C0", "C1", "C2"},
    )
