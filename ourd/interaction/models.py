from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Tuple

from ..constants import SCORE_SCALE
from ..reasoning.models import stable_hash


INTENT_MODES = {
    "INSPECT",
    "SUMMARIZE",
    "EXPLAIN",
    "REASON",
    "COMPARE",
    "PLAN",
    "PROPOSE",
    "WRITE",
    "TEST",
    "EXECUTE",
    "RECOVER",
    "EXPORT",
}
RISK_CLASSES = {"L0", "L1", "L2"}
MUTATING_INTENT_MODES = {"WRITE", "TEST", "EXECUTE", "RECOVER"}
INTENT_RISK_FLOORS = {
    "WRITE": "L1",
    "TEST": "L1",
    "EXECUTE": "L2",
    "RECOVER": "L2",
}
CONTEXT_REFERENCE_KINDS = {
    "file",
    "folder",
    "path",
    "source",
    "sourcefolder",
    "rubric",
    "output",
    "draft",
    "style",
    "evidence",
    "constraint",
}
CONTEXT_REFERENCE_STATUSES = {"resolved", "prospective", "unverified", "unresolved"}
TURN_TOOL_GROUPS = {
    "repository_discovery",
    "workspace_read",
    "corpus_read",
    "hypothesis_control",
    "governance_proposal",
    "certified_reasoning",
    "candidate_preparation",
    "eon_proposal",
    "evidence_gate",
    "transaction_apply",
    "verification",
}
TOOL_FAILURE_CLASSES = {
    "PRECONDITION",
    "POLICY",
    "INPUT",
    "NOT_FOUND",
    "TRANSIENT",
    "PROTOCOL",
    "TERMINAL",
}


def canonical_strings(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _risk_at_least(value: str, floor: str) -> str:
    order = {"L0": 0, "L1": 1, "L2": 2}
    return value if order[value] >= order[floor] else floor


@dataclass(frozen=True)
class ContextReference:
    schema_version: int = 1
    reference_id: str = ""
    kind: str = "path"
    value: str = ""
    status: str = "unresolved"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context reference schema_version must be 1")
        kind = self.kind.strip().casefold()
        status = self.status.strip().casefold()
        value = self.value.strip()
        if kind not in CONTEXT_REFERENCE_KINDS:
            raise ValueError(f"invalid context reference kind: {self.kind}")
        if status not in CONTEXT_REFERENCE_STATUSES:
            raise ValueError(f"invalid context reference status: {self.status}")
        if not value:
            raise ValueError("context reference value must be non-empty")
        material = {
            "schema_version": self.schema_version,
            "kind": kind,
            "value": value,
            "status": status,
        }
        expected_id = f"context:{stable_hash(material)}"
        if self.reference_id and self.reference_id != expected_id:
            raise ValueError("context reference ID mismatch")
        signature_material = {**material, "reference_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("context reference signature mismatch")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "reference_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextReference":
        return cls(**dict(payload))


@dataclass(frozen=True)
class FormalWritingIntent:
    schema_version: int = 1
    operation: str = ""
    profile: str = "general"
    source_paths: Tuple[str, ...] = ()
    source_folder_paths: Tuple[str, ...] = ()
    rubric_paths: Tuple[str, ...] = ()
    output_paths: Tuple[str, ...] = ()
    draft_paths: Tuple[str, ...] = ()
    citation_style: str = "author-date"
    word_target: int = 0
    require_page_accuracy: bool = False
    allow_ocr: bool = False
    network_policy: str = "offline"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("formal writing intent schema_version must be 1")
        if not self.operation.strip():
            raise ValueError("formal writing intent operation must be non-empty")
        if int(self.word_target) < 0:
            raise ValueError("formal writing word target cannot be negative")
        for name in (
            "source_paths",
            "source_folder_paths",
            "rubric_paths",
            "output_paths",
            "draft_paths",
        ):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key != "signature"}
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("formal writing intent signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ResolvedContext:
    schema_version: int = 1
    source_text: str = ""
    objective_text: str = ""
    references: Tuple[ContextReference, ...] = ()
    target_paths: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    unresolved_references: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("resolved context schema_version must be 1")
        source_text = self.source_text.strip()
        objective_text = self.objective_text.strip()
        if not source_text:
            raise ValueError("resolved context source text must be non-empty")
        references = tuple(sorted(self.references, key=lambda item: item.reference_id))
        if len({item.reference_id for item in references}) != len(references):
            raise ValueError("resolved context references must be unique")
        object.__setattr__(self, "source_text", source_text)
        object.__setattr__(self, "objective_text", objective_text)
        object.__setattr__(self, "references", references)
        object.__setattr__(self, "target_paths", canonical_strings(self.target_paths))
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))
        object.__setattr__(self, "constraints", canonical_strings(self.constraints))
        object.__setattr__(
            self,
            "unresolved_references",
            canonical_strings(self.unresolved_references),
        )
        material = {
            "schema_version": self.schema_version,
            "source_text": source_text,
            "objective_text": objective_text,
            "references": tuple(asdict(item) for item in references),
            "target_paths": self.target_paths,
            "evidence_ids": self.evidence_ids,
            "constraints": self.constraints,
            "unresolved_references": self.unresolved_references,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("resolved context signature mismatch")
        object.__setattr__(self, "signature", expected)

    @property
    def has_unresolved_references(self) -> bool:
        return bool(self.unresolved_references)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResolvedContext":
        values = dict(payload)
        values["references"] = tuple(
            ContextReference.from_dict(item) for item in values.get("references", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class InterpretedIntent:
    schema_version: int = 1
    intent_id: str = ""
    source_text: str = ""
    objective: str = ""
    mode: str = "REASON"
    target_paths: Tuple[str, ...] = ()
    referenced_evidence_ids: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    requested_outputs: Tuple[str, ...] = ()
    ambiguity_bp: int = 0
    proposed_risk: str = "L0"
    requires_confirmation: bool = False
    authoritative: bool = False
    formal_writing: FormalWritingIntent | None = None
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("interpreted intent schema_version must be 1")
        if self.authoritative:
            raise ValueError("interpreted intent cannot be authoritative")
        source_text = self.source_text.strip()
        objective = self.objective.strip()
        mode = self.mode.strip().upper()
        risk = self.proposed_risk.strip().upper()
        ambiguity = int(self.ambiguity_bp)
        if not source_text:
            raise ValueError("interpreted intent source text must be non-empty")
        if not objective:
            raise ValueError("interpreted intent objective must be non-empty")
        if mode not in INTENT_MODES:
            raise ValueError(f"invalid interpreted intent mode: {self.mode}")
        if risk not in RISK_CLASSES:
            raise ValueError(f"invalid interpreted intent risk: {self.proposed_risk}")
        if not 0 <= ambiguity <= SCORE_SCALE:
            raise ValueError(f"intent ambiguity must be 0..{SCORE_SCALE}")
        if mode in INTENT_RISK_FLOORS:
            risk = _risk_at_least(risk, INTENT_RISK_FLOORS[mode])
        requires_confirmation = bool(self.requires_confirmation or mode in MUTATING_INTENT_MODES)
        object.__setattr__(self, "source_text", source_text)
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "target_paths", canonical_strings(self.target_paths))
        object.__setattr__(
            self,
            "referenced_evidence_ids",
            canonical_strings(self.referenced_evidence_ids),
        )
        object.__setattr__(self, "constraints", canonical_strings(self.constraints))
        object.__setattr__(self, "requested_outputs", canonical_strings(self.requested_outputs))
        object.__setattr__(self, "ambiguity_bp", ambiguity)
        object.__setattr__(self, "proposed_risk", risk)
        object.__setattr__(self, "requires_confirmation", requires_confirmation)
        identity_material = {
            "schema_version": self.schema_version,
            "source_text": source_text,
            "objective": objective,
            "mode": mode,
            "target_paths": self.target_paths,
            "referenced_evidence_ids": self.referenced_evidence_ids,
            "constraints": self.constraints,
            "requested_outputs": self.requested_outputs,
            "ambiguity_bp": ambiguity,
            "proposed_risk": risk,
            "requires_confirmation": requires_confirmation,
            "authoritative": False,
            "formal_writing_signature": self.formal_writing.signature if self.formal_writing else "",
        }
        expected_id = f"intent:{stable_hash(identity_material)}"
        if self.intent_id and self.intent_id != expected_id:
            raise ValueError("interpreted intent ID mismatch")
        signature_material = {**identity_material, "intent_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("interpreted intent signature mismatch")
        object.__setattr__(self, "intent_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterpretedIntent":
        values = dict(payload)
        formal = values.get("formal_writing")
        if isinstance(formal, Mapping):
            values["formal_writing"] = FormalWritingIntent(**dict(formal))
        return cls(**values)


@dataclass(frozen=True)
class SlashCommand:
    schema_version: int = 1
    name: str = ""
    command_id: str = ""
    arguments: Tuple[str, ...] = ()
    options: Tuple[Tuple[str, str], ...] = ()
    privileged: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("slash command schema_version must be 1")
        name = self.name.strip().casefold().lstrip("/")
        if not name:
            raise ValueError("slash command name must be non-empty")
        arguments = tuple(str(value) for value in self.arguments)
        options = tuple(sorted((str(key), str(value)) for key, value in self.options))
        if len({key for key, _ in options}) != len(options):
            raise ValueError("slash command options must be unique")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "arguments", arguments)
        object.__setattr__(self, "options", options)
        material = {
            "schema_version": self.schema_version,
            "name": name,
            "arguments": arguments,
            "options": options,
            "privileged": bool(self.privileged),
        }
        expected_id = f"slash:{name}:{stable_hash(material)}"
        if self.command_id and self.command_id != expected_id:
            raise ValueError("slash command ID mismatch")
        signature_material = {**material, "command_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("slash command signature mismatch")
        object.__setattr__(self, "command_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SlashCommand":
        return cls(**dict(payload))


@dataclass(frozen=True)
class InteractionRoute:
    schema_version: int = 1
    route_id: str = ""
    kind: str = "INTENT"
    target: str = ""
    requires_confirmation: bool = False
    command: SlashCommand | None = None
    intent: InterpretedIntent | None = None
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("interaction route schema_version must be 1")
        if self.authoritative:
            raise ValueError("interaction route cannot be authoritative")
        kind = self.kind.strip().upper()
        target = self.target.strip()
        if kind not in {"COMMAND", "INTENT"}:
            raise ValueError(f"invalid interaction route kind: {self.kind}")
        if not target:
            raise ValueError("interaction route target must be non-empty")
        if (self.command is None) == (self.intent is None):
            raise ValueError("interaction route must contain exactly one command or intent")
        if kind == "COMMAND" and self.command is None:
            raise ValueError("command route requires a slash command")
        if kind == "INTENT" and self.intent is None:
            raise ValueError("intent route requires an interpreted intent")
        requires_confirmation = bool(
            self.requires_confirmation
            or (self.command is not None and self.command.privileged)
            or (self.intent is not None and self.intent.requires_confirmation)
        )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "requires_confirmation", requires_confirmation)
        material = {
            "schema_version": self.schema_version,
            "kind": kind,
            "target": target,
            "requires_confirmation": requires_confirmation,
            "command_signature": self.command.signature if self.command else "",
            "intent_signature": self.intent.signature if self.intent else "",
            "authoritative": False,
        }
        expected_id = f"route:{stable_hash(material)}"
        if self.route_id and self.route_id != expected_id:
            raise ValueError("interaction route ID mismatch")
        signature_material = {**material, "route_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("interaction route signature mismatch")
        object.__setattr__(self, "route_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)


@dataclass(frozen=True)
class TurnExecutionPolicy:
    schema_version: int = 1
    policy_id: str = ""
    route_id: str = ""
    route_signature: str = ""
    source_snapshot_hash: str = ""
    intent_mode: str = "REASON"
    route_target: str = "agent.read_only"
    target_paths: Tuple[str, ...] = ()
    allowed_tool_groups: Tuple[str, ...] = ()
    requires_reasoning_certificate: bool = False
    allows_candidate_preparation: bool = False
    allows_action_tools: bool = False
    corpus_request: Tuple[Tuple[str, str], ...] = ()
    context_envelope_signature: str = ""
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("turn execution policy schema_version must be 1")
        if self.authoritative:
            raise ValueError("turn execution policy cannot be authoritative")
        mode = self.intent_mode.strip().upper()
        route_id = self.route_id.strip()
        route_signature = self.route_signature.strip()
        source_snapshot_hash = self.source_snapshot_hash.strip()
        route_target = self.route_target.strip()
        if mode not in INTENT_MODES:
            raise ValueError(f"invalid turn execution policy mode: {self.intent_mode}")
        if not route_id or not route_signature or not source_snapshot_hash or not route_target:
            raise ValueError("turn execution policy route and snapshot bindings are required")
        groups = canonical_strings(self.allowed_tool_groups)
        unknown_groups = set(groups) - TURN_TOOL_GROUPS
        if unknown_groups:
            raise ValueError(f"unknown turn tool groups: {sorted(unknown_groups)!r}")
        corpus_request = tuple(
            sorted(
                (str(key).strip(), str(value).strip())
                for key, value in self.corpus_request
                if str(key).strip() and str(value).strip()
            )
        )
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "route_signature", route_signature)
        object.__setattr__(self, "source_snapshot_hash", source_snapshot_hash)
        object.__setattr__(self, "intent_mode", mode)
        object.__setattr__(self, "route_target", route_target)
        object.__setattr__(self, "target_paths", canonical_strings(self.target_paths))
        object.__setattr__(self, "allowed_tool_groups", groups)
        object.__setattr__(self, "corpus_request", corpus_request)
        material = {
            "schema_version": self.schema_version,
            "route_id": route_id,
            "route_signature": route_signature,
            "source_snapshot_hash": source_snapshot_hash,
            "intent_mode": mode,
            "route_target": route_target,
            "target_paths": self.target_paths,
            "allowed_tool_groups": groups,
            "requires_reasoning_certificate": bool(self.requires_reasoning_certificate),
            "allows_candidate_preparation": bool(self.allows_candidate_preparation),
            "allows_action_tools": bool(self.allows_action_tools),
            "corpus_request": corpus_request,
            "context_envelope_signature": self.context_envelope_signature.strip(),
            "authoritative": False,
        }
        expected_id = f"turn-policy:{stable_hash(material)}"
        if self.policy_id and self.policy_id != expected_id:
            raise ValueError("turn execution policy ID mismatch")
        expected_signature = stable_hash({**material, "policy_id": expected_id})
        if self.signature and self.signature != expected_signature:
            raise ValueError("turn execution policy signature mismatch")
        object.__setattr__(self, "policy_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TurnExecutionPolicy":
        values = dict(payload)
        values["target_paths"] = tuple(values.get("target_paths", ()))
        values["allowed_tool_groups"] = tuple(values.get("allowed_tool_groups", ()))
        values["corpus_request"] = tuple(tuple(item) for item in values.get("corpus_request", ()))
        return cls(**values)


@dataclass(frozen=True)
class ToolAvailability:
    tool_name: str
    available: bool
    reason_code: str
    required_state: str = ""
    current_state_signature: str = ""
    authority_hash: str = ""
    governance_signature: str = ""
    turn_policy_signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolFailureEnvelope:
    error_code: str
    message: str
    failure_class: str
    recoverable: bool
    required_transition: str
    tool_name: str
    call_fingerprint: str
    state_signature: str
    collision_id: str = ""
    retry_disposition: str = "do not retry unchanged"

    def __post_init__(self) -> None:
        if self.failure_class not in TOOL_FAILURE_CLASSES:
            raise ValueError(f"invalid tool failure class: {self.failure_class}")

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, **asdict(self)}


__all__ = [
    "CONTEXT_REFERENCE_KINDS",
    "CONTEXT_REFERENCE_STATUSES",
    "ContextReference",
    "FormalWritingIntent",
    "INTENT_MODES",
    "INTENT_RISK_FLOORS",
    "InteractionRoute",
    "InterpretedIntent",
    "MUTATING_INTENT_MODES",
    "RISK_CLASSES",
    "ResolvedContext",
    "SlashCommand",
    "TOOL_FAILURE_CLASSES",
    "TURN_TOOL_GROUPS",
    "ToolAvailability",
    "ToolFailureEnvelope",
    "TurnExecutionPolicy",
]
