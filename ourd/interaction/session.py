from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from ..errors import PolicyError
from ..reasoning.models import stable_hash
from .envelope import InteractionContextEnvelope
from .freshness import require_fresh_pinned_context
from .models import InteractionRoute
from .pinned import PinnedContextSet


SESSION_ACTIONS = {
    "RUN_AGENT",
    "NEW_CONTEXT",
    "LOCAL_REPLY",
    "PROVIDER_PREFLIGHT",
    "STOP",
    "EXIT",
    "SHOW_PROJECTION",
    "ATTACH_CONTEXT",
    "DETACH_CONTEXT",
    "REFRESH_CONTEXT",
    "GOVERNANCE_REQUIRED",
    "RESTART_REQUIRED",
}

ICPI_HELP = """OIEC-STM-SR-AgentICPI commands:
/new  /status  /help  /model [name]  /preflight  /context [refresh|--refresh]  /scope [path]
/attach <path...>  /detach <path...>|--all  /files [path]  /evidence [id]  /hypotheses
/summarize <path...>  /summarise <path...>
/writing-help  /writing-inspect  /writing-locate  /writing-reference
/writing-paraphrase  /writing-concepts  /writing-argument  /writing-outline
/writing-draft  /writing-validate  /writing-write
/paths  /topology  /certificate  /diff [path]  /export <kind> [format]
/approve <plan-id>  /deny <plan-id>  /stop  /exit
Natural language is interpreted into INSPECT, SUMMARIZE, EXPLAIN, REASON, COMPARE, PLAN,
PROPOSE, WRITE, TEST, EXECUTE, RECOVER, or EXPORT. Interpretation never grants authority."""


def _canonical_pairs(values: Mapping[str, Any] | Tuple[Tuple[str, str], ...]) -> Tuple[Tuple[str, str], ...]:
    source = values.items() if isinstance(values, Mapping) else values
    return tuple(sorted((str(key), str(value)) for key, value in source))


@dataclass(frozen=True)
class InteractionSessionSnapshot:
    schema_version: int = 1
    repository_root: str = ""
    source_snapshot: str = ""
    provider: str = ""
    model: str = ""
    authority_task_id: str = ""
    mode: str = "read-only"
    context_message_count: int = 0
    pinned_context_count: int = 0
    pinned_context_signature: str = ""
    pinned_context_envelope_id: str = ""
    pinned_context_source_snapshot: str = ""
    pinned_context_freshness: str = "EMPTY"
    active_operation: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("interaction session snapshot schema_version must be 1")
        repository_root = self.repository_root.strip()
        mode = self.mode.strip().casefold()
        context_count = int(self.context_message_count)
        pinned_count = int(self.pinned_context_count)
        pinned_freshness = self.pinned_context_freshness.strip().upper()
        if not repository_root:
            raise ValueError("interaction session repository root must be non-empty")
        if not mode:
            raise ValueError("interaction session mode must be non-empty")
        if context_count < 0:
            raise ValueError("interaction context message count cannot be negative")
        if pinned_count < 0:
            raise ValueError("pinned context count cannot be negative")
        if pinned_freshness not in {"EMPTY", "UNBOUND", "FRESH", "STALE"}:
            raise ValueError(
                f"invalid pinned context freshness: {self.pinned_context_freshness}"
            )
        if pinned_count == 0 and pinned_freshness != "EMPTY":
            raise ValueError("empty pinned context must use EMPTY freshness")
        if pinned_count > 0 and pinned_freshness == "EMPTY":
            raise ValueError("non-empty pinned context cannot use EMPTY freshness")
        object.__setattr__(self, "repository_root", repository_root)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "context_message_count", context_count)
        object.__setattr__(self, "pinned_context_count", pinned_count)
        object.__setattr__(self, "pinned_context_freshness", pinned_freshness)
        material = {
            "schema_version": self.schema_version,
            "repository_root": repository_root,
            "source_snapshot": self.source_snapshot,
            "provider": self.provider,
            "model": self.model,
            "authority_task_id": self.authority_task_id,
            "mode": mode,
            "context_message_count": context_count,
            "pinned_context_count": pinned_count,
            "pinned_context_signature": self.pinned_context_signature,
            "pinned_context_envelope_id": self.pinned_context_envelope_id,
            "pinned_context_source_snapshot": self.pinned_context_source_snapshot,
            "pinned_context_freshness": pinned_freshness,
            "active_operation": bool(self.active_operation),
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("interaction session snapshot signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class InteractionDirective:
    schema_version: int = 1
    directive_id: str = ""
    route: InteractionRoute | None = None
    action: str = "LOCAL_REPLY"
    message: str = ""
    payload: Tuple[Tuple[str, str], ...] = ()
    requires_confirmation: bool = False
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("interaction directive schema_version must be 1")
        if self.authoritative:
            raise ValueError("interaction directive cannot be authoritative")
        if self.route is None:
            raise ValueError("interaction directive requires a route")
        action = self.action.strip().upper()
        if action not in SESSION_ACTIONS:
            raise ValueError(f"invalid interaction session action: {self.action}")
        payload = _canonical_pairs(self.payload)
        requires_confirmation = bool(
            self.requires_confirmation or self.route.requires_confirmation
        )
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "message", self.message.strip())
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "requires_confirmation", requires_confirmation)
        material = {
            "schema_version": self.schema_version,
            "route_signature": self.route.signature,
            "action": action,
            "message": self.message,
            "payload": payload,
            "requires_confirmation": requires_confirmation,
            "authoritative": False,
        }
        expected_id = f"directive:{stable_hash(material)}"
        if self.directive_id and self.directive_id != expected_id:
            raise ValueError("interaction directive ID mismatch")
        signature_material = {**material, "directive_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("interaction directive signature mismatch")
        object.__setattr__(self, "directive_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)


@dataclass(frozen=True)
class InteractionConfirmation:
    schema_version: int = 2
    confirmation_id: str = ""
    route_id: str = ""
    route_signature: str = ""
    binding_kind: str = "CONTEXT"
    source_snapshot_hash: str = ""
    context_envelope_id: str = ""
    context_envelope_signature: str = ""
    context_budget_signature: str = ""
    context_reference_count: int = 0
    context_file_count: int = 0
    model_input_sha256: str = ""
    pinned_context_id: str = ""
    pinned_context_signature: str = ""
    pinned_context_count: int = 0
    pinned_context_envelope_id: str = ""
    pinned_context_envelope_signature: str = ""
    pinned_context_freshness: str = "EMPTY"
    title: str = "Confirm exact ICPI request"
    summary_lines: Tuple[str, ...] = ()
    risk: str = "L0"
    ambiguity_bp: int = 0
    target_paths: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("interaction confirmation schema_version must be 2")
        if self.authoritative:
            raise ValueError("interaction confirmation cannot be authoritative")
        if not self.route_id or not self.route_signature:
            raise ValueError("interaction confirmation requires route identity")
        binding_kind = self.binding_kind.strip().upper()
        if binding_kind not in {"CONTEXT", "ROUTE"}:
            raise ValueError(f"invalid interaction confirmation binding: {self.binding_kind}")
        context_reference_count = int(self.context_reference_count)
        context_file_count = int(self.context_file_count)
        pinned_context_count = int(self.pinned_context_count)
        if min(context_reference_count, context_file_count, pinned_context_count) < 0:
            raise ValueError("interaction confirmation counts cannot be negative")
        pinned_freshness = self.pinned_context_freshness.strip().upper()
        if pinned_freshness not in {"EMPTY", "FRESH"}:
            raise ValueError(
                "interaction confirmation pinned context must be EMPTY or FRESH"
            )
        if binding_kind == "CONTEXT":
            if len(self.source_snapshot_hash) != 64:
                raise ValueError("context-bound confirmation requires a source snapshot")
            for name in (
                "context_envelope_id",
                "context_envelope_signature",
                "context_budget_signature",
            ):
                if not str(getattr(self, name)).strip():
                    raise ValueError(f"context-bound confirmation requires {name}")
            if len(self.model_input_sha256) != 64:
                raise ValueError("context-bound confirmation requires a model-input SHA-256")
        elif any(
            (
                self.source_snapshot_hash,
                self.context_envelope_id,
                self.context_envelope_signature,
                self.context_budget_signature,
                self.model_input_sha256,
                context_reference_count,
                context_file_count,
                pinned_context_count,
                self.pinned_context_id,
                self.pinned_context_signature,
                self.pinned_context_envelope_id,
                self.pinned_context_envelope_signature,
            )
        ):
            raise ValueError("route-only confirmation cannot carry context bindings")
        if pinned_context_count == 0:
            if pinned_freshness != "EMPTY":
                raise ValueError("empty confirmation pins must use EMPTY freshness")
            if any(
                (
                    self.pinned_context_envelope_id,
                    self.pinned_context_envelope_signature,
                )
            ):
                raise ValueError("empty confirmation pins cannot bind a draft envelope")
        else:
            if pinned_freshness != "FRESH":
                raise ValueError("non-empty confirmation pins must be FRESH")
            for name in (
                "pinned_context_id",
                "pinned_context_signature",
                "pinned_context_envelope_id",
                "pinned_context_envelope_signature",
            ):
                if not str(getattr(self, name)).strip():
                    raise ValueError(f"pinned confirmation requires {name}")
        lines = tuple(str(line).strip() for line in self.summary_lines if str(line).strip())
        if not lines:
            raise ValueError("interaction confirmation requires summary lines")
        ambiguity = int(self.ambiguity_bp)
        if not 0 <= ambiguity <= 10_000:
            raise ValueError("interaction confirmation ambiguity must be 0..10000")
        targets = tuple(sorted({str(value).strip() for value in self.target_paths if str(value).strip()}))
        constraints = tuple(sorted({str(value).strip() for value in self.constraints if str(value).strip()}))
        object.__setattr__(self, "summary_lines", lines)
        object.__setattr__(self, "binding_kind", binding_kind)
        object.__setattr__(self, "context_reference_count", context_reference_count)
        object.__setattr__(self, "context_file_count", context_file_count)
        object.__setattr__(self, "pinned_context_count", pinned_context_count)
        object.__setattr__(self, "pinned_context_freshness", pinned_freshness)
        object.__setattr__(self, "ambiguity_bp", ambiguity)
        object.__setattr__(self, "target_paths", targets)
        object.__setattr__(self, "constraints", constraints)
        material = {
            "schema_version": self.schema_version,
            "route_id": self.route_id,
            "route_signature": self.route_signature,
            "binding_kind": binding_kind,
            "source_snapshot_hash": self.source_snapshot_hash,
            "context_envelope_id": self.context_envelope_id,
            "context_envelope_signature": self.context_envelope_signature,
            "context_budget_signature": self.context_budget_signature,
            "context_reference_count": context_reference_count,
            "context_file_count": context_file_count,
            "model_input_sha256": self.model_input_sha256,
            "pinned_context_id": self.pinned_context_id,
            "pinned_context_signature": self.pinned_context_signature,
            "pinned_context_count": pinned_context_count,
            "pinned_context_envelope_id": self.pinned_context_envelope_id,
            "pinned_context_envelope_signature": self.pinned_context_envelope_signature,
            "pinned_context_freshness": pinned_freshness,
            "title": self.title,
            "summary_lines": lines,
            "risk": self.risk,
            "ambiguity_bp": ambiguity,
            "target_paths": targets,
            "constraints": constraints,
            "authoritative": False,
        }
        expected_id = f"confirmation:{stable_hash(material)}"
        if self.confirmation_id and self.confirmation_id != expected_id:
            raise ValueError("interaction confirmation ID mismatch")
        signature_material = {**material, "confirmation_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("interaction confirmation signature mismatch")
        object.__setattr__(self, "confirmation_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InteractionConfirmation":
        return cls(**dict(payload))

    def render_text(self) -> str:
        return "\n".join(
            (
                *self.summary_lines,
                "",
                "This confirms the exact interpretation and model-input identity only. It does not grant authority, approve evidence, or approve an EON action.",
            )
        )


@dataclass(frozen=True)
class InteractionConfirmationReceipt:
    schema_version: int = 1
    receipt_id: str = ""
    confirmation_id: str = ""
    confirmation_signature: str = ""
    decision: str = "REJECTED"
    route_id: str = ""
    route_signature: str = ""
    binding_kind: str = "CONTEXT"
    source_snapshot_hash: str = ""
    context_envelope_id: str = ""
    context_envelope_signature: str = ""
    context_budget_signature: str = ""
    context_reference_count: int = 0
    context_file_count: int = 0
    model_input_sha256: str = ""
    pinned_context_id: str = ""
    pinned_context_signature: str = ""
    pinned_context_count: int = 0
    pinned_context_envelope_id: str = ""
    pinned_context_envelope_signature: str = ""
    pinned_context_freshness: str = "EMPTY"
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("interaction confirmation receipt schema_version must be 1")
        if self.authoritative:
            raise ValueError("interaction confirmation receipt cannot be authoritative")
        decision = self.decision.strip().upper()
        binding_kind = self.binding_kind.strip().upper()
        if decision not in {"ACCEPTED", "REJECTED"}:
            raise ValueError(f"invalid interaction confirmation decision: {self.decision}")
        if binding_kind not in {"CONTEXT", "ROUTE"}:
            raise ValueError(f"invalid interaction confirmation binding: {self.binding_kind}")
        for name in (
            "confirmation_id",
            "confirmation_signature",
            "route_id",
            "route_signature",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"interaction confirmation receipt requires {name}")
        if binding_kind == "CONTEXT":
            if len(self.source_snapshot_hash) != 64:
                raise ValueError("context confirmation receipt requires a source snapshot")
            if not all(
                (
                    self.context_envelope_id,
                    self.context_envelope_signature,
                    self.context_budget_signature,
                )
            ):
                raise ValueError("context confirmation receipt requires envelope identity")
            if len(self.model_input_sha256) != 64:
                raise ValueError("context confirmation receipt requires model-input SHA-256")
        context_reference_count = int(self.context_reference_count)
        context_file_count = int(self.context_file_count)
        pinned_context_count = int(self.pinned_context_count)
        if min(context_reference_count, context_file_count, pinned_context_count) < 0:
            raise ValueError("interaction confirmation receipt counts cannot be negative")
        if binding_kind == "ROUTE" and any(
            (
                self.source_snapshot_hash,
                self.context_envelope_id,
                self.context_envelope_signature,
                self.context_budget_signature,
                self.model_input_sha256,
                context_reference_count,
                context_file_count,
                pinned_context_count,
                self.pinned_context_id,
                self.pinned_context_signature,
                self.pinned_context_envelope_id,
                self.pinned_context_envelope_signature,
            )
        ):
            raise ValueError("route-only confirmation receipt cannot carry context bindings")
        pinned_freshness = self.pinned_context_freshness.strip().upper()
        if pinned_freshness not in {"EMPTY", "FRESH"}:
            raise ValueError("invalid confirmation receipt pinned freshness")
        if pinned_context_count == 0:
            if pinned_freshness != "EMPTY":
                raise ValueError("empty confirmation receipt pins must be EMPTY")
            if any(
                (
                    self.pinned_context_id,
                    self.pinned_context_signature,
                    self.pinned_context_envelope_id,
                    self.pinned_context_envelope_signature,
                )
            ):
                raise ValueError("empty confirmation receipt pins cannot bind context")
        else:
            if pinned_freshness != "FRESH":
                raise ValueError("non-empty confirmation receipt pins must be FRESH")
            if not all(
                (
                    self.pinned_context_id,
                    self.pinned_context_signature,
                    self.pinned_context_envelope_id,
                    self.pinned_context_envelope_signature,
                )
            ):
                raise ValueError("confirmation receipt requires pinned-context identity")
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "binding_kind", binding_kind)
        object.__setattr__(self, "context_reference_count", context_reference_count)
        object.__setattr__(self, "context_file_count", context_file_count)
        object.__setattr__(self, "pinned_context_count", pinned_context_count)
        object.__setattr__(self, "pinned_context_freshness", pinned_freshness)
        material = {
            "schema_version": self.schema_version,
            "confirmation_id": self.confirmation_id,
            "confirmation_signature": self.confirmation_signature,
            "decision": decision,
            "route_id": self.route_id,
            "route_signature": self.route_signature,
            "binding_kind": binding_kind,
            "source_snapshot_hash": self.source_snapshot_hash,
            "context_envelope_id": self.context_envelope_id,
            "context_envelope_signature": self.context_envelope_signature,
            "context_budget_signature": self.context_budget_signature,
            "context_reference_count": context_reference_count,
            "context_file_count": context_file_count,
            "model_input_sha256": self.model_input_sha256,
            "pinned_context_id": self.pinned_context_id,
            "pinned_context_signature": self.pinned_context_signature,
            "pinned_context_count": pinned_context_count,
            "pinned_context_envelope_id": self.pinned_context_envelope_id,
            "pinned_context_envelope_signature": self.pinned_context_envelope_signature,
            "pinned_context_freshness": pinned_freshness,
            "authoritative": False,
        }
        expected_id = f"confirmation-receipt:{stable_hash(material)}"
        if self.receipt_id and self.receipt_id != expected_id:
            raise ValueError("interaction confirmation receipt ID mismatch")
        expected_signature = stable_hash({**material, "receipt_id": expected_id})
        if self.signature and self.signature != expected_signature:
            raise ValueError("interaction confirmation receipt signature mismatch")
        object.__setattr__(self, "receipt_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InteractionConfirmationReceipt":
        return cls(**dict(payload))


def _status_message(snapshot: InteractionSessionSnapshot) -> str:
    operation = "running" if snapshot.active_operation else "idle"
    return (
        f"Repository: {snapshot.repository_root}\n"
        f"Snapshot: {snapshot.source_snapshot or 'unavailable'}\n"
        f"Provider: {snapshot.provider or 'unconfigured'}\n"
        f"Model: {snapshot.model or 'unconfigured'}\n"
        f"Authority: {snapshot.authority_task_id or 'external/default'}\n"
        f"Mode: {snapshot.mode}\n"
        f"Context messages: {snapshot.context_message_count}\n"
        f"Pinned context paths: {snapshot.pinned_context_count}\n"
        f"Pinned context signature: {snapshot.pinned_context_signature or 'empty'}\n"
        f"Pinned context envelope: {snapshot.pinned_context_envelope_id or 'none'}\n"
        f"Pinned context source snapshot: {snapshot.pinned_context_source_snapshot or 'none'}\n"
        f"Pinned context freshness: {snapshot.pinned_context_freshness}\n"
        f"Operation: {operation}"
    )


def dispatch_interaction(
    route: InteractionRoute,
    snapshot: InteractionSessionSnapshot,
) -> InteractionDirective:
    if route.kind == "INTENT":
        assert route.intent is not None
        return InteractionDirective(
            route=route,
            action="RUN_AGENT",
            message=(
                f"Route {route.intent.mode} -> {route.target}; downstream policy and EON remain authoritative."
            ),
            payload={
                "intent_id": route.intent.intent_id,
                "mode": route.intent.mode,
                "risk": route.intent.proposed_risk,
            },
        )

    assert route.command is not None
    command = route.command
    name = command.name
    if name == "new":
        return InteractionDirective(route=route, action="NEW_CONTEXT")
    if name == "help":
        return InteractionDirective(route=route, action="LOCAL_REPLY", message=ICPI_HELP)
    if name == "status":
        return InteractionDirective(
            route=route,
            action="LOCAL_REPLY",
            message=_status_message(snapshot),
        )
    if name == "context":
        options = dict(command.options)
        refresh = command.arguments == ("refresh",) or options.get(
            "refresh", "false"
        ).casefold() in {"1", "true", "yes", "on"}
        if refresh:
            return InteractionDirective(
                route=route,
                action="REFRESH_CONTEXT",
                message=(
                    "The pinned draft context will be rebuilt against the exact current "
                    "workspace snapshot. This is read-only and does not invoke the model."
                ),
            )
        return InteractionDirective(
            route=route,
            action="LOCAL_REPLY",
            message=(
                f"Active bounded context contains {snapshot.context_message_count} messages and "
                f"{snapshot.pinned_context_count} pinned paths. "
                f"Pinned freshness is {snapshot.pinned_context_freshness}. "
                "Use /new to establish a new model-context boundary without deleting audit history."
            ),
        )
    if name == "scope":
        requested = command.arguments[0] if command.arguments else "."
        return InteractionDirective(
            route=route,
            action="LOCAL_REPLY",
            message=(
                f"Requested read scope: {requested}. Scope remains bounded by the active authority; "
                "this command does not establish reasoning governance or mutation authority."
            ),
            payload={"path": requested},
        )
    if name in {"summarize", "summarise"}:
        references = " ".join(f"@path[{path}]" for path in command.arguments)
        return InteractionDirective(
            route=route,
            action="RUN_AGENT",
            message="Compile this command as a read-only SUMMARIZE turn.",
            payload={"agent_message": f"Summarize each document in {references}."},
        )
    if name == "writing-help":
        return InteractionDirective(
            route=route,
            action="LOCAL_REPLY",
            message=(
                "Formal writing accepts @source[path], @sourcefolder[path], @rubric[path], "
                "@draft[path], @output[path], and @style[name]. Read-only lookup never grants "
                "write authority; /writing-write requires exact confirmation and governed mutation."
            ),
        )
    if name.startswith("writing-"):
        operation = name.removeprefix("writing-")
        paths = command.arguments[:-1] if name == "writing-write" else command.arguments
        output = command.arguments[-1] if name == "writing-write" else ""
        source_references = " ".join(f"@source[{path}]" for path in paths)
        output_reference = f" @output[{output}]" if output else ""
        return InteractionDirective(
            route=route,
            action="RUN_AGENT",
            message="Compile this command through the formal-writing request schema.",
            payload={
                "agent_message": f"{operation.replace('-', ' ')} formal writing using {source_references}{output_reference}."
            },
        )
    if name == "model":
        if command.arguments:
            return InteractionDirective(
                route=route,
                action="RESTART_REQUIRED",
                message=(
                    f"Model change requested: {command.arguments[0]}. Restart ICPI with an explicit "
                    "provider/model configuration; a prompt command cannot silently replace the governed provider."
                ),
            )
        return InteractionDirective(
            route=route,
            action="LOCAL_REPLY",
            message=f"Provider: {snapshot.provider or 'unconfigured'}\nModel: {snapshot.model or 'unconfigured'}",
        )
    if name == "preflight":
        return InteractionDirective(route=route, action="PROVIDER_PREFLIGHT")
    if name == "stop":
        return InteractionDirective(route=route, action="STOP")
    if name in {"exit", "quit"}:
        return InteractionDirective(route=route, action="EXIT")
    if name == "attach":
        return InteractionDirective(
            route=route,
            action="ATTACH_CONTEXT",
            message=(
                "Attachment references will be resolved into a read-only draft context envelope and inserted "
                "into the composer. No model turn, authority change, or repository mutation occurs."
            ),
            payload={"paths": "\n".join(command.arguments)},
        )
    if name == "detach":
        options = dict(command.options)
        return InteractionDirective(
            route=route,
            action="DETACH_CONTEXT",
            message=(
                "Pinned context paths will be removed from future natural-language turns. "
                "No model turn, authority change, or repository mutation occurs."
            ),
            payload={
                "paths": "\n".join(command.arguments),
                "all": options.get("all", "false"),
            },
        )
    if name in {"approve", "deny"}:
        return InteractionDirective(
            route=route,
            action="GOVERNANCE_REQUIRED",
            message=(
                f"/{name} identified plan {command.arguments[0]}. Use the EON approval surface so identity, "
                "authority, constraints, expiry, and use limits are recorded before mutation."
            ),
            payload={"plan_id": command.arguments[0], "decision": name},
        )
    return InteractionDirective(
        route=route,
        action="SHOW_PROJECTION",
        message=(
            f"/{name} maps to {route.target}. The current surface should render that canonical projection; "
            "it must not ask the model to invent state."
        ),
        payload={"target": route.target},
    )


def build_interaction_confirmation(
    directive: InteractionDirective,
    *,
    context_envelope: InteractionContextEnvelope | None = None,
    pinned_context: PinnedContextSet | None = None,
    pinned_context_envelope: InteractionContextEnvelope | None = None,
) -> InteractionConfirmation:
    if not directive.requires_confirmation:
        raise ValueError("interaction directive does not require confirmation")
    route = directive.route
    assert route is not None
    if route.intent is not None:
        if context_envelope is None:
            raise ValueError(
                "natural-language confirmation requires an exact context envelope"
            )
        if context_envelope.route_id != route.route_id:
            raise ValueError("confirmation context envelope route ID mismatch")
        if context_envelope.route_signature != route.signature:
            raise ValueError("confirmation context envelope route signature mismatch")
        pins = pinned_context or PinnedContextSet()
        projected_paths = {
            item.value
            for item in context_envelope.attachments
            if item.kind in {"file", "folder", "path"}
        }
        missing_pins = set(pins.paths) - projected_paths
        if missing_pins:
            raise ValueError(
                f"confirmation context envelope omits pinned paths: {sorted(missing_pins)!r}"
            )
        require_fresh_pinned_context(
            pins,
            pinned_context_envelope,
            current_source_snapshot_hash=context_envelope.source_snapshot_hash,
        )
        intent = route.intent
        lines = (
            f"Mode: {intent.mode}",
            f"Objective: {intent.objective}",
            f"Route: {route.target}",
            f"Proposed risk: {intent.proposed_risk}",
            f"Ambiguity: {intent.ambiguity_bp / 100:.2f}%",
            f"Targets: {', '.join(intent.target_paths) if intent.target_paths else 'not specified'}",
            f"Evidence references: {', '.join(intent.referenced_evidence_ids) if intent.referenced_evidence_ids else 'none'}",
            f"Requested outputs: {', '.join(intent.requested_outputs)}",
            f"Source snapshot: {context_envelope.source_snapshot_hash}",
            f"Context envelope: {context_envelope.envelope_id}",
            f"Context signature: {context_envelope.signature}",
            f"Context budget signature: {context_envelope.budget.signature}",
            f"Context references/files: {len(context_envelope.attachments)}/{len(context_envelope.files)}",
            f"Model input SHA-256: {hashlib.sha256(context_envelope.model_input.encode('utf-8')).hexdigest()}",
            f"Pinned context: {pins.context_id if pins.paths else 'none'}",
            f"Pinned signature: {pins.signature if pins.paths else 'none'}",
            f"Pinned draft envelope: {pinned_context_envelope.envelope_id if pinned_context_envelope is not None else 'none'}",
            f"Pinned draft signature: {pinned_context_envelope.signature if pinned_context_envelope is not None else 'none'}",
        )
        risk = intent.proposed_risk
        ambiguity = intent.ambiguity_bp
        targets = intent.target_paths
        constraints = intent.constraints
        binding = {
            "binding_kind": "CONTEXT",
            "source_snapshot_hash": context_envelope.source_snapshot_hash,
            "context_envelope_id": context_envelope.envelope_id,
            "context_envelope_signature": context_envelope.signature,
            "context_budget_signature": context_envelope.budget.signature,
            "context_reference_count": len(context_envelope.attachments),
            "context_file_count": len(context_envelope.files),
            "model_input_sha256": hashlib.sha256(
                context_envelope.model_input.encode("utf-8")
            ).hexdigest(),
            "pinned_context_id": pins.context_id if pins.paths else "",
            "pinned_context_signature": pins.signature if pins.paths else "",
            "pinned_context_count": len(pins.paths),
            "pinned_context_envelope_id": (
                pinned_context_envelope.envelope_id
                if pinned_context_envelope is not None
                else ""
            ),
            "pinned_context_envelope_signature": (
                pinned_context_envelope.signature
                if pinned_context_envelope is not None
                else ""
            ),
            "pinned_context_freshness": "FRESH" if pins.paths else "EMPTY",
        }
    else:
        if context_envelope is not None or pinned_context_envelope is not None:
            raise ValueError("route-only confirmation cannot bind a context envelope")
        if pinned_context is not None and pinned_context.paths:
            raise ValueError("route-only confirmation cannot bind pinned context")
        assert route.command is not None
        command = route.command
        lines = (
            f"Command: /{command.name}",
            f"Route: {route.target}",
            f"Arguments: {', '.join(command.arguments) if command.arguments else 'none'}",
            f"Options: {', '.join(f'--{key}={value}' for key, value in command.options) if command.options else 'none'}",
        )
        risk = "L0"
        ambiguity = 0
        targets = command.arguments
        constraints = ()
        binding = {
            "binding_kind": "ROUTE",
            "pinned_context_freshness": "EMPTY",
        }
    return InteractionConfirmation(
        route_id=route.route_id,
        route_signature=route.signature,
        summary_lines=lines,
        risk=risk,
        ambiguity_bp=ambiguity,
        target_paths=targets,
        constraints=constraints,
        **binding,
    )


def build_interaction_confirmation_receipt(
    confirmation: InteractionConfirmation,
    *,
    accepted: bool,
) -> InteractionConfirmationReceipt:
    return InteractionConfirmationReceipt(
        confirmation_id=confirmation.confirmation_id,
        confirmation_signature=confirmation.signature,
        decision="ACCEPTED" if accepted else "REJECTED",
        route_id=confirmation.route_id,
        route_signature=confirmation.route_signature,
        binding_kind=confirmation.binding_kind,
        source_snapshot_hash=confirmation.source_snapshot_hash,
        context_envelope_id=confirmation.context_envelope_id,
        context_envelope_signature=confirmation.context_envelope_signature,
        context_budget_signature=confirmation.context_budget_signature,
        context_reference_count=confirmation.context_reference_count,
        context_file_count=confirmation.context_file_count,
        model_input_sha256=confirmation.model_input_sha256,
        pinned_context_id=confirmation.pinned_context_id,
        pinned_context_signature=confirmation.pinned_context_signature,
        pinned_context_count=confirmation.pinned_context_count,
        pinned_context_envelope_id=confirmation.pinned_context_envelope_id,
        pinned_context_envelope_signature=confirmation.pinned_context_envelope_signature,
        pinned_context_freshness=confirmation.pinned_context_freshness,
    )


def require_interaction_confirmation_receipt(
    confirmation: InteractionConfirmation,
    receipt: InteractionConfirmationReceipt,
    *,
    current_source_snapshot_hash: str,
    context_envelope: InteractionContextEnvelope | None = None,
    pinned_context: PinnedContextSet | None = None,
    pinned_context_envelope: InteractionContextEnvelope | None = None,
) -> None:
    if receipt.decision != "ACCEPTED":
        raise PolicyError("ICPI confirmation receipt was not accepted")
    expected_receipt = build_interaction_confirmation_receipt(
        confirmation,
        accepted=True,
    )
    if receipt.signature != expected_receipt.signature:
        raise PolicyError("ICPI confirmation receipt does not match the confirmation")
    if confirmation.binding_kind == "ROUTE":
        if context_envelope is not None or pinned_context_envelope is not None:
            raise PolicyError("route-only confirmation cannot authorize context dispatch")
        return
    if context_envelope is None:
        raise PolicyError("context-bound confirmation requires the exact context envelope")
    if current_source_snapshot_hash != confirmation.source_snapshot_hash:
        raise PolicyError("ICPI confirmation source snapshot is stale")
    expected_model_input_hash = hashlib.sha256(
        context_envelope.model_input.encode("utf-8")
    ).hexdigest()
    exact_context = (
        context_envelope.route_id == confirmation.route_id
        and context_envelope.route_signature == confirmation.route_signature
        and context_envelope.source_snapshot_hash == confirmation.source_snapshot_hash
        and context_envelope.envelope_id == confirmation.context_envelope_id
        and context_envelope.signature == confirmation.context_envelope_signature
        and context_envelope.budget.signature == confirmation.context_budget_signature
        and len(context_envelope.attachments) == confirmation.context_reference_count
        and len(context_envelope.files) == confirmation.context_file_count
        and expected_model_input_hash == confirmation.model_input_sha256
    )
    if not exact_context:
        raise PolicyError("ICPI confirmation does not match the exact context envelope")
    pins = pinned_context or PinnedContextSet()
    if len(pins.paths) != confirmation.pinned_context_count:
        raise PolicyError("ICPI confirmation pinned-context count mismatch")
    if pins.paths:
        if (
            pins.context_id != confirmation.pinned_context_id
            or pins.signature != confirmation.pinned_context_signature
            or pinned_context_envelope is None
            or pinned_context_envelope.envelope_id
            != confirmation.pinned_context_envelope_id
            or pinned_context_envelope.signature
            != confirmation.pinned_context_envelope_signature
        ):
            raise PolicyError("ICPI confirmation pinned-context identity mismatch")
    require_fresh_pinned_context(
        pins,
        pinned_context_envelope,
        current_source_snapshot_hash=current_source_snapshot_hash,
    )


def interaction_confirmation_receipt_audit_metadata(
    receipt: InteractionConfirmationReceipt,
) -> dict[str, Any]:
    return {
        "confirmation_receipt_id": receipt.receipt_id,
        "confirmation_receipt_signature": receipt.signature,
        "confirmation_id": receipt.confirmation_id,
        "confirmation_signature": receipt.confirmation_signature,
        "confirmation_decision": receipt.decision,
        "confirmation_route_id": receipt.route_id,
        "confirmation_route_signature": receipt.route_signature,
        "confirmation_binding_kind": receipt.binding_kind,
        "confirmation_source_snapshot": receipt.source_snapshot_hash,
        "confirmation_context_envelope_id": receipt.context_envelope_id,
        "confirmation_context_envelope_signature": receipt.context_envelope_signature,
        "confirmation_context_budget_signature": receipt.context_budget_signature,
        "confirmation_context_reference_count": receipt.context_reference_count,
        "confirmation_context_file_count": receipt.context_file_count,
        "confirmation_model_input_sha256": receipt.model_input_sha256,
        "confirmation_pinned_context_id": receipt.pinned_context_id,
        "confirmation_pinned_context_signature": receipt.pinned_context_signature,
        "confirmation_pinned_context_count": receipt.pinned_context_count,
        "confirmation_pinned_context_envelope_id": receipt.pinned_context_envelope_id,
        "confirmation_pinned_context_envelope_signature": receipt.pinned_context_envelope_signature,
        "confirmation_pinned_context_freshness": receipt.pinned_context_freshness,
        "confirmation_authoritative": False,
        "confirmation_prompt_body_persisted": False,
        "confirmation_model_input_body_persisted": False,
    }


__all__ = [
    "ICPI_HELP",
    "SESSION_ACTIONS",
    "InteractionDirective",
    "InteractionConfirmation",
    "InteractionConfirmationReceipt",
    "InteractionSessionSnapshot",
    "dispatch_interaction",
    "build_interaction_confirmation",
    "build_interaction_confirmation_receipt",
    "interaction_confirmation_receipt_audit_metadata",
    "require_interaction_confirmation_receipt",
]
