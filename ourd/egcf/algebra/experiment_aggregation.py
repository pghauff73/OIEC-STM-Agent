from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .algorithm_experiment import AlgorithmABExperimentResult


EXPERIMENT_AGGREGATION_VERSION = "saa-repeated-experiment-aggregation-v1"
MAX_AGGREGATED_EXPERIMENTS = 64


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


@dataclass(frozen=True)
class AggregatedMetricEvidence:
    metric_name: str
    direction: str
    experiment_count: int
    material_improvement_count: int
    material_regression_count: int
    no_material_change_count: int
    mean_signed_improvement: Fraction
    minimum_signed_improvement: Fraction
    maximum_signed_improvement: Fraction

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "direction": self.direction,
            "experiment_count": self.experiment_count,
            "material_improvement_count": self.material_improvement_count,
            "material_regression_count": self.material_regression_count,
            "no_material_change_count": self.no_material_change_count,
            "mean_signed_improvement": _fraction_payload(self.mean_signed_improvement),
            "minimum_signed_improvement": _fraction_payload(self.minimum_signed_improvement),
            "maximum_signed_improvement": _fraction_payload(self.maximum_signed_improvement),
        }


@dataclass(frozen=True)
class RepeatedExperimentAggregate:
    schema_version: int
    aggregation_version: str
    design_signature: str
    result_signatures: Tuple[str, ...]
    grounded_evidence_ids: Tuple[str, ...]
    independence_groups: Tuple[str, ...]
    experiment_count: int
    minimum_required_experiments: int
    minimum_required_independence_groups: int
    metric_evidence: Tuple[AggregatedMetricEvidence, ...]
    status: str
    sustained_improvement_qualified: bool
    qualification_required_before_canonical_reuse: bool
    aggregate_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "aggregation_version": self.aggregation_version,
            "design_signature": self.design_signature,
            "result_signatures": list(self.result_signatures),
            "grounded_evidence_ids": list(self.grounded_evidence_ids),
            "independence_groups": list(self.independence_groups),
            "experiment_count": self.experiment_count,
            "minimum_required_experiments": self.minimum_required_experiments,
            "minimum_required_independence_groups": self.minimum_required_independence_groups,
            "metric_evidence": [item.to_dict() for item in self.metric_evidence],
            "status": self.status,
            "sustained_improvement_qualified": self.sustained_improvement_qualified,
            "qualification_required_before_canonical_reuse": self.qualification_required_before_canonical_reuse,
            "aggregate_signature": self.aggregate_signature,
        }


def aggregate_repeated_experiments(
    results: Sequence[AlgorithmABExperimentResult],
    *,
    minimum_experiments: int = 2,
    minimum_independence_groups: int = 2,
) -> RepeatedExperimentAggregate:
    count_required = int(minimum_experiments)
    groups_required = int(minimum_independence_groups)
    if count_required < 2 or count_required > MAX_AGGREGATED_EXPERIMENTS:
        raise EGCFError("SAA-11.4 minimum experiment count outside supported range")
    if groups_required < 1 or groups_required > MAX_AGGREGATED_EXPERIMENTS:
        raise EGCFError("SAA-11.4 minimum independence-group count outside supported range")
    items = tuple(results)
    if len(items) < count_required or len(items) > MAX_AGGREGATED_EXPERIMENTS:
        raise EGCFError("SAA-11.4 repeated experiment count violates aggregation bounds")
    if any(not isinstance(item, AlgorithmABExperimentResult) for item in items):
        raise EGCFError("SAA-11.4 requires AlgorithmABExperimentResult objects")
    design_signatures = {item.design_signature for item in items}
    if len(design_signatures) != 1:
        raise EGCFError("SAA-11.4 can aggregate only exact experiment-design matches")
    result_signatures = tuple(sorted(item.result_signature for item in items))
    if len(set(result_signatures)) != len(result_signatures):
        raise EGCFError("SAA-11.4 duplicate experiment results cannot be counted twice")

    evidence_ids = tuple(sorted({eid for item in items for eid in item.grounded_evidence_ids}))
    groups = tuple(sorted({group for item in items for group in item.independence_groups if group}))

    metric_names = tuple(comparison.metric_name for comparison in items[0].metric_comparisons)
    first_directions = {comparison.metric_name: comparison.direction for comparison in items[0].metric_comparisons}
    for item in items[1:]:
        names = tuple(comparison.metric_name for comparison in item.metric_comparisons)
        if names != metric_names:
            raise EGCFError("SAA-11.4 metric order/identity differs across repeated results")
        for comparison in item.metric_comparisons:
            if first_directions.get(comparison.metric_name) != comparison.direction:
                raise EGCFError("SAA-11.4 metric direction differs across repeated results")

    summaries: list[AggregatedMetricEvidence] = []
    any_regression = False
    any_improvement = False
    any_tradeoff_status = False
    any_unqualified = False
    for metric_name in metric_names:
        comparisons = [
            next(value for value in item.metric_comparisons if value.metric_name == metric_name)
            for item in items
        ]
        signed = [item.signed_improvement for item in comparisons]
        improvement_count = sum(item.status == "MATERIAL_IMPROVEMENT" for item in comparisons)
        regression_count = sum(item.status == "MATERIAL_REGRESSION" for item in comparisons)
        unchanged_count = len(comparisons) - improvement_count - regression_count
        any_regression = any_regression or bool(regression_count)
        any_improvement = any_improvement or bool(improvement_count)
        summaries.append(
            AggregatedMetricEvidence(
                metric_name=metric_name,
                direction=comparisons[0].direction,
                experiment_count=len(comparisons),
                material_improvement_count=improvement_count,
                material_regression_count=regression_count,
                no_material_change_count=unchanged_count,
                mean_signed_improvement=sum(signed, Fraction(0)) / len(signed),
                minimum_signed_improvement=min(signed),
                maximum_signed_improvement=max(signed),
            )
        )

    for item in items:
        if item.status == "EXPERIMENT_TRADEOFF_UNRESOLVED":
            any_tradeoff_status = True
        if item.status not in {"CANDIDATE_IMPROVEMENT_QUALIFIED", "NO_MATERIAL_IMPROVEMENT"}:
            any_unqualified = True
        if not item.invariant_gate_passed or item.evidence_requirement_coverage_bp != 10000 or not item.independent_review:
            any_unqualified = True

    if any_regression:
        status = "REPEATED_EVIDENCE_REGRESSION_DETECTED"
    elif any_tradeoff_status:
        status = "REPEATED_EVIDENCE_TRADEOFF_UNRESOLVED"
    elif any_unqualified:
        status = "REPEATED_EVIDENCE_CONTAINS_UNQUALIFIED_RESULT"
    elif len(groups) < groups_required:
        status = "REPEATED_EVIDENCE_INDEPENDENCE_INSUFFICIENT"
    elif all(item.candidate_improvement_qualified for item in items) and any_improvement:
        status = "SUSTAINED_CANDIDATE_IMPROVEMENT_QUALIFIED"
    else:
        status = "REPEATED_EVIDENCE_NO_SUSTAINED_IMPROVEMENT"

    sustained = status == "SUSTAINED_CANDIDATE_IMPROVEMENT_QUALIFIED"
    payload = {
        "version": EXPERIMENT_AGGREGATION_VERSION,
        "design_signature": next(iter(design_signatures)),
        "result_signatures": list(result_signatures),
        "grounded_evidence_ids": list(evidence_ids),
        "independence_groups": list(groups),
        "experiment_count": len(items),
        "minimum_required_experiments": count_required,
        "minimum_required_independence_groups": groups_required,
        "metric_evidence": [item.to_dict() for item in summaries],
        "status": status,
        "sustained_improvement_qualified": sustained,
    }
    return RepeatedExperimentAggregate(
        schema_version=1,
        aggregation_version=EXPERIMENT_AGGREGATION_VERSION,
        design_signature=next(iter(design_signatures)),
        result_signatures=result_signatures,
        grounded_evidence_ids=evidence_ids,
        independence_groups=groups,
        experiment_count=len(items),
        minimum_required_experiments=count_required,
        minimum_required_independence_groups=groups_required,
        metric_evidence=tuple(summaries),
        status=status,
        sustained_improvement_qualified=sustained,
        qualification_required_before_canonical_reuse=True,
        aggregate_signature=sha256_json(payload),
    )
