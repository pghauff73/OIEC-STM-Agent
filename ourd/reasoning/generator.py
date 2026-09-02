from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from ..errors import PolicyError, ProviderError
from .diversity import (
    DEFAULT_DIVERSITY_CONFIGURATION,
    bind_diversity_scores,
    is_structural_duplicate,
    structure_material_from_parts,
)
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
    "direct",
    "mechanistic",
    "counterexample_first",
    "assumption_inversion",
    "causal",
    "mathematical",
    "evidence_synthesis",
    "abductive",
)

REASONING_BATCH_TOOL_NAME = "submit_oiec_reasoning_batch"
REASONING_OBJECT_TOOL_NAME = "submit_oiec_reasoning_object"
PROPOSER_BATCH_MAX_OUTPUT_TOKENS = 2_048

PERSPECTIVE_CONTRACTS: Mapping[str, Mapping[str, Any]] = {
    "direct": {
        "contract_type": "declared_perspective",
        "objective": "Derive the shortest supported answer from explicit task facts.",
        "primary_inference_mode": "deductive",
        "fallback_inference_modes": ("constraint", "defeasible"),
        "required_path_shape": (
            "Begin with the decisive supplied premise or constraint.",
            "Use no intermediate mechanism unless the conclusion requires one.",
        ),
        "falsifier_focus": "Identify the smallest supplied fact change that defeats the conclusion.",
    },
    "mechanistic": {
        "contract_type": "declared_perspective",
        "objective": "Explain the dependency or state-transition mechanism that produces the answer.",
        "primary_inference_mode": "causal",
        "fallback_inference_modes": ("constraint", "deductive"),
        "required_path_shape": (
            "Identify an intermediate dependency, state transition, or enabling condition.",
            "Connect that mechanism to the conclusion without inventing external facts.",
        ),
        "falsifier_focus": "Identify the mechanism link whose failure would defeat the path.",
    },
    "counterexample_first": {
        "contract_type": "declared_perspective",
        "objective": "Test the strongest plausible answer against a task-grounded counterexample first.",
        "primary_inference_mode": "defeasible",
        "fallback_inference_modes": ("deductive", "constraint"),
        "required_path_shape": (
            "State the strongest present counterexample or boundary case before the conclusion.",
            "Explain whether that challenge defeats, qualifies, or leaves the answer intact.",
        ),
        "falsifier_focus": "Use a concrete present counterexample, not hypothetical future evidence.",
    },
    "assumption_inversion": {
        "contract_type": "declared_perspective",
        "objective": "Invert one genuinely necessary candidate assumption and compare consequences.",
        "primary_inference_mode": "abductive",
        "fallback_inference_modes": ("defeasible", "constraint"),
        "required_path_shape": (
            "Name no assumption when the supplied facts already settle the task.",
            "Otherwise compare the original and inverted assumption against the same supplied facts.",
        ),
        "falsifier_focus": "Identify an observation that makes the inverted assumption fit better.",
    },
    "causal": {
        "contract_type": "declared_perspective",
        "objective": "Test causal direction, intervention relevance, and possible confounding.",
        "primary_inference_mode": "causal",
        "fallback_inference_modes": ("probabilistic", "constraint"),
        "required_path_shape": (
            "Separate association or sequence from an asserted causal relation.",
            "State whether an intervention claim is supported by the supplied task facts.",
        ),
        "falsifier_focus": "Identify reversed direction, confounding, or absent intervention support.",
    },
    "mathematical": {
        "contract_type": "declared_perspective",
        "objective": "Formalize the relevant quantities, relations, or finite constraints and check them.",
        "primary_inference_mode": "computational",
        "fallback_inference_modes": ("deductive", "constraint"),
        "required_path_shape": (
            "Express at least one task-grounded relation or finite comparison explicitly.",
            "Do not invent numerical values when the task supplies none.",
        ),
        "falsifier_focus": "Identify a boundary value, counter-calculation, or violated relation.",
    },
    "evidence_synthesis": {
        "contract_type": "declared_perspective",
        "objective": "Compare the supplied evidence coverage, agreement, and conflict before answering.",
        "primary_inference_mode": "inductive",
        "fallback_inference_modes": ("probabilistic", "defeasible"),
        "required_path_shape": (
            "Account for supporting and conflicting supplied evidence without fabricating artifacts.",
            "Calibrate the conclusion to the weakest material evidence link.",
        ),
        "falsifier_focus": "Identify the supplied or obtainable evidence class that would reverse the balance.",
    },
    "abductive": {
        "contract_type": "declared_perspective",
        "objective": "Compare competing explanations by fit, assumptions, and residual uncertainty.",
        "primary_inference_mode": "abductive",
        "fallback_inference_modes": ("probabilistic", "defeasible"),
        "required_path_shape": (
            "Contrast at least two task-compatible explanations when two exist.",
            "Prefer the explanation requiring the fewest unsupported assumptions.",
        ),
        "falsifier_focus": "Identify an observation that would make an alternative explanation superior.",
    },
}

_INDEPENDENT_PROBE_MODES = (
    "constraint",
    "defeasible",
    "probabilistic",
    "deductive",
    "inductive",
    "abductive",
    "causal",
    "computational",
)

_INDEPENDENT_PROBE_FOCI = (
    "boundary conditions",
    "weakest premise",
    "evidence conflict",
    "alternative explanation",
    "scope qualification",
    "prediction failure",
    "dependency reversal",
    "finite consistency check",
)


def perspective_contract(perspective: str) -> Mapping[str, Any]:
    name = str(perspective).strip()
    if not name:
        raise PolicyError("reasoning perspective must be non-empty")
    declared = PERSPECTIVE_CONTRACTS.get(name)
    if declared is not None:
        return {"contract_id": f"oiec-sr-perspective:{name}:v1", **declared}
    selector = int(stable_hash({"perspective": name})[:8], 16)
    primary_mode = _INDEPENDENT_PROBE_MODES[selector % len(_INDEPENDENT_PROBE_MODES)]
    focus = _INDEPENDENT_PROBE_FOCI[selector % len(_INDEPENDENT_PROBE_FOCI)]
    return {
        "contract_id": f"oiec-sr-perspective:independent-probe:{stable_hash(name)[:12]}:v1",
        "contract_type": "independent_probe",
        "objective": "Construct an independent task-grounded audit path rather than paraphrasing another path.",
        "primary_inference_mode": primary_mode,
        "fallback_inference_modes": ("constraint", "defeasible"),
        "required_path_shape": (
            f"Center the path on {focus}.",
            "Use only declared premises, hypotheses, and evidence identifiers.",
        ),
        "falsifier_focus": f"State a concrete task-grounded defeat condition focused on {focus}.",
    }


def provider_problem_context(problem: ReasoningProblem) -> Mapping[str, Any]:
    return {
        "premise_id": "problem",
        "statement": problem.statement,
        "goal": problem.goal,
        "evidence_ids": list(problem.evidence_ids),
        "uncertainty_bp": problem.uncertainty_bp,
        "difficulty_bp": problem.difficulty_bp,
        "mutually_exclusive_hypotheses": problem.mutually_exclusive_hypotheses,
    }


def provider_hypothesis_context(hypothesis: Hypothesis) -> Mapping[str, Any]:
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "proposition": hypothesis.proposition,
        "posterior_bp": hypothesis.posterior_bp,
        "supporting_evidence": list(hypothesis.supporting_evidence),
        "conflicting_evidence": list(hypothesis.conflicting_evidence),
        "assumptions": list(hypothesis.assumptions),
        "predictions": list(hypothesis.predictions),
        "falsifiers": list(hypothesis.falsifiers),
        "status": hypothesis.status,
    }


def _response_usage(response: Any) -> tuple[int, int, int, int]:
    def get(value: Any, name: str, default: Any = None) -> Any:
        return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)

    usage = get(response, "usage", {}) or {}
    input_tokens = max(0, int(get(usage, "input_tokens", 0) or 0))
    output_value = get(usage, "output_tokens", None)
    total_tokens = max(0, int(get(usage, "total_tokens", 0) or 0))
    if output_value is None:
        output_tokens = max(0, total_tokens - input_tokens)
    else:
        output_tokens = max(0, int(output_value or 0))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    tool_calls = sum(
        1
        for item in get(response, "output", ()) or ()
        if str(get(item, "type", "")) in {"function_call", "tool_call"}
    )
    return input_tokens, output_tokens, total_tokens, tool_calls


@dataclass
class BoundedReasoningProvider:
    provider: Any
    max_calls: int
    max_tokens: int
    max_tool_calls: int
    calls_used: int = 0
    tokens_used: int = 0
    input_tokens_observed: int = 0
    total_tokens_observed: int = 0
    tool_calls_used: int = 0

    @property
    def config(self) -> Any:
        return getattr(self.provider, "config", None)

    @property
    def reasoning_role_batch_size(self) -> int:
        return max(1, int(getattr(self.provider, "reasoning_role_batch_size", 1)))

    def create_responses(self, *, requests: Sequence[Mapping[str, Any]], max_responses: int) -> tuple[Any, ...]:
        count = len(requests)
        if count > max_responses or self.calls_used + count > self.max_calls:
            raise PolicyError("reasoning provider call budget exceeded")
        self.calls_used += count
        batch = getattr(self.provider, "create_responses", None)
        if callable(batch):
            responses = tuple(batch(requests=list(requests), max_responses=max_responses))
        else:
            responses = tuple(
                self.provider.create_response(
                    instructions=str(request["instructions"]),
                    input_items=list(request["input_items"]),
                    tools=list(request.get("tools", [])),
                )
                for request in requests
            )
        if len(responses) != count:
            raise ProviderError("reasoning provider response count does not match request count")
        for response in responses:
            input_tokens, output_tokens, total_tokens, tool_calls = _response_usage(response)
            self.input_tokens_observed += input_tokens
            self.tokens_used += output_tokens
            self.total_tokens_observed += total_tokens
            self.tool_calls_used += tool_calls
        if self.tokens_used > self.max_tokens:
            raise PolicyError("reasoning token budget exceeded")
        if self.tool_calls_used > self.max_tool_calls:
            raise PolicyError("reasoning tool-call budget exceeded")
        return responses

    def record_reasoning_repair(
        self,
        *,
        role: str,
        reason: str,
        item_ids: Sequence[str],
    ) -> None:
        recorder = getattr(self.provider, "record_reasoning_repair", None)
        if callable(recorder):
            recorder(role=role, reason=reason, item_ids=item_ids)


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
        item_type = str(get(item, "type", ""))
        if item_type in {"function_call", "tool_call"}:
            arguments = get(item, "arguments", "")
            if isinstance(arguments, dict):
                return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if str(arguments).strip():
                return str(arguments)
            continue
        if item_type != "message":
            continue
        for content in get(item, "content", []) or []:
            if get(content, "type", "") == "output_text":
                parts.append(str(get(content, "text", "")))
    return "".join(parts)


def reasoning_batch_tool(collection_key: str) -> Mapping[str, Any]:
    return {
        "name": REASONING_BATCH_TOOL_NAME,
        "description": "Submit one deterministic OIEC-SR role micro-batch result.",
        "parameters": {
            "type": "object",
            "properties": {
                str(collection_key): {
                    "type": "array",
                    "items": {},
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def reasoning_object_tool(
    property_keys: Sequence[str],
    *,
    required_keys: Sequence[str] = (),
) -> Mapping[str, Any]:
    properties = tuple(dict.fromkeys(str(value) for value in property_keys if str(value)))
    required = tuple(dict.fromkeys(str(value) for value in required_keys if str(value)))
    if not properties:
        raise PolicyError("reasoning object tool requires declared properties")
    if set(required) - set(properties):
        raise PolicyError("reasoning object tool required keys must be declared properties")
    return {
        "type": "function",
        "name": REASONING_OBJECT_TOOL_NAME,
        "description": "Submit one deterministic OIEC-SR structured reasoning object.",
        "parameters": {
            "type": "object",
            "properties": {name: {} for name in properties},
            "required": list(required),
            "additionalProperties": False,
        },
    }


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


def reasoning_role_batch_size(provider: Any, configured_batch_size: int) -> int:
    supported = max(1, int(getattr(provider, "reasoning_role_batch_size", 1)))
    return min(max(1, int(configured_batch_size)), supported)


def parse_ordered_role_batch_payloads(
    response: Any,
    *,
    collection_key: str,
    expected_count: int,
) -> tuple[Mapping[str, Any], ...]:
    payload = parse_json_object(response_text(response))
    raw_items = payload.get(collection_key)
    if not isinstance(raw_items, list):
        raise ProviderError(f"reasoning batch response {collection_key!r} must be an array")
    if len(raw_items) != int(expected_count):
        raise ProviderError("reasoning batch response count does not match the request")
    if any(not isinstance(raw_item, dict) for raw_item in raw_items):
        raise ProviderError("reasoning batch response entries must be JSON objects")
    return tuple(raw_items)


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
    contract = perspective_contract(perspective)
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
                "assumptions": ["indispensable unstated assumption; empty when none"],
                "falsifier": "condition that would count against this step",
            }
        ],
    }
    return {
        "instructions": (
            "Act only as an OIEC-SR proposer. Call "
            f"{REASONING_OBJECT_TOOL_NAME} exactly once with one object matching the "
            "provided schema. Give concise claims, premises, evidence references, "
            "assumptions, and falsifiers. Do not reveal private chain-of-thought, use "
            "any other tool, approve actions, or claim authority. Use the exact premise ID "
            "'problem' for facts stated in the problem; never emit a problem hash, "
            "dotted problem field, source hash, boundary signature, or dimension "
            "signature as a premise or as evidence. The assumptions array is only for "
            "indispensable propositions not stated by the problem, goal, hypotheses, or "
            "declared evidence semantics. Do not restate a supplied task fact or the "
            "ordinary meaning of the question as an assumption; use an empty array when "
            "no genuinely unstated assumption is required. Follow the supplied perspective "
            "contract as an analysis method, not as evidence. Use its primary inference mode "
            "when semantically valid; otherwise use one declared fallback mode. Do not force "
            "an invalid causal, mathematical, or empirical claim. Make the path materially "
            "different through its inference structure, evidence comparison, assumption test, "
            "or falsifier; paraphrase alone is not an independent path."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": provider_problem_context(problem),
                        "hypotheses": [provider_hypothesis_context(item) for item in hypotheses],
                        "perspective": perspective,
                        "perspective_contract": contract,
                        "inference_modes": sorted(INFERENCE_MODES - {"unspecified"}),
                        "maximum_steps": budget.max_steps_per_path,
                        "premise_contract": {
                            "problem": "validated facts explicitly stated in the problem",
                            "hypothesis": "one exact declared hypothesis_id",
                            "prior_step": "one exact earlier step_id",
                        },
                        "schema": schema,
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [
            reasoning_object_tool(
                tuple(schema),
            )
        ],
    }


def proposer_batch_request(
    *,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    perspectives: Sequence[str],
    budget: ReasoningBudget,
) -> Mapping[str, Any]:
    requested = tuple(str(value) for value in perspectives)
    if len(requested) < 2:
        raise PolicyError("batched proposer request requires at least two perspectives")
    example_request = proposer_request(
        problem=problem,
        hypotheses=hypotheses,
        perspective=requested[0],
        budget=budget,
    )
    example = json.loads(str(example_request["input_items"][0]["content"]))
    return {
        "instructions": (
            "Act only as an OIEC-SR proposer micro-batch. Call "
            f"{REASONING_BATCH_TOOL_NAME} exactly once with a 'candidates' array. "
            "Produce one independently structured "
            "candidate for every requested perspective in the exact request order. "
            "Each array entry is the ordinary proposer object. Do not omit, duplicate, "
            "reorder, merge, compare, or cross-reference candidates. "
            "Apply the supplied proposer contract to every payload. Use the exact premise "
            "ID 'problem' for supplied facts and only declared hypothesis or evidence IDs. "
            "Do not reveal private chain-of-thought, use tools, approve actions, or claim "
            "authority."
        ),
        "input_items": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem": example["problem"],
                        "hypotheses": example["hypotheses"],
                        "inference_modes": example["inference_modes"],
                        "maximum_steps": example["maximum_steps"],
                        "premise_contract": example["premise_contract"],
                        "requests": [
                            {
                                "perspective": perspective,
                                "perspective_contract": perspective_contract(perspective),
                            }
                            for perspective in requested
                        ],
                        "response_schema": {
                            "candidates": [example["schema"]]
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "tools": [reasoning_batch_tool("candidates")],
        "max_output_tokens": PROPOSER_BATCH_MAX_OUTPUT_TOKENS,
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
    problem_aliases = {"problem", "problem.statement", problem.problem_id}
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
                "premises": stable_strings(
                    "problem" if str(item).strip() in problem_aliases else str(item)
                    for item in raw.get("premises", ())
                ),
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
    structure_material = structure_material_from_parts(
        perspective=perspective,
        hypothesis_ids=hypothesis_ids,
        steps=tuple(normalized_steps),
        conclusion=conclusion,
    )
    structure_signature = stable_hash(structure_material)
    path_digest = structure_signature
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
        structure_signature=structure_signature,
        signature=stable_hash(path_payload),
    )


def generate_reasoning_paths(
    *,
    provider: Any,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    budget: ReasoningBudget,
    diversity_filter_enabled: bool = True,
    role_batch_size: int = 1,
) -> tuple[ReasoningPath, ...]:
    perspectives = perspective_names(budget.max_generation_attempts)
    initial_perspectives = perspectives[: budget.candidate_count]
    batch_size = reasoning_role_batch_size(provider, role_batch_size)
    generated: list[tuple[str, Mapping[str, Any]]] = []
    for start in range(0, len(initial_perspectives), batch_size):
        group = initial_perspectives[start : start + batch_size]
        if len(group) == 1:
            response = create_provider_responses(
                provider,
                (
                    proposer_request(
                        problem=problem,
                        hypotheses=hypotheses,
                        perspective=group[0],
                        budget=budget,
                    ),
                ),
                max_responses=budget.max_provider_calls,
            )[0]
            try:
                payloads = (parse_json_object(response_text(response)),)
            except ProviderError as exc:
                provider.record_reasoning_repair(
                    role="proposer",
                    reason=str(exc),
                    item_ids=group,
                )
                continue
        else:
            response = create_provider_responses(
                provider,
                (
                    proposer_batch_request(
                        problem=problem,
                        hypotheses=hypotheses,
                        perspectives=group,
                        budget=budget,
                    ),
                ),
                max_responses=budget.max_provider_calls,
            )[0]
            try:
                payloads = parse_ordered_role_batch_payloads(
                    response,
                    collection_key="candidates",
                    expected_count=len(group),
                )
            except ProviderError as exc:
                provider.record_reasoning_repair(
                    role="proposer",
                    reason=str(exc),
                    item_ids=group,
                )
                continue
        generated.extend(zip(group, payloads))
    paths = []
    for perspective, payload in generated:
        try:
            candidate = parse_reasoning_path(
                payload=payload,
                problem=problem,
                hypotheses=hypotheses,
                perspective=perspective,
                budget=budget,
            )
        except ProviderError as exc:
            provider.record_reasoning_repair(
                role="proposer",
                reason=str(exc),
                item_ids=(perspective,),
            )
            continue
        if not diversity_filter_enabled or not is_structural_duplicate(
            candidate, paths, config=DEFAULT_DIVERSITY_CONFIGURATION
        ):
            paths.append(candidate)
    for perspective in perspectives[budget.candidate_count :]:
        if len(paths) >= budget.candidate_count:
            break
        response = create_provider_responses(
            provider,
            (
                proposer_request(
                    problem=problem,
                    hypotheses=hypotheses,
                    perspective=perspective,
                    budget=budget,
                ),
            ),
            max_responses=budget.max_generation_attempts,
        )[0]
        try:
            candidate = parse_reasoning_path(
                payload=parse_json_object(response_text(response)),
                problem=problem,
                hypotheses=hypotheses,
                perspective=perspective,
                budget=budget,
            )
        except ProviderError as exc:
            provider.record_reasoning_repair(
                role="proposer",
                reason=str(exc),
                item_ids=(perspective,),
            )
            continue
        if not diversity_filter_enabled or not is_structural_duplicate(
            candidate, paths, config=DEFAULT_DIVERSITY_CONFIGURATION
        ):
            paths.append(candidate)
    if len(paths) < budget.candidate_count:
        raise ProviderError(
            "proposer responses did not produce the required materially distinct paths"
        )
    return bind_diversity_scores(
        tuple(paths),
        config=DEFAULT_DIVERSITY_CONFIGURATION,
    )


__all__ = [
    "DEFAULT_PERSPECTIVES",
    "PERSPECTIVE_CONTRACTS",
    "PROPOSER_BATCH_MAX_OUTPUT_TOKENS",
    "REASONING_BATCH_TOOL_NAME",
    "REASONING_OBJECT_TOOL_NAME",
    "BoundedReasoningProvider",
    "create_provider_responses",
    "generate_reasoning_paths",
    "parse_json_object",
    "parse_ordered_role_batch_payloads",
    "parse_reasoning_path",
    "perspective_contract",
    "perspective_names",
    "provider_hypothesis_context",
    "provider_problem_context",
    "proposer_batch_request",
    "proposer_request",
    "reasoning_batch_tool",
    "reasoning_object_tool",
    "reasoning_role_batch_size",
    "response_text",
]
