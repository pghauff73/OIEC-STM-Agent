from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact
from .reasoning import CanonicalReasoningAlgorithm


REASONING_OUTCOME_VERSION = "saa-reasoning-outcome-v1"
FALSIFIER_RESULTS = {"SURVIVED", "TRIGGERED", "UNTESTED"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


def _pairs(values: Mapping[str, bool] | Sequence[tuple[str, bool]]) -> Tuple[tuple[str, bool], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, bool] = {}
    for key, value in items:
        label = _text(key)
        if not label:
            raise EGCFError("reasoning outcome invariant labels must be non-empty")
        if label in normalized:
            raise EGCFError("duplicate reasoning outcome invariant result")
        normalized[label] = bool(value)
    return tuple(sorted(normalized.items()))


def _falsifier_pairs(
    values: Mapping[str, str] | Sequence[tuple[str, str]],
) -> Tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, str] = {}
    for key, value in items:
        label = _text(key)
        result = str(value).strip().upper()
        if not label:
            raise EGCFError("reasoning falsifier labels must be non-empty")
        if result not in FALSIFIER_RESULTS:
            raise EGCFError(f"unsupported reasoning falsifier result: {value!r}")
        if label in normalized:
            raise EGCFError("duplicate reasoning falsifier result")
        normalized[label] = result
    return tuple(sorted(normalized.items()))


def reasoning_evidence_requirements(algorithm: CanonicalReasoningAlgorithm) -> Tuple[str, ...]:
    values: set[str] = set()
    for node in algorithm.canonical_nodes:
        values.update(_text(value) for value in node.get("evidence_requirements", ()) if _text(value))
    return tuple(sorted(values))


def reasoning_falsifiers(algorithm: CanonicalReasoningAlgorithm) -> Tuple[str, ...]:
    values: set[str] = set()
    for node in algorithm.canonical_nodes:
        values.update(_text(value) for value in node.get("falsifiers", ()) if _text(value))
    return tuple(sorted(values))


@dataclass(frozen=True)
class ReasoningExecutionOutcome:
    schema_version: int
    outcome_version: str
    canonical_reasoning_signature: str
    execution_id: str
    observed_output_semantics: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    invariant_results: Tuple[tuple[str, bool], ...]
    falsifier_results: Tuple[tuple[str, str], ...]
    termination_satisfied: bool
    steps_used: int
    execution_success: bool
    independent_review: bool
    outcome_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome_version": self.outcome_version,
            "canonical_reasoning_signature": self.canonical_reasoning_signature,
            "execution_id": self.execution_id,
            "observed_output_semantics": list(self.observed_output_semantics),
            "evidence_ids": list(self.evidence_ids),
            "invariant_results": [[name, value] for name, value in self.invariant_results],
            "falsifier_results": [[name, value] for name, value in self.falsifier_results],
            "termination_satisfied": self.termination_satisfied,
            "steps_used": self.steps_used,
            "execution_success": self.execution_success,
            "independent_review": self.independent_review,
            "outcome_signature": self.outcome_signature,
        }


@dataclass(frozen=True)
class ReasoningOutcomeQualification:
    schema_version: int
    outcome_version: str
    canonical_reasoning_signature: str
    outcome_signature: str
    status: str
    evidence_requirement_coverage_bp: int
    grounded_evidence_ids: Tuple[str, ...]
    independence_groups: Tuple[str, ...]
    invariant_eligible: bool
    falsifier_eligible: bool
    termination_eligible: bool
    output_contract_eligible: bool
    canonical_reuse_eligible: bool
    qualification_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome_version": self.outcome_version,
            "canonical_reasoning_signature": self.canonical_reasoning_signature,
            "outcome_signature": self.outcome_signature,
            "status": self.status,
            "evidence_requirement_coverage_bp": self.evidence_requirement_coverage_bp,
            "grounded_evidence_ids": list(self.grounded_evidence_ids),
            "independence_groups": list(self.independence_groups),
            "invariant_eligible": self.invariant_eligible,
            "falsifier_eligible": self.falsifier_eligible,
            "termination_eligible": self.termination_eligible,
            "output_contract_eligible": self.output_contract_eligible,
            "canonical_reuse_eligible": self.canonical_reuse_eligible,
            "qualification_signature": self.qualification_signature,
            "warnings": list(self.warnings),
        }


def make_reasoning_execution_outcome(
    algorithm: CanonicalReasoningAlgorithm,
    *,
    execution_id: str,
    observed_output_semantics: Sequence[str],
    evidence_ids: Sequence[str],
    invariant_results: Mapping[str, bool] | Sequence[tuple[str, bool]],
    falsifier_results: Mapping[str, str] | Sequence[tuple[str, str]] = (),
    termination_satisfied: bool,
    steps_used: int,
    execution_success: bool,
    independent_review: bool,
) -> ReasoningExecutionOutcome:
    if not isinstance(algorithm, CanonicalReasoningAlgorithm):
        raise EGCFError("SAA-8.5 requires CanonicalReasoningAlgorithm")
    execution = str(execution_id).strip()
    if not execution:
        raise EGCFError("reasoning outcome execution_id must be non-empty")
    if steps_used < 0:
        raise EGCFError("reasoning outcome steps_used cannot be negative")
    outputs = _texts(observed_output_semantics)
    evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    invariants = _pairs(invariant_results)
    falsifiers = _falsifier_pairs(falsifier_results)
    payload = {
        "schema_version": 1,
        "outcome_version": REASONING_OUTCOME_VERSION,
        "canonical_reasoning_signature": algorithm.canonical_reasoning_signature,
        "execution_id": execution,
        "observed_output_semantics": list(outputs),
        "evidence_ids": list(evidence),
        "invariant_results": [[name, value] for name, value in invariants],
        "falsifier_results": [[name, value] for name, value in falsifiers],
        "termination_satisfied": bool(termination_satisfied),
        "steps_used": int(steps_used),
        "execution_success": bool(execution_success),
        "independent_review": bool(independent_review),
    }
    return ReasoningExecutionOutcome(
        schema_version=1,
        outcome_version=REASONING_OUTCOME_VERSION,
        canonical_reasoning_signature=algorithm.canonical_reasoning_signature,
        execution_id=execution,
        observed_output_semantics=outputs,
        evidence_ids=evidence,
        invariant_results=invariants,
        falsifier_results=falsifiers,
        termination_satisfied=bool(termination_satisfied),
        steps_used=int(steps_used),
        execution_success=bool(execution_success),
        independent_review=bool(independent_review),
        outcome_signature=sha256_json(payload),
    )


def _grounded_evidence(egcf_store: Any, evidence_id: str) -> EvidenceArtifact:
    try:
        record = egcf_store.get(evidence_id)
    except Exception as exc:
        raise EGCFError(f"reasoning outcome evidence is not registered: {evidence_id}") from exc
    if not isinstance(record, EvidenceArtifact):
        raise EGCFError("reasoning outcome evidence must reference EvidenceArtifact")
    if record.success is not True or record.simulated:
        raise EGCFError("reasoning outcome evidence must be successful and non-simulated")
    if not record.producer.startswith(("deterministic-", "human-")):
        raise EGCFError("reasoning outcome evidence must be deterministic or human-grounded")
    if _text(record.method) in {"reported", "model-claimed", "model-generated-claim"}:
        raise EGCFError("reported/model-claimed evidence cannot qualify reasoning outcomes")
    return record


def qualify_reasoning_outcome(
    egcf_store: Any,
    algorithm: CanonicalReasoningAlgorithm,
    outcome: ReasoningExecutionOutcome,
) -> ReasoningOutcomeQualification:
    if not isinstance(algorithm, CanonicalReasoningAlgorithm):
        raise EGCFError("SAA-8.5 requires CanonicalReasoningAlgorithm")
    if not isinstance(outcome, ReasoningExecutionOutcome):
        raise EGCFError("SAA-8.5 requires ReasoningExecutionOutcome")
    if outcome.canonical_reasoning_signature != algorithm.canonical_reasoning_signature:
        raise EGCFError("reasoning outcome belongs to a different canonical algorithm")

    expected_outputs = tuple(sorted(algorithm.output_semantics))
    output_eligible = outcome.observed_output_semantics == expected_outputs

    expected_invariants = set(algorithm.invariants)
    invariant_map = dict(outcome.invariant_results)
    invariant_eligible = set(invariant_map) == expected_invariants and all(invariant_map.values())

    expected_falsifiers = set(reasoning_falsifiers(algorithm))
    falsifier_map = dict(outcome.falsifier_results)
    falsifier_eligible = (
        set(falsifier_map) == expected_falsifiers
        and all(value == "SURVIVED" for value in falsifier_map.values())
    )

    max_steps = int(algorithm.termination.get("max_steps", 0))
    termination_eligible = (
        outcome.termination_satisfied
        and outcome.execution_success
        and 0 <= outcome.steps_used <= max_steps
    )

    requirements = set(reasoning_evidence_requirements(algorithm))
    grounded: list[str] = []
    covered: set[str] = set()
    groups: set[str] = set()
    evidence_error = False
    for evidence_id in outcome.evidence_ids:
        try:
            record = _grounded_evidence(egcf_store, evidence_id)
        except EGCFError:
            evidence_error = True
            continue
        grounded.append(evidence_id)
        covered.update(_text(value) for value in record.requirement_ids if _text(value))
        if record.independence_group:
            groups.add(_text(record.independence_group))

    if requirements:
        coverage_bp = (10000 * len(requirements & covered)) // len(requirements)
    else:
        coverage_bp = 10000
    evidence_eligible = (
        not evidence_error
        and bool(grounded)
        and coverage_bp == 10000
        and bool(groups)
    )

    exact_canonical = algorithm.canonicalization_strength == "EXACT_BOUNDED_GRAPH_CANONICALIZATION"
    eligible = all(
        (
            exact_canonical,
            output_eligible,
            invariant_eligible,
            falsifier_eligible,
            termination_eligible,
            evidence_eligible,
            outcome.independent_review,
        )
    )

    if not exact_canonical:
        status = "UNQUALIFIED_REASONING_CANONICALIZATION"
    elif not output_eligible:
        status = "UNQUALIFIED_REASONING_OUTPUT_CONTRACT"
    elif not invariant_eligible:
        status = "UNQUALIFIED_REASONING_INVARIANT_FAILURE"
    elif not falsifier_eligible:
        status = "UNQUALIFIED_REASONING_FALSIFIER"
    elif not termination_eligible:
        status = "UNQUALIFIED_REASONING_TERMINATION"
    elif not evidence_eligible:
        status = "UNQUALIFIED_REASONING_EVIDENCE"
    elif not outcome.independent_review:
        status = "UNQUALIFIED_REASONING_INDEPENDENT_REVIEW"
    else:
        status = "QUALIFIED_REASONING_OUTCOME"

    warnings: list[str] = []
    if not eligible:
        warnings.append(
            "A completed reasoning execution is not reusable canonical evidence until semantics, invariants, falsifiers, termination and grounded evidence all qualify."
        )
    payload = {
        "schema_version": 1,
        "outcome_version": REASONING_OUTCOME_VERSION,
        "canonical_reasoning_signature": algorithm.canonical_reasoning_signature,
        "outcome_signature": outcome.outcome_signature,
        "status": status,
        "coverage_bp": coverage_bp,
        "grounded_evidence_ids": sorted(grounded),
        "independence_groups": sorted(groups),
        "invariant_eligible": invariant_eligible,
        "falsifier_eligible": falsifier_eligible,
        "termination_eligible": termination_eligible,
        "output_contract_eligible": output_eligible,
        "canonical_reuse_eligible": eligible,
    }
    return ReasoningOutcomeQualification(
        schema_version=1,
        outcome_version=REASONING_OUTCOME_VERSION,
        canonical_reasoning_signature=algorithm.canonical_reasoning_signature,
        outcome_signature=outcome.outcome_signature,
        status=status,
        evidence_requirement_coverage_bp=coverage_bp,
        grounded_evidence_ids=tuple(sorted(grounded)),
        independence_groups=tuple(sorted(groups)),
        invariant_eligible=invariant_eligible,
        falsifier_eligible=falsifier_eligible,
        termination_eligible=termination_eligible,
        output_contract_eligible=output_eligible,
        canonical_reuse_eligible=eligible,
        qualification_signature=sha256_json(payload),
        warnings=tuple(warnings),
    )
