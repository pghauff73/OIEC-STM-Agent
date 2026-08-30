from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..errors import PolicyError
from .models import ReasoningBudget, SCORE_SCALE, bounded_score, stable_hash


DEFAULT_BASE_CANDIDATES = 4


def derive_reasoning_budget(
    *,
    dimension_budget: Any,
    uncertainty_bp: int,
    difficulty_bp: int,
    verifier_disagreement_bp: int = 0,
    configured_max_candidates: int = 16,
    configured_max_provider_calls: int = 64,
    minimum_voi_bp: int = 100,
) -> ReasoningBudget:
    uncertainty = bounded_score(uncertainty_bp, "reasoning uncertainty")
    difficulty = bounded_score(difficulty_bp, "reasoning difficulty")
    disagreement = bounded_score(verifier_disagreement_bp, "verifier disagreement")
    maximum_candidates = min(
        max(1, int(configured_max_candidates)),
        max(1, int(dimension_budget.max_candidate_actions)),
    )
    adaptive = (
        DEFAULT_BASE_CANDIDATES
        + uncertainty // 2_500
        + difficulty // 2_500
        + disagreement // 2_500
    )
    candidate_count = min(maximum_candidates, max(1, adaptive))
    verifier_count = candidate_count
    falsifier_count = min(2, verifier_count)
    required_calls = candidate_count + verifier_count + falsifier_count + 1
    max_provider_calls = min(
        max(1, int(configured_max_provider_calls)),
        max(required_calls, 1),
    )
    if required_calls > max_provider_calls:
        while candidate_count > 1:
            candidate_count -= 1
            verifier_count = candidate_count
            falsifier_count = min(2, verifier_count)
            required_calls = candidate_count + verifier_count + falsifier_count + 1
            if required_calls <= max_provider_calls:
                break
    if required_calls > max_provider_calls:
        raise PolicyError("provider-call budget cannot support one reasoning candidate")
    payload = {
        "max_hypotheses": int(dimension_budget.max_active_hypotheses),
        "minimum_candidates": 1,
        "maximum_candidates": maximum_candidates,
        "candidate_count": candidate_count,
        "max_steps_per_path": int(dimension_budget.max_decomposition_depth),
        "max_branch_factor": int(dimension_budget.max_branch_factor),
        "max_topology_nodes": max(
            16,
            int(dimension_budget.max_active_relations),
        ),
        "max_topology_edges": max(
            32,
            int(dimension_budget.max_active_relations) * 2,
        ),
        "max_provider_calls": max_provider_calls,
        "verifier_count": verifier_count,
        "falsifier_count": falsifier_count,
        "max_compute_bp": SCORE_SCALE,
        "minimum_voi_bp": bounded_score(minimum_voi_bp, "minimum value of information"),
    }
    return ReasoningBudget(**payload, signature=stable_hash(payload))


def expected_value_of_information_bp(
    *,
    expected_quality_gain_bp: int,
    cost_bp: int,
    cost_weight: int = 100,
) -> int:
    gain = bounded_score(expected_quality_gain_bp, "expected quality gain")
    cost = bounded_score(cost_bp, "reasoning operation cost")
    weight = int(cost_weight)
    if not 0 <= weight <= 1_000:
        raise PolicyError("value-of-information cost weight must be 0..1000")
    return gain - (cost * weight // 100)


def should_continue_reasoning(
    *,
    budget: ReasoningBudget,
    expected_quality_gain_bp: int,
    cost_bp: int,
    cost_weight: int = 100,
) -> bool:
    return expected_value_of_information_bp(
        expected_quality_gain_bp=expected_quality_gain_bp,
        cost_bp=cost_bp,
        cost_weight=cost_weight,
    ) >= budget.minimum_voi_bp


__all__ = [
    "DEFAULT_BASE_CANDIDATES",
    "derive_reasoning_budget",
    "expected_value_of_information_bp",
    "should_continue_reasoning",
]
