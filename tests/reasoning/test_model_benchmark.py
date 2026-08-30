from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from ourd.errors import PolicyError, ProviderError
from ourd.providers.base import ProviderConfig
from ourd.reasoning.benchmark import (
    BENCHMARK_SYSTEM_IDS,
    BenchmarkTask,
    SourceFileRecord,
    run_benchmark,
)
from ourd.reasoning.model_benchmark import (
    MODEL_EXECUTION_MODE,
    MODEL_QUALIFICATION_STATUS,
    BaseModelBenchmarkExecutor,
    InstrumentedProvider,
    OIECBenchmarkExecutor,
    RuntimeEnvironment,
    bind_provider_profile,
    make_model_benchmark_executors,
    release_ollama_runtime,
)
from ourd.reasoning.models import stable_hash
from ourd.reasoning.verifier import PROCESS_CHECKS
from tools.run_reasoning_model_benchmark import _write_new


def runtime_environment(allocation: str = "100% GPU") -> RuntimeEnvironment:
    return RuntimeEnvironment(
        schema_version=1,
        platform_system="Linux",
        kernel_release="test-kernel",
        architecture="x86_64",
        python_version="3.12.0",
        cpu_model="Test CPU",
        logical_cpu_count=8,
        memory_bytes=16_000_000_000,
        gpu_name="Test GPU",
        gpu_uuid="GPU-test",
        gpu_driver="1.0",
        gpu_memory_bytes=16_000_000_000,
        accelerator_allocation=allocation,
        runtime_context_tokens=8192,
        clock_source="time.perf_counter_ns",
    )


def task() -> BenchmarkTask:
    return BenchmarkTask.from_dict(
        {
            "schema_version": 1,
            "problem_id": "logic-test",
            "category": "logic",
            "prompt": "All governed mutations require EON. No EON action exists. Is mutation permitted?",
            "oracle": {"kind": "exact", "expected": "no"},
            "oracle_method": "modus tollens",
            "required_evidence_ids": ["logic:eon-required"],
            "required_counterexamples": [],
            "source_refs": ["README.md"],
        }
    )


class FakeBoundProvider:
    def __init__(self, *, model_digest: str = "a" * 64, fail: bool = False):
        self.config = ProviderConfig(
            model="fake-bound-model",
            base_url="http://127.0.0.1:11434/v1",
            reasoning_effort="medium",
            max_output_tokens=2048,
            context_budget_tokens=6000,
            timeout_seconds=60,
            max_transport_retries=0,
            max_reasoning_samples=16,
        )
        self.model_digest = model_digest
        self.fail = fail
        self.requests = []

    def preflight(self):
        return {
            "provider": "openai_responses",
            "model": self.config.model,
            "base_url": self.config.base_url,
            "endpoint_type": "ollama_local",
            "context_budget_tokens": self.config.context_budget_tokens,
            "max_output_tokens": self.config.max_output_tokens,
            "reasoning_effort": self.config.reasoning_effort,
            "max_transport_retries": 0,
            "max_reasoning_samples": 16,
            "status": "ready",
            "model_family": "fake",
            "parameter_size": "1B",
            "quantization_level": "Q4",
            "model_info": {
                "general.sampling.temp": 1,
                "general.sampling.top_p": 0.95,
            },
            "model_digest": self.model_digest,
            "model_size": 1_000_000,
        }

    def _response(self, text: str):
        return {
            "model": self.config.model,
            "status": "completed",
            "temperature": 1,
            "top_p": 1,
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "output": [
                {
                    "type": "reasoning",
                    "encrypted_content": "private-reasoning-must-not-persist",
                },
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": text}],
                },
            ],
        }

    def create_response(self, *, instructions, input_items, tools):
        self.requests.append(
            {"instructions": instructions, "input_items": input_items, "tools": tools}
        )
        if self.fail:
            raise ProviderError("synthetic provider failure")
        lowered = instructions.casefold()
        payload = json.loads(input_items[0]["content"])
        if "proposer" in lowered:
            problem = payload["problem"]
            hypothesis_ids = [item["hypothesis_id"] for item in payload["hypotheses"]]
            perspective = payload["perspective"]
            return self._response(
                json.dumps(
                    {
                        "conclusion": "no",
                        "hypothesis_ids": hypothesis_ids[:1],
                        "provider_confidence_bp": 9500,
                        "estimated_cost_bp": 500,
                        "goal_relevance_bp": 9000,
                        "risk_bp": 500,
                        "steps": [
                            {
                                "step_id": f"{perspective}-step",
                                "claim": f"{perspective} supports no",
                                "premises": ["problem", hypothesis_ids[0]],
                                "evidence_ids": problem["evidence_ids"],
                                "inference": "deductive",
                                "confidence_bp": 9500,
                                "assumptions": [],
                                "falsifier": "An EON action exists.",
                            }
                        ],
                    }
                )
            )
        if "process verifier" in lowered:
            candidate = payload["candidate"]
            return self._response(
                json.dumps(
                    {
                        "steps": [
                            {
                                "step_id": item["step_id"],
                                "checks": {name: True for name in PROCESS_CHECKS},
                                "failures": [],
                            }
                            for item in candidate["steps"]
                        ],
                        "contradictions": [],
                    }
                )
            )
        if "falsifier" in lowered:
            return self._response(
                json.dumps(
                    {
                        "searched_falsifiers": ["An EON action exists."],
                        "counterexamples": [],
                        "contradicted_step_ids": [],
                        "unresolved_defeat_conditions": [],
                        "critical": False,
                        "survival_bp": 9000,
                    }
                )
            )
        if "synthesizer" in lowered:
            return self._response(
                json.dumps(
                    {
                        "conclusion": "no",
                        "source_path_ids": [payload["selected_winner"]],
                    }
                )
            )
        return self._response(
            json.dumps(
                {
                    "answer": "no",
                    "confidence_bp": 9000,
                    "evidence_ids": ["logic:eon-required"],
                    "counterexamples": [],
                    "terminal_state": "ANSWER",
                }
            )
        )


class ModelBenchmarkTests(unittest.TestCase):
    def test_provider_binding_requires_exact_model_digest(self) -> None:
        with self.assertRaises(PolicyError):
            bind_provider_profile(FakeBoundProvider(model_digest=""))

    def test_provider_binding_rejects_credentials_in_base_url(self) -> None:
        provider = FakeBoundProvider()
        provider.config.base_url = "http://user:secret@127.0.0.1:11434/v1"
        with self.assertRaises(PolicyError):
            bind_provider_profile(provider)

    def test_direct_executor_does_not_persist_private_reasoning(self) -> None:
        provider = FakeBoundProvider()
        executor = BaseModelBenchmarkExecutor(
            system_id="base",
            provider=provider,
            source_snapshot_hash="b" * 64,
            runtime_collector=lambda _: runtime_environment(),
        )
        observation = executor.execute(task())
        descriptor = executor.descriptor()
        serialized = json.dumps({"observation": asdict(observation), "descriptor": descriptor})
        self.assertEqual("no", observation.answer)
        self.assertEqual(15, observation.token_count)
        self.assertNotIn("private-reasoning-must-not-persist", serialized)
        self.assertEqual(1, descriptor["telemetry"]["provider_calls"])
        self.assertEqual(1, len(descriptor["telemetry"]["response_hashes"]))
        self.assertEqual(1, len(descriptor["telemetry"]["runtime_observation_hashes"]))

    def test_oracle_answer_and_method_do_not_enter_direct_provider_context(self) -> None:
        provider = FakeBoundProvider()
        executor = OIECBenchmarkExecutor(
            system_id="oiec",
            provider=provider,
            source_snapshot_hash="b" * 64,
            runtime_collector=lambda _: runtime_environment(),
        )
        executor.execute(task())
        request = json.dumps(provider.requests[0], sort_keys=True)
        self.assertNotIn("modus tollens", request)
        self.assertNotIn('"expected"', request)

    def test_provider_failure_is_recorded_as_result(self) -> None:
        executor = BaseModelBenchmarkExecutor(
            system_id="base",
            provider=FakeBoundProvider(fail=True),
            source_snapshot_hash="b" * 64,
            runtime_collector=lambda _: runtime_environment(),
        )
        observation = executor.execute(task())
        self.assertEqual("INSUFFICIENT_EVIDENCE", observation.terminal_state)
        self.assertEqual(1, observation.collisions)
        self.assertEqual(0, observation.retries)

    def test_reasoning_batch_halts_after_first_malformed_response(self) -> None:
        provider = FakeBoundProvider()
        provider.create_response = lambda **_: provider._response("")
        instrumented = InstrumentedProvider(provider)
        responses = instrumented.create_responses(
            requests=[
                {"instructions": "proposer", "input_items": [], "tools": []}
                for _ in range(4)
            ],
            max_responses=4,
        )
        self.assertEqual(4, len(responses))
        self.assertEqual(1, instrumented.calls)
        self.assertEqual(1, instrumented.failures)
        self.assertTrue(all(item["type"] == "reasoning_error" for item in responses))

    def test_model_artifact_write_is_append_only_and_checksummed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.json"
            _write_new(path, "{}\n")
            self.assertEqual("{}\n", path.read_text(encoding="utf-8"))
            checksum = path.with_suffix(".sha256").read_text(encoding="utf-8")
            self.assertTrue(checksum.endswith("  run.json\n"))
            with self.assertRaises(PolicyError):
                _write_new(path, "{}\n")

    def test_local_descriptor_fails_closed_without_full_gpu_allocation(self) -> None:
        executor = BaseModelBenchmarkExecutor(
            system_id="base",
            provider=FakeBoundProvider(),
            source_snapshot_hash="b" * 64,
            runtime_collector=lambda _: runtime_environment("50% CPU/50% GPU"),
        )
        executor.execute(task())
        with self.assertRaises(PolicyError):
            executor.descriptor()

    def test_four_path_model_run_is_provider_and_hardware_bound(self) -> None:
        source_files = (SourceFileRecord(path="fixture", sha256="c" * 64),)
        source_hash = stable_hash([asdict(item) for item in source_files])
        executors = make_model_benchmark_executors(
            provider_factory=FakeBoundProvider,
            source_snapshot_hash=source_hash,
            runtime_collector=lambda _: runtime_environment(),
            runtime_releaser=lambda _: None,
        )
        run = run_benchmark(
            tasks=(task(),),
            executors=executors,
            generated_on="2026-08-28",
            package_version="test",
            git_head="head",
            worktree_dirty=True,
            source_files=source_files,
            execution_mode=MODEL_EXECUTION_MODE,
            qualification_status=MODEL_QUALIFICATION_STATUS,
        )
        self.assertEqual(BENCHMARK_SYSTEM_IDS, tuple(item["system_id"] for item in run.systems))
        self.assertFalse(run.performance_claim_allowed)
        self.assertEqual(
            "super_reasoning_kernel_four_path_grounded_topology_v2_task_isolated",
            run.systems[2]["pipeline"],
        )
        self.assertEqual(11, run.systems[2]["telemetry"]["provider_calls"])
        self.assertEqual(10_000, run.results[2].correctness_bp)
        for descriptor in run.systems:
            self.assertTrue(descriptor["provider_binding"]["model_digest"])
            self.assertEqual("100% GPU", descriptor["runtime_environment"]["accelerator_allocation"])
            self.assertEqual(
                "single_run_not_reproducibility_evidence",
                descriptor["telemetry"]["nondeterminism_status"],
            )

    def test_provider_bound_run_releases_runtime_after_each_task(self) -> None:
        released = []
        source_files = (SourceFileRecord(path="fixture", sha256="c" * 64),)
        source_hash = stable_hash([asdict(item) for item in source_files])
        executors = make_model_benchmark_executors(
            provider_factory=FakeBoundProvider,
            source_snapshot_hash=source_hash,
            runtime_collector=lambda _: runtime_environment(),
            runtime_releaser=lambda profile: released.append(profile.model),
        )
        run_benchmark(
            tasks=(task(),),
            executors=executors,
            generated_on="2026-08-28",
            package_version="test",
            git_head="head",
            worktree_dirty=True,
            source_files=source_files,
            execution_mode=MODEL_EXECUTION_MODE,
            qualification_status=MODEL_QUALIFICATION_STATUS,
        )
        self.assertEqual(["fake-bound-model"] * 3, released)

    @mock.patch("ourd.reasoning.model_benchmark.time.sleep", return_value=None)
    @mock.patch(
        "ourd.reasoning.model_benchmark._ollama_allocation",
        side_effect=[("100% GPU", 4096), ("", 0)],
    )
    @mock.patch("ourd.reasoning.model_benchmark.urllib.request.urlopen")
    def test_ollama_release_uses_zero_keep_alive(
        self,
        urlopen,
        _allocation,
        _sleep,
    ) -> None:
        profile = bind_provider_profile(FakeBoundProvider())
        release_ollama_runtime(profile)
        request = urlopen.call_args.args[0]
        self.assertEqual("http://127.0.0.1:11434/api/generate", request.full_url)
        self.assertEqual(0, json.loads(request.data)["keep_alive"])


if __name__ == "__main__":
    unittest.main()
