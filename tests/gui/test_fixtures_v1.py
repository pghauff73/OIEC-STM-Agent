from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.models import (
    ApprovalRecord,
    ArtifactRecord,
    ExecutionPlan,
    ExecutionRecord,
    FailureRecord,
)
from ourd_gui.governance_models import build_evidence_dashboard, matching_approval
from ourd_gui.read_models import ReadOnlyEGCFRepository
from ourd_gui.selection_trace import SelectionTraceAssembler

from .fixtures_v1 import FIXTURE_BUNDLE_SHA256, install_fixture_repository


class GuiFixtureV1Tests(unittest.TestCase):
    def test_bundle_is_digest_locked_and_loads_through_gui_read_models(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = install_fixture_repository(root)
            self.assertEqual(FIXTURE_BUNDLE_SHA256, bundle.digest)
            repository = ReadOnlyEGCFRepository(root)
            trace = SelectionTraceAssembler(repository).assemble(
                bundle.ids["selection"],
                invocation_id=bundle.ids["invocation"],
                compiled_workflow_id=bundle.ids["compiled_workflow"],
            )
            self.assertEqual(
                ["fixture.axial-profile@1", "fixture.axial-profile-unbounded@1"],
                [candidate.algorithm_id for candidate in trace.candidates],
            )
            self.assertTrue(trace.candidates[0].selected)
            self.assertEqual(
                ("required capability C3 exceeds fixture authority C1",),
                trace.candidates[1].rejection_reasons,
            )
            dashboard = build_evidence_dashboard(
                repository,
                [bundle.ids["confidence"], bundle.ids["evidence"]],
            )
            self.assertEqual("APPROVE_WITH_LIMITS", dashboard.verdict)
            self.assertEqual(1.0, dashboard.dimensions[2].coverage)
            plan = repository.get(bundle.ids["execution_plan"])
            self.assertIsInstance(plan, ExecutionPlan)
            approval = matching_approval(repository, plan, [bundle.ids["approval"]])
            self.assertIsInstance(approval, ApprovalRecord)
            self.assertIsInstance(repository.get(bundle.ids["execution"]), ExecutionRecord)
            self.assertIsInstance(repository.get(bundle.ids["failure"]), FailureRecord)
            artifact = repository.get(bundle.ids["artifact"])
            self.assertIsInstance(artifact, ArtifactRecord)
            self.assertEqual(
                b"GUI fixture assurance report\n",
                repository.artifact_content_path(artifact).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
