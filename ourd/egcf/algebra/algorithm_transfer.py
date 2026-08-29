from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .semantic_units import SemanticConcept


ALGORITHM_TRANSFER_VERSION = "saa-algorithm-transfer-v1"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


def _sha(value: str, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise EGCFError(f"{label} must be SHA-256")
    return digest


@dataclass(frozen=True)
class AlgorithmDomainContract:
    domain: str
    input_concepts: Tuple[SemanticConcept, ...]
    invariants: Tuple[str, ...]
    boundary_signatures: Tuple[str, ...]
    dynamics_signature: str
    evidence_requirements: Tuple[str, ...] = ()
    qualification_evidence_signatures: Tuple[str, ...] = ()
    evidence_scope_signature: str = ""

    def canonical(self) -> "AlgorithmDomainContract":
        concepts = tuple(sorted(self.input_concepts, key=lambda item: item.concept_signature))
        if any(not isinstance(item, SemanticConcept) or not item.canonical_eligible for item in concepts):
            raise EGCFError("SAA-10.2 requires canonically resolved transfer concepts")
        dynamics = _sha(self.dynamics_signature, "SAA-10.2 dynamics signature")
        boundaries = tuple(sorted(_sha(value, "SAA-10.2 boundary signature") for value in self.boundary_signatures))
        evidence = tuple(sorted(_sha(value, "SAA-10.2 qualification evidence signature") for value in self.qualification_evidence_signatures))
        scope = _sha(self.evidence_scope_signature, "SAA-10.2 evidence scope signature") if self.evidence_scope_signature else ""
        return AlgorithmDomainContract(
            domain=_text(self.domain),
            input_concepts=concepts,
            invariants=_texts(self.invariants),
            boundary_signatures=boundaries,
            dynamics_signature=dynamics,
            evidence_requirements=_texts(self.evidence_requirements),
            qualification_evidence_signatures=evidence,
            evidence_scope_signature=scope,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "input_concept_signatures": [item.concept_signature for item in self.input_concepts],
            "invariants": list(self.invariants),
            "boundary_signatures": list(self.boundary_signatures),
            "dynamics_signature": self.dynamics_signature,
            "evidence_requirements": list(self.evidence_requirements),
            "qualification_evidence_signatures": list(self.qualification_evidence_signatures),
            "evidence_scope_signature": self.evidence_scope_signature,
        }


@dataclass(frozen=True)
class AlgorithmTransferAssessment:
    schema_version: int
    transfer_version: str
    source_algorithm_id: str
    source_domain: str
    target_domain: str
    semantic_contract_match: bool
    boundary_contract_match: bool
    invariant_contract_match: bool
    dynamics_contract_match: bool
    evidence_contract_match: bool
    status: str
    transfer_without_requalification: bool
    adaptation_required: bool
    blocking_gaps: Tuple[str, ...]
    adaptation_gaps: Tuple[str, ...]
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transfer_version": self.transfer_version,
            "source_algorithm_id": self.source_algorithm_id,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "semantic_contract_match": self.semantic_contract_match,
            "boundary_contract_match": self.boundary_contract_match,
            "invariant_contract_match": self.invariant_contract_match,
            "dynamics_contract_match": self.dynamics_contract_match,
            "evidence_contract_match": self.evidence_contract_match,
            "status": self.status,
            "transfer_without_requalification": self.transfer_without_requalification,
            "adaptation_required": self.adaptation_required,
            "blocking_gaps": list(self.blocking_gaps),
            "adaptation_gaps": list(self.adaptation_gaps),
            "assessment_signature": self.assessment_signature,
        }


def _concept_equivalent(left: SemanticConcept, right: SemanticConcept, ontology: Any | None) -> bool:
    if left.concept_signature == right.concept_signature:
        return True
    if ontology is None or not hasattr(ontology, "meanings_equivalent"):
        return False
    left_terms = (left.canonical_name, left.meaning, *left.aliases)
    right_terms = (right.canonical_name, right.meaning, *right.aliases)
    for a in left_terms:
        for b in right_terms:
            try:
                if ontology.meanings_equivalent(a, b):
                    return True
            except Exception:
                continue
    return False


def assess_algorithm_transfer(
    source_algorithm_id: str,
    source: AlgorithmDomainContract,
    target: AlgorithmDomainContract,
    *,
    ontology: Any | None = None,
) -> AlgorithmTransferAssessment:
    src = source.canonical()
    dst = target.canonical()
    semantic_match = len(src.input_concepts) == len(dst.input_concepts) and all(
        any(_concept_equivalent(left, right, ontology) for right in dst.input_concepts)
        for left in src.input_concepts
    )
    boundary_match = src.boundary_signatures == dst.boundary_signatures
    invariant_match = set(src.invariants).issubset(set(dst.invariants))
    dynamics_match = src.dynamics_signature == dst.dynamics_signature
    evidence_requirements_match = set(src.evidence_requirements).issubset(set(dst.evidence_requirements))
    evidence_signatures_match = bool(src.qualification_evidence_signatures) and set(src.qualification_evidence_signatures).issubset(
        set(dst.qualification_evidence_signatures)
    )
    evidence_scope_match = bool(src.evidence_scope_signature) and src.evidence_scope_signature == dst.evidence_scope_signature
    evidence_match = evidence_requirements_match and evidence_signatures_match and evidence_scope_match

    blockers: list[str] = []
    adaptation: list[str] = []
    if not semantic_match:
        blockers.append("semantic contracts are not exactly equivalent")
    if not boundary_match:
        adaptation.append("BOUNDARY_CONTRACT")
    if not invariant_match:
        adaptation.append("INVARIANT_CONTRACT")
    if not dynamics_match:
        adaptation.append("DYNAMICS_CONTRACT")
    if not evidence_match:
        adaptation.append("EVIDENCE_CONTRACT")

    exact = semantic_match and boundary_match and invariant_match and dynamics_match and evidence_match
    if exact:
        status = "EXACT_TRANSFER_CONTRACT_MATCH"
    elif blockers:
        status = "TRANSFER_BLOCKED_SEMANTIC_MISMATCH"
    else:
        status = "TRANSFER_REQUIRES_DOMAIN_REQUALIFICATION"
    payload = {
        "version": ALGORITHM_TRANSFER_VERSION,
        "source_algorithm_id": str(source_algorithm_id),
        "source": src.to_dict(),
        "target": dst.to_dict(),
        "semantic_match": semantic_match,
        "boundary_match": boundary_match,
        "invariant_match": invariant_match,
        "dynamics_match": dynamics_match,
        "evidence_requirements_match": evidence_requirements_match,
        "evidence_signatures_match": evidence_signatures_match,
        "evidence_scope_match": evidence_scope_match,
        "status": status,
        "blocking_gaps": blockers,
        "adaptation_gaps": adaptation,
    }
    return AlgorithmTransferAssessment(
        schema_version=1,
        transfer_version=ALGORITHM_TRANSFER_VERSION,
        source_algorithm_id=str(source_algorithm_id),
        source_domain=src.domain,
        target_domain=dst.domain,
        semantic_contract_match=semantic_match,
        boundary_contract_match=boundary_match,
        invariant_contract_match=invariant_match,
        dynamics_contract_match=dynamics_match,
        evidence_contract_match=evidence_match,
        status=status,
        transfer_without_requalification=exact,
        adaptation_required=bool(adaptation),
        blocking_gaps=tuple(blockers),
        adaptation_gaps=tuple(adaptation),
        assessment_signature=sha256_json(payload),
    )
