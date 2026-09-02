from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Iterable, Sequence

from ..errors import PolicyError
from .ablation import AblationConfiguration
from .contradictions import build_contradiction_records
from .falsifier import falsify_reasoning_paths
from .diversity import DEFAULT_DIVERSITY_CONFIGURATION
from .generator import BoundedReasoningProvider, generate_reasoning_paths
from .models import (
    CandidateSet,
    FalsifierReport,
    Hypothesis,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    SCORE_SCALE,
    VerifierReport,
    stable_hash,
)
from .scoring import (
    DEFAULT_SCORE_CONFIGURATION,
    rank_reasoning_paths,
    score_reasoning_path,
)
from .synthesis import (
    synthesize_conclusion,
    synthesize_verified_result,
    synthesizer_request,
)
from .verifier import verify_reasoning_paths


def _rejected_falsifier(path: ReasoningPath) -> FalsifierReport:
    material = {
        "path_id": path.path_id,
        "searched_falsifiers": (),
        "counterexamples": (),
        "contradicted_step_ids": (),
        "unresolved_defeat_conditions": ("candidate did not reach falsifier stage",),
        "survival_bp": 0,
        "verdict": "REJECT",
    }
    report_id = f"falsifier:{stable_hash(material)}"
    return FalsifierReport(
        report_id=report_id,
        **material,
        signature=stable_hash({**material, "report_id": report_id}),
    )


def _bypass_verifier(
    path: ReasoningPath,
    declared_evidence_ids: Iterable[str],
) -> VerifierReport:
    declared = set(declared_evidence_ids)
    referenced = {evidence_id for step in path.steps for evidence_id in step.evidence_ids}
    unknown = tuple(sorted(referenced - declared))
    if unknown:
        raise PolicyError(
            f"qualification verifier ablation cannot admit unknown evidence: {unknown!r}"
        )
    material = {
        "path_id": path.path_id,
        "step_scores": tuple((step.step_id, SCORE_SCALE) for step in path.steps),
        "failures": (),
        "contradictions": (),
        "unsupported_nodes": (),
        "missing_assumptions": (),
        "premise_validity_bp": SCORE_SCALE,
        "evidence_support_bp": SCORE_SCALE if referenced else 0,
        "inference_quality_bp": SCORE_SCALE,
        "consistency_bp": SCORE_SCALE,
        "completeness_bp": SCORE_SCALE,
        "weakest_step_bp": SCORE_SCALE,
        "score_bp": SCORE_SCALE,
        "verdict": "ACCEPT",
        "ablation": "without_verifier",
    }
    report_id = f"verifier:{stable_hash(material)}"
    report_payload = dict(material)
    report_payload.pop("ablation")
    return VerifierReport(
        report_id=report_id,
        **report_payload,
        signature=stable_hash({**report_payload, "report_id": report_id}),
    )


def _bypass_falsifier(path: ReasoningPath) -> FalsifierReport:
    material = {
        "path_id": path.path_id,
        "searched_falsifiers": (),
        "counterexamples": (),
        "contradicted_step_ids": (),
        "unresolved_defeat_conditions": (),
        "alternative_explanations": (),
        "boundary_cases": (),
        "reversed_causal_directions": (),
        "invalid_invariants": (),
        "evidence_reversal_conditions": (),
        "severity_bp": 0,
        "survival_bp": SCORE_SCALE,
        "verdict": "SURVIVES",
        "ablation": "without_falsifier",
    }
    report_id = f"falsifier:{stable_hash(material)}"
    report_payload = dict(material)
    report_payload.pop("ablation")
    return FalsifierReport(
        report_id=report_id,
        **report_payload,
        signature=stable_hash({**report_payload, "report_id": report_id}),
    )


def search_reasoning_candidates(
    *,
    provider: Any,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    declared_evidence_ids: Iterable[str],
    budget: ReasoningBudget,
    ablation: AblationConfiguration | None = None,
) -> CandidateSet:
    profile = ablation or AblationConfiguration()
    bounded_provider = BoundedReasoningProvider(
        provider=provider,
        max_calls=budget.max_provider_calls,
        max_tokens=budget.max_tokens,
        max_tool_calls=budget.max_tool_calls,
    )
    paths = generate_reasoning_paths(
        provider=bounded_provider,
        problem=problem,
        hypotheses=hypotheses,
        budget=budget,
        diversity_filter_enabled=profile.diversity_filter_enabled,
        role_batch_size=profile.proposer_batch_size,
    )
    verifier_reports = (
        verify_reasoning_paths(
            provider=bounded_provider,
            problem=problem,
            paths=paths,
            hypotheses=hypotheses,
            declared_evidence_ids=declared_evidence_ids,
            budget=budget,
            role_batch_size=profile.verifier_batch_size,
        )
        if profile.verifier_enabled
        else tuple(_bypass_verifier(path, declared_evidence_ids) for path in paths)
    )
    verifier_by_path = {item.path_id: item for item in verifier_reports}
    verifier_ranked = tuple(
        sorted(
            paths,
            key=lambda path: (
                verifier_by_path[path.path_id].verdict == "REJECT",
                -verifier_by_path[path.path_id].score_bp,
                path.path_id,
            ),
        )
    )
    falsifier_targets = tuple(
        path
        for path in verifier_ranked
        if verifier_by_path[path.path_id].verdict != "REJECT"
    )[: budget.falsifier_count]
    actual_falsifier_reports = (
        falsify_reasoning_paths(
            provider=bounded_provider,
            problem=problem,
            paths=falsifier_targets,
            budget=budget,
            role_batch_size=profile.falsifier_batch_size,
        )
        if profile.falsifier_enabled and falsifier_targets
        else tuple(_bypass_falsifier(path) for path in falsifier_targets)
    )
    falsifier_by_path = {item.path_id: item for item in actual_falsifier_reports}
    for path in paths:
        falsifier_by_path.setdefault(path.path_id, _rejected_falsifier(path))
    falsifier_reports = tuple(falsifier_by_path[path.path_id] for path in paths)
    metrics = tuple(
        score_reasoning_path(
            path=path,
            verifier=verifier_by_path[path.path_id],
            falsifier=falsifier_by_path[path.path_id],
            declared_evidence_ids=declared_evidence_ids,
            config=DEFAULT_SCORE_CONFIGURATION,
        )
        for path in paths
    )
    ranked = rank_reasoning_paths(
        paths=paths,
        metrics=metrics,
        verifier_reports=verifier_reports,
        falsifier_reports=falsifier_reports,
    )
    survivors = tuple(
        path
        for path in ranked
        if verifier_by_path[path.path_id].verdict != "REJECT"
        and falsifier_by_path[path.path_id].verdict == "SURVIVES"
    )
    selected_path_id = survivors[0].path_id if survivors else ""
    synthesis = None
    if survivors:
        synthesis = synthesize_verified_result(
            provider=bounded_provider,
            problem=problem,
            hypotheses=hypotheses,
            winner=survivors[0],
            survivors=survivors,
            verifier_reports=verifier_reports,
            declared_evidence_ids=declared_evidence_ids,
            budget=budget,
            verify_synthesis=(
                profile.synthesis_verification_enabled and profile.verifier_enabled
            ),
            verifier_batch_size=profile.verifier_batch_size,
        )
    rejected = tuple(path.path_id for path in paths if path.path_id != selected_path_id)
    candidate_set = CandidateSet(
        problem_id=problem.problem_id,
        paths=paths,
        verifier_reports=verifier_reports,
        falsifier_reports=falsifier_reports,
        metrics=metrics,
        selected_path_id=selected_path_id,
        surviving_path_ids=tuple(path.path_id for path in survivors),
        rejected_path_ids=rejected,
        synthesis=synthesis,
        score_config_id=DEFAULT_SCORE_CONFIGURATION.config_id,
        score_config_hash=DEFAULT_SCORE_CONFIGURATION.signature,
        diversity_config_hash=stable_hash(
            {
                "configuration": DEFAULT_DIVERSITY_CONFIGURATION.signature,
                "filter_enabled": profile.diversity_filter_enabled,
            }
        ),
        ablation_id=profile.ablation_id,
        ablation_config_hash=profile.signature,
    )
    contradictions = build_contradiction_records(candidate_set)
    candidate_set = replace(
        candidate_set,
        contradiction_ids=tuple(item.contradiction_id for item in contradictions),
    )
    material = asdict(candidate_set)
    material.pop("schema_version", None)
    material.pop("signature", None)
    return replace(candidate_set, signature=stable_hash(material))


__all__ = [
    "search_reasoning_candidates",
    "synthesize_conclusion",
    "synthesizer_request",
]
