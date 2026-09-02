from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from ..errors import PolicyError
from .ablation import (
    AblationConfiguration,
    REQUIRED_ABLATIONS,
    ablation_pipeline,
    standard_ablation_configurations,
)
from .benchmark import (
    BENCHMARK_SYSTEM_IDS,
    HELD_OUT_MODEL_QUALIFICATION_STATUS,
    BenchmarkResult,
    BenchmarkRun,
)
from .models import SCORE_SCALE, stable_hash


REQUIRED_QUALIFICATION_CATEGORIES = (
    "logic",
    "arithmetic",
    "debugging",
    "scientific_inference",
    "causal_reasoning",
    "adversarial",
)
MIN_ABLATION_TASKS_PER_CATEGORY = 10
def wilson_interval_bp(successes: int, total: int, *, z: float = 1.96) -> tuple[int, int]:
    if total < 1 or not 0 <= successes <= total:
        raise ValueError("Wilson interval requires 0 <= successes <= total")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return (
        max(0, int(round((center - margin) * SCORE_SCALE))),
        min(SCORE_SCALE, int(round((center + margin) * SCORE_SCALE))),
    )


def _mean(values: Sequence[int]) -> int:
    return sum(values) // len(values) if values else 0


def _system_metrics(
    runs: Sequence[BenchmarkRun],
    results: Sequence[BenchmarkResult],
    system_id: str,
) -> dict:
    selected = tuple(result for result in results if result.system_id == system_id)
    successes = sum(result.correctness_bp == SCORE_SCALE for result in selected)
    unsupported_empirical = sum(
        result.category in {"scientific_inference", "causal_reasoning"}
        and result.terminal_state == "ANSWER"
        and result.evidence_coverage_bp < SCORE_SCALE
        for result in selected
    )
    return {
        "system_id": system_id,
        "result_count": len(selected),
        "accuracy_bp": _mean([result.correctness_bp for result in selected]),
        "accuracy_ci95_bp": wilson_interval_bp(successes, len(selected)),
        "evidence_coverage_bp": _mean(
            [result.evidence_coverage_bp for result in selected]
        ),
        "counterexample_detection_bp": _mean(
            [result.counterexample_detection_bp for result in selected]
        ),
        "mean_calibration_error_bp": _mean(
            [result.calibration_error_bp for result in selected]
        ),
        "total_tokens": sum(result.token_count for result in selected),
        "total_tool_calls": sum(result.tool_calls for result in selected),
        "total_collisions": sum(result.collisions for result in selected),
        "total_retries": sum(result.retries for result in selected),
        "total_wall_time_ms": sum(result.wall_time_ms for result in selected),
        "total_provider_failures": sum(
            int(run.systems[BENCHMARK_SYSTEM_IDS.index(system_id)]["telemetry"]["provider_failures"])
            for run in runs
            if run.execution_mode == "provider_bound"
        ),
        "unsupported_empirical_claims": unsupported_empirical,
    }


def certificate_reproducibility_bp(runs: Sequence[BenchmarkRun]) -> int:
    if len(runs) < 2:
        return 0
    signatures = []
    for run in runs:
        telemetry = run.systems[BENCHMARK_SYSTEM_IDS.index("oiec_sr")].get(
            "telemetry", {}
        )
        values = telemetry.get("certificate_signatures", ())
        if not isinstance(values, (list, tuple)) or len(values) != run.task_count:
            return 0
        signatures.append(tuple(str(value) for value in values))
    reproducible = sum(
        bool(signatures[0][index])
        and all(row[index] == signatures[0][index] for row in signatures[1:])
        for index in range(len(signatures[0]))
    )
    return reproducible * SCORE_SCALE // len(signatures[0])


@dataclass(frozen=True)
class ReasoningQualificationReport:
    schema_version: int
    qualification_id: str
    source_manifest_hash: str
    provider_identity_signature: str
    benchmark_run_signatures: tuple[str, ...]
    repeated_run_count: int
    task_count_per_run: int
    category_counts: tuple[tuple[str, int], ...]
    system_metrics: tuple[Mapping[str, object], ...]
    difficult_accuracy_gain_bp: int
    certificate_reproducibility_bp: int
    required_ablation_ids: tuple[str, ...]
    present_ablation_ids: tuple[str, ...]
    missing_ablation_ids: tuple[str, ...]
    ablation_task_count_per_run: int
    ablation_category_counts: tuple[tuple[str, int], ...]
    ablation_evidence: tuple[Mapping[str, object], ...]
    task_failures: tuple[Mapping[str, object], ...]
    limitations: tuple[str, ...]
    performance_gate_passed: bool
    performance_claim_allowed: bool
    human_review_required: bool
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("qualification report schema_version must be 1")
        if self.performance_claim_allowed:
            raise ValueError("automated qualification cannot authorize a performance claim")
        material = asdict(self)
        material.pop("qualification_id", None)
        material.pop("signature", None)
        qualification_id = f"reasoning-qualification:{stable_hash(material)}"
        if self.qualification_id and self.qualification_id != qualification_id:
            raise ValueError("qualification report ID mismatch")
        object.__setattr__(self, "qualification_id", qualification_id)
        expected = stable_hash({**material, "qualification_id": qualification_id})
        if self.signature and self.signature != expected:
            raise ValueError("qualification report signature mismatch")
        object.__setattr__(self, "signature", expected)


def _task_signature_sequence(run: BenchmarkRun) -> tuple[str, ...]:
    signatures = tuple(
        result.task_signature
        for result in run.results
        if result.system_id == "base"
    )
    if len(signatures) != run.task_count:
        raise PolicyError("benchmark run does not contain one base task signature per task")
    return signatures


def _execution_identity(run: BenchmarkRun) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            key: value
            for key, value in descriptor.items()
            if key not in {"pipeline", "telemetry"}
        }
        for descriptor in run.systems
    )


def _ablation_evidence(
    *,
    main_runs: Sequence[BenchmarkRun],
    ablation_runs: Mapping[str, Sequence[BenchmarkRun]],
) -> tuple[
    tuple[Mapping[str, object], ...],
    tuple[str, ...],
    tuple[tuple[str, int], ...],
    int,
]:
    unknown = sorted(set(ablation_runs) - set(REQUIRED_ABLATIONS))
    if unknown:
        raise PolicyError(f"qualification ablation manifest has unknown IDs: {unknown!r}")
    configurations = {
        item.ablation_id: item for item in standard_ablation_configurations()
    }
    reference = main_runs[0]
    reference_identity = _execution_identity(reference)
    evidence = []
    ablation_task_signatures: tuple[str, ...] = ()
    ablation_category_counts: tuple[tuple[str, int], ...] = ()
    provider_failures = 0
    for ablation_id in REQUIRED_ABLATIONS:
        candidates = tuple(ablation_runs.get(ablation_id, ()))
        if not candidates:
            continue
        configuration = configurations[ablation_id]
        expected_pipeline = ablation_pipeline(configuration)
        signatures = []
        for run in candidates:
            if not isinstance(run, BenchmarkRun):
                raise PolicyError("qualification ablation evidence must be benchmark runs")
            if run.execution_mode != "provider_bound":
                raise PolicyError("qualification ablation run is not provider-bound")
            if run.qualification_status != HELD_OUT_MODEL_QUALIFICATION_STATUS:
                raise PolicyError("qualification ablation run is not held-out evidence")
            if run.source_manifest_hash != reference.source_manifest_hash:
                raise PolicyError("qualification ablation source manifest mismatch")
            task_signatures = _task_signature_sequence(run)
            if ablation_task_signatures and task_signatures != ablation_task_signatures:
                raise PolicyError("qualification ablation task set mismatch")
            if not ablation_task_signatures:
                ablation_task_signatures = task_signatures
                ablation_category_counts = tuple(
                    sorted(
                        (
                            category,
                            len(
                                {
                                    result.problem_id
                                    for result in run.results
                                    if result.system_id == "base"
                                    and result.category == category
                                }
                            ),
                        )
                        for category in REQUIRED_QUALIFICATION_CATEGORIES
                    )
                )
            if _execution_identity(run) != reference_identity:
                raise PolicyError("qualification ablation provider/runtime identity mismatch")
            if run.systems[BENCHMARK_SYSTEM_IDS.index("oiec_sr")]["pipeline"] != expected_pipeline:
                raise PolicyError(
                    f"qualification ablation pipeline mismatch: {ablation_id}"
                )
            signatures.append(run.signature)
            provider_failures += sum(
                int(descriptor["telemetry"]["provider_failures"])
                for descriptor in run.systems
            )
        if len(signatures) != len(set(signatures)):
            raise PolicyError(f"qualification ablation repeats one artifact: {ablation_id}")
        evidence.append(
            {
                "ablation_id": ablation_id,
                "configuration_signature": configuration.signature,
                "benchmark_run_signatures": tuple(signatures),
            }
        )
    return (
        tuple(evidence),
        ablation_task_signatures,
        ablation_category_counts,
        provider_failures,
    )


def qualify_reasoning_runs(
    runs: Sequence[BenchmarkRun],
    *,
    ablation_runs: Mapping[str, Sequence[BenchmarkRun]],
    certificate_reproducibility_assertion_bp: int | None = None,
) -> ReasoningQualificationReport:
    if not runs:
        raise PolicyError("qualification requires at least one matched benchmark run")
    source_hashes = {run.source_manifest_hash for run in runs}
    task_counts = {run.task_count for run in runs}
    if len(source_hashes) != 1 or len(task_counts) != 1:
        raise PolicyError("qualification runs must use one source and task cardinality")
    task_signature_sequences = {_task_signature_sequence(run) for run in runs}
    if len(task_signature_sequences) != 1:
        raise PolicyError("qualification runs do not use the same matched tasks")
    provider_identity_signatures = {
        stable_hash(_execution_identity(run)) for run in runs
    }
    if len(provider_identity_signatures) != 1:
        raise PolicyError("qualification runs do not share one provider/runtime identity")
    provider_identity_signature = next(iter(provider_identity_signatures))
    full_sr = next(
        item for item in standard_ablation_configurations() if item.ablation_id == "full_sr"
    )
    for run in runs:
        if (
            run.execution_mode == "provider_bound"
            and run.qualification_status == HELD_OUT_MODEL_QUALIFICATION_STATUS
            and run.systems[BENCHMARK_SYSTEM_IDS.index("oiec_sr")]["pipeline"]
            != ablation_pipeline(full_sr)
        ):
            raise PolicyError("qualification main run is not the full_sr configuration")
    (
        ablation_evidence,
        ablation_task_signatures,
        ablation_category_counts,
        ablation_provider_failures,
    ) = _ablation_evidence(
        main_runs=runs,
        ablation_runs=ablation_runs,
    )
    all_results = tuple(result for run in runs for result in run.results)
    derived_certificate_reproducibility_bp = certificate_reproducibility_bp(runs)
    if (
        certificate_reproducibility_assertion_bp is not None
        and int(certificate_reproducibility_assertion_bp)
        != derived_certificate_reproducibility_bp
    ):
        raise PolicyError(
            "certificate reproducibility assertion does not match benchmark evidence"
        )
    category_counts = {}
    first_run = runs[0]
    for category in REQUIRED_QUALIFICATION_CATEGORIES:
        category_counts[category] = len(
            {
                result.problem_id
                for result in first_run.results
                if result.category == category and result.system_id == "base"
            }
        )
    metrics = tuple(
        _system_metrics(runs, all_results, system_id)
        for system_id in BENCHMARK_SYSTEM_IDS
    )
    metric_by_system = {str(item["system_id"]): item for item in metrics}
    accuracy_gain = int(metric_by_system["oiec_sr"]["accuracy_bp"]) - int(
        metric_by_system["base"]["accuracy_bp"]
    )
    failures = tuple(
        {
            "run_signature": run.signature,
            "problem_id": result.problem_id,
            "category": result.category,
            "system_id": result.system_id,
            "correctness_bp": result.correctness_bp,
            "terminal_state": result.terminal_state,
        }
        for run in runs
        for result in run.results
        if result.correctness_bp < SCORE_SCALE
    )
    present_ablations = tuple(
        str(item["ablation_id"]) for item in ablation_evidence
    )
    missing_ablations = tuple(
        item for item in REQUIRED_ABLATIONS if item not in present_ablations
    )
    limitations = []
    if any(
        run.execution_mode != "provider_bound"
        or run.qualification_status != HELD_OUT_MODEL_QUALIFICATION_STATUS
        for run in runs
    ):
        limitations.append("runs are not held-out provider qualification candidates")
    if len(runs) < 2:
        limitations.append("fewer than two matched repeated runs")
    for category, count in category_counts.items():
        if count < 100:
            limitations.append(f"{category} has only {count} held-out tasks")
    if missing_ablations:
        limitations.append("required ablation results are incomplete")
    if ablation_task_signatures:
        for category, count in ablation_category_counts:
            if count < MIN_ABLATION_TASKS_PER_CATEGORY:
                limitations.append(
                    f"ablation corpus {category} has only {count} held-out tasks"
                )
    if ablation_provider_failures:
        limitations.append("provider failures occurred during ablation runs")
    if derived_certificate_reproducibility_bp < SCORE_SCALE:
        limitations.append("certificate reproducibility is below 100 percent")
    if any(int(item["total_provider_failures"]) != 0 for item in metrics):
        limitations.append("provider failures occurred during qualification")
    if any(int(item["total_retries"]) != 0 for item in metrics):
        limitations.append("blind retries occurred during qualification")
    sr_metrics = metric_by_system["oiec_sr"]
    gate = (
        not limitations
        and accuracy_gain >= 1_000
        and int(sr_metrics["counterexample_detection_bp"]) >= 9_000
        and int(sr_metrics["total_retries"]) == 0
        and int(sr_metrics["unsupported_empirical_claims"]) == 0
        and derived_certificate_reproducibility_bp == SCORE_SCALE
    )
    return ReasoningQualificationReport(
        schema_version=1,
        qualification_id="",
        source_manifest_hash=next(iter(source_hashes)),
        provider_identity_signature=provider_identity_signature,
        benchmark_run_signatures=tuple(run.signature for run in runs),
        repeated_run_count=len(runs),
        task_count_per_run=next(iter(task_counts)),
        category_counts=tuple(sorted(category_counts.items())),
        system_metrics=metrics,
        difficult_accuracy_gain_bp=accuracy_gain,
        certificate_reproducibility_bp=derived_certificate_reproducibility_bp,
        required_ablation_ids=REQUIRED_ABLATIONS,
        present_ablation_ids=present_ablations,
        missing_ablation_ids=missing_ablations,
        ablation_task_count_per_run=len(ablation_task_signatures),
        ablation_category_counts=ablation_category_counts,
        ablation_evidence=ablation_evidence,
        task_failures=failures,
        limitations=tuple(limitations),
        performance_gate_passed=gate,
        performance_claim_allowed=False,
        human_review_required=True,
    )


__all__ = [
    "AblationConfiguration",
    "MIN_ABLATION_TASKS_PER_CATEGORY",
    "REQUIRED_ABLATIONS",
    "REQUIRED_QUALIFICATION_CATEGORIES",
    "ReasoningQualificationReport",
    "certificate_reproducibility_bp",
    "qualify_reasoning_runs",
    "standard_ablation_configurations",
    "wilson_interval_bp",
]
