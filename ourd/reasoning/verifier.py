from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable, Mapping, Sequence

from ..errors import ProviderError
from .generator import create_provider_responses, parse_json_object, response_text
from .models import (
    Hypothesis,
    INFERENCE_MODES,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    SCORE_SCALE,
    VerifierReport,
    stable_hash,
)


PROCESS_CHECKS = (
    "premises_available",
    "evidence_declared",
    "evidence_relevant",
    "inference_supported",
    "grounding_traceable",
    "assumptions_explicit",
    "counterexample_addressed",
    "alternative_considered",
    "conclusion_not_overstated",
)


def verifier_request(
    *,
    problem: ReasoningProblem,
    path: ReasoningPath,
    hypotheses: Sequence[Hypothesis],
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an independent OIEC-SR process verifier. Inspect the supplied "
            "candidate without assuming it is correct. Return JSON with one entry per "
            "step and every named boolean check. Do not reveal private chain-of-thought, "
            "use tools, approve actions, or choose a final winner."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": asdict(problem),
                        "hypotheses": [asdict(item) for item in hypotheses],
                        "candidate": asdict(path),
                        "required_checks": PROCESS_CHECKS,
                        "response_schema": {
                            "steps": [
                                {
                                    "step_id": "candidate step ID",
                                    "checks": {name: True for name in PROCESS_CHECKS},
                                    "failures": ["concise failure"],
                                }
                            ],
                            "contradictions": ["concise contradiction"],
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [],
    }


def verify_reasoning_path(
    *,
    path: ReasoningPath,
    hypotheses: Sequence[Hypothesis],
    declared_evidence_ids: Iterable[str],
    payload: Mapping[str, Any],
) -> VerifierReport:
    raw_steps = payload.get("steps", [])
    if not isinstance(raw_steps, list):
        raise ProviderError("verifier response steps must be an array")
    reported = {str(item.get("step_id", "")): item for item in raw_steps if isinstance(item, dict)}
    if set(reported) != {step.step_id for step in path.steps}:
        raise ProviderError("verifier response must cover every candidate step exactly once")
    declared = set(declared_evidence_ids)
    known_hypotheses = {item.hypothesis_id for item in hypotheses}
    hypothesis_grounding: dict[str, set[str]] = {}
    for hypothesis in hypotheses:
        roots = {
            "evidence"
            for evidence_id in hypothesis.supporting_evidence
            if evidence_id in declared
        }
        if hypothesis.assumptions:
            roots.add("assumption")
        hypothesis_grounding[hypothesis.hypothesis_id] = roots
    prior_steps: set[str] = set()
    prior_grounding: dict[str, set[str]] = {}
    scores = []
    failures = []
    critical = False
    for step in path.steps:
        item = reported[step.step_id]
        checks = item.get("checks", {})
        if not isinstance(checks, dict) or set(checks) != set(PROCESS_CHECKS):
            raise ProviderError("verifier response must provide every process check")
        normalized = {name: bool(checks[name]) for name in PROCESS_CHECKS}
        allowed_premises = {"problem", *known_hypotheses, *prior_steps}
        if set(step.premises) - allowed_premises:
            normalized["premises_available"] = False
        if set(step.evidence_ids) - declared:
            normalized["evidence_declared"] = False
        if step.inference not in INFERENCE_MODES - {"unspecified"}:
            normalized["inference_supported"] = False
        grounding: set[str] = set()
        for premise in step.premises:
            if premise == "problem":
                grounding.add("validated_premise")
            elif premise in hypothesis_grounding:
                grounding.update(hypothesis_grounding[premise])
            elif premise in prior_grounding:
                grounding.update(prior_grounding[premise])
        if any(evidence_id in declared for evidence_id in step.evidence_ids):
            grounding.add("evidence")
        if step.assumptions:
            grounding.add("assumption")
        if not grounding:
            normalized["grounding_traceable"] = False
        score = sum(1 for value in normalized.values() if value) * SCORE_SCALE // len(PROCESS_CHECKS)
        scores.append((step.step_id, score))
        item_failures = [str(value) for value in item.get("failures", ()) if str(value)]
        failures.extend(f"{step.step_id}: {value}" for value in item_failures)
        if not normalized["premises_available"]:
            failures.append(f"{step.step_id}: unavailable premise")
            critical = True
        if not normalized["evidence_declared"]:
            failures.append(f"{step.step_id}: undeclared evidence")
            critical = True
        if not normalized["inference_supported"]:
            failures.append(f"{step.step_id}: unsupported inference")
            critical = True
        if not normalized["grounding_traceable"]:
            failures.append(f"{step.step_id}: no grounding trace")
            critical = True
        prior_steps.add(step.step_id)
        prior_grounding[step.step_id] = grounding
    contradictions = tuple(
        str(value) for value in payload.get("contradictions", ()) if str(value)
    )
    score_bp = min(score for _, score in scores)
    if critical:
        score_bp = 0
        verdict = "REJECT"
    elif score_bp >= 7_500 and not contradictions:
        verdict = "ACCEPT"
    elif score_bp >= 5_000:
        verdict = "REVISE"
    else:
        verdict = "REJECT"
    material = {
        "path_id": path.path_id,
        "step_scores": tuple(scores),
        "failures": tuple(failures),
        "contradictions": contradictions,
        "score_bp": score_bp,
        "verdict": verdict,
    }
    report_id = f"verifier:{stable_hash(material)}"
    return VerifierReport(
        report_id=report_id,
        **material,
        signature=stable_hash({**material, "report_id": report_id}),
    )


def verify_reasoning_paths(
    *,
    provider: Any,
    problem: ReasoningProblem,
    paths: Sequence[ReasoningPath],
    hypotheses: Sequence[Hypothesis],
    declared_evidence_ids: Iterable[str],
    budget: ReasoningBudget,
) -> tuple[VerifierReport, ...]:
    requests = tuple(
        verifier_request(problem=problem, path=path, hypotheses=hypotheses)
        for path in paths
    )
    responses = create_provider_responses(
        provider,
        requests,
        max_responses=budget.max_provider_calls,
    )
    return tuple(
        verify_reasoning_path(
            path=path,
            hypotheses=hypotheses,
            declared_evidence_ids=declared_evidence_ids,
            payload=parse_json_object(response_text(response)),
        )
        for path, response in zip(paths, responses)
    )


__all__ = [
    "PROCESS_CHECKS",
    "verifier_request",
    "verify_reasoning_path",
    "verify_reasoning_paths",
]
