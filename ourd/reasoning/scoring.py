from __future__ import annotations

from typing import Iterable, Sequence

from .models import (
    CandidateSet,
    FalsifierReport,
    ReasoningMetrics,
    ReasoningPath,
    SCORE_SCALE,
    ScoreConfiguration,
    VerifierReport,
    bounded_score,
    stable_hash,
)


DEFAULT_SCORE_CONFIGURATION = ScoreConfiguration()
PATH_SCORE_WEIGHTS = {
    "verifier": DEFAULT_SCORE_CONFIGURATION.verifier_weight,
    "evidence": DEFAULT_SCORE_CONFIGURATION.evidence_weight,
    "consistency": DEFAULT_SCORE_CONFIGURATION.consistency_weight,
    "falsifier": DEFAULT_SCORE_CONFIGURATION.falsifier_weight,
    "goal": DEFAULT_SCORE_CONFIGURATION.goal_weight,
    "diversity": DEFAULT_SCORE_CONFIGURATION.diversity_weight,
    "uncertainty": DEFAULT_SCORE_CONFIGURATION.uncertainty_penalty,
    "cost": DEFAULT_SCORE_CONFIGURATION.compute_penalty,
}


def evidence_coverage_bp(path: ReasoningPath, declared_evidence_ids: Iterable[str]) -> int:
    declared = set(declared_evidence_ids)
    referenced = {evidence_id for step in path.steps for evidence_id in step.evidence_ids}
    if not declared:
        return SCORE_SCALE if not referenced else 0
    return min(SCORE_SCALE, len(referenced & declared) * SCORE_SCALE // len(declared))


def path_uncertainty_bp(path: ReasoningPath, unresolved_assumption_count: int = 0) -> int:
    confidence = min(step.confidence_bp for step in path.steps)
    assumption_penalty = min(SCORE_SCALE, max(0, int(unresolved_assumption_count)) * 500)
    return min(SCORE_SCALE, (SCORE_SCALE - confidence) + assumption_penalty)


def score_reasoning_path(
    *,
    path: ReasoningPath,
    verifier: VerifierReport,
    falsifier: FalsifierReport,
    declared_evidence_ids: Iterable[str],
    config: ScoreConfiguration = DEFAULT_SCORE_CONFIGURATION,
) -> ReasoningMetrics:
    coverage = evidence_coverage_bp(path, declared_evidence_ids)
    consistency = min(
        verifier.consistency_bp,
        max(0, SCORE_SCALE - len(verifier.contradictions) * 2_000),
    )
    unresolved = len(verifier.missing_assumptions) + sum(
        len(step.assumptions) for step in path.steps
    )
    uncertainty = path_uncertainty_bp(path, unresolved)
    positive = (
        config.verifier_weight * verifier.score_bp
        + config.evidence_weight * coverage
        + config.consistency_weight * consistency
        + config.falsifier_weight * falsifier.survival_bp
        + config.goal_weight * path.goal_relevance_bp
        + config.diversity_weight * path.diversity_bp
    ) // 100
    penalties = (
        config.uncertainty_penalty * uncertainty
        + config.compute_penalty * path.estimated_cost_bp
    ) // 100
    total = max(-SCORE_SCALE, min(SCORE_SCALE, positive - penalties))
    payload = {
        "path_id": path.path_id,
        "evidence_support_bp": coverage,
        "verifier_bp": verifier.score_bp,
        "consistency_bp": consistency,
        "falsifier_bp": falsifier.survival_bp,
        "goal_relevance_bp": path.goal_relevance_bp,
        "diversity_bp": path.diversity_bp,
        "uncertainty_bp": uncertainty,
        "risk_bp": path.risk_bp,
        "cost_bp": path.estimated_cost_bp,
        "total_score_bp": total,
        "score_config_id": config.config_id,
        "score_config_hash": config.signature,
    }
    return ReasoningMetrics(**payload, signature=stable_hash(payload))


def rank_reasoning_paths(
    *,
    paths: Sequence[ReasoningPath],
    metrics: Sequence[ReasoningMetrics],
    verifier_reports: Sequence[VerifierReport],
    falsifier_reports: Sequence[FalsifierReport],
) -> tuple[ReasoningPath, ...]:
    metrics_by_path = {item.path_id: item for item in metrics}
    verifier_by_path = {item.path_id: item for item in verifier_reports}
    falsifier_by_path = {item.path_id: item for item in falsifier_reports}
    return tuple(
        sorted(
            paths,
            key=lambda path: (
                -metrics_by_path[path.path_id].total_score_bp,
                -verifier_by_path[path.path_id].score_bp,
                -falsifier_by_path[path.path_id].survival_bp,
                path.estimated_cost_bp,
                path.path_id,
            ),
        )
    )


def conclusion_agreement_bp(candidates: CandidateSet) -> int:
    if not candidates.paths or not candidates.selected_path_id:
        return 0
    selected = next(
        path for path in candidates.paths if path.path_id == candidates.selected_path_id
    )
    selected_key = " ".join(selected.conclusion.casefold().split())
    matching = sum(
        1
        for path in candidates.paths
        if " ".join(path.conclusion.casefold().split()) == selected_key
    )
    return matching * SCORE_SCALE // len(candidates.paths)


def derive_reasoning_confidence_bp(candidates: CandidateSet) -> int:
    if not candidates.selected_path_id:
        return 0
    metrics = next(
        item for item in candidates.metrics if item.path_id == candidates.selected_path_id
    )
    agreement = conclusion_agreement_bp(candidates)
    value = (
        30 * metrics.verifier_bp
        + 20 * agreement
        + 20 * metrics.evidence_support_bp
        + 20 * metrics.falsifier_bp
        + 10 * (SCORE_SCALE - metrics.uncertainty_bp)
    ) // 100
    return bounded_score(value, "derived reasoning confidence")


def score_configuration_signature(
    config: ScoreConfiguration = DEFAULT_SCORE_CONFIGURATION,
) -> str:
    return config.signature


__all__ = [
    "DEFAULT_SCORE_CONFIGURATION",
    "PATH_SCORE_WEIGHTS",
    "conclusion_agreement_bp",
    "derive_reasoning_confidence_bp",
    "evidence_coverage_bp",
    "path_uncertainty_bp",
    "rank_reasoning_paths",
    "score_configuration_signature",
    "score_reasoning_path",
]
