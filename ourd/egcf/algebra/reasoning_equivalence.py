from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .reasoning import CanonicalReasoningAlgorithm, REASONING_ALGEBRA_VERSION


REASONING_EQUIVALENCE_VERSION = "saa-reasoning-equivalence-v1"


@dataclass(frozen=True)
class ReasoningTopologyDelta:
    added_operators: Tuple[str, ...]
    removed_operators: Tuple[str, ...]
    added_relations: Tuple[str, ...]
    removed_relations: Tuple[str, ...]
    semantic_input_delta: Tuple[str, ...]
    semantic_output_delta: Tuple[str, ...]
    delta_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_operators": list(self.added_operators),
            "removed_operators": list(self.removed_operators),
            "added_relations": list(self.added_relations),
            "removed_relations": list(self.removed_relations),
            "semantic_input_delta": list(self.semantic_input_delta),
            "semantic_output_delta": list(self.semantic_output_delta),
            "delta_signature": self.delta_signature,
        }


@dataclass(frozen=True)
class ReasoningEquivalenceAssessment:
    schema_version: int
    equivalence_version: str
    status: str
    exact_equivalence: bool
    topology_match: bool
    semantic_match: bool
    conservative_source_binding: bool
    relation_candidates: Tuple[str, ...]
    delta: ReasoningTopologyDelta
    canonical_reuse_eligible: bool
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "equivalence_version": self.equivalence_version,
            "status": self.status,
            "exact_equivalence": self.exact_equivalence,
            "topology_match": self.topology_match,
            "semantic_match": self.semantic_match,
            "conservative_source_binding": self.conservative_source_binding,
            "relation_candidates": list(self.relation_candidates),
            "delta": self.delta.to_dict(),
            "canonical_reuse_eligible": self.canonical_reuse_eligible,
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


def _expanded_counter_delta(left: Counter[str], right: Counter[str]) -> tuple[Tuple[str, ...], Tuple[str, ...]]:
    added: list[str] = []
    removed: list[str] = []
    for key in sorted(set(left) | set(right)):
        difference = right[key] - left[key]
        if difference > 0:
            added.extend([key] * difference)
        elif difference < 0:
            removed.extend([key] * (-difference))
    return tuple(added), tuple(removed)


def reasoning_topology_delta(
    left: CanonicalReasoningAlgorithm,
    right: CanonicalReasoningAlgorithm,
) -> ReasoningTopologyDelta:
    if not isinstance(left, CanonicalReasoningAlgorithm) or not isinstance(right, CanonicalReasoningAlgorithm):
        raise EGCFError("SAA-8.1 requires canonical reasoning algorithms")
    left_ops = Counter(str(node["operator"]) for node in left.canonical_nodes)
    right_ops = Counter(str(node["operator"]) for node in right.canonical_nodes)
    added_ops, removed_ops = _expanded_counter_delta(left_ops, right_ops)
    left_rel = Counter(str(edge["relation"]) for edge in left.canonical_edges)
    right_rel = Counter(str(edge["relation"]) for edge in right.canonical_edges)
    added_rel, removed_rel = _expanded_counter_delta(left_rel, right_rel)
    input_delta = tuple(sorted(set(left.input_semantics) ^ set(right.input_semantics)))
    output_delta = tuple(sorted(set(left.output_semantics) ^ set(right.output_semantics)))
    material = {
        "version": REASONING_EQUIVALENCE_VERSION,
        "added_operators": added_ops,
        "removed_operators": removed_ops,
        "added_relations": added_rel,
        "removed_relations": removed_rel,
        "input_delta": input_delta,
        "output_delta": output_delta,
    }
    return ReasoningTopologyDelta(
        added_operators=added_ops,
        removed_operators=removed_ops,
        added_relations=added_rel,
        removed_relations=removed_rel,
        semantic_input_delta=input_delta,
        semantic_output_delta=output_delta,
        delta_signature=sha256_json(material),
    )


def compare_reasoning_algorithms(
    left: CanonicalReasoningAlgorithm,
    right: CanonicalReasoningAlgorithm,
) -> ReasoningEquivalenceAssessment:
    if not isinstance(left, CanonicalReasoningAlgorithm) or not isinstance(right, CanonicalReasoningAlgorithm):
        raise EGCFError("SAA-8.1 requires CanonicalReasoningAlgorithm inputs")
    topology_match = left.topology_signature == right.topology_signature
    semantic_match = left.semantic_signature == right.semantic_signature
    exact = left.canonical_reasoning_signature == right.canonical_reasoning_signature
    conservative = (
        left.canonicalization_strength != "EXACT_BOUNDED_GRAPH_CANONICALIZATION"
        or right.canonicalization_strength != "EXACT_BOUNDED_GRAPH_CANONICALIZATION"
    )
    delta = reasoning_topology_delta(left, right)
    relations: list[str] = []
    if exact and not conservative:
        status = "EXACT_REASONING_ALGORITHM_EQUIVALENCE"
        reuse = True
        relations.append("EQUIVALENT_TO")
    elif exact:
        status = "CONSERVATIVE_REASONING_IDENTITY_MATCH"
        reuse = False
        relations.append("POTENTIAL_EQUIVALENT_TO")
    elif topology_match and not semantic_match:
        status = "OPERATOR_TOPOLOGY_MATCH_SEMANTIC_DIFFERENCE"
        reuse = False
        relations.append("NEAR_VARIANT_OF")
    elif semantic_match and not topology_match:
        status = "SEMANTIC_GOAL_MATCH_TOPOLOGY_DIFFERENCE"
        reuse = False
        relations.append("ALTERNATIVE_REASONING_TOPOLOGY")
    else:
        left_ops = Counter(str(node["operator"]) for node in left.canonical_nodes)
        right_ops = Counter(str(node["operator"]) for node in right.canonical_nodes)
        left_rel = Counter(str(edge["relation"]) for edge in left.canonical_edges)
        right_rel = Counter(str(edge["relation"]) for edge in right.canonical_edges)
        left_subset = all(left_ops[key] <= right_ops[key] for key in left_ops) and all(
            left_rel[key] <= right_rel[key] for key in left_rel
        )
        right_subset = all(right_ops[key] <= left_ops[key] for key in right_ops) and all(
            right_rel[key] <= left_rel[key] for key in right_rel
        )
        if left_subset and set(left.input_semantics).issubset(right.input_semantics) and set(left.output_semantics).issubset(right.output_semantics):
            status = "POTENTIAL_REASONING_SPECIALIZATION_EXTENSION"
            relations.append("POTENTIAL_SPECIALIZES")
        elif right_subset and set(right.input_semantics).issubset(left.input_semantics) and set(right.output_semantics).issubset(left.output_semantics):
            status = "POTENTIAL_REASONING_GENERALIZATION_RELATION"
            relations.append("POTENTIAL_GENERALIZES")
        else:
            status = "DISTINCT_REASONING_ALGORITHMS"
        reuse = False
    material = {
        "version": REASONING_EQUIVALENCE_VERSION,
        "left": left.canonical_reasoning_signature,
        "right": right.canonical_reasoning_signature,
        "status": status,
        "topology_match": topology_match,
        "semantic_match": semantic_match,
        "conservative": conservative,
        "relations": relations,
        "delta": delta.delta_signature,
    }
    warnings = (
        "GENERALIZES/SPECIALIZES candidates are structural hypotheses only. They require separate evidence before becoming qualified Algorithm Store relations.",
    )
    return ReasoningEquivalenceAssessment(
        schema_version=1,
        equivalence_version=REASONING_EQUIVALENCE_VERSION,
        status=status,
        exact_equivalence=exact and not conservative,
        topology_match=topology_match,
        semantic_match=semantic_match,
        conservative_source_binding=conservative,
        relation_candidates=tuple(relations),
        delta=delta,
        canonical_reuse_eligible=reuse,
        assessment_signature=sha256_json(material),
        warnings=warnings,
    )
