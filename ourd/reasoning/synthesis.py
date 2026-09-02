from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable, Mapping, Sequence

from ..errors import ProviderError
from .diversity import structure_material_from_parts
from .generator import (
    REASONING_OBJECT_TOOL_NAME,
    create_provider_responses,
    parse_json_object,
    provider_problem_context,
    reasoning_object_tool,
    response_text,
)
from .models import (
    Hypothesis,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    ReasoningStep,
    SynthesisResult,
    VerifierReport,
    bounded_score,
    stable_hash,
)
from .verifier import verify_reasoning_paths


def synthesizer_request(
    *,
    problem: ReasoningProblem,
    winner: ReasoningPath,
    survivors: Sequence[ReasoningPath],
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an OIEC-SR synthesizer. Use only claims and steps from the "
            "supplied verified surviving paths. Call "
            f"{REASONING_OBJECT_TOOL_NAME} exactly once with one concise object. Do not invent a "
            "source path, evidence, premise, step, authority, approval, or tool result. "
            "Do not reveal private chain-of-thought or change the selected winner. Follow "
            "the problem goal's answer format exactly: for a yes/no question return only "
            "'yes' or 'no' when the verified survivor supports one. Accepted and rejected "
            "step IDs must be disjoint, and a step used in the synthesized path cannot be "
            "listed as rejected. Do not use any other tool."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": provider_problem_context(problem),
                        "selected_winner": winner.path_id,
                        "survivors": [asdict(path) for path in survivors],
                        "response_schema": {
                            "conclusion": "shortest conclusion satisfying the problem goal",
                            "source_path_ids": ["surviving path ID"],
                            "accepted_step_ids": ["step ID from a source path"],
                            "rejected_step_ids": ["step ID from a source path"],
                            "remaining_uncertainties": ["explicit uncertainty"],
                            "confidence_bp": 0,
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [
            reasoning_object_tool(
                (
                    "conclusion",
                    "source_path_ids",
                    "accepted_step_ids",
                    "rejected_step_ids",
                    "remaining_uncertainties",
                    "confidence_bp",
                ),
            )
        ],
    }


def _compatible_sources(winner: ReasoningPath, sources: Sequence[ReasoningPath]) -> bool:
    winner_hypotheses = set(winner.hypothesis_ids)
    winner_conclusion = " ".join(winner.conclusion.casefold().split())
    for path in sources:
        if path.path_id == winner.path_id:
            continue
        if winner_hypotheses & set(path.hypothesis_ids):
            continue
        if " ".join(path.conclusion.casefold().split()) == winner_conclusion:
            continue
        return False
    return True


def _source_steps(sources: Sequence[ReasoningPath]) -> dict[str, ReasoningStep]:
    steps: dict[str, ReasoningStep] = {}
    for path in sources:
        for step in path.steps:
            previous = steps.get(step.step_id)
            if previous is not None and previous.signature != step.signature:
                raise ProviderError("synthesis source paths contain conflicting step IDs")
            steps[step.step_id] = step
    return steps


def _make_synthesis_path(
    *,
    problem: ReasoningProblem,
    winner: ReasoningPath,
    sources: Sequence[ReasoningPath],
    conclusion: str,
    accepted_step_ids: Iterable[str],
) -> ReasoningPath:
    available = _source_steps(sources)
    accepted = tuple(dict.fromkeys(str(value) for value in accepted_step_ids if str(value)))
    if not accepted:
        accepted = tuple(step.step_id for step in winner.steps)
    if set(accepted) - set(available):
        raise ProviderError("synthesis references a step outside its source paths")
    ordered_steps = tuple(available[step_id] for step_id in accepted)
    known_prior: set[str] = set()
    known_hypotheses = {item for path in sources for item in path.hypothesis_ids}
    for step in ordered_steps:
        allowed = {"problem", *known_hypotheses, *known_prior}
        if set(step.premises) - allowed:
            raise ProviderError("synthesis step order breaks a source premise")
        known_prior.add(step.step_id)
    structure = structure_material_from_parts(
        perspective="synthesis",
        hypothesis_ids=known_hypotheses,
        steps=tuple(
            {
                "evidence_ids": step.evidence_ids,
                "inference": step.inference,
                "assumptions": step.assumptions,
                "falsifier": step.falsifier,
            }
            for step in ordered_steps
        ),
        conclusion=conclusion,
    )
    structure_signature = stable_hash(structure)
    path_id = f"synthesis-path:{structure_signature}"
    material = {
        "problem_id": problem.problem_id,
        "path_id": path_id,
        "perspective": "synthesis",
        "hypothesis_ids": tuple(sorted(known_hypotheses)),
        "steps": [asdict(step) for step in ordered_steps],
        "conclusion": conclusion,
        "provider_confidence_bp": 0,
        "estimated_cost_bp": sum(path.estimated_cost_bp for path in sources),
        "goal_relevance_bp": min(path.goal_relevance_bp for path in sources),
        "risk_bp": max(path.risk_bp for path in sources),
        "structure_signature": structure_signature,
    }
    return ReasoningPath(
        path_id=path_id,
        perspective="synthesis",
        hypothesis_ids=tuple(sorted(known_hypotheses)),
        steps=ordered_steps,
        conclusion=conclusion,
        provider_confidence_bp=0,
        estimated_cost_bp=min(10_000, material["estimated_cost_bp"]),
        goal_relevance_bp=material["goal_relevance_bp"],
        risk_bp=material["risk_bp"],
        structure_signature=structure_signature,
        signature=stable_hash(material),
    )


def fallback_to_verified_winner(
    *,
    winner: ReasoningPath,
    verifier: VerifierReport,
    reasons: Iterable[str] = (),
) -> SynthesisResult:
    return SynthesisResult(
        winning_path_id=winner.path_id,
        synthesized_path_id=winner.path_id,
        source_path_ids=(winner.path_id,),
        accepted_node_ids=tuple(step.step_id for step in winner.steps),
        merged_conclusion=winner.conclusion,
        confidence_bp=verifier.score_bp,
        verifier_report_id=verifier.report_id,
        topology_signature=winner.structure_signature,
        verified=verifier.verdict != "REJECT",
        fallback_used=True,
        failure_reasons=tuple(reasons),
    )


def synthesize_verified_result(
    *,
    provider: Any,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    winner: ReasoningPath,
    survivors: Sequence[ReasoningPath],
    verifier_reports: Sequence[VerifierReport],
    declared_evidence_ids: Iterable[str],
    budget: ReasoningBudget,
    verify_synthesis: bool = True,
    verifier_batch_size: int = 1,
) -> SynthesisResult:
    verifier_by_path = {report.path_id: report for report in verifier_reports}
    winner_verifier = verifier_by_path[winner.path_id]
    try:
        response = create_provider_responses(
            provider,
            (synthesizer_request(problem=problem, winner=winner, survivors=survivors),),
            max_responses=budget.max_provider_calls,
        )[0]
        payload = parse_json_object(response_text(response))
        conclusion = str(payload.get("conclusion", "")).strip()
        source_ids = tuple(
            sorted({str(value) for value in payload.get("source_path_ids", ()) if str(value)})
        )
        available = {path.path_id: path for path in survivors}
        if not conclusion or winner.path_id not in source_ids or set(source_ids) - set(available):
            raise ProviderError("synthesis source binding is invalid")
        sources = tuple(available[path_id] for path_id in source_ids)
        if not _compatible_sources(winner, sources):
            raise ProviderError("synthesis source paths are structurally incompatible")
        accepted = tuple(
            str(value) for value in payload.get("accepted_step_ids", ()) if str(value)
        )
        rejected = tuple(
            str(value) for value in payload.get("rejected_step_ids", ()) if str(value)
        )
        source_step_ids = set(_source_steps(sources))
        if set(rejected) - source_step_ids:
            raise ProviderError("synthesis rejects a step outside its sources")
        if set(accepted) & set(rejected):
            raise ProviderError("synthesis cannot both accept and reject the same step")
        synthesis_path = _make_synthesis_path(
            problem=problem,
            winner=winner,
            sources=sources,
            conclusion=conclusion,
            accepted_step_ids=accepted,
        )
        if not verify_synthesis:
            confidence = min(
                winner_verifier.score_bp,
                bounded_score(int(payload.get("confidence_bp", 0)), "synthesis confidence")
                if "confidence_bp" in payload
                else winner_verifier.score_bp,
            )
            return SynthesisResult(
                winning_path_id=winner.path_id,
                synthesized_path_id=synthesis_path.path_id,
                source_path_ids=source_ids,
                accepted_node_ids=tuple(step.step_id for step in synthesis_path.steps),
                rejected_node_ids=rejected,
                merged_conclusion=conclusion,
                remaining_uncertainties=tuple(
                    str(value)
                    for value in payload.get("remaining_uncertainties", ())
                    if str(value)
                ),
                confidence_bp=confidence,
                verifier_report_id="",
                topology_signature=synthesis_path.structure_signature,
                verified=False,
                failure_reasons=("synthesis verification disabled by qualification ablation",),
            )
        synthesis_verifier = verify_reasoning_paths(
            provider=provider,
            problem=problem,
            paths=(synthesis_path,),
            hypotheses=hypotheses,
            declared_evidence_ids=declared_evidence_ids,
            budget=budget,
            role_batch_size=verifier_batch_size,
        )[0]
        if synthesis_verifier.verdict == "REJECT":
            raise ProviderError("synthesized candidate failed independent verification")
        confidence = min(
            synthesis_verifier.score_bp,
            bounded_score(int(payload.get("confidence_bp", 0)), "synthesis confidence")
            if "confidence_bp" in payload
            else synthesis_verifier.score_bp,
        )
        return SynthesisResult(
            winning_path_id=winner.path_id,
            synthesized_path_id=synthesis_path.path_id,
            source_path_ids=source_ids,
            accepted_node_ids=tuple(step.step_id for step in synthesis_path.steps),
            rejected_node_ids=rejected,
            merged_conclusion=conclusion,
            remaining_uncertainties=tuple(
                str(value)
                for value in payload.get("remaining_uncertainties", ())
                if str(value)
            ),
            confidence_bp=confidence,
            verifier_report_id=synthesis_verifier.report_id,
            topology_signature=synthesis_path.structure_signature,
            verified=True,
        )
    except (ProviderError, ValueError, KeyError) as exc:
        return fallback_to_verified_winner(
            winner=winner,
            verifier=winner_verifier,
            reasons=(str(exc),),
        )


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
    source_ids = tuple(
        sorted({str(value) for value in payload.get("source_path_ids", ()) if str(value)})
    )
    allowed = {path.path_id for path in survivors}
    if not conclusion or winner.path_id not in source_ids or set(source_ids) - allowed:
        return winner.conclusion, (winner.path_id,)
    return conclusion, source_ids


__all__ = [
    "fallback_to_verified_winner",
    "synthesize_conclusion",
    "synthesize_verified_result",
    "synthesizer_request",
]
