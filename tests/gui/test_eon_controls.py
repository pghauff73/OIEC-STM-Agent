from __future__ import annotations

import unittest

from ourd.egcf.models import CompiledWorkflow
from ourd_gui.views.eon import eon_control_state


def workflow(*, level: str, approval: str, dry_run: bool = False) -> CompiledWorkflow:
    return CompiledWorkflow(
        workflow_id="fixture@1",
        source_snapshot_hash="a" * 64,
        command_context={"dry_run": dry_run},
        nodes=[],
        edges=[],
        execution_order=[],
        capability_level=level,
        capability_requirements=[],
        risk="L0",
        evidence_requirements=[],
        approval_policy=approval,
        budget={},
        rollback_graph={},
        unresolved=[],
        created_at="2026-08-21T00:00:00Z",
    )


class EONControlTests(unittest.TestCase):
    def test_human_approval_and_execution_are_separate(self) -> None:
        compiled = workflow(level="C3", approval="human")
        before = eon_control_state(
            compiled,
            snapshot_current=True,
            approval_available=False,
        )
        after = eon_control_state(
            compiled,
            snapshot_current=True,
            approval_available=True,
        )
        self.assertTrue(before["approve"])
        self.assertFalse(before["execute"])
        self.assertTrue(after["execute"])

    def test_c4_and_c5_never_offer_approval_or_execution(self) -> None:
        for level in ("C4", "C5"):
            controls = eon_control_state(
                workflow(level=level, approval="human"),
                snapshot_current=True,
                approval_available=True,
            )
            self.assertTrue(controls["critical_block"])
            self.assertFalse(controls["approve"])
            self.assertFalse(controls["execute"])
            self.assertTrue(controls["simulate"])


if __name__ == "__main__":
    unittest.main()
