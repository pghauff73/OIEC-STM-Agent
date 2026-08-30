from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ourd.cli import main as agent_cli_main
from ourd.egcf.ids import sha256_json
from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.store import EGCFStore


def evidence(group: str) -> EvidenceArtifact:
    payload = {"group": group, "kind": "improvement-cli"}
    return EvidenceArtifact(
        subject_id="saa-12.4-cli",
        claim_ids=[],
        requirement_ids=["improvement-scheduling"],
        category="improvement-scheduling",
        producer="deterministic-saa-12-4-cli-test",
        method="controlled-observation",
        source_snapshot_hash=sha256_json(payload),
        target="improvement opportunity",
        oracle="deterministic-test-oracle",
        environment={"suite": "saa-12.4-cli"},
        command_id="improvement.schedule@1",
        algorithm_id="saa-12.4",
        created_at="2026-08-30T04:00:00Z",
        sha256=sha256_json(payload),
        success=True,
        limitations=[],
        independence_group=group,
        simulated=False,
    )


def run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = agent_cli_main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


class SAA124ImprovementCLITests(unittest.TestCase):
    def _workspace(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        with EGCFStore(root) as store:
            evidence_low = store.register(evidence("low-risk"))
            evidence_high = store.register(evidence("high-risk"))
        return temporary, root, evidence_low, evidence_high

    def test_main_cli_dispatches_improvement_help(self):
        with self.assertRaises(SystemExit) as caught:
            agent_cli_main(["improvement", "--help"])
        self.assertEqual(0, caught.exception.code)

    def test_add_list_schedule_record_and_history(self):
        temporary, root, evidence_low, evidence_high = self._workspace()
        try:
            source_a = "a" * 64
            rc, out, err = run_cli(
                [
                    "improvement", "add", "--repo", str(root),
                    "--id", "parser-precedence",
                    "--kind", "FAILURE_PATTERN",
                    "--source-signature", source_a,
                    "--objective", "Investigate repeated parser precedence failure",
                    "--evidence-value-bp", "9000",
                    "--impact-bp", "8500",
                    "--uncertainty-reduction-bp", "8000",
                    "--cost-bp", "2500",
                    "--risk-bp", "1500",
                    "--evidence", evidence_low,
                ]
            )
            self.assertEqual(0, rc, err)
            self.assertIn("parser-precedence", out)

            source_b = "b" * 64
            rc, out, err = run_cli(
                [
                    "improvement", "add", "--repo", str(root),
                    "--id", "external-risk",
                    "--kind", "RETRIEVAL_GAP",
                    "--source-signature", source_b,
                    "--objective", "Investigate a high-risk external integration gap",
                    "--evidence-value-bp", "9500",
                    "--impact-bp", "9500",
                    "--uncertainty-reduction-bp", "9000",
                    "--cost-bp", "2000",
                    "--risk-bp", "9000",
                    "--evidence", evidence_high,
                ]
            )
            self.assertEqual(0, rc, err)

            rc, out, err = run_cli(["improvement", "list", "--repo", str(root), "--json"])
            self.assertEqual(0, rc, err)
            listed = json.loads(out)
            self.assertEqual({"parser-precedence", "external-risk"}, {item["opportunity_id"] for item in listed})

            rc, out, err = run_cli(
                [
                    "improvement", "schedule", "--repo", str(root),
                    "--max-selected", "2",
                    "--cost-budget-bp", "10000",
                    "--max-risk-bp", "4000",
                    "--min-priority-bp", "1000",
                    "--record",
                    "--explain",
                    "--json",
                ]
            )
            self.assertEqual(0, rc, err)
            result = json.loads(out)
            self.assertEqual("IMPROVEMENT_INVESTIGATIONS_SCHEDULED", result["status"])
            self.assertEqual(["parser-precedence"], [item["opportunity_id"] for item in result["selected"]])
            deferred = {item["opportunity_id"]: item["reason"] for item in result["deferred"]}
            self.assertEqual("RISK_CEILING_EXCEEDED", deferred["external-risk"])
            self.assertTrue(result["recorded_schedule_ref"].startswith("improvement-schedule:sha256:"))
            self.assertEqual("INVESTIGATION_PRIORITY_ONLY_NO_MUTATION_AUTHORITY", result["authority_effect"])
            self.assertTrue(result["explanation"])

            rc, history_out, err = run_cli(["improvement", "history", "--repo", str(root), "--json"])
            self.assertEqual(0, rc, err)
            history = json.loads(history_out)
            self.assertEqual(1, len(history))

            rc, out2, err = run_cli(
                [
                    "improvement", "schedule", "--repo", str(root),
                    "--max-selected", "2",
                    "--cost-budget-bp", "10000",
                    "--max-risk-bp", "4000",
                    "--min-priority-bp", "1000",
                    "--record",
                    "--json",
                ]
            )
            self.assertEqual(0, rc, err)
            self.assertEqual(result["recorded_schedule_ref"], json.loads(out2)["recorded_schedule_ref"])
            rc, history_out, err = run_cli(["improvement", "history", "--repo", str(root), "--json"])
            self.assertEqual(0, rc, err)
            self.assertEqual(1, len(json.loads(history_out)))
        finally:
            temporary.cleanup()

    def test_duplicate_human_id_with_different_content_is_rejected(self):
        temporary, root, evidence_low, _ = self._workspace()
        try:
            base = [
                "improvement", "add", "--repo", str(root),
                "--id", "same-id",
                "--kind", "BENCHMARK_GAP",
                "--source-signature", "c" * 64,
                "--evidence-value-bp", "8000",
                "--impact-bp", "8000",
                "--uncertainty-reduction-bp", "7000",
                "--cost-bp", "2000",
                "--risk-bp", "1000",
                "--evidence", evidence_low,
            ]
            rc, _, err = run_cli(base + ["--objective", "First investigation"])
            self.assertEqual(0, rc, err)
            rc, _, err = run_cli(base + ["--objective", "Different investigation"])
            self.assertEqual(2, rc)
            self.assertIn("already registered with different content", err)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
