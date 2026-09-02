from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple

from ourd.errors import PolicyError
from ourd.interaction import (
    SLASH_COMMAND_SPECS,
    PinnedContextSet,
    format_path_references,
    route_interaction,
)
from ourd.workspace import Workspace


ICPI_IDLE_PREVIEW = "ICPI ready · natural language or /help"

COMMAND_DESCRIPTIONS = {
    "new": "start a new bounded model context",
    "status": "show repository, model, authority, and operation status",
    "help": "show ICPI command help",
    "model": "show the configured provider/model",
    "preflight": "run or explain provider preflight",
    "context": "check context freshness or explicitly refresh the draft",
    "attach": "bind paths through the context resolver",
    "detach": "remove pinned context paths",
    "files": "show the canonical file projection",
    "evidence": "show evidence records",
    "hypotheses": "show the OIEC-SR hypothesis pool",
    "paths": "show candidate reasoning paths",
    "topology": "show the reasoning topology",
    "certificate": "show the latest reasoning certificate",
    "diff": "show a governed candidate diff",
    "approve": "open the governed EON approval path",
    "deny": "record a governed plan rejection",
    "stop": "request cancellation of the active turn",
    "export": "export a canonical projection",
    "exit": "exit a terminal session",
    "quit": "exit a terminal session",
}

PROJECTION_SURFACES = {
    "projection.context": "context",
    "projection.files": "repository",
    "projection.evidence": "evidence",
    "projection.hypotheses": "reasoning",
    "projection.paths": "reasoning",
    "projection.topology": "reasoning",
    "projection.certificate": "reasoning",
    "projection.diff": "eon",
    "projection.export": "artifacts",
}


def attachment_reference_text(paths: Iterable[str]) -> str:
    return format_path_references(paths)


@dataclass
class ICPICommandHistory:
    maximum_entries: int = 100
    _entries: list[str] = field(default_factory=list)
    _cursor: int | None = None
    _draft: str = ""

    def __post_init__(self) -> None:
        self.maximum_entries = max(1, int(self.maximum_entries))

    @property
    def entries(self) -> Tuple[str, ...]:
        return tuple(self._entries)

    def record(self, text: str) -> None:
        value = text.strip()
        if not value:
            return
        if not self._entries or self._entries[-1] != value:
            self._entries.append(value)
            self._entries = self._entries[-self.maximum_entries :]
        self._cursor = None
        self._draft = ""

    def previous(self, current: str) -> str:
        if not self._entries:
            return current
        if self._cursor is None:
            self._draft = current
            self._cursor = len(self._entries) - 1
        elif self._cursor > 0:
            self._cursor -= 1
        return self._entries[self._cursor]

    def next(self, current: str) -> str:
        if self._cursor is None:
            return current
        if self._cursor < len(self._entries) - 1:
            self._cursor += 1
            return self._entries[self._cursor]
        self._cursor = None
        return self._draft


def command_suggestions(text: str, *, limit: int = 6) -> Tuple[str, ...]:
    raw = text.lstrip()
    if not raw.startswith("/"):
        return ()
    first_token = raw.split(maxsplit=1)[0]
    prefix = first_token[1:].casefold()
    matches = [
        name
        for name in sorted(SLASH_COMMAND_SPECS)
        if not prefix or name.startswith(prefix)
    ]
    return tuple(
        f"/{name} — {COMMAND_DESCRIPTIONS.get(name, 'ICPI command')}"
        for name in matches[: max(1, int(limit))]
    )


def complete_slash_command(text: str) -> str:
    leading_length = len(text) - len(text.lstrip())
    leading = text[:leading_length]
    raw = text[leading_length:]
    if not raw.startswith("/"):
        return text
    parts = raw.split(maxsplit=1)
    command_token = parts[0]
    command_name = command_token[1:].casefold()
    if command_name in SLASH_COMMAND_SPECS:
        return text
    suggestions = command_suggestions(command_token, limit=1)
    if not suggestions:
        return text
    completed_command = suggestions[0].split(" — ", 1)[0]
    suffix = f" {parts[1]}" if len(parts) == 2 else " "
    return f"{leading}{completed_command}{suffix}"


def format_route_preview(
    text: str,
    workspace: Workspace,
    *,
    known_evidence_ids: Iterable[str] = (),
) -> str:
    raw = text.strip()
    if not raw:
        return ICPI_IDLE_PREVIEW
    if raw.startswith("/") and not any(character.isspace() for character in raw):
        command_name = raw[1:].casefold()
        suggestions = command_suggestions(raw)
        if suggestions and command_name not in SLASH_COMMAND_SPECS:
            return f"{raw} · {len(suggestions)} command suggestion(s) · continue typing or choose one"
    try:
        route = route_interaction(
            raw,
            workspace,
            known_evidence_ids=known_evidence_ids,
        )
    except (PolicyError, ValueError) as exc:
        return f"BLOCKED · {type(exc).__name__}: {exc}"
    confirmation = "confirmation required" if route.requires_confirmation else "ready"
    if route.command is not None:
        return f"/{route.command.name} → {route.target} · {confirmation}"
    assert route.intent is not None
    return (
        f"{route.intent.mode} → {route.target} · risk {route.intent.proposed_risk} · "
        f"ambiguity {route.intent.ambiguity_bp / 100:.2f}% · {confirmation}"
    )


def format_pinned_route_preview(
    text: str,
    workspace: Workspace,
    pinned_context: PinnedContextSet,
    *,
    known_evidence_ids: Iterable[str] = (),
) -> str:
    try:
        routed_text = pinned_context.apply_to(text, workspace)
    except Exception as exc:
        return f"BLOCKED · {type(exc).__name__}: {exc}"
    preview = format_route_preview(
        routed_text,
        workspace,
        known_evidence_ids=known_evidence_ids,
    )
    if not pinned_context.paths:
        return preview
    return (
        f"PINNED {len(pinned_context.paths)} "
        f"[{pinned_context.signature[:12]}] · {preview}"
    )


def projection_surface(target: str) -> str:
    return PROJECTION_SURFACES.get(target.strip(), "")


__all__ = [
    "COMMAND_DESCRIPTIONS",
    "ICPICommandHistory",
    "ICPI_IDLE_PREVIEW",
    "PROJECTION_SURFACES",
    "attachment_reference_text",
    "command_suggestions",
    "complete_slash_command",
    "format_route_preview",
    "format_pinned_route_preview",
    "projection_surface",
]
