from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from tools.icpi_chat_scenario_generator import (
    SCENARIO_SCHEMA_PATH,
    build_scenarios,
    render_jsonl,
)
from tools.icpi_chat_scenario_runner import (
    build_category_worker_command,
    build_parser,
    evaluate_scenario,
    load_scenarios,
    normalize_provider_path_args,
    run_campaign,
    scenario_dependency_issue,
    source_file_manifest,
    validate_selected_scenarios,
)


ROOT = Path(__file__).resolve().parents[2]


class ChatScenarioRunnerTests(unittest.TestCase):
    def test_schema_validates_every_canonical_scenario(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is unavailable")
        schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))
        for scenario in build_scenarios():
            from tools.icpi_chat_scenario_generator import scenario_payload

            jsonschema.validate(scenario_payload(scenario), schema)

    def test_loader_rejects_noncanonical_payload_drift(self) -> None:
        scenario = build_scenarios()[0]
        with self.assertRaisesRegex(ValueError, "differs from canonical"):
            validate_selected_scenarios((replace(scenario, timeout_seconds=999),))

    def test_source_manifest_excludes_generated_campaigns_and_python_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "owner.py").write_text("OWNER = True\n", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "owner.cpython-313.pyc").write_bytes(b"cache")
            generated = root / "reports" / "icpi-supervised" / "run-1"
            generated.mkdir(parents=True)
            (generated / "results.jsonl").write_text("{}\n", encoding="utf-8")
            implementation = root / "reports" / "icpi-supervised" / "implementation"
            implementation.mkdir(parents=True)
            (implementation / "repair-log.jsonl").write_text("{}\n", encoding="utf-8")
            manifest = source_file_manifest(root)
            self.assertIn("src/owner.py", manifest)
            self.assertIn("reports/icpi-supervised/implementation/repair-log.jsonl", manifest)
            self.assertNotIn("reports/icpi-supervised/run-1/results.jsonl", manifest)
            self.assertNotIn("__pycache__/owner.cpython-313.pyc", manifest)

    def test_live_worker_command_propagates_direct_process_identity(self) -> None:
        digest = "d" * 64
        args = build_parser().parse_args(
            [
                "--provider",
                "live",
                "--model",
                "fixture-live-model",
                "--expected-model-sha256",
                digest,
                "--runner-path",
                "/tmp/oiec-llama-runner",
                "--model-path",
                "/tmp/qwen.gguf",
                "--llama-cpp-root",
                "/tmp/llama.cpp",
                "--llama-cpp-build-dir",
                "/tmp/llama.cpp/build",
                "--runtime-context-tokens",
                "65536",
                "--response-temperature-bp",
                "0",
                "--response-top-p-bp",
                "10000",
                "--max-reasoning-samples",
                "2",
            ]
        )
        command = build_category_worker_command(
            args,
            workspace=Path("/tmp/workspace"),
            category_scenarios=Path("/tmp/scenarios.jsonl"),
            category_result=Path("/tmp/result.json"),
            category_artifacts=Path("/tmp/artifacts"),
        )
        digest_index = command.index("--expected-model-sha256")
        self.assertEqual(digest, command[digest_index + 1])
        runner_index = command.index("--runner-path")
        self.assertEqual("/tmp/oiec-llama-runner", command[runner_index + 1])
        sample_index = command.index("--max-reasoning-samples")
        self.assertEqual("2", command[sample_index + 1])

    def test_live_provider_paths_are_canonicalized_before_worker_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                args = normalize_provider_path_args(
                    build_parser().parse_args(
                        [
                            "--provider",
                            "live",
                            "--runner-path",
                            "runner/oiec-llama-runner",
                            "--model-path",
                            "../Neuro-llama/Qwen3.8-27B-Q2_K.gguf",
                            "--llama-cpp-root",
                            "../llama.cpp",
                            "--llama-cpp-build-dir",
                            "../llama.cpp/build",
                            "--llama-grammar-dir",
                            "grammars/providers",
                        ]
                    )
                )
            finally:
                os.chdir(old_cwd)
        command = build_category_worker_command(
            args,
            workspace=Path("/tmp/workspace"),
            category_scenarios=Path("/tmp/scenarios.jsonl"),
            category_result=Path("/tmp/result.json"),
            category_artifacts=Path("/tmp/artifacts"),
        )
        model_index = command.index("--model-path")
        runner_index = command.index("--runner-path")
        self.assertEqual(str((root.parent / "Neuro-llama" / "Qwen3.8-27B-Q2_K.gguf").resolve()), command[model_index + 1])
        self.assertEqual(str((root / "runner" / "oiec-llama-runner").resolve()), command[runner_index + 1])

    def test_live_corpus_summary_requires_every_expected_document_name(self) -> None:
        scenario = next(item for item in build_scenarios() if item.scenario_id == "RTE-001")
        common = {
            "event_types": (
                "CHAT_MESSAGE_ADDED",
                "CHAT_TURN_STARTED",
                "CHAT_MESSAGE_ADDED",
                "CHAT_TURN_FINISHED",
            ),
            "dialog_events": (),
            "source_snapshot_before": "snapshot",
            "source_snapshot_after": "snapshot",
            "chat_status": "idle",
            "pending_operations": 0,
            "fault_result": None,
            "restored": None,
            "provider_mode": "live",
            "live_quality_threshold_bp": 7000,
            "expected_document_paths": ("docs/a.md", "docs/b.md"),
        }
        incomplete_verdict, incomplete_oracles = evaluate_scenario(
            scenario,
            messages=({"role": "assistant", "content": "Summary of docs/a.md with limitations."},),
            **common,
        )
        self.assertEqual("FAIL", incomplete_verdict)
        self.assertFalse(
            next(
                item["passed"]
                for item in incomplete_oracles
                if item["name"] == "live_corpus_path_coverage"
            )
        )
        complete_verdict, complete_oracles = evaluate_scenario(
            scenario,
            messages=(
                {
                    "role": "assistant",
                    "content": "Source summary for docs/a.md and docs/b.md; limitation disclosed.",
                },
            ),
            **common,
        )
        self.assertEqual("PASS", complete_verdict)
        self.assertTrue(
            next(
                item["passed"]
                for item in complete_oracles
                if item["name"] == "live_corpus_path_coverage"
            )
        )

    def test_live_preflight_failure_creates_read_only_incident(self) -> None:
        scenario = next(item for item in build_scenarios() if item.scenario_id == "RTE-001")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = build_parser().parse_args(
                [
                    "--provider",
                    "live",
                    "--model",
                    "fixture-live-model",
                    "--expected-model-sha256",
                    "a" * 64,
                    "--runner-path",
                    "/tmp/oiec-llama-runner",
                    "--model-path",
                    "/tmp/qwen.gguf",
                    "--llama-cpp-root",
                    "/tmp/llama.cpp",
                    "--llama-cpp-build-dir",
                    "/tmp/llama.cpp/build",
                    "--runtime-context-tokens",
                    "65536",
                    "--response-temperature-bp",
                    "0",
                    "--response-top-p-bp",
                    "10000",
                    "--report-root",
                    str(root),
                    "--run-id",
                    "preflight-failure",
                ]
            )
            with (
                mock.patch(
                    "tools.icpi_chat_scenario_runner.prepare_live_provider_runtime",
                    side_effect=RuntimeError("configured context is too small"),
                ),
                mock.patch(
                    "tools.icpi_chat_scenario_runner.source_file_manifest",
                    return_value={},
                ),
                mock.patch(
                    "tools.icpi_chat_scenario_runner.git_baseline",
                    return_value={
                        "available": True,
                        "dirty": False,
                        "status_porcelain": [],
                    },
                ),
            ):
                self.assertEqual(1, run_campaign(args, (scenario,)))
            run_root = root / "preflight-failure"
            manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("INFRASTRUCTURE_FAILURE", manifest["run_status"])
            incident = run_root / "incidents" / "provider-preflight.json"
            self.assertTrue(incident.is_file())
            self.assertEqual(0o444, incident.stat().st_mode & 0o777)

    def test_page_scenarios_fail_closed_when_pdf_dependency_is_missing(self) -> None:
        scenario = next(item for item in build_scenarios() if item.scenario_id == "PAG-001")
        with mock.patch("tools.icpi_chat_scenario_runner.importlib.util.find_spec", return_value=None):
            self.assertIn("PyMuPDF", scenario_dependency_issue(scenario))

    def test_supervised_five_path_smoke_uses_real_widgets(self) -> None:
        xvfb_run = shutil.which("xvfb-run")
        if xvfb_run is None:
            self.skipTest("xvfb-run is unavailable")
        identifiers = {"CTL-008", "FLT-005", "LIF-006", "LIF-009", "VIS-001"}
        scenarios = tuple(
            scenario for scenario in build_scenarios() if scenario.scenario_id in identifiers
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_path = root / "scenarios.jsonl"
            scenario_path.write_text(render_jsonl(scenarios), encoding="utf-8")
            loaded = load_scenarios(scenario_path)
            self.assertEqual(5, len(loaded))
            completed = subprocess.run(
                [
                    xvfb_run,
                    "-a",
                    sys.executable,
                    str(ROOT / "tools" / "icpi_chat_scenario_runner.py"),
                    "--scenarios",
                    str(scenario_path),
                    "--report-root",
                    str(root / "reports"),
                    "--run-id",
                    "smoke",
                    "--time-scale",
                    "0.01",
                    "--continue-on-failure",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            results = [
                json.loads(line)
                for line in (root / "reports" / "smoke" / "results.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(5, len(results))
            self.assertTrue(all(result["verdict"] == "PASS" for result in results))
            visual = next(result for result in results if result["scenario_id"] == "VIS-001")
            self.assertEqual(1, len(visual["screenshot_paths"]))
            self.assertTrue(Path(visual["screenshot_paths"][0]).is_file())


if __name__ == "__main__":
    unittest.main()
