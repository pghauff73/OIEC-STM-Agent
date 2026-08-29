from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact


ALGORITHM_EXPERIMENT_VERSION = "saa-controlled-algorithm-experiment-v1"
MAX_EXPERIMENT_METRICS = 16
MAX_EXPERIMENT_TRIALS = 10000
METRIC_DIRECTIONS = {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _fraction(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact {label}: {value!r}") from exc


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


@dataclass(frozen=True)
class ExperimentMetricSpec:
    name: str
    direction: str
    minimum_material_effect: Fraction = Fraction(0)

    def canonical(self) -> "ExperimentMetricSpec":
        name = _text(self.name)
        if not name:
            raise EGCFError("SAA-11.2 metric name is required")
        direction = str(self.direction).strip().upper()
        if direction not in METRIC_DIRECTIONS:
            raise EGCFError(f"unsupported SAA-11.2 metric direction: {direction}")
        threshold = _fraction(self.minimum_material_effect, "minimum material effect")
        if threshold < 0:
            raise EGCFError("minimum material effect cannot be negative")
        return ExperimentMetricSpec(name, direction, threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "minimum_material_effect": _fraction_payload(self.minimum_material_effect),
        }


@dataclass(frozen=True)
class AlgorithmABExperimentDesign:
    schema_version: int
    experiment_version: str
    baseline_ref: str
    candidate_ref: str
    context_signature: str
    metrics: Tuple[ExperimentMetricSpec, ...]
    required_invariants: Tuple[str, ...]
    evidence_requirements: Tuple[str, ...]
    minimum_trials: int
    paired_context: bool
    design_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_version": self.experiment_version,
            "baseline_ref": self.baseline_ref,
            "candidate_ref": self.candidate_ref,
            "context_signature": self.context_signature,
            "metrics": [item.to_dict() for item in self.metrics],
            "required_invariants": list(self.required_invariants),
            "evidence_requirements": list(self.evidence_requirements),
            "minimum_trials": self.minimum_trials,
            "paired_context": self.paired_context,
            "design_signature": self.design_signature,
        }


@dataclass(frozen=True)
class AlgorithmVariantObservation:
    schema_version: int
    experiment_version: str
    design_signature: str
    variant_ref: str
    metric_values: Tuple[Tuple[str, Fraction], ...]
    evidence_ids: Tuple[str, ...]
    invariant_results: Tuple[Tuple[str, bool], ...]
    trial_count: int
    execution_success: bool
    observation_signature: str

    def metrics_dict(self) -> dict[str, Fraction]:
        return dict(self.metric_values)

    def invariants_dict(self) -> dict[str, bool]:
        return dict(self.invariant_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_version": self.experiment_version,
            "design_signature": self.design_signature,
            "variant_ref": self.variant_ref,
            "metric_values": {name: _fraction_payload(value) for name, value in self.metric_values},
            "evidence_ids": list(self.evidence_ids),
            "invariant_results": {name: result for name, result in self.invariant_results},
            "trial_count": self.trial_count,
            "execution_success": self.execution_success,
            "observation_signature": self.observation_signature,
        }


@dataclass(frozen=True)
class ExperimentMetricComparison:
    metric_name: str
    direction: str
    baseline_value: Fraction
    candidate_value: Fraction
    signed_improvement: Fraction
    minimum_material_effect: Fraction
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "direction": self.direction,
            "baseline_value": _fraction_payload(self.baseline_value),
            "candidate_value": _fraction_payload(self.candidate_value),
            "signed_improvement": _fraction_payload(self.signed_improvement),
            "minimum_material_effect": _fraction_payload(self.minimum_material_effect),
            "status": self.status,
        }


@dataclass(frozen=True)
class AlgorithmABExperimentResult:
    schema_version: int
    experiment_version: str
    design_signature: str
    baseline_observation_signature: str
    candidate_observation_signature: str
    metric_comparisons: Tuple[ExperimentMetricComparison, ...]
    grounded_evidence_ids: Tuple[str, ...]
    independence_groups: Tuple[str, ...]
    evidence_requirement_coverage_bp: int
    invariant_gate_passed: bool
    independent_review: bool
    status: str
    candidate_improvement_qualified: bool
    qualification_required_before_canonical_reuse: bool
    result_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_version": self.experiment_version,
            "design_signature": self.design_signature,
            "baseline_observation_signature": self.baseline_observation_signature,
            "candidate_observation_signature": self.candidate_observation_signature,
            "metric_comparisons": [item.to_dict() for item in self.metric_comparisons],
            "grounded_evidence_ids": list(self.grounded_evidence_ids),
            "independence_groups": list(self.independence_groups),
            "evidence_requirement_coverage_bp": self.evidence_requirement_coverage_bp,
            "invariant_gate_passed": self.invariant_gate_passed,
            "independent_review": self.independent_review,
            "status": self.status,
            "candidate_improvement_qualified": self.candidate_improvement_qualified,
            "qualification_required_before_canonical_reuse": self.qualification_required_before_canonical_reuse,
            "result_signature": self.result_signature,
        }


def make_ab_experiment_design(
    *,
    baseline_ref: str,
    candidate_ref: str,
    context_signature: str,
    metrics: Sequence[ExperimentMetricSpec],
    required_invariants: Sequence[str] = (),
    evidence_requirements: Sequence[str] = (),
    minimum_trials: int = 1,
    paired_context: bool = True,
) -> AlgorithmABExperimentDesign:
    baseline = str(baseline_ref).strip()
    candidate = str(candidate_ref).strip()
    if not baseline or not candidate or baseline == candidate:
        raise EGCFError("SAA-11.2 A/B experiment requires distinct baseline and candidate refs")
    context = str(context_signature).strip().lower()
    if len(context) != 64 or any(character not in "0123456789abcdef" for character in context):
        raise EGCFError("SAA-11.2 context signature must be SHA-256")
    canonical_metrics = tuple(item.canonical() for item in metrics)
    if not canonical_metrics or len(canonical_metrics) > MAX_EXPERIMENT_METRICS:
        raise EGCFError("SAA-11.2 metric count outside bounded range")
    names = [item.name for item in canonical_metrics]
    if len(set(names)) != len(names):
        raise EGCFError("SAA-11.2 metric names must be unique")
    trials = int(minimum_trials)
    if trials < 1 or trials > MAX_EXPERIMENT_TRIALS:
        raise EGCFError("SAA-11.2 minimum trial count outside bounded range")
    invariants = tuple(sorted({_text(value) for value in required_invariants if _text(value)}))
    requirements = tuple(sorted({_text(value) for value in evidence_requirements if _text(value)}))
    payload = {
        "version": ALGORITHM_EXPERIMENT_VERSION,
        "baseline_ref": baseline,
        "candidate_ref": candidate,
        "context_signature": context,
        "metrics": [item.to_dict() for item in canonical_metrics],
        "required_invariants": list(invariants),
        "evidence_requirements": list(requirements),
        "minimum_trials": trials,
        "paired_context": bool(paired_context),
    }
    return AlgorithmABExperimentDesign(
        schema_version=1,
        experiment_version=ALGORITHM_EXPERIMENT_VERSION,
        baseline_ref=baseline,
        candidate_ref=candidate,
        context_signature=context,
        metrics=canonical_metrics,
        required_invariants=invariants,
        evidence_requirements=requirements,
        minimum_trials=trials,
        paired_context=bool(paired_context),
        design_signature=sha256_json(payload),
    )


def make_variant_observation(
    design: AlgorithmABExperimentDesign,
    *,
    variant_ref: str,
    metric_values: Mapping[str, Any],
    evidence_ids: Sequence[str],
    invariant_results: Mapping[str, bool],
    trial_count: int,
    execution_success: bool,
) -> AlgorithmVariantObservation:
    if not isinstance(design, AlgorithmABExperimentDesign):
        raise EGCFError("SAA-11.2 observation requires AlgorithmABExperimentDesign")
    variant = str(variant_ref).strip()
    if variant not in {design.baseline_ref, design.candidate_ref}:
        raise EGCFError("SAA-11.2 observation variant is not part of experiment design")
    canonical_metrics: list[tuple[str, Fraction]] = []
    supplied = {_text(name): value for name, value in metric_values.items()}
    expected_names = {item.name for item in design.metrics}
    if set(supplied) != expected_names:
        raise EGCFError("SAA-11.2 observation must provide every designed metric and no extras")
    for metric in design.metrics:
        canonical_metrics.append((metric.name, _fraction(supplied[metric.name], f"metric {metric.name}")))
    invariants = tuple(sorted((_text(name), bool(value)) for name, value in invariant_results.items()))
    required_invariants = set(design.required_invariants)
    if set(name for name, _ in invariants) != required_invariants:
        raise EGCFError("SAA-11.2 observation must report every required invariant and no extras")
    evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    if not evidence:
        raise EGCFError("SAA-11.2 observation requires evidence references")
    trials = int(trial_count)
    if trials < design.minimum_trials or trials > MAX_EXPERIMENT_TRIALS:
        raise EGCFError("SAA-11.2 observation trial count violates design bounds")
    payload = {
        "version": ALGORITHM_EXPERIMENT_VERSION,
        "design_signature": design.design_signature,
        "variant_ref": variant,
        "metric_values": {name: _fraction_payload(value) for name, value in canonical_metrics},
        "evidence_ids": list(evidence),
        "invariant_results": {name: value for name, value in invariants},
        "trial_count": trials,
        "execution_success": bool(execution_success),
    }
    return AlgorithmVariantObservation(
        schema_version=1,
        experiment_version=ALGORITHM_EXPERIMENT_VERSION,
        design_signature=design.design_signature,
        variant_ref=variant,
        metric_values=tuple(canonical_metrics),
        evidence_ids=evidence,
        invariant_results=invariants,
        trial_count=trials,
        execution_success=bool(execution_success),
        observation_signature=sha256_json(payload),
    )


def _grounded_evidence(store: Any, evidence_ids: Sequence[str], requirements: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    grounded: list[str] = []
    groups: set[str] = set()
    covered: set[str] = set()
    required = set(requirements)
    for evidence_id in evidence_ids:
        try:
            record = store.get(evidence_id)
        except Exception as exc:
            raise EGCFError(f"SAA-11.2 evidence is not registered: {evidence_id}") from exc
        if not isinstance(record, EvidenceArtifact):
            raise EGCFError("SAA-11.2 evidence ID does not reference EvidenceArtifact")
        if record.success is not True or record.simulated:
            raise EGCFError("SAA-11.2 evidence must be successful and non-simulated")
        if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
            raise EGCFError("SAA-11.2 evidence must be deterministic/human grounded and not reported-only")
        grounded.append(evidence_id)
        if record.independence_group:
            groups.add(record.independence_group)
        covered.update(_text(value) for value in record.requirement_ids)
    coverage = 10000 if not required else (10000 * len(required & covered)) // len(required)
    return tuple(sorted(set(grounded))), tuple(sorted(groups)), coverage


def qualify_ab_experiment(
    store: Any,
    design: AlgorithmABExperimentDesign,
    baseline: AlgorithmVariantObservation,
    candidate: AlgorithmVariantObservation,
    *,
    independent_review: bool,
) -> AlgorithmABExperimentResult:
    if baseline.design_signature != design.design_signature or candidate.design_signature != design.design_signature:
        raise EGCFError("SAA-11.2 observations belong to a different experiment design")
    if baseline.variant_ref != design.baseline_ref or candidate.variant_ref != design.candidate_ref:
        raise EGCFError("SAA-11.2 baseline/candidate observations are swapped or mismatched")
    if not baseline.execution_success or not candidate.execution_success:
        status = "EXPERIMENT_EXECUTION_FAILED"
    else:
        status = ""
    grounded_a, groups_a, coverage_a = _grounded_evidence(store, baseline.evidence_ids, design.evidence_requirements)
    grounded_b, groups_b, coverage_b = _grounded_evidence(store, candidate.evidence_ids, design.evidence_requirements)
    evidence_ids = tuple(sorted(set((*grounded_a, *grounded_b))))
    groups = tuple(sorted(set((*groups_a, *groups_b))))
    coverage = min(coverage_a, coverage_b)
    baseline_invariants = baseline.invariants_dict()
    candidate_invariants = candidate.invariants_dict()
    invariant_gate = all(
        baseline_invariants.get(name) is True and candidate_invariants.get(name) is True
        for name in design.required_invariants
    )
    baseline_metrics = baseline.metrics_dict()
    candidate_metrics = candidate.metrics_dict()
    comparisons: list[ExperimentMetricComparison] = []
    improved = 0
    regressed = 0
    for metric in design.metrics:
        a = baseline_metrics[metric.name]
        b = candidate_metrics[metric.name]
        signed = b - a if metric.direction == "HIGHER_IS_BETTER" else a - b
        threshold = metric.minimum_material_effect
        if signed > 0 and signed >= threshold:
            metric_status = "MATERIAL_IMPROVEMENT"
            improved += 1
        elif signed < 0 and -signed >= threshold:
            metric_status = "MATERIAL_REGRESSION"
            regressed += 1
        else:
            metric_status = "NO_MATERIAL_CHANGE"
        comparisons.append(
            ExperimentMetricComparison(
                metric_name=metric.name,
                direction=metric.direction,
                baseline_value=a,
                candidate_value=b,
                signed_improvement=signed,
                minimum_material_effect=threshold,
                status=metric_status,
            )
        )
    if not status:
        if coverage != 10000:
            status = "EXPERIMENT_EVIDENCE_INCOMPLETE"
        elif not invariant_gate:
            status = "EXPERIMENT_INVARIANT_VIOLATION"
        elif not independent_review:
            status = "EXPERIMENT_REVIEW_REQUIRED"
        elif improved and regressed:
            status = "EXPERIMENT_TRADEOFF_UNRESOLVED"
        elif regressed:
            status = "CANDIDATE_REGRESSION_DETECTED"
        elif improved:
            status = "CANDIDATE_IMPROVEMENT_QUALIFIED"
        else:
            status = "NO_MATERIAL_IMPROVEMENT"
    qualified = status == "CANDIDATE_IMPROVEMENT_QUALIFIED"
    payload = {
        "version": ALGORITHM_EXPERIMENT_VERSION,
        "design_signature": design.design_signature,
        "baseline_observation_signature": baseline.observation_signature,
        "candidate_observation_signature": candidate.observation_signature,
        "comparisons": [item.to_dict() for item in comparisons],
        "grounded_evidence_ids": list(evidence_ids),
        "independence_groups": list(groups),
        "evidence_requirement_coverage_bp": coverage,
        "invariant_gate_passed": invariant_gate,
        "independent_review": bool(independent_review),
        "status": status,
        "candidate_improvement_qualified": qualified,
    }
    return AlgorithmABExperimentResult(
        schema_version=1,
        experiment_version=ALGORITHM_EXPERIMENT_VERSION,
        design_signature=design.design_signature,
        baseline_observation_signature=baseline.observation_signature,
        candidate_observation_signature=candidate.observation_signature,
        metric_comparisons=tuple(comparisons),
        grounded_evidence_ids=evidence_ids,
        independence_groups=groups,
        evidence_requirement_coverage_bp=coverage,
        invariant_gate_passed=invariant_gate,
        independent_review=bool(independent_review),
        status=status,
        candidate_improvement_qualified=qualified,
        qualification_required_before_canonical_reuse=True,
        result_signature=sha256_json(payload),
    )
