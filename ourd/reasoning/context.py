from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .models import (
    CandidateSet,
    Hypothesis,
    REASONING_OPERATIONS,
    ReasoningBudget,
    ReasoningContext,
    ReasoningOperationChoice,
    ReasoningProblem,
    ReasoningTopology,
    SCORE_SCALE,
    bounded_score,
)


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def project_reasoning_context(
    *,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    topology: ReasoningTopology | None = None,
    candidates: CandidateSet | None = None,
    collision_ids: Iterable[str] = (),
    top_evidence_ids: Iterable[str] | None = None,
    budget: ReasoningBudget,
) -> ReasoningContext:
    max_items = budget.max_context_items
    max_chars = 512
    evidence = tuple(top_evidence_ids) if top_evidence_ids is not None else problem.evidence_ids
    unresolved = {
        _clip(assumption, max_chars)
        for hypothesis in hypotheses
        if hypothesis.status != "FALSIFIED"
        for assumption in hypothesis.assumptions
        if str(assumption).strip()
    }
    summaries = ()
    if candidates is not None:
        unresolved.update(
            _clip(assumption, max_chars)
            for report in candidates.verifier_reports
            for assumption in report.missing_assumptions
        )
        if candidates.synthesis is not None:
            unresolved.update(
                _clip(item, max_chars)
                for item in candidates.synthesis.remaining_uncertainties
            )
        ranked_metrics = sorted(
            candidates.metrics,
            key=lambda item: (-item.total_score_bp, item.path_id),
        )
        rank = {item.path_id: index for index, item in enumerate(ranked_metrics)}
        summaries = tuple(
            (
                path.path_id,
                _clip(
                    f"rank={rank.get(path.path_id, len(rank)) + 1}; "
                    f"strategy={path.perspective}; conclusion={path.conclusion}",
                    max_chars,
                ),
            )
            for path in sorted(
                candidates.paths,
                key=lambda item: (rank.get(item.path_id, len(rank)), item.path_id),
            )[:max_items]
        )
    context = ReasoningContext(
        problem_hash=problem.signature,
        constraints=(
            _clip(f"goal:{problem.goal}", max_chars),
            _clip(f"boundary:{problem.boundary_signature}", max_chars),
            _clip(f"dimension:{problem.dimension_signature}", max_chars),
        ),
        hypothesis_ids=tuple(
            hypothesis.hypothesis_id
            for hypothesis in hypotheses
            if hypothesis.status != "FALSIFIED"
        )[:max_items],
        evidence_ids=tuple(str(value) for value in evidence if str(value))[:max_items],
        topology_node_ids=(
            tuple(node.node_id for node in topology.nodes)[:max_items]
            if topology is not None
            else ()
        ),
        collision_ids=tuple(str(value) for value in collision_ids if str(value))[:max_items],
        unresolved_questions=tuple(sorted(unresolved))[:max_items],
        candidate_summaries=summaries,
        max_items=max_items,
        max_chars_per_item=max_chars,
        max_total_chars=max(4_096, min(65_536, max_items * max_chars)),
    )
    return context


def choose_reasoning_operation(
    *,
    budget: ReasoningBudget,
    expected_gains_bp: Mapping[str, int],
    allowed_operations: Iterable[str] = REASONING_OPERATIONS,
) -> ReasoningOperationChoice:
    allowed = {str(value) for value in allowed_operations}
    unknown = allowed - REASONING_OPERATIONS
    if unknown:
        raise ValueError(f"unknown reasoning operations: {sorted(unknown)!r}")
    costs = dict(budget.operation_costs_bp)
    choices = []
    for operation in sorted(allowed - {"STOP"}):
        gain = bounded_score(
            int(expected_gains_bp.get(operation, 0)),
            f"{operation} expected gain",
        )
        cost = int(costs.get(operation, SCORE_SCALE))
        value = max(-SCORE_SCALE, min(SCORE_SCALE, gain - cost))
        choices.append((value, operation, gain, cost))
    viable = [item for item in choices if item[0] >= budget.minimum_voi_bp]
    if not viable:
        return ReasoningOperationChoice(operation="STOP")
    value, operation, gain, cost = sorted(
        viable,
        key=lambda item: (-item[0], item[1]),
    )[0]
    return ReasoningOperationChoice(
        operation=operation,
        expected_quality_gain_bp=gain,
        cost_bp=cost,
        value_bp=value,
        requires_iurm=operation == "REFINE_DIMENSION",
        read_only=True,
    )


__all__ = ["choose_reasoning_operation", "project_reasoning_context"]
