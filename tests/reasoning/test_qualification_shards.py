from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import benchmark_json
from ourd.reasoning.models import stable_hash
from tests.reasoning.test_model_benchmark import provider_bound_run, task
from tools.build_reasoning_ablation_manifest import main as build_ablation_manifest_main
from tools.qualify_reasoning_runs import _load_ablation_runs
from tools.run_reasoning_model_benchmark import DEFAULT_BENCHMARK_ROOT, ROOT
from tools.run_reasoning_qualification_shards import (
    build_shard_specs,
    controller_manifest,
    normalized_benchmark_args,
    validate_shard_run,
)


def write_benchmark(path: Path, run) -> None:
    content = benchmark_json(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(".sha256").write_text(
        f"{checksum}  {path.name}\n",
        encoding="utf-8",
    )


class QualificationShardControllerTests(unittest.TestCase):
    def test_shard_specs_cover_tail_exactly(self) -> None:
        self.assertEqual(
            (
                {"index": 0, "start": 0, "count": 10, "path": "shards/shard-000.json"},
                {"index": 1, "start": 10, "count": 10, "path": "shards/shard-001.json"},
                {"index": 2, "start": 20, "count": 1, "path": "shards/shard-002.json"},
            ),
            build_shard_specs(21, 10),
        )

    def test_controller_rejects_owned_or_secret_forwarded_flags(self) -> None:
        for values in (
            ("--date", "2026-08-29", "--output", "x.json"),
            ("--date", "2026-08-29", "--task-start=1"),
            ("--date", "2026-08-29", "--api-key", "secret"),
        ):
            with self.subTest(values=values):
                with self.assertRaises(PolicyError):
                    normalized_benchmark_args(values)

    def test_controller_manifest_is_deterministic_and_source_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            kwargs = {
                "root": ROOT,
                "benchmark_root": DEFAULT_BENCHMARK_ROOT,
                "task_file": DEFAULT_BENCHMARK_ROOT / "tasks/development-v1.jsonl",
                "run_dir": Path(directory),
                "shard_size": 3,
                "merged_name": "merged.json",
                "benchmark_runner": ROOT / "tools/run_reasoning_model_benchmark.py",
                "benchmark_args": ("--date", "2026-08-29"),
            }
            first, tasks = controller_manifest(**kwargs)
            second, repeated_tasks = controller_manifest(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(tasks, repeated_tasks)
        self.assertEqual(8, first["task_count"])
        self.assertEqual(3, len(first["shards"]))
        self.assertEqual("held_out_model_qualification_candidate", first["qualification_status"])
        material = dict(first)
        signature = material.pop("signature")
        self.assertEqual(signature, stable_hash(material))

    def test_shard_validation_checks_range_identity_and_failures(self) -> None:
        run = provider_bound_run()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shard.json"
            write_benchmark(path, run)
            loaded, identity = validate_shard_run(
                path=path,
                spec={"start": 0, "count": 1},
                tasks=(task(),),
                source_manifest_hash=run.source_manifest_hash,
                generated_on="2026-08-29",
            )
            self.assertEqual(run.signature, loaded.signature)
            self.assertTrue(identity)
            with self.assertRaisesRegex(PolicyError, "provider/runtime drift"):
                validate_shard_run(
                    path=path,
                    spec={"start": 0, "count": 1},
                    tasks=(task(),),
                    source_manifest_hash=run.source_manifest_hash,
                    generated_on="2026-08-29",
                    expected_identity="0" * 64,
                )

    def test_signed_ablation_manifest_loads_real_benchmark_artifact(self) -> None:
        run = provider_bound_run(ablation_id="one_path_only")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_path = root / "runs/one-path.json"
            manifest_path = root / "ablation-manifest.json"
            write_benchmark(run_path, run)
            code = build_ablation_manifest_main(
                [
                    "--run",
                    f"one_path_only={run_path}",
                    "--output",
                    str(manifest_path),
                ]
            )
            self.assertEqual(0, code)
            loaded = _load_ablation_runs(manifest_path)
        self.assertEqual((run.signature,), tuple(item.signature for item in loaded["one_path_only"]))


if __name__ == "__main__":
    unittest.main()
