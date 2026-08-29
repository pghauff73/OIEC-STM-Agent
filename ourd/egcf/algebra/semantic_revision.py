from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact
from .semantic_units import (
    SEMANTIC_UNITS_VERSION,
    PhysicalDimensionVector,
    PhysicalUnit,
    SemanticConcept,
    make_semantic_concept,
    physical_unit,
)


SEMANTIC_REVISION_VERSION = "saa-semantic-revision-v1"
SEMANTIC_REVISION_SUBSYSTEMS = (
    "EON",
    "OURD",
    "IURM",
    "CFEL",
    "BD_DL",
    "HYPOTHESIS_STATE",
    "ALGORITHM_STORE",
)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _evidence_id(value: Any) -> str:
    return str(value).strip()


@dataclass(frozen=True)
class SemanticContradiction:
    contradiction_id: str
    concept_signature: str
    contradiction_kind: str
    observed_statement: str
    observed_meaning: str
    observed_quantity_kind: str
    observed_dimension: PhysicalDimensionVector | None
    observed_unit_symbol: str
    evidence_ids: Tuple[str, ...]
    severity_bp: int
    status: str
    contradiction_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "concept_signature": self.concept_signature,
            "contradiction_kind": self.contradiction_kind,
            "observed_statement": self.observed_statement,
            "observed_meaning": self.observed_meaning,
            "observed_quantity_kind": self.observed_quantity_kind,
            "observed_dimension": self.observed_dimension.to_dict() if self.observed_dimension else None,
            "observed_unit_symbol": self.observed_unit_symbol,
            "evidence_ids": list(self.evidence_ids),
            "severity_bp": self.severity_bp,
            "status": self.status,
            "contradiction_signature": self.contradiction_signature,
        }


def detect_semantic_contradiction(
    concept: SemanticConcept,
    *,
    observed_statement: str,
    evidence_ids: Sequence[str],
    observed_meaning: str = "",
    observed_quantity_kind: str = "",
    observed_dimension: PhysicalDimensionVector | None = None,
    observed_unit: str | PhysicalUnit | None = None,
    severity_bp: int = 7500,
) -> SemanticContradiction:
    if not isinstance(concept, SemanticConcept):
        raise EGCFError("SAA-9.2 contradiction detection requires SemanticConcept")
    statement = " ".join(str(observed_statement).strip().split())
    if not statement:
        raise EGCFError("semantic contradiction requires observed statement")
    evidence = tuple(sorted({_evidence_id(value) for value in evidence_ids if _evidence_id(value)}))
    if not evidence:
        raise EGCFError("semantic contradiction requires evidence references")
    severity = max(0, min(int(severity_bp), 10000))
    unit = physical_unit(observed_unit) if isinstance(observed_unit, str) else observed_unit
    dimension = observed_dimension or (unit.dimension if unit else None)
    meaning = _text(observed_meaning)
    quantity = _text(observed_quantity_kind)
    kinds: list[str] = []
    if meaning and meaning != concept.meaning:
        kinds.append("MEANING_CONTRADICTION")
    if quantity and quantity != concept.quantity_kind:
        kinds.append("QUANTITY_KIND_CONTRADICTION")
    if dimension is not None and concept.physical_dimension is not None and dimension != concept.physical_dimension:
        kinds.append("DIMENSION_CONTRADICTION")
    if unit is not None and concept.canonical_unit is not None and unit.dimension != concept.canonical_unit.dimension:
        kinds.append("UNIT_DIMENSION_CONTRADICTION")
    if not kinds:
        kinds.append("EVIDENCE_CONTRADICTS_DECLARED_SEMANTICS")
    kind = "+".join(kinds)
    payload = {
        "version": SEMANTIC_REVISION_VERSION,
        "concept_signature": concept.concept_signature,
        "contradiction_kind": kind,
        "observed_statement": statement,
        "observed_meaning": meaning,
        "observed_quantity_kind": quantity,
        "observed_dimension": list(dimension.exponents) if dimension else None,
        "observed_unit_signature": unit.signature if unit else None,
        "evidence_ids": list(evidence),
        "severity_bp": severity,
    }
    signature = sha256_json(payload)
    return SemanticContradiction(
        contradiction_id=f"semantic-contradiction:{signature[:24]}",
        concept_signature=concept.concept_signature,
        contradiction_kind=kind,
        observed_statement=statement,
        observed_meaning=meaning,
        observed_quantity_kind=quantity,
        observed_dimension=dimension,
        observed_unit_symbol=unit.canonical_symbol if unit else "",
        evidence_ids=evidence,
        severity_bp=severity,
        status="SEMANTIC_CONTRADICTION_OPEN",
        contradiction_signature=signature,
    )


@dataclass(frozen=True)
class SemanticRevisionProposal:
    proposal_id: str
    source_concept_signature: str
    contradiction_signatures: Tuple[str, ...]
    proposed_name: str
    proposed_meaning: str
    proposed_domain: str
    proposed_quantity_kind: str
    proposed_aliases: Tuple[str, ...]
    proposed_dimension: PhysicalDimensionVector | None
    proposed_unit_symbol: str
    assumptions: Tuple[str, ...]
    falsifiers: Tuple[str, ...]
    epistemic_status: str
    proposal_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "source_concept_signature": self.source_concept_signature,
            "contradiction_signatures": list(self.contradiction_signatures),
            "proposed_name": self.proposed_name,
            "proposed_meaning": self.proposed_meaning,
            "proposed_domain": self.proposed_domain,
            "proposed_quantity_kind": self.proposed_quantity_kind,
            "proposed_aliases": list(self.proposed_aliases),
            "proposed_dimension": self.proposed_dimension.to_dict() if self.proposed_dimension else None,
            "proposed_unit_symbol": self.proposed_unit_symbol,
            "assumptions": list(self.assumptions),
            "falsifiers": list(self.falsifiers),
            "epistemic_status": self.epistemic_status,
            "proposal_signature": self.proposal_signature,
        }


def propose_semantic_revision(
    concept: SemanticConcept,
    contradictions: Sequence[SemanticContradiction],
    *,
    meaning: str,
    quantity_kind: str | None = None,
    name: str | None = None,
    domain: str | None = None,
    aliases: Sequence[str] | None = None,
    physical_dimension: PhysicalDimensionVector | None = None,
    canonical_unit: str | PhysicalUnit | None = None,
    assumptions: Sequence[str] = (),
    falsifiers: Sequence[str] = (),
) -> SemanticRevisionProposal:
    if not contradictions:
        raise EGCFError("SAA-9.2 semantic revision requires at least one contradiction")
    if any(item.concept_signature != concept.concept_signature for item in contradictions):
        raise EGCFError("semantic revision contradictions target different concepts")
    unit = physical_unit(canonical_unit) if isinstance(canonical_unit, str) else canonical_unit
    dimension = physical_dimension if physical_dimension is not None else (
        unit.dimension if unit is not None else concept.physical_dimension
    )
    if unit is not None and dimension != unit.dimension:
        raise EGCFError("proposed semantic unit contradicts proposed dimension")
    proposed_name = _text(name if name is not None else concept.canonical_name)
    proposed_meaning = _text(meaning)
    proposed_domain = _text(domain if domain is not None else concept.domain)
    proposed_quantity = _text(quantity_kind if quantity_kind is not None else concept.quantity_kind)
    proposed_aliases = tuple(sorted({_text(value) for value in (aliases if aliases is not None else concept.aliases) if _text(value)}))
    if not proposed_meaning:
        raise EGCFError("semantic revision requires proposed meaning")
    contradiction_signatures = tuple(sorted({item.contradiction_signature for item in contradictions}))
    canonical_assumptions = tuple(sorted({_text(value) for value in assumptions if _text(value)}))
    canonical_falsifiers = tuple(sorted({_text(value) for value in falsifiers if _text(value)}))
    payload = {
        "version": SEMANTIC_REVISION_VERSION,
        "source_concept_signature": concept.concept_signature,
        "contradictions": list(contradiction_signatures),
        "name": proposed_name,
        "meaning": proposed_meaning,
        "domain": proposed_domain,
        "quantity_kind": proposed_quantity,
        "aliases": list(proposed_aliases),
        "dimension": list(dimension.exponents) if dimension else None,
        "unit_signature": unit.signature if unit else (concept.canonical_unit.signature if concept.canonical_unit else None),
        "assumptions": list(canonical_assumptions),
        "falsifiers": list(canonical_falsifiers),
    }
    signature = sha256_json(payload)
    return SemanticRevisionProposal(
        proposal_id=f"semantic-revision:{signature[:24]}",
        source_concept_signature=concept.concept_signature,
        contradiction_signatures=contradiction_signatures,
        proposed_name=proposed_name,
        proposed_meaning=proposed_meaning,
        proposed_domain=proposed_domain,
        proposed_quantity_kind=proposed_quantity,
        proposed_aliases=proposed_aliases,
        proposed_dimension=dimension,
        proposed_unit_symbol=(unit or concept.canonical_unit).canonical_symbol if (unit or concept.canonical_unit) else "",
        assumptions=canonical_assumptions,
        falsifiers=canonical_falsifiers,
        epistemic_status="MODEL_PROPOSED_SEMANTIC_REVISION",
        proposal_signature=signature,
    )


@dataclass(frozen=True)
class SemanticRevisionFalsifierResult:
    falsifier: str
    outcome: str
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "falsifier": _text(self.falsifier),
            "outcome": str(self.outcome).strip().upper(),
            "evidence_id": _evidence_id(self.evidence_id),
        }


@dataclass(frozen=True)
class SemanticRequalification:
    source_concept_signature: str
    replacement_concept: SemanticConcept | None
    proposal_signature: str
    contradiction_signatures: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    falsifier_results: Tuple[SemanticRevisionFalsifierResult, ...]
    independent_review: bool
    status: str
    canonical_replacement_eligible: bool
    requalification_signature: str
    blocking_reasons: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_concept_signature": self.source_concept_signature,
            "replacement_concept": self.replacement_concept.to_dict() if self.replacement_concept else None,
            "proposal_signature": self.proposal_signature,
            "contradiction_signatures": list(self.contradiction_signatures),
            "evidence_ids": list(self.evidence_ids),
            "falsifier_results": [item.to_dict() for item in self.falsifier_results],
            "independent_review": self.independent_review,
            "status": self.status,
            "canonical_replacement_eligible": self.canonical_replacement_eligible,
            "requalification_signature": self.requalification_signature,
            "blocking_reasons": list(self.blocking_reasons),
        }


def _grounded_evidence(store: Any, evidence_id: str) -> EvidenceArtifact:
    try:
        record = store.get(evidence_id)
    except Exception as exc:
        raise EGCFError(f"semantic requalification evidence is not registered: {evidence_id}") from exc
    if not isinstance(record, EvidenceArtifact):
        raise EGCFError("semantic requalification evidence ID does not reference EvidenceArtifact")
    if record.success is not True or record.simulated:
        raise EGCFError("semantic requalification evidence must be successful and non-simulated")
    if not record.producer.startswith(("deterministic-", "human-")):
        raise EGCFError("semantic requalification evidence requires deterministic or human producer")
    if record.method in {"reported", "model-claimed", "model-generated-claim"}:
        raise EGCFError("reported/model-claimed evidence cannot requalify semantics")
    return record


def requalify_semantic_revision(
    store: Any,
    source: SemanticConcept,
    proposal: SemanticRevisionProposal,
    *,
    evidence_ids: Sequence[str],
    falsifier_results: Sequence[SemanticRevisionFalsifierResult],
    independent_review: bool,
) -> SemanticRequalification:
    if proposal.source_concept_signature != source.concept_signature:
        raise EGCFError("semantic revision proposal targets a different source concept")
    evidence = tuple(sorted({_evidence_id(value) for value in evidence_ids if _evidence_id(value)}))
    blockers: list[str] = []
    if not evidence:
        blockers.append("no grounded semantic requalification evidence")
    else:
        for evidence_id in evidence:
            try:
                _grounded_evidence(store, evidence_id)
            except EGCFError as exc:
                blockers.append(str(exc))
    by_falsifier = {_text(item.falsifier): item for item in falsifier_results}
    normalized_results: list[SemanticRevisionFalsifierResult] = []
    for falsifier in proposal.falsifiers:
        result = by_falsifier.get(falsifier)
        if result is None:
            blockers.append(f"missing falsifier result: {falsifier}")
            continue
        outcome = str(result.outcome).strip().upper()
        if outcome != "SURVIVED":
            blockers.append(f"semantic revision falsifier did not survive: {falsifier}")
        if result.evidence_id:
            try:
                _grounded_evidence(store, result.evidence_id)
            except EGCFError as exc:
                blockers.append(str(exc))
        normalized_results.append(
            SemanticRevisionFalsifierResult(falsifier, outcome, result.evidence_id)
        )
    if not independent_review:
        blockers.append("independent semantic review missing")

    unit = physical_unit(proposal.proposed_unit_symbol) if proposal.proposed_unit_symbol else None
    replacement: SemanticConcept | None = None
    if not blockers:
        replacement = make_semantic_concept(
            name=proposal.proposed_name,
            meaning=proposal.proposed_meaning,
            domain=proposal.proposed_domain,
            quantity_kind=proposal.proposed_quantity_kind,
            aliases=proposal.proposed_aliases,
            physical_dimension=proposal.proposed_dimension,
            canonical_unit=unit,
            evidence_ids=evidence,
            semantic_status="SEMANTICALLY_RESOLVED",
        )
    status = "SEMANTIC_REQUALIFIED" if replacement is not None else "SEMANTIC_REQUALIFICATION_BLOCKED"
    payload = {
        "version": SEMANTIC_REVISION_VERSION,
        "source": source.concept_signature,
        "proposal": proposal.proposal_signature,
        "contradictions": list(proposal.contradiction_signatures),
        "replacement": replacement.concept_signature if replacement else None,
        "evidence_ids": list(evidence),
        "falsifiers": [item.to_dict() for item in normalized_results],
        "independent_review": bool(independent_review),
        "status": status,
        "blocking_reasons": blockers,
    }
    return SemanticRequalification(
        source_concept_signature=source.concept_signature,
        replacement_concept=replacement,
        proposal_signature=proposal.proposal_signature,
        contradiction_signatures=proposal.contradiction_signatures,
        evidence_ids=evidence,
        falsifier_results=tuple(normalized_results),
        independent_review=bool(independent_review),
        status=status,
        canonical_replacement_eligible=replacement is not None,
        requalification_signature=sha256_json(payload),
        blocking_reasons=tuple(blockers),
    )


@dataclass(frozen=True)
class SemanticRevisionDirective:
    subsystem: str
    action: str
    blocking: bool
    contradiction_signature: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "action": self.action,
            "blocking": self.blocking,
            "contradiction_signature": self.contradiction_signature,
            "rationale": self.rationale,
        }


def propagate_semantic_contradiction(contradiction: SemanticContradiction) -> Tuple[SemanticRevisionDirective, ...]:
    actions = {
        "EON": "SURFACE_SEMANTIC_CONTRADICTION",
        "OURD": "CREATE_SEMANTIC_REVISION_OBJECTIVE",
        "IURM": "BLOCK_CONTRADICTED_MEANING_AS_INDEPENDENT_DIMENSION",
        "CFEL": "REGISTER_SEMANTIC_COLLISION",
        "BD_DL": "REASSESS_MEANING_DOMAIN_AND_BOUNDS",
        "HYPOTHESIS_STATE": "STORE_REVISED_MEANING_AS_UNVERIFIED_HYPOTHESIS",
        "ALGORITHM_STORE": "SUSPEND_DEPENDENT_CANONICAL_REUSE_PENDING_REQUALIFICATION",
    }
    return tuple(
        SemanticRevisionDirective(
            subsystem=subsystem,
            action=actions[subsystem],
            blocking=subsystem in {"IURM", "ALGORITHM_STORE"},
            contradiction_signature=contradiction.contradiction_signature,
            rationale=(
                "Contradicted semantics cannot remain canonical merely because prior knowledge used them. "
                "Revision requires evidence-backed requalification."
            ),
        )
        for subsystem in SEMANTIC_REVISION_SUBSYSTEMS
    )
