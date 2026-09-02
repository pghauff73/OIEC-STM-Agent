from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .algorithm_adaptation import AdaptationStep, AdaptedAlgorithmCandidate


ADAPTATION_LINEAGE_VERSION = "saa-adaptation-lineage-v1"
MAX_LINEAGE_DEPTH = 64


def _sha(value: str, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EGCFError(f"{label} must be an exact SHA-256 digest")
    return digest


def adapted_candidate_ref(signature: str) -> str:
    return f"adapted-candidate:sha256:{_sha(signature, 'adapted candidate signature')}"


@dataclass(frozen=True)
class AdaptationLineageEdge:
    schema_version: int
    lineage_version: str
    relation: str
    parent_ref: str
    child_ref: str
    base_algorithm_id: str
    component: str
    changed_dimension: str
    step_signature: str
    source_explanation_signature: str
    candidate_signature: str
    parent_candidate_signature: str
    edge_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lineage_version": self.lineage_version,
            "relation": self.relation,
            "parent_ref": self.parent_ref,
            "child_ref": self.child_ref,
            "base_algorithm_id": self.base_algorithm_id,
            "component": self.component,
            "changed_dimension": self.changed_dimension,
            "step_signature": self.step_signature,
            "source_explanation_signature": self.source_explanation_signature,
            "candidate_signature": self.candidate_signature,
            "parent_candidate_signature": self.parent_candidate_signature,
            "edge_signature": self.edge_signature,
        }


@dataclass(frozen=True)
class AdaptationPromotionRecord:
    schema_version: int
    lineage_version: str
    candidate_ref: str
    canonical_algorithm_ref: str
    qualification_signature: str
    evidence_ids: Tuple[str, ...]
    promotion_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lineage_version": self.lineage_version,
            "candidate_ref": self.candidate_ref,
            "canonical_algorithm_ref": self.canonical_algorithm_ref,
            "qualification_signature": self.qualification_signature,
            "evidence_ids": list(self.evidence_ids),
            "promotion_signature": self.promotion_signature,
        }


def make_adaptation_lineage_edge(
    candidate: AdaptedAlgorithmCandidate,
    step: AdaptationStep,
    *,
    source_explanation_signature: str,
) -> AdaptationLineageEdge:
    if not isinstance(candidate, AdaptedAlgorithmCandidate):
        raise EGCFError("SAA-11.1 lineage requires AdaptedAlgorithmCandidate")
    if not isinstance(step, AdaptationStep):
        raise EGCFError("SAA-11.1 lineage requires the originating AdaptationStep")
    if candidate.changed_dimension != step.dimension:
        raise EGCFError("lineage candidate dimension differs from originating adaptation step")
    if candidate.component != step.component:
        raise EGCFError("lineage candidate component differs from originating adaptation step")
    if candidate.base_algorithm_id != step.base_algorithm_id:
        raise EGCFError("lineage candidate base algorithm differs from originating adaptation step")
    if not candidate.qualification_required or candidate.canonical_reuse_eligible:
        raise EGCFError("SAA-11.1 lineage accepts only unqualified adaptation candidates")
    explanation_signature = _sha(source_explanation_signature, "source explanation signature")
    _sha(step.step_signature, "adaptation step signature")
    _sha(candidate.candidate_signature, "adapted candidate signature")
    parent_signature = str(candidate.parent_candidate_signature).strip().lower()
    if parent_signature:
        _sha(parent_signature, "parent adapted candidate signature")
        if parent_signature == candidate.candidate_signature:
            raise EGCFError("adaptation lineage cannot self-parent")
        parent_ref = adapted_candidate_ref(parent_signature)
    else:
        if not str(candidate.base_algorithm_id).strip():
            raise EGCFError("first-generation adaptation candidate requires a canonical base algorithm reference")
        parent_ref = str(candidate.base_algorithm_id).strip()
    child_ref = adapted_candidate_ref(candidate.candidate_signature)
    payload = {
        "version": ADAPTATION_LINEAGE_VERSION,
        "relation": "ADAPTED_FROM",
        "parent_ref": parent_ref,
        "child_ref": child_ref,
        "base_algorithm_id": candidate.base_algorithm_id,
        "component": candidate.component,
        "changed_dimension": candidate.changed_dimension,
        "step_signature": step.step_signature,
        "source_explanation_signature": explanation_signature,
        "candidate_signature": candidate.candidate_signature,
        "parent_candidate_signature": parent_signature,
    }
    return AdaptationLineageEdge(
        schema_version=1,
        lineage_version=ADAPTATION_LINEAGE_VERSION,
        relation="ADAPTED_FROM",
        parent_ref=parent_ref,
        child_ref=child_ref,
        base_algorithm_id=candidate.base_algorithm_id,
        component=candidate.component,
        changed_dimension=candidate.changed_dimension,
        step_signature=step.step_signature,
        source_explanation_signature=explanation_signature,
        candidate_signature=candidate.candidate_signature,
        parent_candidate_signature=parent_signature,
        edge_signature=sha256_json(payload),
    )


def make_adaptation_promotion(
    *,
    candidate_ref: str,
    canonical_algorithm_ref: str,
    qualification_signature: str,
    evidence_ids: Sequence[str],
) -> AdaptationPromotionRecord:
    candidate = str(candidate_ref).strip()
    if not candidate.startswith("adapted-candidate:sha256:"):
        raise EGCFError("SAA-11.1 promotion requires adapted-candidate reference")
    _sha(candidate.rsplit(":", 1)[-1], "promotion candidate signature")
    canonical = str(canonical_algorithm_ref).strip()
    if not canonical.startswith(("canonical-algorithm:sha256:", "canonical-reasoning:sha256:")):
        raise EGCFError("SAA-11.1 promotion target must be canonical mathematical or reasoning algorithm")
    qualification = _sha(qualification_signature, "promotion qualification signature")
    evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    if not evidence:
        raise EGCFError("SAA-11.1 promotion requires grounded qualification evidence")
    payload = {
        "version": ADAPTATION_LINEAGE_VERSION,
        "candidate_ref": candidate,
        "canonical_algorithm_ref": canonical,
        "qualification_signature": qualification,
        "evidence_ids": list(evidence),
    }
    return AdaptationPromotionRecord(
        schema_version=1,
        lineage_version=ADAPTATION_LINEAGE_VERSION,
        candidate_ref=candidate,
        canonical_algorithm_ref=canonical,
        qualification_signature=qualification,
        evidence_ids=evidence,
        promotion_signature=sha256_json(payload),
    )
