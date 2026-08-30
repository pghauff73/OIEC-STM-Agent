from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from ..errors import ProviderError
from .generator import create_provider_responses, parse_json_object, response_text
from .models import (
    FalsifierReport,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    bounded_score,
    stable_hash,
)


def falsifier_request(
    *,
    problem: ReasoningProblem,
    path: ReasoningPath,
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an adversarial OIEC-SR falsifier. Search for observations, "
            "counterexamples, interpretations, or tests that would make the candidate "
            "wrong. Return concise JSON. Do not reveal private chain-of-thought, use "
            "tools, approve actions, or protect the candidate."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": asdict(problem),
                        "candidate": asdict(path),
                        "response_schema": {
                            "searched_falsifiers": ["condition searched"],
                            "counterexamples": ["counterexample found"],
                            "contradicted_step_ids": ["candidate step ID"],
                            "unresolved_defeat_conditions": ["remaining test"],
                            "critical": False,
                            "survival_bp": 0,
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [],
    }


def falsify_reasoning_path(
    *,
    path: ReasoningPath,
    payload: Mapping[str, Any],
) -> FalsifierReport:
    searched = tuple(str(value) for value in payload.get("searched_falsifiers", ()) if str(value))
    counterexamples = tuple(str(value) for value in payload.get("counterexamples", ()) if str(value))
    contradicted = tuple(str(value) for value in payload.get("contradicted_step_ids", ()) if str(value))
    unresolved = tuple(
        str(value) for value in payload.get("unresolved_defeat_conditions", ()) if str(value)
    )
    if set(contradicted) - {step.step_id for step in path.steps}:
        raise ProviderError("falsifier response references an unknown candidate step")
    proposed_survival = bounded_score(
        int(payload.get("survival_bp", 0)),
        "falsifier proposed survival",
    )
    critical = bool(payload.get("critical", False))
    if critical or contradicted:
        survival_bp = 0
        verdict = "REJECT"
    elif counterexamples:
        survival_bp = min(4_000, proposed_survival)
        verdict = "REVISE"
    elif unresolved:
        survival_bp = min(6_000, proposed_survival)
        verdict = "REVISE"
    else:
        survival_bp = max(5_000, proposed_survival)
        verdict = "SURVIVES"
    material = {
        "path_id": path.path_id,
        "searched_falsifiers": searched,
        "counterexamples": counterexamples,
        "contradicted_step_ids": contradicted,
        "unresolved_defeat_conditions": unresolved,
        "survival_bp": survival_bp,
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
) -> tuple[FalsifierReport, ...]:
    requests = tuple(falsifier_request(problem=problem, path=path) for path in paths)
    responses = create_provider_responses(
        provider,
        requests,
        max_responses=budget.max_provider_calls,
    )
    return tuple(
        falsify_reasoning_path(
            path=path,
            payload=parse_json_object(response_text(response)),
        )
        for path, response in zip(paths, responses)
    )


__all__ = [
    "falsifier_request",
    "falsify_reasoning_path",
    "falsify_reasoning_paths",
]
