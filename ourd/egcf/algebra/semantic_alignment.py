from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact
from .semantic_units import SemanticConcept, physical_semantic_relation


SEMANTIC_ALIGNMENT_VERSION = "saa-semantic-alignment-v1"
ALIGNMENT_RELATIONS = {
    "EXACT_EQUIVALENT",
    "SPECIALIZES",
    "GENERALIZES",
    "ANALOGOUS_TO",
    "RELATED_TO",
    "NOT_EQUIVALENT",
}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _grounded_evidence(store: Any, evidence_id: str) -> EvidenceArtifact:
    try:
        record = store.get(evidence_id)
    except Exception as exc:
        raise EGCFError(f"semantic alignment evidence is not registered: {evidence_id}") from exc
    if not isinstance(record, EvidenceArtifact):
        raise EGCFError("semantic alignment evidence ID does not reference EvidenceArtifact")
    if record.success is not True or record.simulated:
        raise EGCFError("semantic alignment evidence must be successful and non-simulated")
    if not record.producer.startswith(("deterministic-", "human-")):
        raise EGCFError("semantic alignment evidence requires deterministic or human producer")
    if record.method in {"reported", "model-claimed", "model-generated-claim"}:
        raise EGCFError("reported/model-claimed evidence cannot establish semantic alignment")
    return record


@dataclass(frozen=True)
class SemanticAlignmentProposal:
    left_concept_signature: str
    right_concept_signature: str
    relation: str
    shared_meaning: str
    expected_effects_match: bool
    evidence_ids: Tuple[str, ...]
    falsifiers: Tuple[str, ...]
    independent_review: bool
    proposal_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_concept_signature": self.left_concept_signature,
            "right_concept_signature": self.right_concept_signature,
            "relation": self.relation,
            "shared_meaning": self.shared_meaning,
            "expected_effects_match": self.expected_effects_match,
            "evidence_ids": list(self.evidence_ids),
            "falsifiers": list(self.falsifiers),
            "independent_review": self.independent_review,
            "proposal_signature": self.proposal_signature,
        }


def propose_semantic_alignment(
    left: SemanticConcept,
    right: SemanticConcept,
    *,
    relation: str,
    shared_meaning: str,
    expected_effects_match: bool,
    evidence_ids: Sequence[str] = (),
    falsifiers: Sequence[str] = (),
    independent_review: bool = False,
) -> SemanticAlignmentProposal:
    normalized_relation = str(relation).strip().upper()
    if normalized_relation not in ALIGNMENT_RELATIONS:
        raise EGCFError(f"unsupported semantic alignment relation: {relation!r}")
    shared = _text(shared_meaning)
    if normalized_relation != "NOT_EQUIVALENT" and not shared:
        raise EGCFError("semantic alignment requires an explicit shared-meaning proposition")
    evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    normalized_falsifiers = tuple(sorted({_text(value) for value in falsifiers if _text(value)}))
    payload = {
        "version": SEMANTIC_ALIGNMENT_VERSION,
        "left": left.concept_signature,
        "right": right.concept_signature,
        "relation": normalized_relation,
        "shared_meaning": shared,
        "expected_effects_match": bool(expected_effects_match),
        "evidence_ids": list(evidence),
        "falsifiers": list(normalized_falsifiers),
        "independent_review": bool(independent_review),
    }
    return SemanticAlignmentProposal(
        left_concept_signature=left.concept_signature,
        right_concept_signature=right.concept_signature,
        relation=normalized_relation,
        shared_meaning=shared,
        expected_effects_match=bool(expected_effects_match),
        evidence_ids=evidence,
        falsifiers=normalized_falsifiers,
        independent_review=bool(independent_review),
        proposal_signature=sha256_json(payload),
    )


@dataclass(frozen=True)
class SemanticAlignmentFalsifierResult:
    falsifier: str
    outcome: str
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "falsifier": _text(self.falsifier),
            "outcome": str(self.outcome).strip().upper(),
            "evidence_id": str(self.evidence_id).strip(),
        }


@dataclass(frozen=True)
class SemanticAlignmentAssessment:
    left_concept_signature: str
    right_concept_signature: str
    relation: str
    status: str
    physical_relation: str
    evidence_ids: Tuple[str, ...]
    falsifier_results: Tuple[SemanticAlignmentFalsifierResult, ...]
    independent_review: bool
    exact_substitution_eligible: bool
    canonical_alignment_eligible: bool
    alignment_signature: str
    blocking_reasons: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_concept_signature": self.left_concept_signature,
            "right_concept_signature": self.right_concept_signature,
            "relation": self.relation,
            "status": self.status,
            "physical_relation": self.physical_relation,
            "evidence_ids": list(self.evidence_ids),
            "falsifier_results": [item.to_dict() for item in self.falsifier_results],
            "independent_review": self.independent_review,
            "exact_substitution_eligible": self.exact_substitution_eligible,
            "canonical_alignment_eligible": self.canonical_alignment_eligible,
            "alignment_signature": self.alignment_signature,
            "blocking_reasons": list(self.blocking_reasons),
        }


def assess_semantic_alignment(
    store: Any,
    left: SemanticConcept,
    right: SemanticConcept,
    proposal: SemanticAlignmentProposal,
    *,
    falsifier_results: Sequence[SemanticAlignmentFalsifierResult] = (),
) -> SemanticAlignmentAssessment:
    signatures = {left.concept_signature, right.concept_signature}
    if {proposal.left_concept_signature, proposal.right_concept_signature} != signatures:
        raise EGCFError("semantic alignment proposal targets different concepts")
    physical_relation = physical_semantic_relation(left, right)
    blockers: list[str] = []
    evidence: list[str] = []
    for evidence_id in proposal.evidence_ids:
        try:
            _grounded_evidence(store, evidence_id)
            evidence.append(evidence_id)
        except EGCFError as exc:
            blockers.append(str(exc))
    if proposal.relation != "NOT_EQUIVALENT" and not evidence:
        blockers.append("qualified semantic alignment requires grounded evidence")
    if not proposal.independent_review:
        blockers.append("independent semantic alignment review missing")
    if not left.canonical_eligible or not right.canonical_eligible:
        blockers.append("both aligned concepts must already be canonically resolved")

    by_falsifier = {_text(item.falsifier): item for item in falsifier_results}
    normalized_results: list[SemanticAlignmentFalsifierResult] = []
    for falsifier in proposal.falsifiers:
        result = by_falsifier.get(falsifier)
        if result is None:
            blockers.append(f"missing alignment falsifier result: {falsifier}")
            continue
        outcome = str(result.outcome).strip().upper()
        if outcome != "SURVIVED":
            blockers.append(f"semantic alignment falsifier did not survive: {falsifier}")
        if result.evidence_id:
            try:
                _grounded_evidence(store, result.evidence_id)
            except EGCFError as exc:
                blockers.append(str(exc))
        normalized_results.append(SemanticAlignmentFalsifierResult(falsifier, outcome, result.evidence_id))

    exact_requested = proposal.relation == "EXACT_EQUIVALENT"
    if exact_requested:
        if physical_relation == "DIMENSIONALLY_INCOMPATIBLE":
            blockers.append("exact semantic equivalence is dimensionally contradicted")
        if physical_relation == "SAME_DIMENSION_DIFFERENT_QUANTITY_KIND":
            blockers.append("same dimensions but different quantity kinds are not exact semantic equivalence")
        if not proposal.expected_effects_match:
            blockers.append("exact semantic equivalence requires matching expected effects")
        if not proposal.shared_meaning:
            blockers.append("exact semantic equivalence requires shared meaning")

    if blockers:
        if physical_relation == "DIMENSIONALLY_INCOMPATIBLE":
            status = "SEMANTIC_ALIGNMENT_CONTRADICTED"
        elif physical_relation == "SAME_DIMENSION_DIFFERENT_QUANTITY_KIND":
            status = "DIMENSION_COMPATIBLE_SEMANTICALLY_DISTINCT"
        else:
            status = "SEMANTIC_ALIGNMENT_UNRESOLVED"
        canonical_eligible = False
        exact_eligible = False
    else:
        status_map = {
            "EXACT_EQUIVALENT": "EXACT_CROSS_DOMAIN_SEMANTIC_EQUIVALENCE",
            "SPECIALIZES": "QUALIFIED_SEMANTIC_SPECIALIZATION",
            "GENERALIZES": "QUALIFIED_SEMANTIC_GENERALIZATION",
            "ANALOGOUS_TO": "QUALIFIED_SEMANTIC_ANALOGY",
            "RELATED_TO": "QUALIFIED_SEMANTIC_RELATION",
            "NOT_EQUIVALENT": "QUALIFIED_SEMANTIC_NON_EQUIVALENCE",
        }
        status = status_map[proposal.relation]
        canonical_eligible = True
        exact_eligible = proposal.relation == "EXACT_EQUIVALENT"

    payload = {
        "version": SEMANTIC_ALIGNMENT_VERSION,
        "left": left.concept_signature,
        "right": right.concept_signature,
        "proposal": proposal.proposal_signature,
        "relation": proposal.relation,
        "physical_relation": physical_relation,
        "status": status,
        "evidence_ids": sorted(evidence),
        "falsifiers": [item.to_dict() for item in normalized_results],
        "independent_review": proposal.independent_review,
        "exact_substitution_eligible": exact_eligible,
        "blocking_reasons": blockers,
    }
    return SemanticAlignmentAssessment(
        left_concept_signature=left.concept_signature,
        right_concept_signature=right.concept_signature,
        relation=proposal.relation,
        status=status,
        physical_relation=physical_relation,
        evidence_ids=tuple(sorted(evidence)),
        falsifier_results=tuple(normalized_results),
        independent_review=proposal.independent_review,
        exact_substitution_eligible=exact_eligible,
        canonical_alignment_eligible=canonical_eligible,
        alignment_signature=sha256_json(payload),
        blocking_reasons=tuple(blockers),
    )
