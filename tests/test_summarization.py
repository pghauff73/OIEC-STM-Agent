from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.agent import OURDAgent
from ourd.interaction import compile_turn_execution_policy, route_interaction
from ourd.workspace import Workspace


class SummarizationArtifactTests(unittest.TestCase):
    def test_manifest_coverage_summary_and_exact_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "a.md").write_text("# A\nalpha\nbeta\n", encoding="utf-8")
            (root / "docs" / "b.md").write_text("# B\ngamma\n", encoding="utf-8")
            (root / "docs" / "skip.txt").write_text("skip\n", encoding="utf-8")
            workspace = Workspace(root)
            route = route_interaction("Summarize @folder[docs]", workspace)
            policy = compile_turn_execution_policy(route, source_snapshot_hash=workspace.snapshot_hash())
            with OURDAgent(root, turn_execution_policy=policy) as agent:
                manifest_result = agent.dispatch(
                    "build_corpus_manifest",
                    {"root_path": "docs", "include_patterns": ["*.md", "**/*.md"], "exclude_patterns": []},
                )
                manifest = manifest_result["manifest"]
                self.assertEqual(["docs/a.md", "docs/b.md"], [item["path"] for item in manifest["files"]])
                for path in ("docs/a.md", "docs/b.md"):
                    read = agent.dispatch(
                        "read_corpus_document",
                        {"manifest_id": manifest["manifest_id"], "path": path, "start_line": 1, "end_line": 2000},
                    )
                    self.assertTrue(read["coverage"]["coverage_complete"])
                    summary = agent.dispatch(
                        "record_document_summary",
                        {
                            "manifest_id": manifest["manifest_id"],
                            "path": path,
                            "summary_text": f"Summary of {path}.",
                            "prompt_signature": "prompt:test",
                            "model_identity": "test-model",
                        },
                    )
                    self.assertEqual("MODEL_SUMMARY_BOUND_TO_VERIFIED_SOURCE", summary["summary"]["epistemic_status"])
                report = agent.dispatch("corpus_summary_report", {"manifest_id": manifest["manifest_id"]})
                self.assertEqual("COMPLETE", report["report"]["coverage_status"])
                self.assertEqual(report["report"]["expected_paths"], report["report"]["summarized_paths"])

    def test_original_incident_prompt_completes_exact_corpus_control_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "first.md").write_text("# First\n\nAlpha.\n", encoding="utf-8")
            (root / "docs" / "second.md").write_text("# Second\n\nBeta.\n", encoding="utf-8")
            workspace = Workspace(root)
            route = route_interaction("Summarise each /docs/ markdown file.", workspace)
            policy = compile_turn_execution_policy(route, source_snapshot_hash=workspace.snapshot_hash())
            with OURDAgent(root, turn_execution_policy=policy) as agent:
                manifest = agent.dispatch(
                    "build_corpus_manifest",
                    {
                        "root_path": route.intent.target_paths[0],
                        "include_patterns": ["*.md", "**/*.md"],
                        "exclude_patterns": [],
                    },
                )["manifest"]
                for record in manifest["files"]:
                    agent.dispatch(
                        "read_corpus_document",
                        {
                            "manifest_id": manifest["manifest_id"],
                            "path": record["path"],
                            "start_line": 1,
                            "end_line": record["line_count"],
                        },
                    )
                    agent.dispatch(
                        "record_document_summary",
                        {
                            "manifest_id": manifest["manifest_id"],
                            "path": record["path"],
                            "summary_text": f"Bound summary for {record['path']}",
                            "prompt_signature": route.signature,
                            "model_identity": "fixture-model",
                        },
                    )
                report = agent.dispatch(
                    "corpus_summary_report",
                    {"manifest_id": manifest["manifest_id"]},
                )["report"]
            self.assertEqual("COMPLETE", report["coverage_status"])
            self.assertEqual(("docs/first.md", "docs/second.md"), tuple(report["summarized_paths"]))


if __name__ == "__main__":
    unittest.main()
