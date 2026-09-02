from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json


FAILURE_ALGEBRA_VERSION = "saa-failure-algebra-v1"
FAILURE_CLASSES = {
    "INVARIANT_VIOLATION",
    "EXPERIMENT_REGRESSION",
    "EXPERIMENT_TRADEOFF",
    "SEMANTIC_MISMATCH",
    "RETRIEVAL_MISMATCH",
    "CYCLE_STOP",
    "ADAPTATION_REJECTED",
    "QUALIFICATION_FAILURE",
    "EVIDENCE_FAILURE",
    "OTHER_BOUNDED_FAILURE",
}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


def _sha(value: str, label: str, *, allow_empty: bool = True) -> str:
    normalized = str(value).strip().lower()
    if not normalized and allow_empty:
        return ""
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise EGCFError(f"{label} must be an exact SHA-256 signature")
    return normalized


@dataclass(frozen=True)
class FailureObservation:
    source_kind: str
    component: str
    failure_class: str
    mechanism: str
    semantic_roles: Tuple[str, ...]
    violated_invariants: Tuple[str, ...]
    boundary_signature: str
    context_signature: str
    evidence_ids: Tuple[str, ...]
    provenance_id: str
    observation_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "component": self.component,
            "failure_class": self.failure_class,
            "mechanism": self.mechanism,
            "semantic_roles": list(self.semantic_roles),
            "violated_invariants": list(self.violated_invariants),
            "boundary_signature": self.boundary_signature,
            "context_signature": self.context_signature,
            "evidence_ids": list(self.evidence_ids),
            "provenance_id": self.provenance_id,
            "observation_signature": self.observation_signature,
        }


@dataclass(frozen=True)
class CanonicalFailurePattern:
    failure_class: str
    component: str
    mechanism: str
    semantic_roles: Tuple[str, ...]
    violated_invariants: Tuple[str, ...]
    boundary_signature: str
    context_signature: str
    pattern_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class,
            "component": self.component,
            "mechanism": self.mechanism,
            "semantic_roles": list(self.semantic_roles),
            "violated_invariants": list(self.violated_invariants),
            "boundary_signature": self.boundary_signature,
            "context_signature": self.context_signature,
            "pattern_signature": self.pattern_signature,
        }


@dataclass(frozen=True)
class FailureMatchAssessment:
    status: str
    exact_match: bool
    retry_blocked: bool
    matched_pattern_signature: str
    differences: Tuple[str, ...]
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exact_match": self.exact_match,
            "retry_blocked": self.retry_blocked,
            "matched_pattern_signature": self.matched_pattern_signature,
            "differences": list(self.differences),
            "assessment_signature": self.assessment_signature,
        }


def make_failure_observation(
    *,
    source_kind: str,
    component: str,
    failure_class: str,
    mechanism: str,
    semantic_roles: Sequence[str] = (),
    violated_invariants: Sequence[str] = (),
    boundary_signature: str = "",
    context_signature: str = "",
    evidence_ids: Sequence[str],
    provenance_id: str,
) -> FailureObservation:
    source = _text(source_kind)
    canonical_component = _text(component)
    klass = str(failure_class).strip().upper()
    canonical_mechanism = _text(mechanism)
    if not source or not canonical_component or not canonical_mechanism:
        raise EGCFError("SAA-12.1 failure source, component and mechanism are required")
    if klass not in FAILURE_CLASSES:
        raise EGCFError(f"unsupported SAA-12.1 failure class: {klass}")
    boundary = _sha(boundary_signature, "failure boundary signature")
    context = _sha(context_signature, "failure context signature")
    evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    if not evidence:
        raise EGCFError("SAA-12.1 failure observation requires evidence references")
    provenance = str(provenance_id).strip()
    if not provenance:
        raise EGCFError("SAA-12.1 failure observation requires provenance_id")
    material = {
        "version": FAILURE_ALGEBRA_VERSION,
        "source_kind": source,
        "component": canonical_component,
        "failure_class": klass,
        "mechanism": canonical_mechanism,
        "semantic_roles": list(_texts(semantic_roles)),
        "violated_invariants": list(_texts(violated_invariants)),
        "boundary_signature": boundary,
        "context_signature": context,
        "evidence_ids": list(evidence),
        "provenance_id": provenance,
    }
    return FailureObservation(
        source_kind=source,
        component=canonical_component,
        failure_class=klass,
        mechanism=canonical_mechanism,
        semantic_roles=_texts(semantic_roles),
        violated_invariants=_texts(violated_invariants),
        boundary_signature=boundary,
        context_signature=context,
        evidence_ids=evidence,
        provenance_id=provenance,
        observation_signature=sha256_json(material),
    )


def canonicalize_failure(observation: FailureObservation) -> CanonicalFailurePattern:
    if not isinstance(observation, FailureObservation):
        raise EGCFError("SAA-12.1 canonicalization requires FailureObservation")
    material = {
        "version": FAILURE_ALGEBRA_VERSION,
        "component": observation.component,
        "failure_class": observation.failure_class,
        "mechanism": observation.mechanism,
        "semantic_roles": list(observation.semantic_roles),
        "violated_invariants": list(observation.violated_invariants),
        "boundary_signature": observation.boundary_signature,
        "context_signature": observation.context_signature,
    }
    return CanonicalFailurePattern(
        failure_class=observation.failure_class,
        component=observation.component,
        mechanism=observation.mechanism,
        semantic_roles=observation.semantic_roles,
        violated_invariants=observation.violated_invariants,
        boundary_signature=observation.boundary_signature,
        context_signature=observation.context_signature,
        pattern_signature=sha256_json(material),
    )


def compare_failure_to_pattern(
    observation: FailureObservation,
    pattern: CanonicalFailurePattern,
    *,
    prior_occurrence_count: int = 1,
) -> FailureMatchAssessment:
    if not isinstance(observation, FailureObservation) or not isinstance(pattern, CanonicalFailurePattern):
        raise EGCFError("SAA-12.1 comparison requires failure observation and canonical pattern")
    candidate = canonicalize_failure(observation)
    differences: list[str] = []
    for field in (
        "failure_class",
        "component",
        "mechanism",
        "semantic_roles",
        "violated_invariants",
        "boundary_signature",
        "context_signature",
    ):
        if getattr(candidate, field) != getattr(pattern, field):
            differences.append(field.upper())
    exact = not differences and candidate.pattern_signature == pattern.pattern_signature
    if exact:
        status = "EXACT_CANONICAL_FAILURE_MATCH"
    elif candidate.failure_class == pattern.failure_class and candidate.mechanism == pattern.mechanism:
        status = "SAME_FAILURE_MECHANISM_DIFFERENT_SCOPE"
    else:
        status = "DISTINCT_FAILURE_PATTERN"
    retry_blocked = exact and int(prior_occurrence_count) > 0
    payload = {
        "version": FAILURE_ALGEBRA_VERSION,
        "observation_signature": observation.observation_signature,
        "pattern_signature": pattern.pattern_signature,
        "status": status,
        "differences": differences,
        "prior_occurrence_count": int(prior_occurrence_count),
        "retry_blocked": retry_blocked,
    }
    return FailureMatchAssessment(
        status=status,
        exact_match=exact,
        retry_blocked=retry_blocked,
        matched_pattern_signature=pattern.pattern_signature if exact else "",
        differences=tuple(differences),
        assessment_signature=sha256_json(payload),
    )
