from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import (
    BENCHMARK_CATEGORIES,
    BENCHMARK_SYSTEM_IDS,
    BenchmarkObservation,
    BenchmarkTask,
    benchmark_json,
    load_benchmark_run,
    load_benchmark_tasks,
    load_fixture_observations,
    verify_benchmark_checksum,
)
from tools.run_reasoning_benchmark import (
    DEFAULT_BENCHMARK_ROOT,
    DEFAULT_SOURCE_PATHS,
    ROOT,
    build_fixture_baseline,
)


def assert_strict_objects(test_case: unittest.TestCase, value, label: str) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object" and "properties" in value:
            test_case.assertIs(
                False,
                value.get("additionalProperties"),
                f"{label} must reject unknown fields",
            )
            test_case.assertTrue(value.get("required"), f"{label} must name required fields")
        for key, child in value.items():
            assert_strict_objects(test_case, child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_strict_objects(test_case, child, f"{label}[{index}]")


def file_hashes(paths: tuple[str, ...]) -> dict[str, str]:
    return {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in paths
    }


class ReasoningBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks = load_benchmark_tasks(DEFAULT_BENCHMARK_ROOT / "tasks")
        self.fixture_path = (
            DEFAULT_BENCHMARK_ROOT / "fixtures" / "development-v1.outputs.json"
        )

    def test_benchmark_schema_is_strict(self) -> None:
        schema = json.loads(
            (DEFAULT_BENCHMARK_ROOT / "schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema",
            schema["$schema"],
        )
        self.assertEqual(
            {
                "task",
                "observation",
                "fixture",
                "source_file",
                "provider_binding",
                "runtime_environment",
                "provider_telemetry",
                "system",
                "result",
                "summary",
                "run",
                "oracle",
            },
            set(schema["$defs"]),
        )
        assert_strict_objects(self, schema, "benchmark")

    def test_task_ids_are_unique_and_cover_every_category(self) -> None:
        problem_ids = [task.problem_id for task in self.tasks]
        self.assertEqual(len(problem_ids), len(set(problem_ids)))
        self.assertEqual(set(BENCHMARK_CATEGORIES), {task.category for task in self.tasks})
        self.assertEqual(8, len(self.tasks))

    def test_runner_preserves_task_and_system_order(self) -> None:
        run = build_fixture_baseline(
            root=ROOT,
            benchmark_root=DEFAULT_BENCHMARK_ROOT,
            generated_on="2026-08-28",
        )
        expected = [
            (task.problem_id, system_id)
            for task in self.tasks
            for system_id in BENCHMARK_SYSTEM_IDS
        ]
        self.assertEqual(expected, [(item.problem_id, item.system_id) for item in run.results])

    def test_result_binds_source_manifest_and_provider_descriptors(self) -> None:
        run = build_fixture_baseline(
            root=ROOT,
            benchmark_root=DEFAULT_BENCHMARK_ROOT,
            generated_on="2026-08-28",
        )
        self.assertTrue(run.source_manifest_hash)
        self.assertEqual(set(DEFAULT_SOURCE_PATHS), {item.path for item in run.source_files})
        for item in run.source_files:
            with self.subTest(source=item.path):
                self.assertEqual(
                    hashlib.sha256((ROOT / item.path).read_bytes()).hexdigest(),
                    item.sha256,
                )
        self.assertEqual(BENCHMARK_SYSTEM_IDS, tuple(item["system_id"] for item in run.systems))
        self.assertTrue(all(item["provider"] == "deterministic-fixture-v1" for item in run.systems))
        self.assertEqual("development_fixture_only", run.qualification_status)
        self.assertFalse(run.performance_claim_allowed)

    def test_correctness_oracle_is_explicit(self) -> None:
        for task in self.tasks:
            with self.subTest(problem_id=task.problem_id):
                self.assertTrue(task.oracle_method)
                self.assertTrue(task.oracle.expected)
                self.assertTrue(task.source_refs)

    def test_baseline_generation_is_byte_reproducible(self) -> None:
        first = build_fixture_baseline(
            root=ROOT,
            benchmark_root=DEFAULT_BENCHMARK_ROOT,
            generated_on="2026-08-28",
        )
        second = build_fixture_baseline(
            root=ROOT,
            benchmark_root=DEFAULT_BENCHMARK_ROOT,
            generated_on="2026-08-28",
        )
        self.assertEqual(first.signature, second.signature)
        self.assertEqual(benchmark_json(first), benchmark_json(second))

    def test_benchmark_does_not_mutate_source_files(self) -> None:
        before = file_hashes(DEFAULT_SOURCE_PATHS)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "baseline.json"
            run = build_fixture_baseline(
                root=ROOT,
                benchmark_root=DEFAULT_BENCHMARK_ROOT,
                generated_on="2026-08-28",
            )
            output.write_text(benchmark_json(run), encoding="utf-8")
            self.assertTrue(output.is_file())
        self.assertEqual(before, file_hashes(DEFAULT_SOURCE_PATHS))

    def test_fixture_requires_one_observation_per_system_and_task(self) -> None:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        payload["observations"] = payload["observations"][:-1]
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "incomplete.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(PolicyError):
                load_fixture_observations(fixture, self.tasks)

    def test_unknown_task_and_observation_fields_fail_closed(self) -> None:
        task_payload = {
            "schema_version": 1,
            "problem_id": "x",
            "category": "logic",
            "prompt": "p",
            "oracle": {"kind": "exact", "expected": "x"},
            "oracle_method": "exact",
            "required_evidence_ids": [],
            "required_counterexamples": [],
            "source_refs": ["fixture"],
            "unexpected": True,
        }
        with self.assertRaises(PolicyError):
            BenchmarkTask.from_dict(task_payload)

        observation_payload = {
            "schema_version": 1,
            "problem_id": "x",
            "system_id": "base",
            "answer": "x",
            "confidence_bp": 10000,
            "evidence_ids": [],
            "counterexamples": [],
            "token_count": 0,
            "tool_calls": 0,
            "collisions": 0,
            "retries": 0,
            "wall_time_ms": 0,
            "terminal_state": "ANSWER",
            "unexpected": True,
        }
        with self.assertRaises(PolicyError):
            BenchmarkObservation.from_dict(observation_payload)

    def test_checked_in_baseline_preserves_historical_integrity(self) -> None:
        baseline = DEFAULT_BENCHMARK_ROOT / "baseline-v1.json"
        checksum = DEFAULT_BENCHMARK_ROOT / "baseline-v1.sha256"
        recorded = load_benchmark_run(baseline)
        self.assertEqual(
            "a26710c08f619536f0b128977a9f9f1dde3c186a2ffd9ef503a649f487462c87",
            recorded.signature,
        )
        self.assertEqual(
            "cb10269b5016d3bbc1a7dc31d2cd753438f9431702bfed5d38425d212e914027",
            verify_benchmark_checksum(baseline, checksum),
        )


if __name__ == "__main__":
    unittest.main()
