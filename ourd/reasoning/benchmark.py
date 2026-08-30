from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Protocol, Sequence, Tuple

from ..constants import SCORE_SCALE
from ..errors import PolicyError
from .models import canonical_strings, stable_hash


BENCHMARK_CATEGORIES = (
    "logic",
    "arithmetic",
    "debugging",
    "evidence_synthesis",
    "scientific_inference",
    "causal_reasoning",
    "ambiguity_resolution",
    "adversarial",
)

BENCHMARK_SYSTEM_IDS = ("base", "oiec", "oiec_sr")
ORACLE_KINDS = ("exact", "contains")
TERMINAL_STATES = (
    "ANSWER",
    "EPISTEMIC_STOP",
    "INSUFFICIENT_EVIDENCE",
    "GOVERNANCE_STOP",
    "COMPUTE_BUDGET_EXHAUSTED",
    "NO_SURVIVING_HYPOTHESIS",
)

SYSTEM_DESCRIPTOR_KEYS = {
    "system_id",
    "executor",
    "provider",
    "model",
    "reasoning_effort",
    "context_budget_tokens",
    "max_output_tokens",
    "decoding",
}

MODEL_SYSTEM_DESCRIPTOR_KEYS = SYSTEM_DESCRIPTOR_KEYS | {
    "pipeline",
    "source_snapshot_hash",
    "prompt_template_hash",
    "evidence_context_mode",
    "provider_binding",
    "runtime_environment",
    "telemetry",
}


def _strict_keys(
    payload: Mapping[str, Any],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
    label: str,
) -> None:
    required_keys = set(required)
    allowed_keys = required_keys | set(optional)
    actual_keys = set(payload)
    missing = sorted(required_keys - actual_keys)
    unknown = sorted(actual_keys - allowed_keys)
    if missing:
        raise PolicyError(f"{label} is missing required fields: {missing!r}")
    if unknown:
        raise PolicyError(f"{label} contains unknown fields: {unknown!r}")


def _bounded(value: Any, label: str) -> int:
    score = int(value)
    if not 0 <= score <= SCORE_SCALE:
        raise PolicyError(f"{label} must be 0..{SCORE_SCALE}")
    return score


def _non_negative(value: Any, label: str) -> int:
    result = int(value)
    if result < 0:
        raise PolicyError(f"{label} must be non-negative")
    return result


def _normalized_answer(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _validate_signature_object(payload: Mapping[str, Any], label: str) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be an object")
    signature = str(payload.get("signature", ""))
    if not signature:
        raise ValueError(f"{label} signature must be non-empty")
    material = dict(payload)
    material.pop("signature", None)
    if signature != stable_hash(material):
        raise ValueError(f"{label} signature mismatch")


def _validate_system_descriptor(
    descriptor: Mapping[str, Any],
    *,
    execution_mode: str,
    source_manifest_hash: str,
) -> None:
    keys = set(descriptor)
    expected = (
        MODEL_SYSTEM_DESCRIPTOR_KEYS
        if execution_mode == "provider_bound"
        else SYSTEM_DESCRIPTOR_KEYS
    )
    if keys != expected:
        raise ValueError(
            "benchmark system descriptor fields mismatch: "
            f"missing={sorted(expected - keys)!r} unknown={sorted(keys - expected)!r}"
        )
    if descriptor["system_id"] not in BENCHMARK_SYSTEM_IDS:
        raise ValueError("benchmark system descriptor has an invalid system_id")
    if execution_mode != "provider_bound":
        return
    if descriptor["source_snapshot_hash"] != source_manifest_hash:
        raise ValueError("model benchmark system is bound to the wrong source snapshot")
    provider_binding = descriptor["provider_binding"]
    runtime = descriptor["runtime_environment"]
    telemetry = descriptor["telemetry"]
    _validate_signature_object(provider_binding, "provider binding")
    _validate_signature_object(runtime, "runtime environment")
    if provider_binding.get("status") != "ready":
        raise ValueError("model benchmark provider binding is not ready")
    if provider_binding.get("model") != descriptor["model"]:
        raise ValueError("model benchmark descriptor model binding mismatch")
    if provider_binding.get("provider") != descriptor["provider"]:
        raise ValueError("model benchmark descriptor provider binding mismatch")
    if int(provider_binding.get("max_transport_retries", -1)) != 0:
        raise ValueError("model benchmark transport retries must remain disabled")
    provider_calls = int(telemetry.get("provider_calls", -1))
    response_hashes = telemetry.get("response_hashes", ())
    if provider_calls < 1 or not isinstance(response_hashes, (list, tuple)):
        raise ValueError("model benchmark telemetry is incomplete")
    if len(response_hashes) > provider_calls:
        raise ValueError("model benchmark response hash count exceeds provider calls")
    runtime_hashes = telemetry.get("runtime_observation_hashes", ())
    if not isinstance(runtime_hashes, (list, tuple)) or not runtime_hashes:
        raise ValueError("model benchmark has no in-call runtime observation")
    successful_calls = provider_calls - int(telemetry.get("provider_failures", 0))
    if successful_calls > 0 and (
        not telemetry.get("observed_temperatures") or not telemetry.get("observed_top_p")
    ):
        raise ValueError("model benchmark did not record observed sampling values")
    if telemetry.get("nondeterminism_status") != "single_run_not_reproducibility_evidence":
        raise ValueError("model benchmark nondeterminism status is missing")


@dataclass(frozen=True)
class BenchmarkOracle:
    kind: str
    expected: str

    def __post_init__(self) -> None:
        if self.kind not in ORACLE_KINDS:
            raise ValueError(f"invalid benchmark oracle kind: {self.kind}")
        if not self.expected.strip():
            raise ValueError("benchmark oracle expected value must be non-empty")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkOracle":
        _strict_keys(payload, required=("kind", "expected"), label="benchmark oracle")
        return cls(kind=str(payload["kind"]), expected=str(payload["expected"]))


@dataclass(frozen=True)
class BenchmarkTask:
    schema_version: int
    problem_id: str
    category: str
    prompt: str
    oracle: BenchmarkOracle
    oracle_method: str
    required_evidence_ids: Tuple[str, ...] = ()
    required_counterexamples: Tuple[str, ...] = ()
    source_refs: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("benchmark task schema_version must be 1")
        if not self.problem_id.strip() or not self.prompt.strip():
            raise ValueError("benchmark task identity and prompt must be non-empty")
        if self.category not in BENCHMARK_CATEGORIES:
            raise ValueError(f"invalid benchmark category: {self.category}")
        if not self.oracle_method.strip():
            raise ValueError("benchmark oracle method must be explicit")
        for name in (
            "required_evidence_ids",
            "required_counterexamples",
            "source_refs",
        ):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))
        material = asdict(self)
        material.pop("signature", None)
        expected_signature = stable_hash(material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("benchmark task signature mismatch")
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkTask":
        _strict_keys(
            payload,
            required=(
                "schema_version",
                "problem_id",
                "category",
                "prompt",
                "oracle",
                "oracle_method",
                "required_evidence_ids",
                "required_counterexamples",
                "source_refs",
            ),
            optional=("signature",),
            label="benchmark task",
        )
        return cls(
            schema_version=int(payload["schema_version"]),
            problem_id=str(payload["problem_id"]),
            category=str(payload["category"]),
            prompt=str(payload["prompt"]),
            oracle=BenchmarkOracle.from_dict(payload["oracle"]),
            oracle_method=str(payload["oracle_method"]),
            required_evidence_ids=tuple(payload["required_evidence_ids"]),
            required_counterexamples=tuple(payload["required_counterexamples"]),
            source_refs=tuple(payload["source_refs"]),
            signature=str(payload.get("signature", "")),
        )


@dataclass(frozen=True)
class BenchmarkObservation:
    schema_version: int
    problem_id: str
    system_id: str
    answer: str
    confidence_bp: int
    evidence_ids: Tuple[str, ...] = ()
    counterexamples: Tuple[str, ...] = ()
    token_count: int = 0
    tool_calls: int = 0
    collisions: int = 0
    retries: int = 0
    wall_time_ms: int = 0
    terminal_state: str = "ANSWER"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("benchmark observation schema_version must be 1")
        if not self.problem_id.strip() or self.system_id not in BENCHMARK_SYSTEM_IDS:
            raise ValueError("benchmark observation identity is invalid")
        if not self.answer.strip() and self.terminal_state == "ANSWER":
            raise ValueError("answer terminal state requires a non-empty answer")
        _bounded(self.confidence_bp, "benchmark confidence")
        for name in ("token_count", "tool_calls", "collisions", "retries", "wall_time_ms"):
            _non_negative(getattr(self, name), f"benchmark {name}")
        if self.terminal_state not in TERMINAL_STATES:
            raise ValueError(f"invalid benchmark terminal state: {self.terminal_state}")
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))
        object.__setattr__(self, "counterexamples", canonical_strings(self.counterexamples))
        material = asdict(self)
        material.pop("signature", None)
        expected_signature = stable_hash(material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("benchmark observation signature mismatch")
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkObservation":
        _strict_keys(
            payload,
            required=(
                "schema_version",
                "problem_id",
                "system_id",
                "answer",
                "confidence_bp",
                "evidence_ids",
                "counterexamples",
                "token_count",
                "tool_calls",
                "collisions",
                "retries",
                "wall_time_ms",
                "terminal_state",
            ),
            optional=("signature",),
            label="benchmark observation",
        )
        return cls(
            schema_version=int(payload["schema_version"]),
            problem_id=str(payload["problem_id"]),
            system_id=str(payload["system_id"]),
            answer=str(payload["answer"]),
            confidence_bp=int(payload["confidence_bp"]),
            evidence_ids=tuple(payload["evidence_ids"]),
            counterexamples=tuple(payload["counterexamples"]),
            token_count=int(payload["token_count"]),
            tool_calls=int(payload["tool_calls"]),
            collisions=int(payload["collisions"]),
            retries=int(payload["retries"]),
            wall_time_ms=int(payload["wall_time_ms"]),
            terminal_state=str(payload["terminal_state"]),
            signature=str(payload.get("signature", "")),
        )


@dataclass(frozen=True)
class BenchmarkResult:
    problem_id: str
    category: str
    system_id: str
    task_signature: str
    observation_signature: str
    answer: str
    correctness_bp: int
    evidence_coverage_bp: int
    counterexample_detection_bp: int
    calibration_error_bp: int
    token_count: int
    tool_calls: int
    collisions: int
    retries: int
    wall_time_ms: int
    terminal_state: str
    signature: str = ""

    def __post_init__(self) -> None:
        if self.system_id not in BENCHMARK_SYSTEM_IDS:
            raise ValueError("benchmark result system is invalid")
        if self.category not in BENCHMARK_CATEGORIES:
            raise ValueError("benchmark result category is invalid")
        if self.terminal_state not in TERMINAL_STATES:
            raise ValueError("benchmark result terminal state is invalid")
        for name in (
            "correctness_bp",
            "evidence_coverage_bp",
            "counterexample_detection_bp",
            "calibration_error_bp",
        ):
            _bounded(getattr(self, name), f"benchmark result {name}")
        for name in (
            "token_count",
            "tool_calls",
            "collisions",
            "retries",
            "wall_time_ms",
        ):
            _non_negative(getattr(self, name), f"benchmark result {name}")
        material = asdict(self)
        material.pop("signature", None)
        expected_signature = stable_hash(material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("benchmark result signature mismatch")
        object.__setattr__(self, "signature", expected_signature)


@dataclass(frozen=True)
class BenchmarkSystemSummary:
    system_id: str
    problem_count: int
    accuracy_bp: int
    evidence_coverage_bp: int
    counterexample_detection_bp: int
    mean_calibration_error_bp: int
    total_tokens: int
    total_tool_calls: int
    total_collisions: int
    total_retries: int
    total_wall_time_ms: int
    signature: str = ""

    def __post_init__(self) -> None:
        if self.system_id not in BENCHMARK_SYSTEM_IDS or self.problem_count < 1:
            raise ValueError("benchmark system summary identity is invalid")
        for name in (
            "accuracy_bp",
            "evidence_coverage_bp",
            "counterexample_detection_bp",
            "mean_calibration_error_bp",
        ):
            _bounded(getattr(self, name), f"benchmark summary {name}")
        for name in (
            "total_tokens",
            "total_tool_calls",
            "total_collisions",
            "total_retries",
            "total_wall_time_ms",
        ):
            _non_negative(getattr(self, name), f"benchmark summary {name}")
        material = asdict(self)
        material.pop("signature", None)
        expected_signature = stable_hash(material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("benchmark system summary signature mismatch")
        object.__setattr__(self, "signature", expected_signature)


@dataclass(frozen=True)
class SourceFileRecord:
    path: str
    sha256: str


@dataclass(frozen=True)
class BenchmarkRun:
    schema_version: int
    benchmark_id: str
    generated_on: str
    execution_mode: str
    qualification_status: str
    performance_claim_allowed: bool
    package_version: str
    git_head: str
    worktree_dirty: bool
    source_manifest_hash: str
    source_files: Tuple[SourceFileRecord, ...]
    task_count: int
    systems: Tuple[Mapping[str, Any], ...]
    results: Tuple[BenchmarkResult, ...]
    summaries: Tuple[BenchmarkSystemSummary, ...]
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.task_count < 1:
            raise ValueError("benchmark run schema or task count is invalid")
        try:
            date.fromisoformat(self.generated_on)
        except ValueError as exc:
            raise ValueError("benchmark generated_on must be an ISO date") from exc
        expected_qualification = {
            "deterministic_fixture": "development_fixture_only",
            "provider_bound": "development_model_plumbing_only",
        }.get(self.execution_mode)
        if expected_qualification is None:
            raise ValueError("benchmark execution mode is invalid")
        if self.qualification_status != expected_qualification:
            raise ValueError("benchmark qualification status does not match execution mode")
        if self.performance_claim_allowed:
            raise ValueError("development benchmark cannot authorize a performance claim")
        object.__setattr__(self, "source_files", tuple(sorted(self.source_files, key=lambda item: item.path)))
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "summaries", tuple(sorted(self.summaries, key=lambda item: item.system_id)))
        if len(self.results) != self.task_count * len(BENCHMARK_SYSTEM_IDS):
            raise ValueError("benchmark result count does not match task/system cardinality")
        if tuple(item.system_id for item in self.summaries) != tuple(sorted(BENCHMARK_SYSTEM_IDS)):
            raise ValueError("benchmark summaries do not cover the canonical systems")
        expected_manifest_hash = stable_hash([asdict(item) for item in self.source_files])
        if self.source_manifest_hash != expected_manifest_hash:
            raise ValueError("benchmark source manifest hash mismatch")
        if tuple(item["system_id"] for item in self.systems) != BENCHMARK_SYSTEM_IDS:
            raise ValueError("benchmark system descriptors must use canonical order")
        for descriptor in self.systems:
            _validate_system_descriptor(
                descriptor,
                execution_mode=self.execution_mode,
                source_manifest_hash=self.source_manifest_hash,
            )
        material = asdict(self)
        material.pop("signature", None)
        expected_signature = stable_hash(material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("benchmark run signature mismatch")
        object.__setattr__(self, "signature", expected_signature)


class BenchmarkExecutor(Protocol):
    system_id: str

    def identity_descriptor(self) -> Mapping[str, Any]:
        ...

    def descriptor(self) -> Mapping[str, Any]:
        ...

    def execute(self, task: BenchmarkTask) -> BenchmarkObservation:
        ...


class FixtureBenchmarkExecutor:
    def __init__(self, system_id: str, observations: Mapping[str, BenchmarkObservation]):
        if system_id not in BENCHMARK_SYSTEM_IDS:
            raise PolicyError(f"unknown benchmark system: {system_id}")
        self.system_id = system_id
        self._observations = dict(observations)

    def descriptor(self) -> Mapping[str, Any]:
        return {
            "system_id": self.system_id,
            "executor": "FixtureBenchmarkExecutor",
            "provider": "deterministic-fixture-v1",
            "model": "recorded-output",
            "reasoning_effort": "fixture",
            "context_budget_tokens": 0,
            "max_output_tokens": 0,
            "decoding": "recorded",
        }

    def execute(self, task: BenchmarkTask) -> BenchmarkObservation:
        observation = self._observations.get(task.problem_id)
        if observation is None:
            raise PolicyError(
                f"fixture system {self.system_id!r} has no observation for {task.problem_id!r}"
            )
        if observation.system_id != self.system_id:
            raise PolicyError("fixture observation system mismatch")
        return observation


def load_benchmark_tasks(task_root: Path) -> Tuple[BenchmarkTask, ...]:
    tasks = []
    seen = set()
    for path in sorted(task_root.glob("*.jsonl")):
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise PolicyError(f"{path}:{line_number} benchmark task must be an object")
            task = BenchmarkTask.from_dict(payload)
            if task.problem_id in seen:
                raise PolicyError(f"duplicate benchmark problem_id: {task.problem_id}")
            seen.add(task.problem_id)
            tasks.append(task)
    if not tasks:
        raise PolicyError("benchmark task set is empty")
    return tuple(tasks)


def load_fixture_observations(
    path: Path,
    tasks: Sequence[BenchmarkTask],
) -> Dict[str, Dict[str, BenchmarkObservation]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PolicyError("benchmark fixture must be an object")
    _strict_keys(
        payload,
        required=("schema_version", "fixture_id", "qualification_status", "observations"),
        label="benchmark fixture",
    )
    if int(payload["schema_version"]) != 1:
        raise PolicyError("benchmark fixture schema_version must be 1")
    if payload["qualification_status"] != "development_fixture_only":
        raise PolicyError("fixture qualification status must remain development_fixture_only")
    task_ids = {task.problem_id for task in tasks}
    by_system: Dict[str, Dict[str, BenchmarkObservation]] = {
        system_id: {} for system_id in BENCHMARK_SYSTEM_IDS
    }
    for raw_observation in payload["observations"]:
        observation = BenchmarkObservation.from_dict(raw_observation)
        if observation.problem_id not in task_ids:
            raise PolicyError(
                f"fixture references unknown benchmark problem: {observation.problem_id}"
            )
        existing = by_system[observation.system_id]
        if observation.problem_id in existing:
            raise PolicyError(
                f"duplicate fixture observation: {observation.system_id}/{observation.problem_id}"
            )
        existing[observation.problem_id] = observation
    for system_id, observations in by_system.items():
        missing = sorted(task_ids - set(observations))
        if missing:
            raise PolicyError(f"fixture system {system_id!r} is missing tasks: {missing!r}")
    return by_system


def score_observation(task: BenchmarkTask, observation: BenchmarkObservation) -> BenchmarkResult:
    if observation.problem_id != task.problem_id:
        raise PolicyError("benchmark observation problem mismatch")
    answer = _normalized_answer(observation.answer)
    expected = _normalized_answer(task.oracle.expected)
    if task.oracle.kind == "exact":
        correct = answer == expected
    else:
        correct = expected in answer
    correctness = SCORE_SCALE if correct else 0
    required_evidence = set(task.required_evidence_ids)
    reported_evidence = set(observation.evidence_ids)
    unknown_evidence = sorted(reported_evidence - required_evidence)
    if unknown_evidence:
        raise PolicyError(
            f"benchmark observation cites undeclared evidence: {unknown_evidence!r}"
        )
    evidence_coverage = (
        SCORE_SCALE
        if not required_evidence
        else len(required_evidence & reported_evidence) * SCORE_SCALE // len(required_evidence)
    )
    required_counterexamples = {
        _normalized_answer(item) for item in task.required_counterexamples
    }
    reported_counterexamples = {
        _normalized_answer(item) for item in observation.counterexamples
    }
    counterexample_detection = (
        SCORE_SCALE
        if not required_counterexamples
        else len(required_counterexamples & reported_counterexamples)
        * SCORE_SCALE
        // len(required_counterexamples)
    )
    return BenchmarkResult(
        problem_id=task.problem_id,
        category=task.category,
        system_id=observation.system_id,
        task_signature=task.signature,
        observation_signature=observation.signature,
        answer=observation.answer,
        correctness_bp=correctness,
        evidence_coverage_bp=evidence_coverage,
        counterexample_detection_bp=counterexample_detection,
        calibration_error_bp=abs(observation.confidence_bp - correctness),
        token_count=observation.token_count,
        tool_calls=observation.tool_calls,
        collisions=observation.collisions,
        retries=observation.retries,
        wall_time_ms=observation.wall_time_ms,
        terminal_state=observation.terminal_state,
    )


def summarize_results(
    system_id: str,
    results: Sequence[BenchmarkResult],
) -> BenchmarkSystemSummary:
    selected = [result for result in results if result.system_id == system_id]
    if not selected:
        raise PolicyError(f"benchmark has no results for system: {system_id}")
    count = len(selected)
    return BenchmarkSystemSummary(
        system_id=system_id,
        problem_count=count,
        accuracy_bp=sum(item.correctness_bp for item in selected) // count,
        evidence_coverage_bp=sum(item.evidence_coverage_bp for item in selected) // count,
        counterexample_detection_bp=(
            sum(item.counterexample_detection_bp for item in selected) // count
        ),
        mean_calibration_error_bp=(
            sum(item.calibration_error_bp for item in selected) // count
        ),
        total_tokens=sum(item.token_count for item in selected),
        total_tool_calls=sum(item.tool_calls for item in selected),
        total_collisions=sum(item.collisions for item in selected),
        total_retries=sum(item.retries for item in selected),
        total_wall_time_ms=sum(item.wall_time_ms for item in selected),
    )


def build_source_manifest(root: Path, relative_paths: Iterable[str]) -> Tuple[SourceFileRecord, ...]:
    records = []
    for relative_path in sorted(set(relative_paths)):
        path = root / relative_path
        if not path.is_file():
            raise PolicyError(f"benchmark source file is missing: {relative_path}")
        records.append(
            SourceFileRecord(
                path=relative_path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return tuple(records)


def repository_git_state(root: Path) -> Tuple[str, bool]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "", True
    return head, dirty


def run_benchmark(
    *,
    tasks: Sequence[BenchmarkTask],
    executors: Sequence[BenchmarkExecutor],
    generated_on: str,
    package_version: str,
    git_head: str,
    worktree_dirty: bool,
    source_files: Sequence[SourceFileRecord],
    execution_mode: str = "deterministic_fixture",
    qualification_status: str = "development_fixture_only",
) -> BenchmarkRun:
    if not tasks:
        raise PolicyError("cannot run an empty benchmark")
    executor_ids = tuple(executor.system_id for executor in executors)
    if executor_ids != BENCHMARK_SYSTEM_IDS:
        raise PolicyError(
            f"benchmark executors must be ordered as {BENCHMARK_SYSTEM_IDS!r}"
        )
    results = []
    for task in tasks:
        for executor in executors:
            results.append(score_observation(task, executor.execute(task)))
        for executor in executors:
            release_runtime = getattr(executor, "release_runtime", None)
            if callable(release_runtime):
                release_runtime()
    summaries = tuple(
        summarize_results(system_id, results) for system_id in BENCHMARK_SYSTEM_IDS
    )
    source_manifest_hash = stable_hash([asdict(item) for item in source_files])
    descriptors = tuple(dict(executor.descriptor()) for executor in executors)
    identity_descriptors = tuple(
        dict(executor.identity_descriptor())
        if callable(getattr(executor, "identity_descriptor", None))
        else descriptor
        for executor, descriptor in zip(executors, descriptors)
    )
    benchmark_material = {
        "task_signatures": [task.signature for task in tasks],
        "systems": identity_descriptors,
        "source_manifest_hash": source_manifest_hash,
        "execution_mode": execution_mode,
    }
    return BenchmarkRun(
        schema_version=1,
        benchmark_id=stable_hash(benchmark_material),
        generated_on=generated_on,
        execution_mode=execution_mode,
        qualification_status=qualification_status,
        performance_claim_allowed=False,
        package_version=package_version,
        git_head=git_head,
        worktree_dirty=worktree_dirty,
        source_manifest_hash=source_manifest_hash,
        source_files=tuple(source_files),
        task_count=len(tasks),
        systems=descriptors,
        results=tuple(results),
        summaries=summaries,
    )


def benchmark_json(run: BenchmarkRun) -> str:
    return json.dumps(asdict(run), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_benchmark_run(path: Path, run: BenchmarkRun) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(benchmark_json(run), encoding="utf-8")


def load_benchmark_run(path: Path) -> BenchmarkRun:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PolicyError("benchmark run must be an object")
    _strict_keys(
        payload,
        required=(
            "schema_version",
            "benchmark_id",
            "generated_on",
            "execution_mode",
            "qualification_status",
            "performance_claim_allowed",
            "package_version",
            "git_head",
            "worktree_dirty",
            "source_manifest_hash",
            "source_files",
            "task_count",
            "systems",
            "results",
            "summaries",
            "signature",
        ),
        label="benchmark run",
    )
    try:
        return BenchmarkRun(
            schema_version=int(payload["schema_version"]),
            benchmark_id=str(payload["benchmark_id"]),
            generated_on=str(payload["generated_on"]),
            execution_mode=str(payload["execution_mode"]),
            qualification_status=str(payload["qualification_status"]),
            performance_claim_allowed=bool(payload["performance_claim_allowed"]),
            package_version=str(payload["package_version"]),
            git_head=str(payload["git_head"]),
            worktree_dirty=bool(payload["worktree_dirty"]),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            source_files=tuple(SourceFileRecord(**item) for item in payload["source_files"]),
            task_count=int(payload["task_count"]),
            systems=tuple(dict(item) for item in payload["systems"]),
            results=tuple(BenchmarkResult(**item) for item in payload["results"]),
            summaries=tuple(BenchmarkSystemSummary(**item) for item in payload["summaries"]),
            signature=str(payload["signature"]),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise PolicyError(f"benchmark run is invalid: {exc}") from exc


def verify_benchmark_checksum(path: Path, checksum_path: Path) -> str:
    raw = checksum_path.read_text(encoding="utf-8").strip().split()
    if len(raw) < 1 or len(raw[0]) != 64:
        raise PolicyError("benchmark checksum file is invalid")
    expected = raw[0]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise PolicyError("benchmark artifact checksum mismatch")
    return actual


__all__ = [
    "BENCHMARK_CATEGORIES",
    "BENCHMARK_SYSTEM_IDS",
    "BenchmarkExecutor",
    "BenchmarkObservation",
    "BenchmarkOracle",
    "BenchmarkResult",
    "BenchmarkRun",
    "BenchmarkSystemSummary",
    "BenchmarkTask",
    "FixtureBenchmarkExecutor",
    "SourceFileRecord",
    "benchmark_json",
    "build_source_manifest",
    "load_benchmark_tasks",
    "load_benchmark_run",
    "load_fixture_observations",
    "repository_git_state",
    "run_benchmark",
    "score_observation",
    "summarize_results",
    "verify_benchmark_checksum",
    "write_benchmark_run",
]
