from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from ourd.reasoning.benchmark import BenchmarkTask, load_benchmark_run
from ourd.reasoning.qualification import (
    AblationConfiguration,
    REQUIRED_ABLATIONS,
    qualify_reasoning_runs,
    standard_ablation_configurations,
    wilson_interval_bp,
)
from ourd.reasoning import SuperReasoningKernel
from tests.test_reasoning import FakeReasoningProvider, dimension_budget, hypotheses
from tools.build_reasoning_qualification_tasks import build_tasks, render_tasks
from tools.build_reasoning_ablation_tasks import (
    DEFAULT_PARENT as ABLATION_PARENT,
    build_manifest as build_ablation_task_manifest,
    render_tasks as render_ablation_tasks,
    select_ablation_tasks,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_FILE = ROOT / "benchmarks/reasoning/tasks/qualification-v1.jsonl"
TASK_MANIFEST = ROOT / "benchmarks/reasoning/tasks/qualification-v1.manifest.json"
TASK_FILE_V2 = ROOT / "benchmarks/reasoning/tasks/qualification-v2.jsonl"
TASK_MANIFEST_V2 = ROOT / "benchmarks/reasoning/tasks/qualification-v2.manifest.json"
ABLATION_TASK_FILE = ROOT / "benchmarks/reasoning/tasks/qualification-ablation-v1.jsonl"
ABLATION_TASK_MANIFEST = (
    ROOT / "benchmarks/reasoning/tasks/qualification-ablation-v1.manifest.json"
)


class QualificationCliTests(unittest.TestCase):
    def test_qualification_cli_runs_outside_repository(self) -> None:
        script = ROOT / "tools/qualify_reasoning_runs.py"
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=directory,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--certificate-reproducibility-bp", completed.stdout)


class QualificationTaskTests(unittest.TestCase):
    def test_held_out_task_set_has_six_hundred_tasks(self) -> None:
        tasks = tuple(
            BenchmarkTask.from_dict(json.loads(line))
            for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        counts = Counter(task.category for task in tasks)
        self.assertEqual(600, len(tasks))
        self.assertEqual(
            {
                "logic": 100,
                "arithmetic": 100,
                "debugging": 100,
                "scientific_inference": 100,
                "causal_reasoning": 100,
                "adversarial": 100,
            },
            dict(counts),
        )

    def test_held_out_task_generation_is_byte_reproducible(self) -> None:
        expected = TASK_FILE.read_text(encoding="utf-8")
        self.assertEqual(expected, render_tasks(build_tasks()))

    def test_held_out_task_manifest_binds_checksum(self) -> None:
        manifest = json.loads(TASK_MANIFEST.read_text(encoding="utf-8"))
        actual = hashlib.sha256(TASK_FILE.read_bytes()).hexdigest()
        self.assertEqual(actual, manifest["task_file_sha256"])
        self.assertFalse(manifest["performance_claim_allowed"])

    def test_v2_generation_is_byte_reproducible_without_rewriting_v1(self) -> None:
        expected_v1 = TASK_FILE.read_text(encoding="utf-8")
        expected_v2 = TASK_FILE_V2.read_text(encoding="utf-8")
        self.assertEqual(expected_v1, render_tasks(build_tasks(task_version=1)))
        self.assertEqual(expected_v2, render_tasks(build_tasks(task_version=2)))
        science = [
            task
            for task in build_tasks(task_version=2)
            if task["category"] == "scientific_inference"
        ]
        self.assertTrue(science)
        self.assertTrue(
            all(
                task["oracle"] == {"kind": "hypothesis_label", "expected": "b"}
                for task in science
            )
        )
        debugging = [
            task for task in build_tasks(task_version=2) if task["category"] == "debugging"
        ]
        self.assertTrue(debugging)
        self.assertTrue(
            all(task["oracle"]["kind"] == "component_label" for task in debugging)
        )

    def test_v2_manifest_binds_checksum(self) -> None:
        manifest = json.loads(TASK_MANIFEST_V2.read_text(encoding="utf-8"))
        actual = hashlib.sha256(TASK_FILE_V2.read_bytes()).hexdigest()
        self.assertEqual(actual, manifest["task_file_sha256"])
        self.assertEqual(600, manifest["task_count"])
        self.assertFalse(manifest["performance_claim_allowed"])

    def test_ablation_corpus_is_frozen_balanced_and_reproducible(self) -> None:
        parent_tasks = tuple(
            BenchmarkTask.from_dict(json.loads(line))
            for line in TASK_FILE_V2.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        selected = select_ablation_tasks(parent_tasks)
        expected = ABLATION_TASK_FILE.read_text(encoding="utf-8")
        self.assertEqual(expected, render_ablation_tasks(selected))
        self.assertEqual(60, len(selected))
        self.assertEqual(
            {
                "logic": 10,
                "arithmetic": 10,
                "debugging": 10,
                "scientific_inference": 10,
                "causal_reasoning": 10,
                "adversarial": 10,
            },
            dict(Counter(task.category for task in selected)),
        )
        manifest = json.loads(ABLATION_TASK_MANIFEST.read_text(encoding="utf-8"))
        rebuilt = build_ablation_task_manifest(
            parent=ABLATION_PARENT,
            output=ABLATION_TASK_FILE,
            tasks=selected,
            content=expected,
        )
        self.assertEqual(manifest, rebuilt)


class QualificationAnalysisTests(unittest.TestCase):
    def test_wilson_interval_is_bounded(self) -> None:
        low, high = wilson_interval_bp(90, 100)
        self.assertLess(low, 9000)
        self.assertGreater(high, 9000)
        self.assertGreaterEqual(low, 0)
        self.assertLessEqual(high, 10000)

    def test_standard_ablation_set_is_complete_and_signed(self) -> None:
        configurations = standard_ablation_configurations()
        self.assertEqual(REQUIRED_ABLATIONS, tuple(item.ablation_id for item in configurations))
        self.assertTrue(all(item.signature for item in configurations))

    def test_development_run_cannot_authorize_qualification_claim(self) -> None:
        run = load_benchmark_run(ROOT / "benchmarks/reasoning/baseline-v1.json")
        report = qualify_reasoning_runs(
            (run,),
            ablation_runs={},
        )
        self.assertFalse(report.performance_gate_passed)
        self.assertFalse(report.performance_claim_allowed)
        self.assertTrue(report.human_review_required)
        self.assertTrue(report.missing_ablation_ids)
        self.assertTrue(report.limitations)
        self.assertEqual(0, report.certificate_reproducibility_bp)

    def _run_ablation(
        self,
        ablation_id: str,
        *,
        uncertainty_bp: int = 10_000,
        difficulty_bp: int = 10_000,
    ):
        profile = next(
            item
            for item in standard_ablation_configurations()
            if item.ablation_id == ablation_id
        )
        kernel = SuperReasoningKernel(
            max_candidates=profile.path_count,
            max_provider_calls=32,
            ablation=profile,
        )
        reasoning_problem = kernel.create_problem(
            statement="Select the bounded candidate.",
            goal="Choose the strongest grounded answer.",
            source_snapshot_hash="snapshot",
            boundary_signature="boundary",
            dimension_signature="dimension",
            evidence_ids=("e1",),
            uncertainty_bp=uncertainty_bp,
            difficulty_bp=difficulty_bp,
        )
        provider = FakeReasoningProvider()
        result = kernel.run(
            provider=provider,
            problem=reasoning_problem,
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(candidates=8),
            declared_evidence_ids=("e1",),
        )
        return provider, result

    def test_one_path_ablation_executes_one_proposer(self) -> None:
        provider, (_active, budget, candidates, _topology, certificate) = (
            self._run_ablation("one_path_only")
        )
        proposer_calls = sum(
            "proposer" in item["instructions"].casefold() for item in provider.requests
        )
        self.assertEqual(1, proposer_calls)
        self.assertEqual(1, budget.candidate_count)
        self.assertEqual("one_path_only", candidates.ablation_id)
        self.assertEqual(candidates.ablation_config_hash, certificate.ablation_config_hash)

    def test_verifier_and_falsifier_ablations_remove_role_calls(self) -> None:
        verifier_provider, _ = self._run_ablation("without_verifier")
        falsifier_provider, _ = self._run_ablation("without_falsifier")
        self.assertFalse(
            any(
                "process verifier" in item["instructions"].casefold()
                for item in verifier_provider.requests
            )
        )
        self.assertFalse(
            any(
                "adversarial oiec-sr falsifier" in item["instructions"].casefold()
                for item in falsifier_provider.requests
            )
        )

    def test_hypothesis_and_adaptive_compute_ablations_change_state(self) -> None:
        _provider, (active, _budget, _candidates, _topology, certificate) = (
            self._run_ablation("without_hypothesis_state")
        )
        self.assertEqual(1, len(active))
        self.assertNotEqual("h1", active[0].hypothesis_id)
        self.assertEqual("without_hypothesis_state", certificate.ablation_id)

        _provider, (_active, fixed, _candidates, _topology, _certificate) = (
            self._run_ablation(
                "without_adaptive_compute",
                uncertainty_bp=0,
                difficulty_bp=0,
            )
        )
        _provider, (_active, adaptive_low, _candidates, _topology, _certificate) = (
            self._run_ablation("full_sr", uncertainty_bp=0, difficulty_bp=0)
        )
        _provider, (_active, adaptive_high, _candidates, _topology, _certificate) = (
            self._run_ablation("full_sr")
        )
        self.assertEqual(4, fixed.candidate_count)
        self.assertEqual(2, adaptive_low.candidate_count)
        self.assertEqual(4, adaptive_high.candidate_count)
        self.assertLess(adaptive_low.candidate_count, fixed.candidate_count)


if __name__ == "__main__":
    unittest.main()
