from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Dict, Tuple

from .models import SlashCommand


FORBIDDEN_SHELL_PATTERN = re.compile(r"[;&|<>`$]|\$\(|\n|\r")


@dataclass(frozen=True)
class SlashCommandSpec:
    minimum_arguments: int = 0
    maximum_arguments: int = 0
    privileged: bool = False


SLASH_COMMAND_SPECS: Dict[str, SlashCommandSpec] = {
    "new": SlashCommandSpec(),
    "status": SlashCommandSpec(),
    "help": SlashCommandSpec(maximum_arguments=1),
    "model": SlashCommandSpec(maximum_arguments=1, privileged=True),
    "preflight": SlashCommandSpec(),
    "context": SlashCommandSpec(maximum_arguments=1),
    "scope": SlashCommandSpec(maximum_arguments=1),
    "summarize": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "summarise": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-help": SlashCommandSpec(),
    "writing-inspect": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-locate": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-reference": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-paraphrase": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-concepts": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-argument": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-outline": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-draft": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-validate": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "writing-write": SlashCommandSpec(minimum_arguments=2, maximum_arguments=64, privileged=True),
    "attach": SlashCommandSpec(minimum_arguments=1, maximum_arguments=64),
    "detach": SlashCommandSpec(maximum_arguments=64),
    "files": SlashCommandSpec(maximum_arguments=1),
    "evidence": SlashCommandSpec(maximum_arguments=1),
    "hypotheses": SlashCommandSpec(),
    "paths": SlashCommandSpec(),
    "topology": SlashCommandSpec(),
    "certificate": SlashCommandSpec(),
    "diff": SlashCommandSpec(maximum_arguments=1),
    "approve": SlashCommandSpec(minimum_arguments=1, maximum_arguments=1, privileged=True),
    "deny": SlashCommandSpec(minimum_arguments=1, maximum_arguments=1, privileged=True),
    "stop": SlashCommandSpec(privileged=True),
    "export": SlashCommandSpec(minimum_arguments=1, maximum_arguments=2),
    "exit": SlashCommandSpec(),
    "quit": SlashCommandSpec(),
}


def _parse_options(parts: list[str]) -> Tuple[Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    arguments: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(parts):
        token = parts[index]
        if not token.startswith("--") or token == "--":
            arguments.append(token)
            index += 1
            continue
        option = token[2:]
        if not option:
            raise ValueError("slash command option name must be non-empty")
        if "=" in option:
            key, value = option.split("=", 1)
        else:
            key = option
            if index + 1 < len(parts) and not parts[index + 1].startswith("--"):
                index += 1
                value = parts[index]
            else:
                value = "true"
        key = key.strip().casefold().replace("_", "-")
        if not key or not value:
            raise ValueError("slash command options require non-empty names and values")
        if key in options:
            raise ValueError(f"duplicate slash command option: --{key}")
        options[key] = value
        index += 1
    return tuple(arguments), tuple(sorted(options.items()))


def parse_slash_command(text: str) -> SlashCommand | None:
    raw = text.strip()
    if not raw.startswith("/"):
        return None
    if FORBIDDEN_SHELL_PATTERN.search(raw):
        raise ValueError("shell metacharacters are not accepted by ICPI slash commands")
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        raise ValueError(f"invalid slash command quoting: {exc}") from exc
    if not parts:
        raise ValueError("slash command is empty")
    name = parts.pop(0).lstrip("/").casefold()
    spec = SLASH_COMMAND_SPECS.get(name)
    if spec is None:
        raise ValueError(f"unknown ICPI slash command: /{name}")
    arguments, options = _parse_options(parts)
    if not spec.minimum_arguments <= len(arguments) <= spec.maximum_arguments:
        if spec.minimum_arguments == spec.maximum_arguments:
            expected = str(spec.minimum_arguments)
        else:
            expected = f"{spec.minimum_arguments}..{spec.maximum_arguments}"
        raise ValueError(f"/{name} expects {expected} arguments; received {len(arguments)}")
    if name == "detach":
        option_values = dict(options)
        unknown = set(option_values) - {"all"}
        if unknown:
            raise ValueError(f"/detach does not accept options: {sorted(unknown)!r}")
        remove_all = option_values.get("all", "false").casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if remove_all and arguments:
            raise ValueError("/detach --all cannot be combined with path arguments")
        if not remove_all and not arguments:
            raise ValueError("/detach requires path arguments or --all")
    if name == "context":
        option_values = dict(options)
        unknown = set(option_values) - {"refresh"}
        if unknown:
            raise ValueError(f"/context does not accept options: {sorted(unknown)!r}")
        if arguments and arguments != ("refresh",):
            raise ValueError("/context accepts only the optional 'refresh' argument")
        if arguments and "refresh" in option_values:
            raise ValueError("/context refresh cannot be combined with --refresh")
        if "refresh" in option_values and option_values["refresh"].casefold() not in {
            "1",
            "true",
            "yes",
            "on",
            "0",
            "false",
            "no",
            "off",
        }:
            raise ValueError("/context --refresh requires a boolean value")
    return SlashCommand(
        name=name,
        arguments=arguments,
        options=options,
        privileged=spec.privileged,
    )


__all__ = [
    "FORBIDDEN_SHELL_PATTERN",
    "SLASH_COMMAND_SPECS",
    "SlashCommandSpec",
    "parse_slash_command",
]
