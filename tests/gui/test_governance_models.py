from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ourd.egcf.engine import EGCFEngine
from ourd.egcf.models import ApprovalRecord, EvidenceRequirement, ExecutionPlan
from ourd_gui.governance_models import (
    build_capability_ladder,
    build_evidence_dashboard,
    matching_approval,
)
from ourd_gui.read_models import ReadOnlyEGCFRepository


class GovernanceModelTests(unittest.TestCase):
    def test_capability_ladder_reflects_active_read_only_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root):
                pass
            repository = ReadOnlyEGCFRepository(root)
            ladder = {item.level: item for item in build_capability_ladder(repository)}
            self.assertEqual("available", ladder["C0"].status)
            self.assertEqual("available", ladder["C1"].status)
            self.assertEqual("blocked", ladder["C3"].status)
            self.assertEqual("blocked", ladder["C5"].status)
            self.assertTrue(ladder["C1"].grant_details)
            grant = ladder["C1"].grant_details[0]
            self.assertIn("scope", grant)
            self.assertIn("budget", grant)
            self.assertIn("expires_at", grant)
            self.assertIn("issuer", grant)
            self.assertIn("authority_hash", grant)
            self.assertIn("approval_modes", grant)
            self.assertIn("use_limit", grant)

    def test_evidence_dashboard_reports_dimension_coverage_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root) as engine:
                requirement = EvidenceRequirement(
                    subject_id="subject-1",
                    name="Boundary condition",
                    category="boundary",
                    oracle="deterministic",
                    freshness_seconds=0,
                    independence_group="boundary-group",
                    mandatory=True,
                )
                requirement_id = engine.handlers.evidence.add_requirement(requirement)
                evidence_id = engine.handlers.evidence.collect(
                    subject_id="subject-1",
                    content={"passed": True},
                    category="boundary",
                    producer="deterministic-test",
                    method="unit-test",
                    source_snapshot_hash=engine.workspace.snapshot_hash(),
                    oracle="deterministic",
                    environment={"runner": "unittest"},
                    requirement_ids=[requirement_id],
                    success=True,
                    limitations=["interaction path not exercised"],
                    independence_group="boundary-group",
                )
            repository = ReadOnlyEGCFRepository(root)
            dashboard = build_evidence_dashboard(repository, [evidence_id])
            boundary = next(item for item in dashboard.dimensions if item.code == "C_B")
            self.assertEqual(1.0, boundary.coverage)
            self.assertEqual("APPROVE_WITH_LIMITS", dashboard.verdict)
            self.assertIn("interaction path not exercised", dashboard.known_unknowns)

    def test_matching_approval_requires_exact_plan_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root) as engine:
                plan = ExecutionPlan(
                    compiled_workflow_id="compiled-workflow:sha256:" + "0" * 64,
                    graph_hash="graph",
                    source_snapshot_hash=engine.workspace.snapshot_hash(),
                    node_order=[],
                    eon_action_ids=[],
                    algorithm_digests=[],
                    capability_grant_id=engine.grant_id,
                    evidence_ids=[],
                    budget={},
                    rollback_graph={},
                    approval_policy="human",
                    expires_at="",
                    created_at="2026-08-21T00:00:00Z",
                )
                plan_id = engine.store.register(plan)
                approval = ApprovalRecord(
                    plan_id=plan_id,
                    plan_hash=plan_id.partition(":sha256:")[2],
                    approver="operator",
                    authority="approved exact plan",
                    constraints={},
                    created_at="2026-08-21T00:00:00Z",
                    expires_at="",
                )
                approval_id = engine.store.register(approval)
            repository = ReadOnlyEGCFRepository(root)
            stored_plan = repository.get(plan_id)
            self.assertIsNotNone(
                matching_approval(
                    repository,
                    stored_plan,
                    [approval_id],
                    now=datetime(2026, 8, 21, tzinfo=timezone.utc),
                )
            )

    def test_simulated_evidence_does_not_count_as_real_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root) as engine:
                requirement = EvidenceRequirement(
                    subject_id="subject-simulated",
                    name="Mutation result",
                    category="mutation",
                    oracle="deterministic",
                    freshness_seconds=0,
                    independence_group="simulation",
                    mandatory=True,
                )
                requirement_id = engine.handlers.evidence.add_requirement(requirement)
                evidence_id = engine.handlers.evidence.collect(
                    subject_id="subject-simulated",
                    content={"passed": True},
                    category="mutation",
                    producer="deterministic-test",
                    method="simulation",
                    source_snapshot_hash=engine.workspace.snapshot_hash(),
                    oracle="deterministic",
                    environment={"runner": "unittest"},
                    requirement_ids=[requirement_id],
                    success=True,
                    limitations=[],
                    independence_group="simulation",
                    simulated=True,
                )
            dashboard = build_evidence_dashboard(
                ReadOnlyEGCFRepository(root),
                [evidence_id],
            )
            mutation = next(item for item in dashboard.dimensions if item.code == "C_M")
            self.assertEqual(0.0, mutation.coverage)
            self.assertEqual("SIMULATION_ONLY", dashboard.verdict)
            self.assertEqual((evidence_id,), dashboard.simulated_evidence_ids)


if __name__ == "__main__":
    unittest.main()
