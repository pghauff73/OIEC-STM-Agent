from __future__ import annotations

from typing import Iterable

from ..workspace import Workspace
from .commands import parse_slash_command
from .interpreter import interpret_natural_language
from .models import InteractionRoute


COMMAND_ROUTE_TARGETS = {
    "new": "session.new",
    "status": "projection.status",
    "help": "projection.help",
    "model": "session.model",
    "preflight": "provider.preflight",
    "context": "projection.context",
    "scope": "projection.scope",
    "summarize": "agent.read_only",
    "summarise": "agent.read_only",
    "writing-help": "projection.formal_writing.help",
    "writing-inspect": "agent.formal_writing.inspect",
    "writing-locate": "agent.formal_writing.locate",
    "writing-reference": "agent.formal_writing.explain_reference",
    "writing-paraphrase": "projection.formal_writing.audit",
    "writing-concepts": "agent.formal_writing.explain_reference",
    "writing-argument": "agent.formal_writing.plan",
    "writing-outline": "agent.formal_writing.plan",
    "writing-draft": "agent.formal_writing.plan",
    "writing-validate": "projection.formal_writing.audit",
    "writing-write": "agent.formal_writing.governed_candidate",
    "attach": "context.attach",
    "detach": "context.detach",
    "files": "projection.files",
    "evidence": "projection.evidence",
    "hypotheses": "projection.hypotheses",
    "paths": "projection.paths",
    "topology": "projection.topology",
    "certificate": "projection.certificate",
    "diff": "projection.diff",
    "approve": "governance.approve",
    "deny": "governance.deny",
    "stop": "session.stop",
    "export": "projection.export",
    "exit": "session.exit",
    "quit": "session.exit",
}

INTENT_ROUTE_TARGETS = {
    "INSPECT": "agent.read_only",
    "SUMMARIZE": "agent.read_only",
    "EXPLAIN": "agent.read_only",
    "REASON": "agent.read_only",
    "COMPARE": "agent.read_only",
    "PLAN": "agent.read_only",
    "PROPOSE": "agent.governed_candidate",
    "WRITE": "agent.governed_candidate",
    "TEST": "agent.governed_candidate",
    "EXECUTE": "agent.governed_action",
    "RECOVER": "agent.governed_action",
    "EXPORT": "projection.export",
}


def route_interaction(
    text: str,
    workspace: Workspace,
    *,
    known_evidence_ids: Iterable[str] = (),
) -> InteractionRoute:
    command = parse_slash_command(text)
    if command is not None:
        return InteractionRoute(
            kind="COMMAND",
            target=COMMAND_ROUTE_TARGETS[command.name],
            command=command,
            requires_confirmation=command.privileged,
        )
    intent = interpret_natural_language(
        text,
        workspace,
        known_evidence_ids=known_evidence_ids,
    )
    if intent.formal_writing is not None:
        target = {
            "INSPECT_SOURCES": "agent.formal_writing.inspect",
            "LOCATE_REFERENCE": "agent.formal_writing.locate",
            "EXPLAIN_REFERENCE": "agent.formal_writing.explain_reference",
            "BUILD_SOURCE_MAP": "agent.formal_writing.plan",
            "BUILD_ARGUMENT_MAP": "agent.formal_writing.plan",
            "OUTLINE": "agent.formal_writing.plan",
            "DRAFT": "agent.formal_writing.plan",
            "VALIDATE": "projection.formal_writing.audit",
            "WRITE": "agent.formal_writing.governed_candidate",
            "REVISE": "agent.formal_writing.governed_candidate",
            "EXPORT_REFERENCES": "projection.formal_writing.audit",
        }[intent.formal_writing.operation]
    else:
        target = INTENT_ROUTE_TARGETS[intent.mode]
    return InteractionRoute(
        kind="INTENT",
        target=target,
        intent=intent,
        requires_confirmation=intent.requires_confirmation,
    )


__all__ = ["COMMAND_ROUTE_TARGETS", "INTENT_ROUTE_TARGETS", "route_interaction"]
