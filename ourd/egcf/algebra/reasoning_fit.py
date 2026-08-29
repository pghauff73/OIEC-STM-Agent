from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .reasoning import CanonicalReasoningAlgorithm
from .reasoning_outcome import reasoning_evidence_requirements


REASONING_FIT_VERSION = "saa-reasoning-fit-v1"
MAX_REASONING_RETRIEVAL_RESULTS = 64


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


@dataclass(frozen=True)
class ReasoningTaskRequirements:
    available_inputs: Tuple[str, ...]
    desired_outputs: Tuple[str, ...]
    required_applicability: Tuple[str, ...] = ()
    required_invariants: Tuple[str, ...] = ()
    available_evidence_requirements: Tuple[str, ...] = ()
    max_steps: int = 1024

    def canonical(self) -> "ReasoningTaskRequirements":
        if self.max_steps < 1 or self.max_steps > 1024:
            raise EGCFError("reasoning task max_steps outside supported bounded range")
        return ReasoningTaskRequirements(
            available_inputs=_texts(self.available_inputs),
            desired_outputs=_texts(self.desired_outputs),
            required_applicability=_texts(self.required_applicability),
            required_invariants=_texts(self.required_invariants),
            available_evidence_requirements=_texts(self.available_evidence_requirements),
            max_steps=int(self.max_steps),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "available_inputs": list(self.available_inputs),
            "desired_outputs": list(self.desired_outputs),
            "required_applicability": list(self.required_applicability),
            "required_invariants": list(self.required_invariants),
            "available_evidence_requirements": list(self.available_evidence_requirements),
            "max_steps": self.max_steps,
        }


@dataclass(frozen=True)
class ReasoningFitAssessment:
    reasoning_id: str
    canonical_reasoning_signature: str
    status: str
    fit_score_bp: int
    input_fit_bp: int
    output_fit_bp: int
    applicability_fit_bp: int
    invariant_fit_bp: int
    evidence_fit_bp: int
    termination_fit_bp: int
    blocking_gaps: Tuple[str, ...]
    adaptation_gaps: Tuple[str, ...]
    fit_signature: str

    @property
    def eligible(self) -> bool:
        return not self.blocking_gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning_id": self.reasoning_id,
            "canonical_reasoning_signature": self.canonical_reasoning_signature,
            "status": self.status,
            "fit_score_bp": self.fit_score_bp,
            "input_fit_bp": self.input_fit_bp,
            "output_fit_bp": self.output_fit_bp,
            "applicability_fit_bp": self.applicability_fit_bp,
            "invariant_fit_bp": self.invariant_fit_bp,
            "evidence_fit_bp": self.evidence_fit_bp,
            "termination_fit_bp": self.termination_fit_bp,
            "blocking_gaps": list(self.blocking_gaps),
            "adaptation_gaps": list(self.adaptation_gaps),
            "fit_signature": self.fit_signature,
            "eligible": self.eligible,
        }


@dataclass(frozen=True)
class ReasoningRetrievalResult:
    schema_version: int
    fit_version: str
    requirements_signature: str
    candidates: Tuple[ReasoningFitAssessment, ...]
    selected_reasoning_id: str | None
    selected_fit_score_bp: int
    search_scope: str
    result_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fit_version": self.fit_version,
            "requirements_signature": self.requirements_signature,
            "candidates": [item.to_dict() for item in self.candidates],
            "selected_reasoning_id": self.selected_reasoning_id,
            "selected_fit_score_bp": self.selected_fit_score_bp,
            "search_scope": self.search_scope,
            "result_signature": self.result_signature,
        }


def _coverage(required: set[str], available: set[str]) -> int:
    if not required:
        return 10000
    return (10000 * len(required & available)) // len(required)


def evaluate_reasoning_fit(
    reasoning_id: str,
    algorithm: CanonicalReasoningAlgorithm,
    requirements: ReasoningTaskRequirements,
) -> ReasoningFitAssessment:
    if not isinstance(algorithm, CanonicalReasoningAlgorithm):
        raise EGCFError("SAA-8.4 fit evaluation requires CanonicalReasoningAlgorithm")
    task = requirements.canonical()
    available_inputs = set(task.available_inputs)
    desired_outputs = set(task.desired_outputs)
    required_applicability = set(task.required_applicability)
    required_invariants = set(task.required_invariants)
    available_evidence = set(task.available_evidence_requirements)

    algorithm_inputs = set(algorithm.input_semantics)
    algorithm_outputs = set(algorithm.output_semantics)
    applicability = set(algorithm.applicability)
    invariants = set(algorithm.invariants)
    evidence_requirements = set(reasoning_evidence_requirements(algorithm))
    algorithm_max_steps = int(algorithm.termination.get("max_steps", 0))

    input_fit = _coverage(algorithm_inputs, available_inputs)
    output_fit = _coverage(desired_outputs, algorithm_outputs)
    applicability_fit = _coverage(required_applicability, applicability)
    invariant_fit = _coverage(required_invariants, invariants)
    evidence_fit = _coverage(evidence_requirements, available_evidence)
    termination_fit = 10000 if algorithm_max_steps <= task.max_steps else max(
        0, (10000 * task.max_steps) // max(1, algorithm_max_steps)
    )

    blockers: list[str] = []
    adaptation: list[str] = []
    missing_inputs = sorted(algorithm_inputs - available_inputs)
    missing_outputs = sorted(desired_outputs - algorithm_outputs)
    missing_applicability = sorted(required_applicability - applicability)
    missing_invariants = sorted(required_invariants - invariants)
    missing_evidence = sorted(evidence_requirements - available_evidence)
    if missing_inputs:
        blockers.append("missing required inputs: " + ", ".join(missing_inputs))
    if missing_outputs:
        blockers.append("missing desired outputs: " + ", ".join(missing_outputs))
    if missing_applicability:
        blockers.append("applicability mismatch: " + ", ".join(missing_applicability))
    if missing_invariants:
        blockers.append("required invariants absent: " + ", ".join(missing_invariants))
    if missing_evidence:
        blockers.append("evidence capability unavailable: " + ", ".join(missing_evidence))
    if algorithm_max_steps > task.max_steps:
        blockers.append(
            f"termination budget {algorithm_max_steps} exceeds task budget {task.max_steps}"
        )

    extra_outputs = sorted(algorithm_outputs - desired_outputs) if desired_outputs else []
    if extra_outputs:
        adaptation.append("algorithm produces additional outputs: " + ", ".join(extra_outputs))
    extra_inputs = sorted(available_inputs - algorithm_inputs)
    if extra_inputs:
        adaptation.append("task has unused available inputs: " + ", ".join(extra_inputs))

    score = (
        20 * input_fit
        + 25 * output_fit
        + 15 * applicability_fit
        + 15 * invariant_fit
        + 10 * evidence_fit
        + 15 * termination_fit
    ) // 100
    if blockers:
        status = "INELIGIBLE_REASONING_FIT"
    elif score >= 9000:
        status = "GOOD_REASONING_FIT"
    elif score >= 6500:
        status = "PARTIAL_REASONING_FIT"
    else:
        status = "POOR_REASONING_FIT"
    payload = {
        "version": REASONING_FIT_VERSION,
        "reasoning_id": reasoning_id,
        "algorithm_signature": algorithm.canonical_reasoning_signature,
        "requirements": task.to_dict(),
        "components": {
            "input": input_fit,
            "output": output_fit,
            "applicability": applicability_fit,
            "invariant": invariant_fit,
            "evidence": evidence_fit,
            "termination": termination_fit,
        },
        "score": score,
        "blocking_gaps": blockers,
        "adaptation_gaps": adaptation,
    }
    return ReasoningFitAssessment(
        reasoning_id=str(reasoning_id),
        canonical_reasoning_signature=algorithm.canonical_reasoning_signature,
        status=status,
        fit_score_bp=score,
        input_fit_bp=input_fit,
        output_fit_bp=output_fit,
        applicability_fit_bp=applicability_fit,
        invariant_fit_bp=invariant_fit,
        evidence_fit_bp=evidence_fit,
        termination_fit_bp=termination_fit,
        blocking_gaps=tuple(blockers),
        adaptation_gaps=tuple(adaptation),
        fit_signature=sha256_json(payload),
    )


def retrieve_reasoning_algorithms(
    store: Any,
    requirements: ReasoningTaskRequirements,
    *,
    limit: int = 10,
    include_ineligible: bool = False,
) -> ReasoningRetrievalResult:
    if limit < 1 or limit > MAX_REASONING_RETRIEVAL_RESULTS:
        raise EGCFError("reasoning retrieval limit outside supported range")
    if not hasattr(store, "list") or not hasattr(store, "load_algorithm"):
        raise EGCFError("SAA-8.4 retrieval requires CanonicalReasoningStore")
    task = requirements.canonical()
    requirements_signature = sha256_json(
        {"version": REASONING_FIT_VERSION, "requirements": task.to_dict()}
    )
    assessments: list[ReasoningFitAssessment] = []
    for item in store.list():
        reasoning_id = item["reasoning_id"]
        algorithm = store.load_algorithm(reasoning_id)
        assessment = evaluate_reasoning_fit(reasoning_id, algorithm, task)
        if include_ineligible or assessment.eligible:
            assessments.append(assessment)
    assessments.sort(
        key=lambda item: (
            0 if item.eligible else 1,
            -item.fit_score_bp,
            item.reasoning_id,
        )
    )
    candidates = tuple(assessments[:limit])
    selected = next((item for item in candidates if item.eligible), None)
    payload = {
        "version": REASONING_FIT_VERSION,
        "requirements_signature": requirements_signature,
        "candidate_signatures": [item.fit_signature for item in candidates],
        "selected_reasoning_id": selected.reasoning_id if selected else None,
        "selected_fit_score_bp": selected.fit_score_bp if selected else 0,
        "search_scope": "QUALIFIED_CANONICAL_REASONING_STORE_ONLY",
    }
    return ReasoningRetrievalResult(
        schema_version=1,
        fit_version=REASONING_FIT_VERSION,
        requirements_signature=requirements_signature,
        candidates=candidates,
        selected_reasoning_id=selected.reasoning_id if selected else None,
        selected_fit_score_bp=selected.fit_score_bp if selected else 0,
        search_scope="QUALIFIED_CANONICAL_REASONING_STORE_ONLY",
        result_signature=sha256_json(payload),
    )
