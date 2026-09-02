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
    provider_hypothesis_context,
    provider_problem_context,
    reasoning_batch_tool,
    reasoning_object_tool,
    reasoning_role_batch_size,
    response_text,
)
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

PROCESS_CHECK_ALIASES = {
    "alternative_consideered": "alternative_considered",
}

VERIFIER_BATCH_MAX_OUTPUT_TOKENS = 1_024


def normalize_process_checks(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise ProviderError("verifier response checks must be an object")
    normalized: dict[str, bool] = {}
    for raw_name, raw_value in value.items():
        name = PROCESS_CHECK_ALIASES.get(str(raw_name), str(raw_name))
        if name in normalized:
            raise ProviderError("verifier response contains ambiguous process checks")
        if not isinstance(raw_value, bool):
            raise ProviderError("verifier process checks must be booleans")
        normalized[name] = raw_value
    if set(normalized) != set(PROCESS_CHECKS):
        raise ProviderError("verifier response must provide every process check")
    return {name: normalized[name] for name in PROCESS_CHECKS}


def verifier_request(
    *,
    problem: ReasoningProblem,
    path: ReasoningPath,
    hypotheses: Sequence[Hypothesis],
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an independent OIEC-SR process verifier. Inspect the supplied "
            "candidate without assuming it is correct. Call "
            f"{REASONING_OBJECT_TOOL_NAME} exactly once with one object containing one entry per "
            "step and every named boolean check. Do not reveal private chain-of-thought, "
            "use any other tool, approve actions, or choose a final winner. Treat facts explicitly "
            "stated in the problem as an available validated premise named 'problem'. "
            "Only declared evidence IDs are evidence; governance hashes and signatures "
            "are not factual support. Do not require every declared evidence ID on every "
            "step, do not invent external evidence, and evaluate the closed supplied task "
            "rather than hypothetical unstated context. The problem statement supplies "
            "the task facts and declared evidence IDs are references to those facts; do "
            "not reject a step merely because raw artifact bodies are not embedded. A "
            "stated missing artifact can validly support a conclusion that a claim is not "
            "proven. Return exactly one top-level JSON object with keys 'steps', "
            "'contradictions', and 'missing_assumptions'; never return a bare array or "
            "Markdown fence."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": provider_problem_context(problem),
                        "hypotheses": [provider_hypothesis_context(item) for item in hypotheses],
                        "candidate": asdict(path),
                        "verification_contract": {
                            "top_level_type": "object",
                            "required_top_level_keys": [
                                "steps",
                                "contradictions",
                                "missing_assumptions",
                            ],
                            "problem_is_validated_premise": True,
                            "control_metadata_is_evidence": False,
                            "all_declared_evidence_required_per_step": False,
                            "external_unstated_context_allowed": False,
                        },
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
                            "missing_assumptions": ["implicit assumption that must be explicit"],
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [
            reasoning_object_tool(
                ("steps", "contradictions", "missing_assumptions"),
            )
        ],
    }


def verifier_repair_request(
    *,
    problem: ReasoningProblem,
    path: ReasoningPath,
    hypotheses: Sequence[Hypothesis],
    invalid_response: str,
    validation_error: str,
) -> Mapping[str, Any]:
    return {
        "instructions": (
            "Act only as an OIEC-SR verifier schema repairer. The previous verifier "
            "response failed deterministic validation. Call "
            f"{REASONING_OBJECT_TOOL_NAME} exactly once with one corrected top-level "
            "object. Preserve the previous boolean judgments and failure "
            "meaning; repair keys, types, step coverage, and object shape only. Do not "
            "add evidence, change the candidate, choose a winner, use any other tool, or reveal "
            "private chain-of-thought. Every step checks object must contain each exact "
            "required check name once, with a JSON boolean value."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": provider_problem_context(problem),
                        "hypotheses": [provider_hypothesis_context(item) for item in hypotheses],
                        "candidate": asdict(path),
                        "validation_error": validation_error,
                        "invalid_response": invalid_response,
                        "required_checks": PROCESS_CHECKS,
                        "required_top_level_keys": [
                            "steps",
                            "contradictions",
                            "missing_assumptions",
                        ],
                        "response_schema": {
                            "steps": [
                                {
                                    "step_id": "candidate step ID",
                                    "checks": {name: True for name in PROCESS_CHECKS},
                                    "failures": ["concise failure"],
                                }
                            ],
                            "contradictions": ["concise contradiction"],
                            "missing_assumptions": [
                                "implicit assumption that must be explicit"
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [
            reasoning_object_tool(
                ("steps", "contradictions", "missing_assumptions"),
            )
        ],
    }


def verifier_batch_request(
    *,
    problem: ReasoningProblem,
    paths: Sequence[ReasoningPath],
    hypotheses: Sequence[Hypothesis],
) -> Mapping[str, Any]:
    if not paths:
        raise ProviderError("structured verifier request requires at least one candidate")
    example_request = verifier_request(
        problem=problem,
        path=paths[0],
        hypotheses=hypotheses,
    )
    example = json.loads(str(example_request["input_items"][0]["content"]))
    return {
        "instructions": (
            "Act only as an independent OIEC-SR process verifier micro-batch. Call "
            f"{REASONING_BATCH_TOOL_NAME} exactly once with a 'reports' array. Verify every supplied "
            "candidate independently and return reports in the exact candidate order. "
            "Each array entry is the ordinary verifier object. Do not reorder or compare candidates, "
            "choose a winner, transfer support between paths, or use proposer confidence "
            "as authority. Evaluate every required check for every candidate step. In "
            "the compact wire format, list only failed check names; an empty list means "
            "all required checks passed, and all_checks_evaluated must be true. "
            "Do not reveal private chain-of-thought, use tools, or invent evidence."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": example["problem"],
                        "hypotheses": example["hypotheses"],
                        "candidates": [asdict(path) for path in paths],
                        "verification_contract": example["verification_contract"],
                        "required_checks": example["required_checks"],
                        "response_schema": {
                            "reports": [
                                {
                                    "steps": [
                                        {
                                            "step_id": "candidate step ID",
                                            "all_checks_evaluated": True,
                                            "failed_checks": ["one required check name"],
                                            "failures": ["concise failure"],
                                        }
                                    ],
                                    "contradictions": ["concise contradiction"],
                                    "missing_assumptions": [
                                        "implicit assumption that must be explicit"
                                    ],
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [reasoning_batch_tool("reports")],
        "max_output_tokens": VERIFIER_BATCH_MAX_OUTPUT_TOKENS,
        "allow_invalid_json": True,
    }


def expand_compact_verifier_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        raise ProviderError("compact verifier response steps must be an array")
    steps = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ProviderError("compact verifier step must be an object")
        if raw_step.get("all_checks_evaluated") is not True:
            raise ProviderError("compact verifier must affirm evaluation of all checks")
        failed = raw_step.get("failed_checks", [])
        if not isinstance(failed, list):
            raise ProviderError("compact verifier failed_checks must be an array")
        failed_names = tuple(str(value) for value in failed)
        if len(set(failed_names)) != len(failed_names):
            raise ProviderError("compact verifier failed_checks contains duplicates")
        if set(failed_names) - set(PROCESS_CHECKS):
            raise ProviderError("compact verifier references an unknown process check")
        failures = raw_step.get("failures", [])
        if not isinstance(failures, list):
            raise ProviderError("compact verifier failures must be an array")
        steps.append(
            {
                "step_id": str(raw_step.get("step_id", "")),
                "checks": {name: name not in set(failed_names) for name in PROCESS_CHECKS},
                "failures": [str(value) for value in failures],
            }
        )
    return {
        "steps": steps,
        "contradictions": payload.get("contradictions", []),
        "missing_assumptions": payload.get("missing_assumptions", []),
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
    checks_by_step = []
    failures = []
    unsupported_nodes = []
    missing_assumptions = [
        str(value) for value in payload.get("missing_assumptions", ()) if str(value)
    ]
    critical = False
    for step in path.steps:
        item = reported[step.step_id]
        normalized = normalize_process_checks(item.get("checks", {}))
        allowed_premises = {"problem", *known_hypotheses, *prior_steps}
        if set(step.premises) - allowed_premises:
            normalized["premises_available"] = False
        if set(step.evidence_ids) - declared:
            normalized["evidence_declared"] = False
        if step.inference not in INFERENCE_MODES - {"unspecified"}:
            normalized["inference_supported"] = False
        if (
            step.inference in {"inductive", "causal", "probabilistic", "authority"}
            and not any(evidence_id in declared for evidence_id in step.evidence_ids)
        ):
            normalized["evidence_relevant"] = False
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
        checks_by_step.append(normalized)
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
        if not normalized["evidence_relevant"]:
            failures.append(f"{step.step_id}: missing factual evidence")
            unsupported_nodes.append(step.step_id)
            critical = True
        if not normalized["assumptions_explicit"]:
            missing_assumptions.append(f"{step.step_id}: implicit assumption")
        if not normalized["conclusion_not_overstated"]:
            failures.append(f"{step.step_id}: conclusion stronger than premises")
            unsupported_nodes.append(step.step_id)
            critical = True
        if not all(
            normalized[name]
            for name in (
                "premises_available",
                "evidence_declared",
                "inference_supported",
                "grounding_traceable",
            )
        ):
            unsupported_nodes.append(step.step_id)
        prior_steps.add(step.step_id)
        prior_grounding[step.step_id] = grounding
    contradictions = tuple(
        str(value) for value in payload.get("contradictions", ()) if str(value)
    )
    score_bp = min(score for _, score in scores)
    premise_validity_bp = sum(
        SCORE_SCALE if checks["premises_available"] else 0 for checks in checks_by_step
    ) // len(checks_by_step)
    evidence_support_bp = sum(
        (
            (SCORE_SCALE if checks["evidence_declared"] else 0)
            + (SCORE_SCALE if checks["evidence_relevant"] else 0)
        )
        // 2
        for checks in checks_by_step
    ) // len(checks_by_step)
    inference_quality_bp = sum(
        (
            (SCORE_SCALE if checks["inference_supported"] else 0)
            + (SCORE_SCALE if checks["conclusion_not_overstated"] else 0)
        )
        // 2
        for checks in checks_by_step
    ) // len(checks_by_step)
    consistency_bp = max(0, SCORE_SCALE - len(contradictions) * 2_000)
    completeness_bp = sum(
        (
            (SCORE_SCALE if checks["grounding_traceable"] else 0)
            + (SCORE_SCALE if checks["assumptions_explicit"] else 0)
            + (SCORE_SCALE if checks["counterexample_addressed"] else 0)
        )
        // 3
        for checks in checks_by_step
    ) // len(checks_by_step)
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
        "unsupported_nodes": tuple(unsupported_nodes),
        "missing_assumptions": tuple(missing_assumptions),
        "premise_validity_bp": premise_validity_bp,
        "evidence_support_bp": evidence_support_bp,
        "inference_quality_bp": inference_quality_bp,
        "consistency_bp": consistency_bp,
        "completeness_bp": completeness_bp,
        "weakest_step_bp": score_bp,
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
    role_batch_size: int = 1,
) -> tuple[VerifierReport, ...]:
    batch_size = reasoning_role_batch_size(provider, role_batch_size)
    structured_batches = batch_size > 1
    received: list[tuple[ReasoningPath, Mapping[str, Any], str]] = []
    for start in range(0, len(paths), batch_size):
        group = tuple(paths[start : start + batch_size])
        if len(group) == 1 and not structured_batches:
            response = create_provider_responses(
                provider,
                (verifier_request(problem=problem, path=group[0], hypotheses=hypotheses),),
                max_responses=budget.max_provider_calls,
            )[0]
            raw_text = response_text(response)
            received.append((group[0], parse_json_object(raw_text), raw_text))
        else:
            response = create_provider_responses(
                provider,
                (
                    verifier_batch_request(
                        problem=problem,
                        paths=group,
                        hypotheses=hypotheses,
                    ),
                ),
                max_responses=budget.max_provider_calls,
            )[0]
            try:
                payloads = parse_ordered_role_batch_payloads(
                    response,
                    collection_key="reports",
                    expected_count=len(group),
                )
                payloads = tuple(
                    expand_compact_verifier_payload(payload) for payload in payloads
                )
            except ProviderError as exc:
                if budget.max_verifier_passes < 2:
                    raise
                recorder = getattr(provider, "record_reasoning_repair", None)
                if callable(recorder):
                    recorder(
                        role="verifier_batch",
                        reason=str(exc),
                        item_ids=tuple(path.path_id for path in group),
                    )
                split_responses = create_provider_responses(
                    provider,
                    tuple(
                        verifier_request(
                            problem=problem,
                            path=path,
                            hypotheses=hypotheses,
                        )
                        for path in group
                    ),
                    max_responses=budget.max_provider_calls,
                )
                payloads = tuple(
                    parse_json_object(response_text(split_response))
                    for split_response in split_responses
                )
            received.extend(
                (path, payload, json.dumps(payload, ensure_ascii=False))
                for path, payload in zip(group, payloads)
            )
    reports = []
    for path, payload, raw_text in received:
        try:
            report = verify_reasoning_path(
                path=path,
                hypotheses=hypotheses,
                declared_evidence_ids=declared_evidence_ids,
                payload=payload,
            )
        except ProviderError as exc:
            if budget.max_verifier_passes < 2:
                raise
            repaired = create_provider_responses(
                provider,
                (
                    verifier_repair_request(
                        problem=problem,
                        path=path,
                        hypotheses=hypotheses,
                        invalid_response=raw_text,
                        validation_error=str(exc),
                    ),
                ),
                max_responses=budget.max_provider_calls,
            )[0]
            report = verify_reasoning_path(
                path=path,
                hypotheses=hypotheses,
                declared_evidence_ids=declared_evidence_ids,
                payload=parse_json_object(response_text(repaired)),
            )
        reports.append(report)
    return tuple(reports)


__all__ = [
    "PROCESS_CHECK_ALIASES",
    "PROCESS_CHECKS",
    "VERIFIER_BATCH_MAX_OUTPUT_TOKENS",
    "expand_compact_verifier_payload",
    "normalize_process_checks",
    "verifier_batch_request",
    "verifier_repair_request",
    "verifier_request",
    "verify_reasoning_path",
    "verify_reasoning_paths",
]
