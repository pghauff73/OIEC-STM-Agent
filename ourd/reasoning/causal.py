from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from .models import SCORE_SCALE, bounded_score, stable_hash


CAUSAL_RELATIONS = {"causes", "mediates", "confounds", "moderates", "correlates"}
CAUSAL_NODE_KINDS = {"observed", "latent", "intervention", "outcome"}


@dataclass(frozen=True)
class CausalNode:
    node_id: str
    variable: str
    kind: str = "observed"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.node_id or not self.variable:
            raise ValueError("causal node identity must be non-empty")
        if self.kind not in CAUSAL_NODE_KINDS:
            raise ValueError(f"invalid causal node kind: {self.kind}")
        material = {"node_id": self.node_id, "variable": self.variable, "kind": self.kind}
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("causal node signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class CausalEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    evidence_ids: tuple[str, ...] = ()
    temporal_ordered: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.edge_id or not self.source_id or not self.target_id:
            raise ValueError("causal edge identity must be non-empty")
        if self.relation not in CAUSAL_RELATIONS:
            raise ValueError(f"invalid causal relation: {self.relation}")
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("causal edge signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class Intervention:
    intervention_id: str
    variable_id: str
    assigned_value: str
    assumptions: tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.intervention_id or not self.variable_id:
            raise ValueError("intervention identity must be non-empty")
        object.__setattr__(self, "assumptions", tuple(sorted(set(self.assumptions))))
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("intervention signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class Counterfactual:
    counterfactual_id: str
    intervention_id: str
    outcome_variable_id: str
    predicted_value: str
    assumptions: tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.counterfactual_id or not self.intervention_id or not self.outcome_variable_id:
            raise ValueError("counterfactual identity must be non-empty")
        object.__setattr__(self, "assumptions", tuple(sorted(set(self.assumptions))))
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("counterfactual signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class CausalAssessment:
    claim: str
    confidence_bp: int
    blockers: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    intervention_supported: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.claim:
            raise ValueError("causal assessment claim must be non-empty")
        bounded_score(self.confidence_bp, "causal confidence")
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("causal assessment signature mismatch")
        object.__setattr__(self, "signature", expected)


def assess_causal_claim(
    *,
    claim: str,
    source_id: str,
    target_id: str,
    edges: Sequence[CausalEdge],
    intervention: Intervention | None = None,
    declared_confounders: Iterable[str] = (),
    alternative_explanations: Iterable[str] = (),
    proposed_confidence_bp: int = SCORE_SCALE,
) -> CausalAssessment:
    proposed = bounded_score(proposed_confidence_bp, "proposed causal confidence")
    relevant = tuple(
        edge for edge in edges if edge.source_id == source_id and edge.target_id == target_id
    )
    blockers = []
    evidence_ids = {evidence_id for edge in relevant for evidence_id in edge.evidence_ids}
    direct = tuple(edge for edge in relevant if edge.relation == "causes")
    correlation_only = bool(relevant) and not direct
    if not relevant:
        blockers.append("no causal or observational edge supports the claim")
    if correlation_only:
        blockers.append("observational correlation does not establish intervention effect")
    if direct and not all(edge.temporal_ordered for edge in direct):
        blockers.append("causal temporal ordering is unresolved")
    confounders = tuple(sorted({str(value) for value in declared_confounders if str(value)}))
    if confounders:
        blockers.append("declared confounders remain unresolved: " + ", ".join(confounders))
    alternatives = tuple(
        sorted({str(value) for value in alternative_explanations if str(value)})
    )
    if alternatives:
        blockers.append("alternative explanations remain unresolved: " + ", ".join(alternatives))
    intervention_supported = (
        intervention is not None
        and intervention.variable_id == source_id
        and bool(direct)
        and not blockers
    )
    confidence = proposed
    if blockers:
        confidence = min(confidence, 4_999)
    if correlation_only:
        confidence = min(confidence, 3_000)
    if not evidence_ids:
        confidence = min(confidence, 2_500)
    return CausalAssessment(
        claim=claim,
        confidence_bp=confidence,
        blockers=tuple(blockers),
        evidence_ids=tuple(evidence_ids),
        intervention_supported=intervention_supported,
    )


__all__ = [
    "CAUSAL_NODE_KINDS",
    "CAUSAL_RELATIONS",
    "CausalAssessment",
    "CausalEdge",
    "CausalNode",
    "Counterfactual",
    "Intervention",
    "assess_causal_claim",
]
