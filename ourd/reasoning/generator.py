from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from ..errors import PolicyError, ProviderError
from .models import (
    Hypothesis,
    INFERENCE_MODES,
    ReasoningBudget,
    ReasoningPath,
    ReasoningProblem,
    ReasoningStep,
    bounded_score,
    canonical_inference_mode,
    stable_hash,
    stable_strings,
)


DEFAULT_PERSPECTIVES = (
    "causal_mechanistic",
    "counterexample_first",
    "formal_derivation",
    "evidence_synthesis",
    "assumption_inversion",
    "minimal_change",
    "boundary_first",
    "uncertainty_reduction",
)


def response_text(response: Any) -> str:
    def get(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    if get(response, "type", "") == "reasoning_error":
        raise ProviderError(str(get(response, "error", "reasoning provider request failed")))
    direct = get(response, "output_text", "") or ""
    if direct:
        return str(direct)
    parts = []
    for item in get(response, "output", []) or []:
        if get(item, "type", "") != "message":
            continue
        for content in get(item, "content", []) or []:
            if get(content, "type", "") == "output_text":
                parts.append(str(get(content, "text", "")))
    return "".join(parts)


def parse_json_object(text: str) -> Mapping[str, Any]:
    stripped = text.strip()
    if "</think>" in stripped:
        stripped = stripped.rsplit("</think>", 1)[1].strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"reasoning response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProviderError("reasoning response must be a JSON object")
    return payload


def create_provider_responses(
    provider: Any,
    requests: Sequence[Mapping[str, Any]],
    *,
    max_responses: int,
) -> tuple[Any, ...]:
    if len(requests) > int(max_responses):
        raise PolicyError("reasoning provider request count exceeds hard cap")
    batch = getattr(provider, "create_responses", None)
    if callable(batch):
        responses = tuple(batch(requests=list(requests), max_responses=max_responses))
    else:
        values = []
        for request in requests:
            try:
                values.append(
                    provider.create_response(
                        instructions=str(request["instructions"]),
                        input_items=list(request["input_items"]),
                        tools=list(request.get("tools", [])),
                    )
                )
            except Exception as exc:
                values.append(
                    {"type": "reasoning_error", "error": f"{type(exc).__name__}: {exc}"}
                )
        responses = tuple(values)
    if len(responses) != len(requests):
        raise ProviderError("reasoning provider response count does not match request count")
    return responses


def perspective_names(count: int) -> tuple[str, ...]:
    requested = int(count)
    if requested < 1:
        raise PolicyError("at least one reasoning perspective is required")
    values = list(DEFAULT_PERSPECTIVES[:requested])
    while len(values) < requested:
        values.append(f"independent_probe_{len(values) + 1:02d}")
    return tuple(values)


def proposer_request(
    *,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    perspective: str,
    budget: ReasoningBudget,
) -> Mapping[str, Any]:
    schema = {
        "conclusion": "concise candidate conclusion",
        "hypothesis_ids": ["declared hypothesis ID"],
        "provider_confidence_bp": 0,
        "estimated_cost_bp": 0,
        "goal_relevance_bp": 0,
        "risk_bp": 0,
        "steps": [
            {
                "step_id": "step-01",
                "claim": "auditable claim",
                "premises": ["problem, hypothesis ID, or prior step ID"],
                "evidence_ids": ["declared evidence artifact ID"],
                "inference": "one declared inference mode",
                "confidence_bp": 0,
                "assumptions": ["explicit assumption"],
                "falsifier": "condition that would count against this step",
            }
        ],
    }
    return {
        "instructions": (
            "Act only as an OIEC-SR proposer. Return one JSON object matching the "
            "provided schema. Give concise claims, premises, evidence references, "
            "assumptions, and falsifiers. Do not reveal private chain-of-thought, use "
            "tools, approve actions, or claim authority."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": asdict(problem),
                        "hypotheses": [asdict(item) for item in hypotheses],
                        "perspective": perspective,
                        "inference_modes": sorted(INFERENCE_MODES - {"unspecified"}),
                        "maximum_steps": budget.max_steps_per_path,
                        "schema": schema,
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [],
    }


def parse_reasoning_path(
    *,
    payload: Mapping[str, Any],
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    perspective: str,
    budget: ReasoningBudget,
) -> ReasoningPath:
    conclusion = str(payload.get("conclusion", "")).strip()
    raw_steps = payload.get("steps", [])
    if not conclusion or not isinstance(raw_steps, list) or not raw_steps:
        raise ProviderError("proposer response requires a conclusion and non-empty steps")
    if len(raw_steps) > budget.max_steps_per_path:
        raise ProviderError("proposer response exceeds the step budget")
    known_hypotheses = {item.hypothesis_id for item in hypotheses}
    hypothesis_ids = stable_strings(str(item) for item in payload.get("hypothesis_ids", ()))
    if set(hypothesis_ids) - known_hypotheses:
        raise ProviderError("proposer response references an unknown hypothesis")
    normalized_steps = []
    for index, raw in enumerate(raw_steps, 1):
        if not isinstance(raw, dict):
            raise ProviderError("proposer reasoning steps must be JSON objects")
        try:
            inference_mode = canonical_inference_mode(str(raw.get("inference", "")))
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc
        normalized_steps.append(
            {
                "step_id": str(raw.get("step_id", f"step-{index:02d}")).strip(),
                "claim": str(raw.get("claim", "")).strip(),
                "premises": stable_strings(str(item) for item in raw.get("premises", ())),
                "evidence_ids": stable_strings(
                    str(item) for item in raw.get("evidence_ids", ())
                ),
                "inference": inference_mode,
                "confidence_bp": bounded_score(
                    int(raw.get("confidence_bp", 0)),
                    "provider step confidence",
                ),
                "assumptions": stable_strings(
                    str(item) for item in raw.get("assumptions", ())
                ),
                "falsifier": str(raw.get("falsifier", "")).strip(),
            }
        )
    if any(not item["step_id"] for item in normalized_steps):
        raise ProviderError("proposer reasoning step IDs must be non-empty")
    if len({item["step_id"] for item in normalized_steps}) != len(normalized_steps):
        raise ProviderError("proposer reasoning step IDs must be unique")
    raw_material = {
        "problem_id": problem.problem_id,
        "perspective": perspective,
        "hypothesis_ids": hypothesis_ids,
        "steps": normalized_steps,
        "conclusion": conclusion,
        "provider_confidence_bp": bounded_score(
            int(payload.get("provider_confidence_bp", 0)),
            "provider path confidence",
        ),
        "estimated_cost_bp": bounded_score(
            int(payload.get("estimated_cost_bp", 0)),
            "provider estimated cost",
        ),
        "goal_relevance_bp": bounded_score(
            int(payload.get("goal_relevance_bp", 0)),
            "provider goal relevance",
        ),
        "risk_bp": bounded_score(int(payload.get("risk_bp", 0)), "provider path risk"),
    }
    path_digest = stable_hash(raw_material)
    path_id = f"path:{path_digest}"
    steps = []
    for raw in normalized_steps:
        step_payload = {
            **raw,
        }
        steps.append(ReasoningStep(**step_payload, signature=stable_hash(step_payload)))
    path_payload = {**raw_material, "path_id": path_id, "steps": [asdict(item) for item in steps]}
    return ReasoningPath(
        path_id=path_id,
        perspective=perspective,
        hypothesis_ids=hypothesis_ids,
        steps=tuple(steps),
        conclusion=conclusion,
        provider_confidence_bp=raw_material["provider_confidence_bp"],
        estimated_cost_bp=raw_material["estimated_cost_bp"],
        goal_relevance_bp=raw_material["goal_relevance_bp"],
        risk_bp=raw_material["risk_bp"],
        signature=stable_hash(path_payload),
    )


def generate_reasoning_paths(
    *,
    provider: Any,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    budget: ReasoningBudget,
) -> tuple[ReasoningPath, ...]:
    perspectives = perspective_names(budget.candidate_count)
    requests = tuple(
        proposer_request(
            problem=problem,
            hypotheses=hypotheses,
            perspective=perspective,
            budget=budget,
        )
        for perspective in perspectives
    )
    responses = create_provider_responses(
        provider,
        requests,
        max_responses=budget.max_provider_calls,
    )
    paths = []
    for perspective, response in zip(perspectives, responses):
        payload = parse_json_object(response_text(response))
        paths.append(
            parse_reasoning_path(
                payload=payload,
                problem=problem,
                hypotheses=hypotheses,
                perspective=perspective,
                budget=budget,
            )
        )
    if len({path.path_id for path in paths}) != len(paths):
        raise ProviderError("proposer responses did not produce independent candidate paths")
    return tuple(paths)


__all__ = [
    "DEFAULT_PERSPECTIVES",
    "create_provider_responses",
    "generate_reasoning_paths",
    "parse_json_object",
    "parse_reasoning_path",
    "perspective_names",
    "proposer_request",
    "response_text",
]
