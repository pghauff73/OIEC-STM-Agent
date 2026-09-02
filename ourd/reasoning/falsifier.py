from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable, Mapping, Sequence

from ..errors import ProviderError
from .generator import (
    REASONING_BATCH_TOOL_NAME,
    REASONING_OBJECT_TOOL_NAME,
    create_provider_responses,
    parse_json_object,
    parse_ordered_role_batch_payloads,
    provider_problem_context,
    reasoning_batch_tool,
    reasoning_object_tool,
    reasoning_role_batch_size,
    response_text,
)
from .models import (
    FalsifierReport,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    SCORE_SCALE,
    bounded_score,
    stable_hash,
)


FALSIFIER_BATCH_MAX_OUTPUT_TOKENS = 1_024


def falsifier_request(
    *,
    problem: ReasoningProblem,
    path: ReasoningPath,
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an adversarial OIEC-SR falsifier. Search for observations, "
            "counterexamples, interpretations, or tests that would make the candidate "
            "wrong. Call "
            f"{REASONING_OBJECT_TOOL_NAME} exactly once with one concise object. Do not reveal "
            "private chain-of-thought, use any other tool, approve actions, or protect the candidate. Evaluate only the closed "
            "supplied task. Distinguish 'not proven' from 'proven false': observing that "
            "missing evidence prevents verification supports a 'not proven' conclusion "
            "and is not a reversed causal direction or alternative explanation. A future "
            "artifact that would reverse the conclusion belongs only in "
            "evidence_reversal_conditions and is not a current counterexample. Do not "
            "weaken the problem's word 'proven' into plausible, useful, or sufficient for "
            "a different purpose. Populate counterexamples, alternative_explanations, "
            "boundary_cases, reversed_causal_directions, invalid_invariants, and "
            "unresolved_defeat_conditions only with a condition already supported by the "
            "supplied task that actually defeats the candidate. Hypothetical alternate "
            "definitions, different time scopes, future evidence, and questions about "
            "whether the problem means what it explicitly says are searched challenges, "
            "not current defeats; keep the defeat fields empty when none is present and "
            "assign an appropriately high survival score. Return exactly one top-level "
            "JSON object, never a bare array or Markdown fence."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": provider_problem_context(problem),
                        "candidate": asdict(path),
                        "falsification_contract": {
                            "closed_supplied_task": True,
                            "not_proven_is_not_proven_false": True,
                            "future_reversal_is_current_counterexample": False,
                            "defeat_must_be_present_in_task": True,
                            "alternate_definition_is_current_defeat": False,
                            "top_level_type": "object",
                        },
                        "response_schema": {
                            "searched_falsifiers": ["condition searched"],
                            "counterexamples": ["counterexample found"],
                            "alternative_explanations": ["competing explanation"],
                            "boundary_cases": ["boundary value or scope case"],
                            "reversed_causal_directions": ["plausible reversed direction"],
                            "invalid_invariants": ["incorrectly held invariant"],
                            "evidence_reversal_conditions": ["evidence that reverses the conclusion"],
                            "contradicted_step_ids": ["candidate step ID"],
                            "unresolved_defeat_conditions": ["remaining test"],
                            "unresolved_defeat_evidence_ids": [
                                "declared evidence ID grounding a current unresolved defeat"
                            ],
                            "critical": False,
                            "survival_bp": 0,
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [
            reasoning_object_tool(
                (
                    "searched_falsifiers",
                    "counterexamples",
                    "alternative_explanations",
                    "boundary_cases",
                    "reversed_causal_directions",
                    "invalid_invariants",
                    "evidence_reversal_conditions",
                    "contradicted_step_ids",
                    "unresolved_defeat_conditions",
                    "unresolved_defeat_evidence_ids",
                    "critical",
                    "survival_bp",
                ),
            )
        ],
    }


def falsifier_batch_request(
    *,
    problem: ReasoningProblem,
    paths: Sequence[ReasoningPath],
) -> Mapping[str, Any]:
    if len(paths) < 2:
        raise ProviderError("batched falsifier request requires at least two candidates")
    example_request = falsifier_request(problem=problem, path=paths[0])
    example = json.loads(str(example_request["input_items"][0]["content"]))
    return {
        "instructions": (
            "Act only as an adversarial OIEC-SR falsifier micro-batch. Call "
            f"{REASONING_BATCH_TOOL_NAME} exactly once with a 'reports' array. Challenge every supplied candidate "
            "independently and return reports in the exact candidate order. Each array "
            "entry is the ordinary falsifier object. Do not reorder or compare candidates, protect one "
            "candidate because another is weaker, transfer a defeat between paths, or "
            "invent evidence. Evaluate only the closed supplied task. Do not reveal "
            "private chain-of-thought, use tools, approve actions, or claim authority."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": example["problem"],
                        "candidates": [asdict(path) for path in paths],
                        "falsification_contract": example["falsification_contract"],
                        "response_schema": {
                            "reports": [example["response_schema"]]
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [reasoning_batch_tool("reports")],
        "max_output_tokens": FALSIFIER_BATCH_MAX_OUTPUT_TOKENS,
    }


def falsify_reasoning_path(
    *,
    path: ReasoningPath,
    payload: Mapping[str, Any],
    declared_evidence_ids: Iterable[str] | None = None,
) -> FalsifierReport:
    searched = tuple(str(value) for value in payload.get("searched_falsifiers", ()) if str(value))
    counterexamples = tuple(str(value) for value in payload.get("counterexamples", ()) if str(value))
    contradicted = tuple(str(value) for value in payload.get("contradicted_step_ids", ()) if str(value))
    unresolved = tuple(
        str(value) for value in payload.get("unresolved_defeat_conditions", ()) if str(value)
    )
    alternative_explanations = tuple(
        str(value) for value in payload.get("alternative_explanations", ()) if str(value)
    )
    boundary_cases = tuple(
        str(value) for value in payload.get("boundary_cases", ()) if str(value)
    )
    reversed_causal_directions = tuple(
        str(value)
        for value in payload.get("reversed_causal_directions", ())
        if str(value)
    )
    invalid_invariants = tuple(
        str(value) for value in payload.get("invalid_invariants", ()) if str(value)
    )
    evidence_reversal_conditions = tuple(
        str(value)
        for value in payload.get("evidence_reversal_conditions", ())
        if str(value)
    )
    unresolved_evidence_ids = tuple(
        str(value)
        for value in payload.get("unresolved_defeat_evidence_ids", ())
        if str(value)
    )
    if declared_evidence_ids is not None:
        declared = set(declared_evidence_ids)
        if set(unresolved_evidence_ids) - declared:
            raise ProviderError("falsifier response grounds defeat in undeclared evidence")
        if unresolved_evidence_ids and not unresolved:
            raise ProviderError("falsifier defeat evidence has no unresolved condition")
        if unresolved and not unresolved_evidence_ids:
            evidence_reversal_conditions = tuple(
                dict.fromkeys((*evidence_reversal_conditions, *unresolved))
            )
            unresolved = ()
    if set(contradicted) - {step.step_id for step in path.steps}:
        raise ProviderError("falsifier response references an unknown candidate step")
    proposed_survival = bounded_score(
        int(payload.get("survival_bp", 0)),
        "falsifier proposed survival",
    )
    critical = bool(payload.get("critical", False))
    if critical or contradicted:
        survival_bp = 0
        severity_bp = SCORE_SCALE
        verdict = "REJECT"
    elif counterexamples:
        survival_bp = min(4_000, proposed_survival)
        severity_bp = max(6_000, SCORE_SCALE - survival_bp)
        verdict = "REVISE"
    elif alternative_explanations or boundary_cases or reversed_causal_directions or invalid_invariants:
        survival_bp = min(6_000, proposed_survival)
        severity_bp = max(4_000, SCORE_SCALE - survival_bp)
        verdict = "REVISE"
    else:
        survival_bp = max(5_000, proposed_survival)
        severity_bp = max(0, SCORE_SCALE - survival_bp)
        verdict = "SURVIVES"
    residual_uncertainty_bp = max(0, SCORE_SCALE - survival_bp)
    material = {
        "path_id": path.path_id,
        "searched_falsifiers": searched,
        "counterexamples": counterexamples,
        "contradicted_step_ids": contradicted,
        "unresolved_defeat_conditions": unresolved,
        "unresolved_defeat_evidence_ids": unresolved_evidence_ids,
        "alternative_explanations": alternative_explanations,
        "boundary_cases": boundary_cases,
        "reversed_causal_directions": reversed_causal_directions,
        "invalid_invariants": invalid_invariants,
        "evidence_reversal_conditions": evidence_reversal_conditions,
        "severity_bp": severity_bp,
        "survival_bp": survival_bp,
        "residual_uncertainty_bp": residual_uncertainty_bp,
        "verdict": verdict,
    }
    report_id = f"falsifier:{stable_hash(material)}"
    return FalsifierReport(
        report_id=report_id,
        **material,
        signature=stable_hash({**material, "report_id": report_id}),
    )


def falsify_reasoning_paths(
    *,
    provider: Any,
    problem: ReasoningProblem,
    paths: Sequence[ReasoningPath],
    budget: ReasoningBudget,
    role_batch_size: int = 1,
) -> tuple[FalsifierReport, ...]:
    batch_size = reasoning_role_batch_size(provider, role_batch_size)
    received: list[tuple[ReasoningPath, Mapping[str, Any]]] = []
    for start in range(0, len(paths), batch_size):
        group = tuple(paths[start : start + batch_size])
        if len(group) == 1:
            response = create_provider_responses(
                provider,
                (falsifier_request(problem=problem, path=group[0]),),
                max_responses=budget.max_provider_calls,
            )[0]
            payloads = (parse_json_object(response_text(response)),)
        else:
            response = create_provider_responses(
                provider,
                (falsifier_batch_request(problem=problem, paths=group),),
                max_responses=budget.max_provider_calls,
            )[0]
            payloads = parse_ordered_role_batch_payloads(
                response,
                collection_key="reports",
                expected_count=len(group),
            )
        received.extend(zip(group, payloads))
    return tuple(
        falsify_reasoning_path(
            path=path,
            payload=payload,
            declared_evidence_ids=problem.evidence_ids,
        )
        for path, payload in received
    )


__all__ = [
    "FALSIFIER_BATCH_MAX_OUTPUT_TOKENS",
    "falsifier_batch_request",
    "falsifier_request",
    "falsify_reasoning_path",
    "falsify_reasoning_paths",
]
