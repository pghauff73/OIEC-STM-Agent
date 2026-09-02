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
    FixtureBenchmarkExecutor,
    benchmark_json,
    build_source_manifest,
    load_benchmark_run,
    load_benchmark_tasks,
    load_fixture_observations,
    merge_benchmark_runs,
    run_benchmark,
    score_observation,
    select_benchmark_tasks,
    verify_benchmark_checksum,
)
from tools.run_reasoning_benchmark import (
    DEFAULT_BENCHMARK_ROOT,
    DEFAULT_SOURCE_PATHS,
    ROOT,
    build_fixture_baseline,
)
from tools.merge_reasoning_benchmark_shards import main as merge_shards_main


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
        self.tasks = load_benchmark_tasks(
            DEFAULT_BENCHMARK_ROOT / "tasks" / "development-v1.jsonl"
        )
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

    def test_task_slices_are_explicit_and_bounded(self) -> None:
        selected = select_benchmark_tasks(self.tasks, start=2, count=3)
        self.assertEqual(self.tasks[2:5], selected)
        self.assertEqual(self.tasks[6:], select_benchmark_tasks(self.tasks, start=6))
        for start, count in ((-1, 1), (len(self.tasks), 1), (0, 0), (7, 2)):
            with self.subTest(start=start, count=count):
                with self.assertRaises(PolicyError):
                    select_benchmark_tasks(self.tasks, start=start, count=count)

    def test_fixture_shards_merge_byte_identically_to_monolithic_run(self) -> None:
        observations = load_fixture_observations(self.fixture_path, self.tasks)

        def executors():
            return tuple(
                FixtureBenchmarkExecutor(system_id, observations[system_id])
                for system_id in BENCHMARK_SYSTEM_IDS
            )

        source_files = build_source_manifest(ROOT, DEFAULT_SOURCE_PATHS)
        common = {
            "generated_on": "2026-08-29",
            "package_version": "test",
            "git_head": "head",
            "worktree_dirty": True,
            "source_files": source_files,
        }
        monolithic = run_benchmark(
            tasks=self.tasks,
            executors=executors(),
            **common,
        )
        first = run_benchmark(
            tasks=self.tasks[:3],
            executors=executors(),
            **common,
        )
        second = run_benchmark(
            tasks=self.tasks[3:],
            executors=executors(),
            **common,
        )
        merged = merge_benchmark_runs(
            shards=(second, first),
            tasks=self.tasks,
        )
        self.assertEqual(benchmark_json(monolithic), benchmark_json(merged))

    def test_shard_merge_rejects_overlap_or_missing_coverage(self) -> None:
        observations = load_fixture_observations(self.fixture_path, self.tasks)
        executors = tuple(
            FixtureBenchmarkExecutor(system_id, observations[system_id])
            for system_id in BENCHMARK_SYSTEM_IDS
        )
        shard = run_benchmark(
            tasks=self.tasks[:4],
            executors=executors,
            generated_on="2026-08-29",
            package_version="test",
            git_head="head",
            worktree_dirty=True,
            source_files=build_source_manifest(ROOT, DEFAULT_SOURCE_PATHS),
        )
        with self.assertRaisesRegex(PolicyError, "exactly cover"):
            merge_benchmark_runs(shards=(shard,), tasks=self.tasks)
        with self.assertRaisesRegex(PolicyError, "exactly cover"):
            merge_benchmark_runs(shards=(shard, shard), tasks=self.tasks)

    def test_shard_merge_cli_is_append_only_and_checksummed(self) -> None:
        observations = load_fixture_observations(self.fixture_path, self.tasks)

        def executors():
            return tuple(
                FixtureBenchmarkExecutor(system_id, observations[system_id])
                for system_id in BENCHMARK_SYSTEM_IDS
            )

        source_files = build_source_manifest(ROOT, DEFAULT_SOURCE_PATHS)
        common = {
            "generated_on": "2026-08-29",
            "package_version": "test",
            "git_head": "head",
            "worktree_dirty": True,
            "source_files": source_files,
        }
        first = run_benchmark(tasks=self.tasks[:4], executors=executors(), **common)
        second = run_benchmark(tasks=self.tasks[4:], executors=executors(), **common)
        monolithic = run_benchmark(tasks=self.tasks, executors=executors(), **common)
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            first_path = temporary_root / "first.json"
            second_path = temporary_root / "second.json"
            output = temporary_root / "merged.json"
            first_path.write_text(benchmark_json(first), encoding="utf-8")
            second_path.write_text(benchmark_json(second), encoding="utf-8")
            result = merge_shards_main(
                [
                    str(second_path),
                    str(first_path),
                    "--task-file",
                    str(DEFAULT_BENCHMARK_ROOT / "tasks" / "development-v1.jsonl"),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(0, result)
            self.assertEqual(benchmark_json(monolithic), output.read_text(encoding="utf-8"))
            self.assertEqual(
                hashlib.sha256(output.read_bytes()).hexdigest(),
                output.with_suffix(".sha256").read_text(encoding="utf-8").split()[0],
            )
            self.assertEqual(
                2,
                merge_shards_main(
                    [
                        str(first_path),
                        str(second_path),
                        "--task-file",
                        str(DEFAULT_BENCHMARK_ROOT / "tasks" / "development-v1.jsonl"),
                        "--output",
                        str(output),
                    ]
                ),
            )

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

    def test_hypothesis_label_oracle_accepts_only_canonical_concise_labels(self) -> None:
        task = BenchmarkTask.from_dict(
            {
                "schema_version": 1,
                "problem_id": "science-label",
                "category": "scientific_inference",
                "prompt": "Which hypothesis is better supported?",
                "oracle": {"kind": "hypothesis_label", "expected": "b"},
                "oracle_method": "Select the hypothesis label.",
                "required_evidence_ids": [],
                "required_counterexamples": [],
                "source_refs": ["fixture"],
            }
        )

        def correctness(answer: str) -> int:
            observation = BenchmarkObservation(
                schema_version=1,
                problem_id=task.problem_id,
                system_id="base",
                answer=answer,
                confidence_bp=9000,
                terminal_state="ANSWER",
            )
            return score_observation(task, observation).correctness_bp

        self.assertEqual(10000, correctness("B"))
        self.assertEqual(10000, correctness("Hypothesis B"))
        self.assertEqual(10000, correctness("Hypothesis B is better supported."))
        self.assertEqual(0, correctness("Hypothesis A is better supported."))
        self.assertEqual(0, correctness("Hypothesis B is not better supported."))
        self.assertEqual(0, correctness("A or B"))

    def test_component_label_oracle_accepts_only_canonical_fault_location_forms(self) -> None:
        task = BenchmarkTask.from_dict(
            {
                "schema_version": 1,
                "problem_id": "debug-label",
                "category": "debugging",
                "prompt": "Which named layer is earliest?",
                "oracle": {"kind": "component_label", "expected": "schema validator"},
                "oracle_method": "Select the earliest component.",
                "required_evidence_ids": [],
                "required_counterexamples": [],
                "source_refs": ["fixture"],
            }
        )

        def correctness(answer: str, terminal_state: str = "ANSWER") -> int:
            observation = BenchmarkObservation(
                schema_version=1,
                problem_id=task.problem_id,
                system_id="base",
                answer=answer,
                confidence_bp=9000,
                terminal_state=terminal_state,
            )
            return score_observation(task, observation).correctness_bp

        self.assertEqual(10000, correctness("schema validator"))
        self.assertEqual(
            10000,
            correctness("The schema validator is the earliest supported fault location."),
        )
        self.assertEqual(0, correctness("parser before schema validator"))
        self.assertEqual(0, correctness("schema validator is not the earliest fault location"))
        self.assertEqual(0, correctness("schema validator", "INSUFFICIENT_EVIDENCE"))

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
