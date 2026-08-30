from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any, Iterable, Mapping, Sequence

from .falsifier import falsify_reasoning_paths
from .generator import (
    create_provider_responses,
    generate_reasoning_paths,
    parse_json_object,
    response_text,
)
from .models import (
    CandidateSet,
    FalsifierReport,
    Hypothesis,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    VerifierReport,
    stable_hash,
)
from .scoring import rank_reasoning_paths, score_reasoning_path
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


def synthesizer_request(
    *,
    problem: ReasoningProblem,
    winner: ReasoningPath,
    survivors: Sequence[ReasoningPath],
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an OIEC-SR synthesizer. Produce a concise conclusion using "
            "only the supplied surviving candidate paths. Return JSON with conclusion "
            "and source_path_ids. Do not add unsupported claims, reveal private "
            "chain-of-thought, use tools, approve actions, or change the selected winner."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": asdict(problem),
                        "selected_winner": winner.path_id,
                        "survivors": [asdict(path) for path in survivors],
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [],
    }


def synthesize_conclusion(
    *,
    provider: Any,
    problem: ReasoningProblem,
    winner: ReasoningPath,
    survivors: Sequence[ReasoningPath],
    budget: ReasoningBudget,
) -> tuple[str, tuple[str, ...]]:
    response = create_provider_responses(
        provider,
        (synthesizer_request(problem=problem, winner=winner, survivors=survivors),),
        max_responses=budget.max_provider_calls,
    )[0]
    payload = parse_json_object(response_text(response))
    conclusion = str(payload.get("conclusion", "")).strip()
    source_ids = tuple(sorted({str(value) for value in payload.get("source_path_ids", ()) if str(value)}))
    allowed = {path.path_id for path in survivors}
    if not conclusion or winner.path_id not in source_ids or set(source_ids) - allowed:
        return winner.conclusion, (winner.path_id,)
    return conclusion, source_ids


def search_reasoning_candidates(
    *,
    provider: Any,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    declared_evidence_ids: Iterable[str],
    budget: ReasoningBudget,
) -> CandidateSet:
    paths = generate_reasoning_paths(
        provider=provider,
        problem=problem,
        hypotheses=hypotheses,
        budget=budget,
    )
    verifier_reports = verify_reasoning_paths(
        provider=provider,
        problem=problem,
        paths=paths,
        hypotheses=hypotheses,
        declared_evidence_ids=declared_evidence_ids,
        budget=budget,
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
    actual_falsifier_reports = falsify_reasoning_paths(
        provider=provider,
        problem=problem,
        paths=falsifier_targets,
        budget=budget,
    ) if falsifier_targets else ()
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
    synthesized_conclusion = ""
    synthesis_source_path_ids: tuple[str, ...] = ()
    if survivors:
        synthesized_conclusion, synthesis_source_path_ids = synthesize_conclusion(
            provider=provider,
            problem=problem,
            winner=survivors[0],
            survivors=survivors,
            budget=budget,
        )
    rejected = tuple(path.path_id for path in paths if path.path_id != selected_path_id)
    candidate_set = CandidateSet(
        problem_id=problem.problem_id,
        paths=paths,
        verifier_reports=verifier_reports,
        falsifier_reports=falsifier_reports,
        metrics=metrics,
        selected_path_id=selected_path_id,
        rejected_path_ids=rejected,
        synthesized_conclusion=synthesized_conclusion,
        synthesis_source_path_ids=synthesis_source_path_ids,
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
