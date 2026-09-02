from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from ourd.cli import main as agent_main
from ourd.formal_writing import (
    Claim,
    ConceptDefinition,
    FormalWritingService,
    WRITING_PROFILES,
    compile_formal_writing_request,
)
from ourd.writing_engine import (
    admit_reasoning_algorithm_proposal,
    build_argument_graph,
    build_writing_task,
    generate_claims,
    resolve_meaning,
    retrieve_known_reasoning_patterns,
)
from ourd.writing_engine.pipeline_models import WritingTask
from tools.run_formal_writing_benchmark import run_benchmark


QUALIFIED_SOURCE = """# Adoption evidence

Evidence from controlled deployments shows that structured automation reduces repetitive administrative time. However, adoption can increase verification costs when outputs are not checked. Nevertheless, documented human review procedures reduce those operational errors. Results may not generalize beyond structured repetitive work.
"""


class GovernedFormalWritingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "source.md").write_text(QUALIFIED_SOURCE, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _qualified_result(self):
        request = compile_formal_writing_request(
            operation="draft",
            objective="Evaluate whether structured automation should be adopted",
            profile="argumentative-essay",
            source_paths=("source.md",),
        )
        return FormalWritingService(self.root).execute(request)

    def test_pipeline_builds_all_signed_ir_and_qualified_audit(self) -> None:
        result = self._qualified_result()
        qualified = result.qualified_document
        self.assertIsNotNone(qualified)
        self.assertTrue(qualified.plan.task.task_id.startswith("writing-task:"))
        self.assertTrue(qualified.plan.graph.graph_id.startswith("argument-graph:"))
        self.assertTrue(qualified.plan.document_plan_id.startswith("document-plan:"))
        self.assertTrue(qualified.draft_sections)
        self.assertTrue(qualified.falsification_challenges)
        self.assertTrue(
            all(challenge.qualification_id for challenge in qualified.falsification_challenges)
        )
        self.assertTrue(qualified.novelty_assessments)
        self.assertEqual("QUALIFIED_FORMAL_DOCUMENT", qualified.audit.status)
        self.assertEqual(10_000, qualified.audit.evidence_coverage_bp)
        self.assertEqual(10_000, qualified.audit.argument_connectivity_bp)
        self.assertEqual(10_000, qualified.audit.citation_traceability_bp)
        self.assertIsNotNone(qualified.reasoning_algorithm_proposal)
        mapped_claim_ids = {
            claim_id
            for section in qualified.draft_sections
            for _, _, claim_id in section.sentence_claim_map
        }
        self.assertEqual(
            {claim.claim_id for claim in qualified.plan.graph.claims},
            mapped_claim_ids,
        )

    def test_profile_inventory_matches_pasted_plan(self) -> None:
        self.assertTrue(
            {
                "scientific-essay",
                "argumentative-essay",
                "engineering-report",
                "literature-review",
                "business-analysis",
                "research-proposal",
                "lab-report",
            }
            <= set(WRITING_PROFILES)
        )

    def test_semantic_drift_gate_rejects_inconsistent_redefinition(self) -> None:
        task = WritingTask(question="Evaluate efficiency", discipline="engineering")
        concept = ConceptDefinition(
            preferred_label="efficiency",
            definition="useful output per resource consumed",
            scope=("engineering",),
            exclusions=("vague better performance",),
            evidence_ids=("reference:1",),
        )
        claim = Claim(
            statement="Efficiency means decorative visual complexity.",
            claim_type="DEFINITIONAL",
            semantic_terms=("efficiency",),
            evidence_requirements=("definition",),
            supporting_evidence=("reference:1",),
            confidence_bp=8_000,
            status="SUPPORTED",
            scope=("engineering",),
        )
        thesis = Claim(
            statement=task.question,
            claim_type="INTERPRETIVE",
            evidence_requirements=("supported subordinate claims",),
            supporting_evidence=("reference:1",),
            confidence_bp=8_000,
            status="SUPPORTED",
            scope=("engineering",),
        )
        graph = build_argument_graph(task, (concept,), (thesis, claim), (), ())
        self.assertIn("SEMANTIC_DRIFT", {issue.code for issue in graph.issues})

    def test_source_free_plan_fails_closed_on_evidence(self) -> None:
        request = compile_formal_writing_request(
            operation="plan",
            objective="Evaluate a proposition with no registered evidence",
        )
        result = FormalWritingService(self.root).execute(request)
        self.assertIsNone(result.draft)
        self.assertEqual(
            "EVIDENCE_INSUFFICIENT",
            result.qualified_document.audit.status,
        )

    def test_nested_agent_write_cli_supports_plan(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = agent_main(
                [
                    "write",
                    "plan",
                    "--workspace",
                    str(self.root),
                    "--task",
                    "Evaluate a proposition with no registered evidence",
                    "--profile",
                    "general",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, status)
        self.assertEqual("OUTLINE", payload["request"]["operation"])
        self.assertTrue(
            payload["qualified_document"]["plan"]["document_plan_id"].startswith("document-plan:")
        )

    def test_persisted_draft_revision_preserves_internal_state_boundary(self) -> None:
        draft = self._qualified_result().draft
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = agent_main(
                [
                    "write",
                    "revise",
                    "--workspace",
                    str(self.root),
                    "--draft",
                    draft.draft_id,
                    "--require-qualified",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["draft"]["revision_of_sha256"])
        self.assertEqual(
            "QUALIFIED_FORMAL_DOCUMENT",
            payload["qualified_document"]["audit"]["status"],
        )

    def test_saa_admission_requires_exact_human_approval(self) -> None:
        qualified = self._qualified_result().qualified_document
        with self.assertRaises(ValueError):
            admit_reasoning_algorithm_proposal(
                self.root,
                qualified,
                approved_by="",
                human_approval_id="",
            )
        object_id = admit_reasoning_algorithm_proposal(
            self.root,
            qualified,
            approved_by="human-reviewer",
            human_approval_id="approval:exact-qualified-document-hash",
        )
        self.assertTrue(object_id.startswith("algorithm-definition:"))
        patterns = retrieve_known_reasoning_patterns(self.root, "argumentative-essay")
        self.assertTrue(
            all(object_id not in pattern.source_algorithm_ids for pattern in patterns),
            "a merely proposed SAA algorithm must not be retrieved as qualified",
        )

    def test_oiec_bench_formal_writing_track_passes(self) -> None:
        report = run_benchmark()
        self.assertEqual(0, report["failed_count"], report)
        self.assertEqual(3, report["passed_count"])


if __name__ == "__main__":
    unittest.main()
