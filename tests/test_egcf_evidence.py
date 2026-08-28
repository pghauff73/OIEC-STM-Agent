from __future__ import annotations

import unittest

from ourd.egcf.assurance import AssuranceManager
from ourd.egcf.decisions import DecisionManager
from ourd.egcf.evidence import EvidenceManager
from ourd.egcf.errors import EGCFError
from ourd.egcf.ieps import IEPS
from ourd.egcf.invariants import InvariantManager
from ourd.egcf.store import EGCFStore
from tests.helpers import RepoFixture


class EGCFEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.store = EGCFStore(self.fixture.root)
        self.evidence = EvidenceManager(self.store)
        self.ieps = IEPS(self.evidence)
        self.invariants = InvariantManager(self.store)
        self.decisions = DecisionManager(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.fixture.close()

    def test_evidence_independence_simulation_and_conflicts_are_gated(self) -> None:
        first = self.ieps.oracle("subject", "unit", "test", "unit", independence_group="unit")
        second = self.ieps.oracle(
            "subject", "integration", "test", "integration", independence_group="integration"
        )
        self.evidence.collect(
            subject_id="subject",
            content={"passed": True},
            category="test",
            producer="deterministic-unit",
            method="unit",
            source_snapshot_hash="snapshot",
            oracle="unit",
            requirement_ids=[first, second],
            success=True,
            independence_group="unit",
        )
        self.evidence.collect(
            subject_id="subject",
            content={"passed": True, "simulated": True},
            category="test",
            producer="deterministic-simulation",
            method="simulation",
            source_snapshot_hash="snapshot",
            oracle="integration",
            requirement_ids=[second],
            success=True,
            independence_group="integration",
            simulated=True,
        )
        self.assertIn(second, self.evidence.coverage("subject")["missing_mandatory"])
        self.evidence.collect(
            subject_id="subject",
            content={"passed": True, "real": True},
            category="test",
            producer="deterministic-integration",
            method="integration",
            source_snapshot_hash="snapshot",
            oracle="integration",
            requirement_ids=[second],
            success=True,
            independence_group="integration",
        )
        self.assertFalse(self.evidence.coverage("subject")["missing_mandatory"])
        self.evidence.collect(
            subject_id="subject",
            content={"passed": False},
            category="test",
            producer="deterministic-integration-2",
            method="integration",
            source_snapshot_hash="snapshot",
            oracle="integration",
            requirement_ids=[second],
            success=False,
            independence_group="independent-refutation",
        )
        qualification = self.ieps.qualify("subject")
        self.assertFalse(qualification["qualified"])
        self.assertTrue(qualification["conflicts"])

    def test_duplicate_evidence_blocks_high_confidence(self) -> None:
        requirement = self.ieps.oracle("duplicate", "check", "test", "oracle", independence_group="a")
        for producer in ("deterministic-one", "deterministic-two"):
            self.evidence.collect(
                subject_id="duplicate",
                content={"same": True},
                category="test",
                producer=producer,
                method="test",
                source_snapshot_hash="snapshot",
                oracle="oracle",
                requirement_ids=[requirement],
                success=True,
                independence_group="a",
            )
        confidence = self.evidence.confidence("duplicate")
        self.assertIn("duplicate evidence content", confidence.blocking_gaps)
        self.assertIn("evidence independence groups are reused", confidence.blocking_gaps)
        self.assertEqual("BLOCKED", confidence.conclusion)

    def test_invariant_and_decision_conflicts_remain_append_only(self) -> None:
        evidence_id = self.evidence.collect(
            subject_id="governance",
            content={"validated": True},
            category="test",
            producer="deterministic-validator",
            method="validator",
            source_snapshot_hash="snapshot",
            success=True,
        )
        self.invariants.register(
            name="parser-stability",
            statement="parser accepts legacy inputs",
            scope=["src/**"],
            validator={"kind": "test"},
            evidence_ids=[evidence_id],
            falsifier="a legacy input is rejected",
            authority="human-a",
        )
        self.invariants.register(
            name="parser-stability",
            statement="parser rejects legacy inputs",
            scope=["src/**"],
            validator={"kind": "test"},
            evidence_ids=[evidence_id],
            falsifier="a legacy input is accepted",
            authority="human-b",
        )
        self.assertTrue(self.invariants.conflicts())
        first = self.decisions.create(
            question="Which parser?",
            alternatives=["a", "b"],
            choice="a",
            rationale="first",
            evidence_ids=[evidence_id],
            constraints=[],
            owner="team",
            scope=["src/**"],
        )
        second = self.decisions.create(
            question="Which parser?",
            alternatives=["a", "b"],
            choice="b",
            rationale="second",
            evidence_ids=[evidence_id],
            constraints=[],
            owner="team",
            scope=["src/**"],
        )
        self.decisions.supersede(
            first,
            choice="a",
            rationale="activate a",
            evidence_ids=[evidence_id],
            authority="human-a",
        )
        self.decisions.supersede(
            second,
            choice="b",
            rationale="activate b",
            evidence_ids=[evidence_id],
            authority="human-b",
        )
        self.assertTrue(self.decisions.conflicts())
        with self.assertRaises(EGCFError):
            self.decisions.create(
                question="unsafe",
                alternatives=["yes"],
                choice="yes",
                rationale="model said so",
                evidence_ids=[],
                constraints=[],
                owner="model",
                scope=["**"],
                activate=True,
                authority="model",
            )

    def test_assurance_preserves_gaps_and_cannot_create_approval(self) -> None:
        assurance = AssuranceManager(self.store, self.evidence, self.invariants, self.decisions)
        case = assurance.generate(
            "unproven",
            "candidate is safe",
            capability_facts={},
            approval_facts={"satisfied": False},
            rollback_argument={"required": True, "covered": False},
            uncertainties=["no runtime evidence"],
        )
        self.assertEqual("NOT_SUPPORTED", case.conclusion)
        self.assertTrue(case.gaps)
        self.assertFalse(case.approval_facts["satisfied"])


if __name__ == "__main__":
    unittest.main()
