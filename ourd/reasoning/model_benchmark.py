from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

from ..constants import SCORE_SCALE
from ..errors import ContextBudgetError, PolicyError, ProviderError
from .benchmark import (
    BENCHMARK_SYSTEM_IDS,
    TERMINAL_STATES,
    BenchmarkObservation,
    BenchmarkTask,
)
from .generator import parse_json_object, response_text
from .kernel import SuperReasoningKernel
from .models import CandidateSet, ReasoningCertificate, stable_hash


MODEL_EXECUTION_MODE = "provider_bound"
MODEL_QUALIFICATION_STATUS = "development_model_plumbing_only"
MODEL_EVIDENCE_CONTEXT_MODE = "oracle_handles_exposed_for_plumbing_only"

ANSWER_RESPONSE_KEYS = {
    "answer",
    "confidence_bp",
    "evidence_ids",
    "counterexamples",
    "terminal_state",
}

BASE_INSTRUCTIONS = """
You are the base-model arm of a controlled reasoning benchmark. Answer the user
problem directly. Return exactly one JSON object with keys answer,
confidence_bp, evidence_ids, counterexamples, and terminal_state. confidence_bp
is an integer from 0 to 10000. evidence_ids may contain only identifiers listed
in available_evidence_ids. terminal_state must be ANSWER, EPISTEMIC_STOP,
INSUFFICIENT_EVIDENCE, GOVERNANCE_STOP, COMPUTE_BUDGET_EXHAUSTED, or
NO_SURVIVING_HYPOTHESIS. Do not use tools, claim mutation authority, reveal
private chain-of-thought, or add text outside the JSON object.
""".strip()

OIEC_INSTRUCTIONS = """
You are the governed single-path OIEC arm of a controlled reasoning benchmark.
Before answering, internally identify the question, operational boundary,
relevant evidence, one controlled inference path, and the strongest falsifier.
The reasoning process grants no authority and may not use tools. Return exactly
one JSON object with keys answer, confidence_bp, evidence_ids,
counterexamples, and terminal_state. confidence_bp is an integer from 0 to
10000. evidence_ids may contain only identifiers listed in
available_evidence_ids. terminal_state must be ANSWER, EPISTEMIC_STOP,
INSUFFICIENT_EVIDENCE, GOVERNANCE_STOP, COMPUTE_BUDGET_EXHAUSTED, or
NO_SURVIVING_HYPOTHESIS. Do not reveal private chain-of-thought or add text
outside the JSON object.
""".strip()


def _non_negative_int(value: Any, label: str) -> int:
    result = int(value)
    if result < 0:
        raise PolicyError(f"{label} must be non-negative")
    return result


def _bounded_score(value: Any, label: str) -> int:
    result = int(value)
    if not 0 <= result <= SCORE_SCALE:
        raise PolicyError(f"{label} must be 0..{SCORE_SCALE}")
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        payload = value.model_dump(exclude_none=True)
        if isinstance(payload, Mapping):
            return payload
    if hasattr(value, "to_dict"):
        payload = value.to_dict()
        if isinstance(payload, Mapping):
            return payload
    return {}


def _clean_base_url(value: str) -> str:
    candidate = str(value).strip()
    if not candidate:
        raise PolicyError("provider base URL must be explicit for a bound benchmark")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PolicyError("provider base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PolicyError("provider base URL must not contain credentials, query, or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _command_output(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip()


def _cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.casefold().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    return platform.processor().strip()


def _memory_bytes() -> int:
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def _nvidia_inventory() -> Tuple[str, str, str, int]:
    output = _command_output(
        (
            "nvidia-smi",
            "--query-gpu=name,uuid,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        )
    )
    if not output:
        return "", "", "", 0
    first = output.splitlines()[0]
    values = [item.strip() for item in first.split(",", 3)]
    if len(values) != 4:
        return "", "", "", 0
    try:
        memory = int(values[3]) * 1024 * 1024
    except ValueError:
        memory = 0
    return values[0], values[1], values[2], memory


def _ollama_allocation(model: str) -> Tuple[str, int]:
    output = _command_output(("ollama", "ps"))
    for line in output.splitlines()[1:]:
        columns = re.split(r"\s{2,}", line.strip())
        if not columns or columns[0] not in {model, f"{model}:latest"}:
            continue
        allocation = next((value for value in columns if "%" in value), "")
        context = 0
        for value in columns:
            if value.isdigit():
                numeric = int(value)
                if numeric >= 512:
                    context = numeric
        return allocation, context
    return "", 0


def release_ollama_runtime(profile: "BoundProviderProfile") -> None:
    if profile.endpoint_type != "ollama_local":
        return
    allocation, _ = _ollama_allocation(profile.model)
    if not allocation:
        return
    parsed = urlsplit(profile.base_url)
    endpoint = urlunsplit((parsed.scheme, parsed.netloc, "/api/generate", "", ""))
    payload = json.dumps(
        {
            "model": profile.model,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except (OSError, urllib.error.URLError) as exc:
        raise ProviderError(f"cannot unload Ollama benchmark model: {exc}") from exc
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        allocation, _ = _ollama_allocation(profile.model)
        if not allocation:
            return
        time.sleep(0.25)
    raise ProviderError("Ollama benchmark model did not unload after the task boundary")


@dataclass(frozen=True)
class RuntimeEnvironment:
    schema_version: int
    platform_system: str
    kernel_release: str
    architecture: str
    python_version: str
    cpu_model: str
    logical_cpu_count: int
    memory_bytes: int
    gpu_name: str
    gpu_uuid: str
    gpu_driver: str
    gpu_memory_bytes: int
    accelerator_allocation: str
    runtime_context_tokens: int
    clock_source: str
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("runtime environment schema_version must be 1")
        for name in (
            "platform_system",
            "kernel_release",
            "architecture",
            "python_version",
            "cpu_model",
            "clock_source",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"runtime environment {name} must be non-empty")
        for name in (
            "logical_cpu_count",
            "memory_bytes",
            "gpu_memory_bytes",
            "runtime_context_tokens",
        ):
            _non_negative_int(getattr(self, name), f"runtime environment {name}")
        if self.logical_cpu_count < 1 or self.memory_bytes < 1:
            raise ValueError("runtime CPU and memory inventory must be available")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("runtime environment signature mismatch")
        object.__setattr__(self, "signature", expected)


def collect_runtime_environment(model: str) -> RuntimeEnvironment:
    gpu_name, gpu_uuid, gpu_driver, gpu_memory_bytes = _nvidia_inventory()
    allocation, runtime_context = _ollama_allocation(model)
    payload = {
        "schema_version": 1,
        "platform_system": platform.system(),
        "kernel_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_model": _cpu_model(),
        "logical_cpu_count": os.cpu_count() or 0,
        "memory_bytes": _memory_bytes(),
        "gpu_name": gpu_name,
        "gpu_uuid": gpu_uuid,
        "gpu_driver": gpu_driver,
        "gpu_memory_bytes": gpu_memory_bytes,
        "accelerator_allocation": allocation,
        "runtime_context_tokens": runtime_context,
        "clock_source": "time.perf_counter_ns",
    }
    return RuntimeEnvironment(**payload)


@dataclass(frozen=True)
class BoundProviderProfile:
    schema_version: int
    provider: str
    endpoint_type: str
    base_url: str
    status: str
    model: str
    model_digest: str
    model_family: str
    parameter_size: str
    quantization_level: str
    model_size_bytes: int
    model_info_hash: str
    reasoning_effort: str
    context_budget_tokens: int
    max_output_tokens: int
    timeout_ms: int
    max_transport_retries: int
    max_reasoning_samples: int
    decoding: str
    seed: str
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("provider profile schema_version must be 1")
        for name in (
            "provider",
            "endpoint_type",
            "base_url",
            "status",
            "model",
            "model_digest",
            "model_info_hash",
            "reasoning_effort",
            "decoding",
            "seed",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"provider profile {name} must be non-empty")
        if self.status != "ready":
            raise ValueError("provider profile must be ready")
        if not re.fullmatch(r"[0-9a-f]{64}", self.model_digest):
            raise ValueError("provider model digest must be a SHA-256 value")
        for name in (
            "model_size_bytes",
            "context_budget_tokens",
            "max_output_tokens",
            "timeout_ms",
            "max_transport_retries",
            "max_reasoning_samples",
        ):
            _non_negative_int(getattr(self, name), f"provider profile {name}")
        if self.max_transport_retries != 0:
            raise ValueError("model benchmark requires zero transport retries")
        if (
            self.model_size_bytes < 1
            or self.context_budget_tokens < 1
            or self.max_output_tokens < 1
            or self.timeout_ms < 1
            or self.max_reasoning_samples < 1
        ):
            raise ValueError("provider capacity metadata must be positive")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("provider profile signature mismatch")
        object.__setattr__(self, "signature", expected)


def bind_provider_profile(provider: Any) -> BoundProviderProfile:
    config = getattr(provider, "config", None)
    if config is None:
        raise PolicyError("bound benchmark provider must expose ProviderConfig")
    preflight = provider.preflight()
    if not isinstance(preflight, Mapping):
        raise PolicyError("provider preflight must return an object")
    model_info = preflight.get("model_info", {})
    if not isinstance(model_info, Mapping):
        raise PolicyError("provider model_info must be an object")
    base_url = _clean_base_url(str(preflight.get("base_url", config.base_url)))
    decoding = (
        "provider_default;temperature="
        f"{model_info.get('general.sampling.temp', 'unknown')};top_p="
        f"{model_info.get('general.sampling.top_p', 'unknown')}"
    )
    try:
        return BoundProviderProfile(
            schema_version=1,
            provider=str(preflight.get("provider", "")),
            endpoint_type=str(preflight.get("endpoint_type", "")),
            base_url=base_url,
            status=str(preflight.get("status", "")),
            model=str(preflight.get("model", config.model)),
            model_digest=str(preflight.get("model_digest", "")),
            model_family=str(preflight.get("model_family", "")),
            parameter_size=str(preflight.get("parameter_size", "")),
            quantization_level=str(preflight.get("quantization_level", "")),
            model_size_bytes=int(preflight.get("model_size", 0)),
            model_info_hash=stable_hash(dict(model_info)),
            reasoning_effort=str(
                preflight.get("reasoning_effort", config.reasoning_effort or "provider_default")
            ),
            context_budget_tokens=int(config.context_budget_tokens),
            max_output_tokens=int(config.max_output_tokens),
            timeout_ms=int(float(config.timeout_seconds) * 1000),
            max_transport_retries=int(config.max_transport_retries),
            max_reasoning_samples=int(config.max_reasoning_samples),
            decoding=decoding,
            seed="unsupported",
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError(f"provider identity is incomplete: {exc}") from exc


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    failures: int

    def delta(self, earlier: "ProviderUsageSnapshot") -> "ProviderUsageSnapshot":
        return ProviderUsageSnapshot(
            calls=self.calls - earlier.calls,
            input_tokens=self.input_tokens - earlier.input_tokens,
            output_tokens=self.output_tokens - earlier.output_tokens,
            total_tokens=self.total_tokens - earlier.total_tokens,
            failures=self.failures - earlier.failures,
        )


class InstrumentedProvider:
    def __init__(
        self,
        provider: Any,
        *,
        profile: BoundProviderProfile | None = None,
        runtime_probe: Callable[[str], RuntimeEnvironment] | None = None,
    ):
        self.provider = provider
        self.config = provider.config
        self.profile = profile
        self.runtime_probe = runtime_probe
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.failures = 0
        self.response_hashes: List[str] = []
        self.runtime_observation_hashes: set[str] = set()
        self.latest_runtime: RuntimeEnvironment | None = None
        self.observed_temperatures: set[str] = set()
        self.observed_top_p: set[str] = set()

    def preflight(self) -> Mapping[str, Any]:
        return self.provider.preflight()

    def snapshot(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot(
            calls=self.calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
            failures=self.failures,
        )

    def _record_response(self, response: Any) -> None:
        payload = _mapping(response)
        usage = _mapping(payload.get("usage", {}))
        if not usage:
            raise ProviderError("provider response omitted token usage")
        input_tokens = _non_negative_int(usage.get("input_tokens", 0), "input tokens")
        output_tokens = _non_negative_int(usage.get("output_tokens", 0), "output tokens")
        total_tokens = _non_negative_int(
            usage.get("total_tokens", input_tokens + output_tokens),
            "total tokens",
        )
        if total_tokens < 1:
            raise ProviderError("provider response reported no token usage")
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        if "temperature" in payload:
            self.observed_temperatures.add(str(payload["temperature"]))
        if "top_p" in payload:
            self.observed_top_p.add(str(payload["top_p"]))
        sanitized = {
            "output_text": response_text(response),
            "status": str(payload.get("status", "")),
            "model": str(payload.get("model", "")),
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
        }
        self.response_hashes.append(stable_hash(sanitized))
        if self.runtime_probe is not None:
            runtime = self.runtime_probe(self.config.model)
            if self.profile is not None and self.profile.endpoint_type == "ollama_local":
                if runtime.accelerator_allocation != "100% GPU":
                    raise ProviderError(
                        "local model response was not observed at 100% GPU allocation"
                    )
                if runtime.runtime_context_tokens < self.profile.context_budget_tokens:
                    raise ProviderError(
                        "Ollama runtime context is smaller than the configured context budget"
                    )
                if runtime.runtime_context_tokens < (
                    self.profile.context_budget_tokens + self.profile.max_output_tokens
                ):
                    raise ProviderError(
                        "Ollama runtime context cannot contain the configured input and output budgets"
                    )
            self.latest_runtime = runtime
            self.runtime_observation_hashes.add(runtime.signature)

    def create_response(
        self,
        *,
        instructions: str,
        input_items: List[Any],
        tools: List[Dict[str, Any]],
    ) -> Any:
        self.calls += 1
        try:
            response = self.provider.create_response(
                instructions=instructions,
                input_items=input_items,
                tools=tools,
            )
        except (ContextBudgetError, ProviderError):
            self.failures += 1
            raise
        try:
            self._record_response(response)
        except (PolicyError, ProviderError, ValueError):
            self.failures += 1
            raise
        return response

    def create_responses(
        self,
        *,
        requests: List[Mapping[str, Any]],
        max_responses: int,
    ) -> List[Any]:
        if not requests:
            raise ProviderError("multi-response request must be non-empty")
        if len(requests) > int(max_responses):
            raise ProviderError("multi-response request exceeds benchmark call budget")
        responses = []
        halted_error = ""
        for request in requests:
            if halted_error:
                responses.append({"type": "reasoning_error", "error": halted_error})
                continue
            try:
                failures_before = self.failures
                response = self.create_response(
                    instructions=str(request.get("instructions", "")),
                    input_items=list(request.get("input_items", ())),
                    tools=list(request.get("tools", ())),
                )
                parse_json_object(response_text(response))
                responses.append(response)
            except (ContextBudgetError, ProviderError) as exc:
                if self.failures == failures_before:
                    self.failures += 1
                halted_error = f"{type(exc).__name__}: {exc}"
                responses.append({"type": "reasoning_error", "error": halted_error})
        return responses


def parse_answer_response(
    response: Any,
    *,
    task: BenchmarkTask,
    system_id: str,
) -> BenchmarkObservation:
    payload = parse_json_object(response_text(response))
    unknown = sorted(set(payload) - ANSWER_RESPONSE_KEYS)
    missing = sorted(ANSWER_RESPONSE_KEYS - set(payload))
    if missing:
        raise ProviderError(f"benchmark answer is missing fields: {missing!r}")
    if unknown:
        raise ProviderError(f"benchmark answer contains unknown fields: {unknown!r}")
    evidence_ids = tuple(sorted({str(value) for value in payload["evidence_ids"] if str(value)}))
    available = set(task.required_evidence_ids)
    if set(evidence_ids) - available:
        raise ProviderError("benchmark answer cited an unavailable evidence identifier")
    terminal_state = str(payload["terminal_state"])
    if terminal_state not in TERMINAL_STATES:
        raise ProviderError("benchmark answer terminal state is invalid")
    answer = str(payload["answer"]).strip()
    if terminal_state == "ANSWER" and not answer:
        raise ProviderError("benchmark answer terminal state requires an answer")
    counterexamples = tuple(
        sorted({str(value).strip() for value in payload["counterexamples"] if str(value).strip()})
    )
    return BenchmarkObservation(
        schema_version=1,
        problem_id=task.problem_id,
        system_id=system_id,
        answer=answer,
        confidence_bp=_bounded_score(payload["confidence_bp"], "benchmark confidence"),
        evidence_ids=evidence_ids,
        counterexamples=counterexamples,
        terminal_state=terminal_state,
    )


def _task_input(task: BenchmarkTask) -> Mapping[str, Any]:
    return {
        "problem_id": task.problem_id,
        "category": task.category,
        "problem": task.prompt,
        "available_evidence_ids": list(task.required_evidence_ids),
        "source_refs": list(task.source_refs),
        "output_contract": {
            "answer": "short answer",
            "confidence_bp": "integer 0..10000",
            "evidence_ids": "subset of available_evidence_ids",
            "counterexamples": "zero or more concise challenges",
            "terminal_state": list(TERMINAL_STATES),
        },
    }


def _failure_observation(
    *,
    task: BenchmarkTask,
    system_id: str,
    exc: Exception,
    token_count: int,
    provider_calls: int,
    wall_time_ms: int,
) -> BenchmarkObservation:
    return BenchmarkObservation(
        schema_version=1,
        problem_id=task.problem_id,
        system_id=system_id,
        answer=f"{type(exc).__name__}: {exc}",
        confidence_bp=0,
        evidence_ids=(),
        counterexamples=(),
        token_count=max(0, token_count),
        tool_calls=0,
        collisions=max(1, provider_calls),
        retries=0,
        wall_time_ms=max(0, wall_time_ms),
        terminal_state="INSUFFICIENT_EVIDENCE",
    )


class ProviderBenchmarkExecutor:
    instructions = BASE_INSTRUCTIONS
    pipeline = "direct_provider"

    def __init__(
        self,
        *,
        system_id: str,
        provider: Any,
        source_snapshot_hash: str,
        runtime_collector: Callable[[str], RuntimeEnvironment] = collect_runtime_environment,
        runtime_releaser: Callable[[BoundProviderProfile], None] = release_ollama_runtime,
    ):
        if system_id not in BENCHMARK_SYSTEM_IDS:
            raise PolicyError(f"unknown benchmark system: {system_id}")
        if not source_snapshot_hash:
            raise PolicyError("model benchmark source snapshot must be explicit")
        self.system_id = system_id
        self.source_snapshot_hash = source_snapshot_hash
        self.profile = bind_provider_profile(provider)
        self.runtime_collector = runtime_collector
        self.runtime_releaser = runtime_releaser
        self.provider = InstrumentedProvider(
            provider,
            profile=self.profile,
            runtime_probe=runtime_collector,
        )

    def identity_descriptor(self) -> Mapping[str, Any]:
        return {
            "system_id": self.system_id,
            "executor": type(self).__name__,
            "provider": self.profile.provider,
            "model": self.profile.model,
            "reasoning_effort": self.profile.reasoning_effort,
            "context_budget_tokens": self.profile.context_budget_tokens,
            "max_output_tokens": self.profile.max_output_tokens,
            "decoding": self.profile.decoding,
            "pipeline": self.pipeline,
            "source_snapshot_hash": self.source_snapshot_hash,
            "prompt_template_hash": stable_hash(self.instructions),
            "evidence_context_mode": MODEL_EVIDENCE_CONTEXT_MODE,
            "provider_binding": asdict(self.profile),
        }

    def release_runtime(self) -> None:
        self.runtime_releaser(self.profile)

    def descriptor(self) -> Mapping[str, Any]:
        runtime = self.provider.latest_runtime or self.runtime_collector(self.profile.model)
        if self.profile.endpoint_type == "ollama_local":
            if runtime.accelerator_allocation != "100% GPU":
                raise PolicyError(
                    "local model benchmark requires observed 100% GPU allocation"
                )
            if runtime.runtime_context_tokens < self.profile.context_budget_tokens:
                raise PolicyError(
                    "Ollama runtime context is smaller than the configured context budget"
                )
            if runtime.runtime_context_tokens < (
                self.profile.context_budget_tokens + self.profile.max_output_tokens
            ):
                raise PolicyError(
                    "Ollama runtime context cannot contain the configured input and output budgets"
                )
        telemetry = {
            "provider_calls": self.provider.calls,
            "input_tokens": self.provider.input_tokens,
            "output_tokens": self.provider.output_tokens,
            "total_tokens": self.provider.total_tokens,
            "provider_failures": self.provider.failures,
            "response_hashes": tuple(self.provider.response_hashes),
            "runtime_observation_hashes": tuple(
                sorted(self.provider.runtime_observation_hashes)
            ),
            "observed_temperatures": tuple(sorted(self.provider.observed_temperatures)),
            "observed_top_p": tuple(sorted(self.provider.observed_top_p)),
            "nondeterminism_status": "single_run_not_reproducibility_evidence",
        }
        return {
            **self.identity_descriptor(),
            "runtime_environment": asdict(runtime),
            "telemetry": telemetry,
        }

    def _request(self, task: BenchmarkTask) -> Any:
        return self.provider.create_response(
            instructions=self.instructions,
            input_items=[
                {
                    "role": "user",
                    "content": json.dumps(_task_input(task), sort_keys=True, ensure_ascii=False),
                }
            ],
            tools=[],
        )

    def execute(self, task: BenchmarkTask) -> BenchmarkObservation:
        before = self.provider.snapshot()
        started = time.perf_counter_ns()
        try:
            parsed = parse_answer_response(
                self._request(task),
                task=task,
                system_id=self.system_id,
            )
        except (ContextBudgetError, PolicyError, ProviderError, ValueError) as exc:
            elapsed = (time.perf_counter_ns() - started) // 1_000_000
            usage = self.provider.snapshot().delta(before)
            return _failure_observation(
                task=task,
                system_id=self.system_id,
                exc=exc,
                token_count=usage.total_tokens,
                provider_calls=usage.calls,
                wall_time_ms=elapsed,
            )
        elapsed = (time.perf_counter_ns() - started) // 1_000_000
        usage = self.provider.snapshot().delta(before)
        return BenchmarkObservation(
            **{
                **asdict(parsed),
                "token_count": usage.total_tokens,
                "tool_calls": 0,
                "collisions": usage.failures,
                "retries": 0,
                "wall_time_ms": elapsed,
                "signature": "",
            }
        )


class BaseModelBenchmarkExecutor(ProviderBenchmarkExecutor):
    instructions = BASE_INSTRUCTIONS
    pipeline = "direct_provider_task_isolated"


class OIECBenchmarkExecutor(ProviderBenchmarkExecutor):
    instructions = OIEC_INSTRUCTIONS
    pipeline = "ourd_single_path_governed_prompt_task_isolated"


def _difficulty_for(task: BenchmarkTask) -> int:
    return {
        "arithmetic": 1_000,
        "logic": 3_000,
        "ambiguity_resolution": 4_000,
        "debugging": 5_000,
        "evidence_synthesis": 5_000,
        "causal_reasoning": 6_000,
        "scientific_inference": 6_000,
        "adversarial": 7_000,
    }[task.category]


def _benchmark_hypotheses() -> Tuple[Mapping[str, Any], ...]:
    propositions = (
        "The prompt supports a direct answer under its stated facts.",
        "The prompt is underdetermined and requires an epistemic stop.",
        "A counterexample or alternative explanation defeats the direct answer.",
        "A governance or scope constraint requires refusal or clarification.",
    )
    return tuple(
        {
            "hypothesis_id": f"benchmark-hypothesis-{index}",
            "proposition": proposition,
            "prior_bp": 2_500,
            "posterior_bp": 2_500,
            "supporting_evidence": (),
            "conflicting_evidence": (),
            "assumptions": (),
            "falsifiers": (),
            "status": "ACTIVE",
        }
        for index, proposition in enumerate(propositions, 1)
    )


def _selected_path(candidates: CandidateSet):
    return next(
        (path for path in candidates.paths if path.path_id == candidates.selected_path_id),
        None,
    )


def _terminal_from_certificate(certificate: ReasoningCertificate) -> str:
    if certificate.decision == "ACCEPT":
        return "ANSWER"
    if certificate.decision in {"STOP_NO_VALUE", "STOP_UNRESOLVED"}:
        return "EPISTEMIC_STOP"
    if certificate.decision in {"REVISE", "REGENERATE"}:
        return "INSUFFICIENT_EVIDENCE"
    return "NO_SURVIVING_HYPOTHESIS"


class OIECSRBenchmarkExecutor(ProviderBenchmarkExecutor):
    instructions = "OIEC-SR four-path proposer, verifier, falsifier, and synthesizer contracts"
    pipeline = "super_reasoning_kernel_four_path_grounded_topology_v2_task_isolated"

    def __init__(self, **kwargs: Any):
        super().__init__(system_id="oiec_sr", **kwargs)
        self.kernel = SuperReasoningKernel(
            max_candidates=4,
            max_provider_calls=11,
            minimum_voi_bp=100,
        )

    def execute(self, task: BenchmarkTask) -> BenchmarkObservation:
        before = self.provider.snapshot()
        started = time.perf_counter_ns()
        try:
            boundary_signature = stable_hash(
                {
                    "mode": "read_only_benchmark",
                    "source_snapshot_hash": self.source_snapshot_hash,
                    "task_signature": task.signature,
                }
            )
            dimension_signature = stable_hash(
                {
                    "max_candidate_actions": 4,
                    "max_active_hypotheses": 4,
                    "max_decomposition_depth": 2,
                    "max_branch_factor": 8,
                }
            )
            problem = self.kernel.create_problem(
                statement=task.prompt,
                goal=(
                    "Return the shortest exact answer justified by the stated problem, "
                    "or stop explicitly when the evidence is insufficient."
                ),
                source_snapshot_hash=self.source_snapshot_hash,
                boundary_signature=boundary_signature,
                dimension_signature=dimension_signature,
                evidence_ids=task.required_evidence_ids,
                uncertainty_bp=_difficulty_for(task),
                difficulty_bp=_difficulty_for(task),
                mutually_exclusive_hypotheses=False,
            )
            hypothesis_state = self.kernel.build_hypothesis_state(
                _benchmark_hypotheses(),
                problem_id=problem.problem_id,
                max_hypotheses=4,
                mutually_exclusive=False,
            )
            dimension_budget = SimpleNamespace(
                max_active_hypotheses=4,
                max_candidate_actions=4,
                max_decomposition_depth=2,
                max_branch_factor=8,
                max_active_relations=64,
            )
            _, _, candidates, _, certificate = self.kernel.run(
                provider=self.provider,
                problem=problem,
                hypotheses=hypothesis_state,
                dimension_budget=dimension_budget,
                declared_evidence_ids=task.required_evidence_ids,
            )
            selected = _selected_path(candidates)
            answer = candidates.synthesized_conclusion.strip()
            if not answer and selected is not None:
                answer = selected.conclusion.strip()
            evidence_ids = tuple(
                sorted(
                    {
                        evidence_id
                        for step in (() if selected is None else selected.steps)
                        for evidence_id in step.evidence_ids
                        if evidence_id in set(task.required_evidence_ids)
                    }
                )
            )
            selected_falsifier = next(
                (
                    report
                    for report in candidates.falsifier_reports
                    if report.path_id == candidates.selected_path_id
                ),
                None,
            )
            counterexamples = (
                () if selected_falsifier is None else selected_falsifier.counterexamples
            )
            terminal_state = _terminal_from_certificate(certificate)
            if terminal_state == "ANSWER" and not answer:
                raise ProviderError("accepted reasoning certificate has no answer")
        except (ContextBudgetError, PolicyError, ProviderError, ValueError) as exc:
            elapsed = (time.perf_counter_ns() - started) // 1_000_000
            usage = self.provider.snapshot().delta(before)
            return _failure_observation(
                task=task,
                system_id=self.system_id,
                exc=exc,
                token_count=usage.total_tokens,
                provider_calls=usage.calls,
                wall_time_ms=elapsed,
            )
        elapsed = (time.perf_counter_ns() - started) // 1_000_000
        usage = self.provider.snapshot().delta(before)
        return BenchmarkObservation(
            schema_version=1,
            problem_id=task.problem_id,
            system_id=self.system_id,
            answer=answer,
            confidence_bp=certificate.derived_confidence_bp,
            evidence_ids=evidence_ids,
            counterexamples=counterexamples,
            token_count=usage.total_tokens,
            tool_calls=0,
            collisions=certificate.contradiction_count + usage.failures,
            retries=0,
            wall_time_ms=elapsed,
            terminal_state=terminal_state,
        )


def make_model_benchmark_executors(
    *,
    provider_factory: Callable[[], Any],
    source_snapshot_hash: str,
    runtime_collector: Callable[[str], RuntimeEnvironment] = collect_runtime_environment,
    runtime_releaser: Callable[[BoundProviderProfile], None] = release_ollama_runtime,
) -> Tuple[ProviderBenchmarkExecutor, ...]:
    return (
        BaseModelBenchmarkExecutor(
            system_id="base",
            provider=provider_factory(),
            source_snapshot_hash=source_snapshot_hash,
            runtime_collector=runtime_collector,
            runtime_releaser=runtime_releaser,
        ),
        OIECBenchmarkExecutor(
            system_id="oiec",
            provider=provider_factory(),
            source_snapshot_hash=source_snapshot_hash,
            runtime_collector=runtime_collector,
            runtime_releaser=runtime_releaser,
        ),
        OIECSRBenchmarkExecutor(
            provider=provider_factory(),
            source_snapshot_hash=source_snapshot_hash,
            runtime_collector=runtime_collector,
            runtime_releaser=runtime_releaser,
        ),
    )


__all__ = [
    "BASE_INSTRUCTIONS",
    "MODEL_EVIDENCE_CONTEXT_MODE",
    "MODEL_EXECUTION_MODE",
    "MODEL_QUALIFICATION_STATUS",
    "OIEC_INSTRUCTIONS",
    "BaseModelBenchmarkExecutor",
    "BoundProviderProfile",
    "InstrumentedProvider",
    "OIECBenchmarkExecutor",
    "OIECSRBenchmarkExecutor",
    "ProviderBenchmarkExecutor",
    "ProviderUsageSnapshot",
    "RuntimeEnvironment",
    "bind_provider_profile",
    "collect_runtime_environment",
    "make_model_benchmark_executors",
    "parse_answer_response",
    "release_ollama_runtime",
]
