from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json


KNOWLEDGE_INTEGRITY_VERSION = "saa-longitudinal-knowledge-integrity-v1"


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EGCFError(f"{label} must be a non-negative integer")
    return int(value)


def _rate_bp(numerator: int, denominator: int, *, inverse: bool = False) -> int:
    if denominator <= 0:
        return 10000 if inverse else 0
    raw = min(10000, (10000 * numerator) // denominator)
    return 10000 - raw if inverse else raw


@dataclass(frozen=True)
class KnowledgeIntegritySnapshot:
    generation: int
    canonical_knowledge_count: int
    semantic_contradictions: int
    semantic_drift_events: int
    false_canonical_admissions: int
    corrected_error_opportunities: int
    corrected_error_recurrences: int
    retrieval_queries: int
    retrieval_correct_selections: int
    equivalent_failure_opportunities: int
    equivalent_failure_retries: int
    contradiction_rate_bp: int
    semantic_drift_rate_bp: int
    false_admission_rate_bp: int
    corrected_error_recurrence_rate_bp: int
    retrieval_precision_bp: int
    equivalent_failure_avoidance_bp: int
    snapshot_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "canonical_knowledge_count": self.canonical_knowledge_count,
            "semantic_contradictions": self.semantic_contradictions,
            "semantic_drift_events": self.semantic_drift_events,
            "false_canonical_admissions": self.false_canonical_admissions,
            "corrected_error_opportunities": self.corrected_error_opportunities,
            "corrected_error_recurrences": self.corrected_error_recurrences,
            "retrieval_queries": self.retrieval_queries,
            "retrieval_correct_selections": self.retrieval_correct_selections,
            "equivalent_failure_opportunities": self.equivalent_failure_opportunities,
            "equivalent_failure_retries": self.equivalent_failure_retries,
            "contradiction_rate_bp": self.contradiction_rate_bp,
            "semantic_drift_rate_bp": self.semantic_drift_rate_bp,
            "false_admission_rate_bp": self.false_admission_rate_bp,
            "corrected_error_recurrence_rate_bp": self.corrected_error_recurrence_rate_bp,
            "retrieval_precision_bp": self.retrieval_precision_bp,
            "equivalent_failure_avoidance_bp": self.equivalent_failure_avoidance_bp,
            "snapshot_signature": self.snapshot_signature,
        }


@dataclass(frozen=True)
class KnowledgeIntegrityPolicy:
    max_contradiction_rate_bp: int = 500
    max_semantic_drift_rate_bp: int = 500
    max_false_admission_rate_bp: int = 0
    max_corrected_error_recurrence_rate_bp: int = 500
    min_retrieval_precision_bp: int = 9000
    min_equivalent_failure_avoidance_bp: int = 9000

    def canonical(self) -> "KnowledgeIntegrityPolicy":
        fields = {
            "max_contradiction_rate_bp": self.max_contradiction_rate_bp,
            "max_semantic_drift_rate_bp": self.max_semantic_drift_rate_bp,
            "max_false_admission_rate_bp": self.max_false_admission_rate_bp,
            "max_corrected_error_recurrence_rate_bp": self.max_corrected_error_recurrence_rate_bp,
            "min_retrieval_precision_bp": self.min_retrieval_precision_bp,
            "min_equivalent_failure_avoidance_bp": self.min_equivalent_failure_avoidance_bp,
        }
        for name, value in fields.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000:
                raise EGCFError(f"{name} must be integer basis points in 0..10000")
        return KnowledgeIntegrityPolicy(**fields)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_contradiction_rate_bp": self.max_contradiction_rate_bp,
            "max_semantic_drift_rate_bp": self.max_semantic_drift_rate_bp,
            "max_false_admission_rate_bp": self.max_false_admission_rate_bp,
            "max_corrected_error_recurrence_rate_bp": self.max_corrected_error_recurrence_rate_bp,
            "min_retrieval_precision_bp": self.min_retrieval_precision_bp,
            "min_equivalent_failure_avoidance_bp": self.min_equivalent_failure_avoidance_bp,
        }


@dataclass(frozen=True)
class KnowledgeIntegrityTrajectory:
    snapshot_signatures: Tuple[str, ...]
    latest_generation: int
    status: str
    policy_violations: Tuple[str, ...]
    degraded_dimensions: Tuple[str, ...]
    improved_dimensions: Tuple[str, ...]
    knowledge_integrity_qualified: bool
    trajectory_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_signatures": list(self.snapshot_signatures),
            "latest_generation": self.latest_generation,
            "status": self.status,
            "policy_violations": list(self.policy_violations),
            "degraded_dimensions": list(self.degraded_dimensions),
            "improved_dimensions": list(self.improved_dimensions),
            "knowledge_integrity_qualified": self.knowledge_integrity_qualified,
            "trajectory_signature": self.trajectory_signature,
        }


def make_integrity_snapshot(
    *,
    generation: int,
    canonical_knowledge_count: int,
    semantic_contradictions: int = 0,
    semantic_drift_events: int = 0,
    false_canonical_admissions: int = 0,
    corrected_error_opportunities: int = 0,
    corrected_error_recurrences: int = 0,
    retrieval_queries: int = 0,
    retrieval_correct_selections: int = 0,
    equivalent_failure_opportunities: int = 0,
    equivalent_failure_retries: int = 0,
) -> KnowledgeIntegritySnapshot:
    generation = _count(generation, "generation")
    knowledge = _count(canonical_knowledge_count, "canonical knowledge count")
    contradictions = _count(semantic_contradictions, "semantic contradictions")
    drift = _count(semantic_drift_events, "semantic drift events")
    false_admissions = _count(false_canonical_admissions, "false canonical admissions")
    error_opportunities = _count(corrected_error_opportunities, "corrected error opportunities")
    error_recurrences = _count(corrected_error_recurrences, "corrected error recurrences")
    queries = _count(retrieval_queries, "retrieval queries")
    correct = _count(retrieval_correct_selections, "retrieval correct selections")
    failure_opportunities = _count(equivalent_failure_opportunities, "equivalent failure opportunities")
    failure_retries = _count(equivalent_failure_retries, "equivalent failure retries")
    if error_recurrences > error_opportunities:
        raise EGCFError("corrected error recurrences cannot exceed opportunities")
    if correct > queries:
        raise EGCFError("retrieval correct selections cannot exceed retrieval queries")
    if failure_retries > failure_opportunities:
        raise EGCFError("equivalent failure retries cannot exceed opportunities")
    rates = {
        "contradiction_rate_bp": _rate_bp(contradictions, knowledge),
        "semantic_drift_rate_bp": _rate_bp(drift, knowledge),
        "false_admission_rate_bp": _rate_bp(false_admissions, knowledge),
        "corrected_error_recurrence_rate_bp": _rate_bp(error_recurrences, error_opportunities),
        "retrieval_precision_bp": _rate_bp(correct, queries),
        "equivalent_failure_avoidance_bp": _rate_bp(failure_retries, failure_opportunities, inverse=True),
    }
    material = {
        "version": KNOWLEDGE_INTEGRITY_VERSION,
        "generation": generation,
        "canonical_knowledge_count": knowledge,
        "semantic_contradictions": contradictions,
        "semantic_drift_events": drift,
        "false_canonical_admissions": false_admissions,
        "corrected_error_opportunities": error_opportunities,
        "corrected_error_recurrences": error_recurrences,
        "retrieval_queries": queries,
        "retrieval_correct_selections": correct,
        "equivalent_failure_opportunities": failure_opportunities,
        "equivalent_failure_retries": failure_retries,
        **rates,
    }
    return KnowledgeIntegritySnapshot(
        generation=generation,
        canonical_knowledge_count=knowledge,
        semantic_contradictions=contradictions,
        semantic_drift_events=drift,
        false_canonical_admissions=false_admissions,
        corrected_error_opportunities=error_opportunities,
        corrected_error_recurrences=error_recurrences,
        retrieval_queries=queries,
        retrieval_correct_selections=correct,
        equivalent_failure_opportunities=failure_opportunities,
        equivalent_failure_retries=failure_retries,
        snapshot_signature=sha256_json(material),
        **rates,
    )


def assess_integrity_trajectory(
    snapshots: Sequence[KnowledgeIntegritySnapshot],
    policy: KnowledgeIntegrityPolicy,
) -> KnowledgeIntegrityTrajectory:
    if not snapshots:
        raise EGCFError("SAA-12.3 integrity assessment requires at least one snapshot")
    ordered = tuple(sorted(snapshots, key=lambda item: item.generation))
    if len({item.generation for item in ordered}) != len(ordered):
        raise EGCFError("SAA-12.3 integrity generations must be unique")
    canonical_policy = policy.canonical()
    latest = ordered[-1]
    violations: list[str] = []
    checks = (
        ("CONTRADICTION_RATE", latest.contradiction_rate_bp, canonical_policy.max_contradiction_rate_bp, "MAX"),
        ("SEMANTIC_DRIFT_RATE", latest.semantic_drift_rate_bp, canonical_policy.max_semantic_drift_rate_bp, "MAX"),
        ("FALSE_ADMISSION_RATE", latest.false_admission_rate_bp, canonical_policy.max_false_admission_rate_bp, "MAX"),
        ("CORRECTED_ERROR_RECURRENCE_RATE", latest.corrected_error_recurrence_rate_bp, canonical_policy.max_corrected_error_recurrence_rate_bp, "MAX"),
        ("RETRIEVAL_PRECISION", latest.retrieval_precision_bp, canonical_policy.min_retrieval_precision_bp, "MIN"),
        ("EQUIVALENT_FAILURE_AVOIDANCE", latest.equivalent_failure_avoidance_bp, canonical_policy.min_equivalent_failure_avoidance_bp, "MIN"),
    )
    for name, observed, threshold, mode in checks:
        bad = observed > threshold if mode == "MAX" else observed < threshold
        if bad:
            violations.append(f"{name}:{observed}:{mode}:{threshold}")
    degraded: list[str] = []
    improved: list[str] = []
    if len(ordered) >= 2:
        previous = ordered[-2]
        lower_is_better = (
            "contradiction_rate_bp",
            "semantic_drift_rate_bp",
            "false_admission_rate_bp",
            "corrected_error_recurrence_rate_bp",
        )
        higher_is_better = ("retrieval_precision_bp", "equivalent_failure_avoidance_bp")
        for field in lower_is_better:
            before, after = getattr(previous, field), getattr(latest, field)
            if after > before:
                degraded.append(field.upper())
            elif after < before:
                improved.append(field.upper())
        for field in higher_is_better:
            before, after = getattr(previous, field), getattr(latest, field)
            if after < before:
                degraded.append(field.upper())
            elif after > before:
                improved.append(field.upper())
    qualified = not violations
    if not qualified:
        status = "KNOWLEDGE_INTEGRITY_POLICY_VIOLATION"
    elif degraded:
        status = "KNOWLEDGE_INTEGRITY_QUALIFIED_WITH_DEGRADATION_SIGNAL"
    elif improved:
        status = "KNOWLEDGE_INTEGRITY_QUALIFIED_IMPROVING"
    else:
        status = "KNOWLEDGE_INTEGRITY_QUALIFIED_STABLE"
    payload = {
        "version": KNOWLEDGE_INTEGRITY_VERSION,
        "snapshot_signatures": [item.snapshot_signature for item in ordered],
        "policy": canonical_policy.to_dict(),
        "latest_generation": latest.generation,
        "status": status,
        "violations": violations,
        "degraded": degraded,
        "improved": improved,
    }
    return KnowledgeIntegrityTrajectory(
        snapshot_signatures=tuple(item.snapshot_signature for item in ordered),
        latest_generation=latest.generation,
        status=status,
        policy_violations=tuple(violations),
        degraded_dimensions=tuple(sorted(degraded)),
        improved_dimensions=tuple(sorted(improved)),
        knowledge_integrity_qualified=qualified,
        trajectory_signature=sha256_json(payload),
    )
