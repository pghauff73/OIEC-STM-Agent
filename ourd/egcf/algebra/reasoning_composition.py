from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .reasoning import (
    MAX_REASONING_STEPS,
    CanonicalReasoningAlgorithm,
    ReasoningAlgorithmSpec,
    ReasoningEdgeSpec,
    ReasoningNodeSpec,
    ReasoningTerminationSpec,
    canonicalize_reasoning_algorithm,
)
from .reasoning_outcome import ReasoningOutcomeQualification


REASONING_COMPOSITION_VERSION = "saa-reasoning-composition-v1"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _negation_base(value: str) -> tuple[bool, str]:
    text = _text(value)
    for prefix in ("not ", "!", "¬"):
        if text.startswith(prefix):
            return True, _text(text[len(prefix):])
    return False, text


def _invariant_conflicts(left: Sequence[str], right: Sequence[str]) -> Tuple[str, ...]:
    positive: set[str] = set()
    negative: set[str] = set()
    for value in (*left, *right):
        negated, base = _negation_base(value)
        if not base:
            continue
        (negative if negated else positive).add(base)
    return tuple(sorted(positive & negative))


def _qualified_for(
    qualification: ReasoningOutcomeQualification | None,
    algorithm: CanonicalReasoningAlgorithm,
) -> bool:
    return bool(
        qualification is not None
        and qualification.canonical_reasoning_signature == algorithm.canonical_reasoning_signature
        and qualification.status == "QUALIFIED_REASONING_OUTCOME"
        and qualification.canonical_reuse_eligible
    )


@dataclass(frozen=True)
class ReasoningCompositionAssessment:
    status: str
    interface_eligible: bool
    invariant_eligible: bool
    termination_eligible: bool
    qualification_eligible: bool
    exact_component_identity: bool
    blocking_gaps: Tuple[str, ...]
    assessment_signature: str

    @property
    def composition_eligible(self) -> bool:
        return not self.blocking_gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "interface_eligible": self.interface_eligible,
            "invariant_eligible": self.invariant_eligible,
            "termination_eligible": self.termination_eligible,
            "qualification_eligible": self.qualification_eligible,
            "exact_component_identity": self.exact_component_identity,
            "blocking_gaps": list(self.blocking_gaps),
            "assessment_signature": self.assessment_signature,
            "composition_eligible": self.composition_eligible,
        }


@dataclass(frozen=True)
class CanonicalReasoningComposition:
    schema_version: int
    composition_version: str
    left_signature: str
    right_signature: str
    composed_algorithm: CanonicalReasoningAlgorithm
    interface_semantics: Tuple[str, ...]
    component_qualification_signatures: Tuple[str, str]
    qualification_required: bool
    canonical_reuse_eligible: bool
    composition_signature: str
    warnings: Tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "composition_version": self.composition_version,
            "left_signature": self.left_signature,
            "right_signature": self.right_signature,
            "composed_algorithm": self.composed_algorithm.to_dict(),
            "interface_semantics": list(self.interface_semantics),
            "component_qualification_signatures": list(self.component_qualification_signatures),
            "qualification_required": self.qualification_required,
            "canonical_reuse_eligible": self.canonical_reuse_eligible,
            "composition_signature": self.composition_signature,
            "warnings": list(self.warnings),
        }


def assess_reasoning_composition(
    left: CanonicalReasoningAlgorithm,
    right: CanonicalReasoningAlgorithm,
    *,
    left_qualification: ReasoningOutcomeQualification | None = None,
    right_qualification: ReasoningOutcomeQualification | None = None,
) -> ReasoningCompositionAssessment:
    if not isinstance(left, CanonicalReasoningAlgorithm) or not isinstance(right, CanonicalReasoningAlgorithm):
        raise EGCFError("SAA-8.6 requires canonical reasoning algorithms")
    blockers: list[str] = []
    exact_components = all(
        item.canonicalization_strength == "EXACT_BOUNDED_GRAPH_CANONICALIZATION"
        for item in (left, right)
    )
    if not exact_components:
        blockers.append("composition requires exact bounded canonical component identities")

    interface = set(right.input_semantics).issubset(set(left.output_semantics))
    if not interface:
        missing = sorted(set(right.input_semantics) - set(left.output_semantics))
        blockers.append("downstream inputs not supplied by upstream outputs: " + ", ".join(missing))

    conflicts = _invariant_conflicts(left.invariants, right.invariants)
    invariant_eligible = not conflicts
    if conflicts:
        blockers.append("contradictory component invariants: " + ", ".join(conflicts))

    combined_steps = int(left.termination.get("max_steps", 0)) + int(right.termination.get("max_steps", 0))
    termination_eligible = 1 <= combined_steps <= MAX_REASONING_STEPS
    if not termination_eligible:
        blockers.append(f"combined termination budget {combined_steps} exceeds bounded cap {MAX_REASONING_STEPS}")

    qualification_eligible = _qualified_for(left_qualification, left) and _qualified_for(
        right_qualification, right
    )
    if not qualification_eligible:
        blockers.append("both component algorithms require canonical-reuse-qualified outcomes")

    status = "SAFE_REASONING_COMPOSITION" if not blockers else "BLOCKED_REASONING_COMPOSITION"
    payload = {
        "version": REASONING_COMPOSITION_VERSION,
        "left": left.canonical_reasoning_signature,
        "right": right.canonical_reasoning_signature,
        "interface_eligible": interface,
        "invariant_eligible": invariant_eligible,
        "termination_eligible": termination_eligible,
        "qualification_eligible": qualification_eligible,
        "exact_component_identity": exact_components,
        "blocking_gaps": blockers,
    }
    return ReasoningCompositionAssessment(
        status=status,
        interface_eligible=interface,
        invariant_eligible=invariant_eligible,
        termination_eligible=termination_eligible,
        qualification_eligible=qualification_eligible,
        exact_component_identity=exact_components,
        blocking_gaps=tuple(blockers),
        assessment_signature=sha256_json(payload),
    )


def _nodes_from_algorithm(prefix: str, algorithm: CanonicalReasoningAlgorithm) -> list[ReasoningNodeSpec]:
    result: list[ReasoningNodeSpec] = []
    for index, node in enumerate(algorithm.canonical_nodes):
        result.append(
            ReasoningNodeSpec(
                node_id=f"{prefix}{index}",
                operator=str(node["operator"]),
                semantic_inputs=tuple(node.get("semantic_inputs", ())),
                semantic_outputs=tuple(node.get("semantic_outputs", ())),
                public_claim_ids=tuple(node.get("public_claim_ids", ())),
                evidence_requirements=tuple(node.get("evidence_requirements", ())),
                assumptions=tuple(node.get("assumptions", ())),
                falsifiers=tuple(node.get("falsifiers", ())),
                description="",
            )
        )
    return result


def _edges_from_algorithm(prefix: str, algorithm: CanonicalReasoningAlgorithm) -> list[ReasoningEdgeSpec]:
    return [
        ReasoningEdgeSpec(
            source=f"{prefix}{int(edge['source'])}",
            target=f"{prefix}{int(edge['target'])}",
            relation=str(edge["relation"]),
            condition=str(edge.get("condition", "")),
        )
        for edge in algorithm.canonical_edges
    ]


def _entry_exit(prefix: str, algorithm: CanonicalReasoningAlgorithm) -> tuple[Tuple[str, ...], Tuple[str, ...]]:
    node_ids = {f"{prefix}{index}" for index in range(len(algorithm.canonical_nodes))}
    incoming = {node_id: 0 for node_id in node_ids}
    outgoing = {node_id: 0 for node_id in node_ids}
    for edge in algorithm.canonical_edges:
        source = f"{prefix}{int(edge['source'])}"
        target = f"{prefix}{int(edge['target'])}"
        outgoing[source] += 1
        incoming[target] += 1
    entries = tuple(sorted(node_id for node_id, count in incoming.items() if count == 0))
    exits = tuple(sorted(node_id for node_id, count in outgoing.items() if count == 0))
    if not entries or not exits:
        raise EGCFError("SAA-8.6 composition requires component entry and exit nodes")
    return entries, exits


def compose_reasoning_algorithms(
    left: CanonicalReasoningAlgorithm,
    right: CanonicalReasoningAlgorithm,
    *,
    left_qualification: ReasoningOutcomeQualification,
    right_qualification: ReasoningOutcomeQualification,
) -> CanonicalReasoningComposition:
    assessment = assess_reasoning_composition(
        left,
        right,
        left_qualification=left_qualification,
        right_qualification=right_qualification,
    )
    if not assessment.composition_eligible:
        raise EGCFError("unsafe reasoning composition: " + "; ".join(assessment.blocking_gaps))

    nodes = _nodes_from_algorithm("l", left) + _nodes_from_algorithm("r", right)
    edges = _edges_from_algorithm("l", left) + _edges_from_algorithm("r", right)
    _, left_exits = _entry_exit("l", left)
    right_entries, _ = _entry_exit("r", right)
    for source in left_exits:
        for target in right_entries:
            edges.append(
                ReasoningEdgeSpec(
                    source=source,
                    target=target,
                    relation="NEXT",
                    condition="qualified semantic handoff",
                )
            )

    combined_steps = int(left.termination["max_steps"]) + int(right.termination["max_steps"])
    spec = ReasoningAlgorithmSpec(
        name="qualified reasoning composition",
        inputs=left.input_semantics,
        outputs=right.output_semantics,
        nodes=tuple(nodes),
        edges=tuple(edges),
        invariants=tuple(sorted(set(left.invariants) | set(right.invariants))),
        termination=ReasoningTerminationSpec(
            kind="bounded-composition",
            predicate="all component termination predicates satisfied",
            max_steps=combined_steps,
        ),
        applicability=tuple(sorted(set(left.applicability) | set(right.applicability))),
    )
    composed = canonicalize_reasoning_algorithm(spec)
    if composed.canonicalization_strength != "EXACT_BOUNDED_GRAPH_CANONICALIZATION":
        raise EGCFError("composed reasoning graph exceeded exact canonicalization budget")
    interface = tuple(sorted(set(right.input_semantics)))
    payload = {
        "version": REASONING_COMPOSITION_VERSION,
        "left": left.canonical_reasoning_signature,
        "right": right.canonical_reasoning_signature,
        "composed": composed.canonical_reasoning_signature,
        "interface": list(interface),
        "left_qualification": left_qualification.qualification_signature,
        "right_qualification": right_qualification.qualification_signature,
        "assessment": assessment.assessment_signature,
        "qualification_required": True,
    }
    return CanonicalReasoningComposition(
        schema_version=1,
        composition_version=REASONING_COMPOSITION_VERSION,
        left_signature=left.canonical_reasoning_signature,
        right_signature=right.canonical_reasoning_signature,
        composed_algorithm=composed,
        interface_semantics=interface,
        component_qualification_signatures=(
            left_qualification.qualification_signature,
            right_qualification.qualification_signature,
        ),
        qualification_required=True,
        canonical_reuse_eligible=False,
        composition_signature=sha256_json(payload),
        warnings=(
            "Qualified components do not automatically qualify their composition. The composed algorithm requires its own SAA-8.5 outcome evidence before SAA-8.3 admission.",
        ),
    )
