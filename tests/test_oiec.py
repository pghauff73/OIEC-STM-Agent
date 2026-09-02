from __future__ import annotations

import itertools
import json
import unittest
from dataclasses import replace

from ourd import OURDAgent
from ourd.authority import finalize_authority
from ourd.cfel import record_collision
from ourd.errors import PolicyError
from ourd.models import (
    AuthorityManifest,
    EONAction,
    EvidenceArtifact,
    GateDecision,
    GovernanceRecord,
    RuntimeState,
    SCORE_SCALE,
)
from ourd.oiec import (
    BoundedTransitionKernel,
    TransitionMetrics,
    certify_progress,
    collision_severity_bp,
    empty_evidence_state,
    evidence_mass,
    make_attempt_key,
    membership_uncertainty_bp,
    update_evidence,
)
from ourd.persistence import EventStore, StateStore
from ourd.policy import PolicyEngine
from ourd.workspace import Workspace
from tests.helpers import RepoFixture
from tests.helpers import governance_args


class OIECFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.workspace = Workspace(self.fixture.root)
        self.authority = finalize_authority(
            AuthorityManifest(
                task_id="oiec-test",
                goal="Exercise bounded transitions",
                source_snapshot_hash=self.workspace.snapshot_hash(),
                allowed_paths=["README.md", "src/**"],
                forbidden_paths=["secrets/**", ".ourd-agent/**"],
                max_retries_per_action=1,
                allow_l1_auto_apply=True,
                max_automatic_risk="L1",
                operator="unit-test",
                read_only=False,
            )
        )
        self.runtime = RuntimeState(
            authority=self.authority,
            governance=GovernanceRecord(
                goal="Bound one change",
                objects=["parser", "tokenizer"],
                relations=["tokenizer feeds parser"],
                excluded_scope=["secrets/**", ".ourd-agent/**"],
                allowed_paths=["README.md"],
                dimensions=["precedence", "scope"],
                invariants=["public grammar unchanged"],
                authority_hash=self.authority.authority_hash,
                established=True,
            ),
        )
        self.policy = PolicyEngine()
        self.kernel = BoundedTransitionKernel(max_active_dimensions=2)

    def tearDown(self) -> None:
        self.fixture.close()

    def action(
        self,
        *,
        action_id: str = "action:one",
        operation: str = "read",
        target: str = "README.md",
        evidence: tuple[str, ...] = (),
        required_tests: tuple[str, ...] = (),
        model_risk: str = "L0",
        effective_risk: str = "L0",
        varied_dimensions: tuple[str, ...] = ("precedence",),
    ) -> EONAction:
        return EONAction(
            action_id=action_id,
            summary="Bounded action",
            operation=operation,
            targets=[target],
            preconditions=[],
            postconditions=[],
            preserve=[],
            evidence=list(evidence),
            model_risk=model_risk,
            effective_risk=effective_risk,
            authority_hash=self.authority.authority_hash,
            source_snapshot_hash=self.workspace.snapshot_hash(),
            required_tests=list(required_tests),
            varied_dimensions=list(varied_dimensions),
        )

    @staticmethod
    def gate(action: EONAction, *requirements: str, evidence_ids: tuple[str, ...] = ()) -> GateDecision:
        return GateDecision(
            decision_id="gate:one",
            action_id=action.action_id,
            proposed_verdict="APPROVE",
            verdict="APPROVE",
            evidence_ids=list(evidence_ids),
            evidence_categories={
                "invariant": list(evidence_ids[:1]),
                "boundary": list(evidence_ids[1:2]),
                "counterexample": [],
                "test": [],
                "observation": [],
            },
            satisfied_requirements=list(requirements),
            uncovered=[],
            limits={},
            reason="test gate",
        )

    def add_evidence(
        self,
        action: EONAction,
        *,
        artifact_id: str,
        requirements: tuple[str, ...],
        quality_bp: int = SCORE_SCALE,
        polarity: str = "support",
    ) -> EvidenceArtifact:
        artifact = EvidenceArtifact(
            artifact_id=artifact_id,
            kind="test",
            description="observation",
            sha256="0" * 64,
            action_id=action.action_id,
            source_snapshot_hash=action.source_snapshot_hash,
            success=True,
            requirement_ids=list(requirements),
            quality_bp=quality_bp,
            polarity=polarity,
        )
        self.runtime.evidence_registry[artifact_id] = artifact
        return artifact


class BoundaryTests(OIECFixture):
    def test_semantic_scope_does_not_expand_authority(self) -> None:
        self.runtime.governance.objects.append("src/new.py")
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        self.assertIn("src/new.py", boundary.semantic_objects)
        with self.assertRaises(PolicyError):
            self.policy.require_oiec_boundary_target(self.workspace, boundary, "src/new.py")

    def test_target_must_satisfy_authority_and_governance(self) -> None:
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        self.assertEqual(
            "README.md",
            self.policy.require_oiec_boundary_target(self.workspace, boundary, "README.md"),
        )
        with self.assertRaises(PolicyError):
            self.policy.require_oiec_boundary_target(self.workspace, boundary, "src/a.py")

    def test_forbidden_authority_path_always_wins(self) -> None:
        self.runtime.governance.allowed_paths = ["secrets/**"]
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        with self.assertRaises(PolicyError):
            self.policy.require_oiec_boundary_target(
                self.workspace, boundary, "secrets/value.txt"
            )

    def test_boundary_signature_is_order_independent(self) -> None:
        first = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
            memberships={"parser": 9_000, "tokenizer": 8_000},
        )
        self.runtime.governance.objects.reverse()
        self.runtime.governance.relations.reverse()
        self.runtime.governance.dimensions.reverse()
        second = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
            memberships={"tokenizer": 8_000, "parser": 9_000},
        )
        self.assertEqual(first.signature, second.signature)

    def test_boundary_uncertainty_fixed_point(self) -> None:
        self.assertEqual(0, membership_uncertainty_bp(0))
        self.assertEqual(SCORE_SCALE, membership_uncertainty_bp(5_000))
        self.assertEqual(0, membership_uncertainty_bp(SCORE_SCALE))


class DimensionTests(OIECFixture):
    def test_dimension_count_is_bounded(self) -> None:
        self.runtime.governance.dimensions = ["a", "b", "c"]
        kernel = BoundedTransitionKernel(max_active_dimensions=2)
        boundary = kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = kernel.derive_dimension_budget(
            boundary=boundary,
            authority=self.authority,
            dimension_scores={"a": 1, "b": 3, "c": 2},
        )
        self.assertEqual(("b", "c"), budget.selected_dimensions)

    def test_dimension_ties_use_lexical_order(self) -> None:
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = self.kernel.derive_dimension_budget(
            boundary=boundary,
            authority=self.authority,
            dimension_scores={"precedence": 500, "scope": 500},
        )
        self.assertEqual(("precedence", "scope"), budget.selected_dimensions)

    def test_single_dimension_iurm_default(self) -> None:
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = self.kernel.derive_dimension_budget(
            boundary=boundary,
            authority=self.authority,
        )
        self.policy.require_oiec_dimension_action(budget, ["precedence"])

    def test_interaction_order_violation_blocked(self) -> None:
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = self.kernel.derive_dimension_budget(
            boundary=boundary,
            authority=self.authority,
        )
        with self.assertRaises(PolicyError):
            self.policy.require_oiec_dimension_action(budget, ["precedence", "scope"])

    def test_authority_retry_limit_caps_dimension_budget(self) -> None:
        self.authority.max_retries_per_action = 0
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = self.kernel.derive_dimension_budget(
            boundary=boundary,
            authority=self.authority,
        )
        self.assertEqual(0, budget.max_retries_per_attempt)


class EvidenceTests(OIECFixture):
    def test_evidence_presence_is_monotonic(self) -> None:
        before = empty_evidence_state(["a", "b"])
        after = update_evidence(before, atom="a", artifact_id="e1", quality_bp=4_000)
        later = update_evidence(after, atom="b", artifact_id="e2", quality_bp=5_000)
        self.assertEqual(after.present_mask, after.present_mask & later.present_mask)

    def test_evidence_quality_never_decreases(self) -> None:
        state = update_evidence(
            empty_evidence_state(["a"]), atom="a", artifact_id="e1", quality_bp=8_000
        )
        revised = update_evidence(state, atom="a", artifact_id="e2", quality_bp=3_000)
        self.assertEqual((8_000,), revised.quality_bp)
        self.assertEqual(("e1",), revised.representative_ids)

    def test_conflicting_evidence_does_not_delete_support(self) -> None:
        state = update_evidence(
            empty_evidence_state(["a"]), atom="a", artifact_id="e1", quality_bp=6_000
        )
        revised = update_evidence(
            state, atom="a", artifact_id="e2", quality_bp=7_000, conflict=True
        )
        self.assertEqual(1, revised.present_mask)
        self.assertEqual(1, revised.conflict_mask)

    def test_evidence_universe_overflow_fails_closed(self) -> None:
        kernel = BoundedTransitionKernel(max_active_evidence_atoms=1)
        action = self.action(evidence=("a", "b"))
        boundary = kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = kernel.derive_dimension_budget(boundary=boundary, authority=self.authority)
        with self.assertRaises(PolicyError):
            kernel.project_evidence(runtime=self.runtime, action=action, budget=budget)

    def test_projection_is_action_scoped(self) -> None:
        action = self.action(evidence=("required",))
        self.add_evidence(action, artifact_id="e:relevant", requirements=("required",))
        other = replace(action, action_id="action:other")
        self.add_evidence(other, artifact_id="e:other", requirements=("required",))
        boundary = self.kernel.derive_boundary(
            runtime=self.runtime,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        budget = self.kernel.derive_dimension_budget(boundary=boundary, authority=self.authority)
        projected = self.kernel.project_evidence(
            runtime=self.runtime, action=action, budget=budget
        )
        self.assertEqual(("e:relevant",), projected.representative_ids)


class RetryTests(OIECFixture):
    def test_identical_failed_attempt_is_blocked(self) -> None:
        self.authority.max_retries_per_action = 0
        action = self.action()
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.runtime.failed_attempts[prepared.attempt.digest] = 1
        with self.assertRaises(PolicyError):
            self.kernel.prepare(
                runtime=self.runtime,
                workspace=self.workspace,
                policy=self.policy,
                action=action,
                varied_dimensions=action.varied_dimensions,
            )

    def test_irrelevant_evidence_does_not_unlock_retry(self) -> None:
        action = self.action(evidence=("required",))
        first = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.add_evidence(action, artifact_id="e:irrelevant", requirements=("other",))
        second = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.assertEqual(first.attempt.digest, second.attempt.digest)

    def test_relevant_new_evidence_changes_attempt_key(self) -> None:
        action = self.action(evidence=("required",))
        first = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.add_evidence(action, artifact_id="e:relevant", requirements=("required",))
        second = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.assertNotEqual(first.attempt.digest, second.attempt.digest)

    def test_new_source_snapshot_changes_attempt_key(self) -> None:
        first = make_attempt_key(
            source_snapshot_hash="one",
            action_id="action",
            evidence_signature="evidence",
            boundary_signature="boundary",
            dimension_signature="dimension",
        )
        second = make_attempt_key(
            source_snapshot_hash="two",
            action_id="action",
            evidence_signature="evidence",
            boundary_signature="boundary",
            dimension_signature="dimension",
        )
        self.assertNotEqual(first.digest, second.digest)

    def test_new_dimension_state_changes_attempt_key(self) -> None:
        action = self.action()
        first = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
            dimension_scores={"precedence": 1, "scope": 0},
        )
        second = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
            dimension_scores={"precedence": 2, "scope": 0},
        )
        self.assertNotEqual(first.attempt.digest, second.attempt.digest)


class ProgressTests(OIECFixture):
    def certificate(self, **overrides: object):
        values = {
            "evidence_gain_bp": 0,
            "uncertainty_reduction_bp": 0,
            "goal_improvement_bp": 0,
            "residual_risk_reduction_bp": 0,
            "boundary_uncertainty_reduction_bp": 0,
            "expected_information_gain_bp": 0,
            "novel_evidence": False,
            "novel_experiment": False,
            "terminal": False,
        }
        values.update(overrides)
        return certify_progress(**values)

    def test_new_action_alone_is_not_progress(self) -> None:
        self.assertFalse(self.certificate(novel_experiment=True).accepted)

    def test_new_evidence_can_certify_progress(self) -> None:
        certificate = self.certificate(evidence_gain_bp=1, novel_evidence=True)
        self.assertTrue(certificate.accepted)
        self.assertIn("novel_evidence", certificate.reasons)

    def test_uncertainty_may_increase_with_valid_progress(self) -> None:
        certificate = self.certificate(
            evidence_gain_bp=1,
            novel_evidence=True,
            uncertainty_reduction_bp=-500,
        )
        self.assertTrue(certificate.accepted)

    def test_boundary_resolution_certifies_progress(self) -> None:
        certificate = self.certificate(boundary_uncertainty_reduction_bp=100)
        self.assertTrue(certificate.accepted)

    def test_terminal_stop_is_valid_progress(self) -> None:
        certificate = self.certificate(terminal=True)
        self.assertTrue(certificate.accepted)


class KernelPropertyTests(OIECFixture):
    def test_identical_inputs_have_identical_signatures(self) -> None:
        action = self.action()
        first = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        second = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.assertEqual(first.boundary.signature, second.boundary.signature)
        self.assertEqual(first.budget.signature, second.budget.signature)
        self.assertEqual(first.evidence.signature, second.evidence.signature)
        self.assertEqual(first.attempt.digest, second.attempt.digest)

    def test_kernel_cannot_mutate_workspace(self) -> None:
        action = self.action()
        before = self.workspace.snapshot_hash()
        self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.assertEqual(before, self.workspace.snapshot_hash())
        self.assertFalse(hasattr(self.kernel, "execute"))

    def test_policy_risk_floor_cannot_be_lowered(self) -> None:
        action = self.action(
            operation="write_file",
            model_risk="L0",
            effective_risk="L0",
        )
        with self.assertRaises(PolicyError):
            self.kernel.prepare(
                runtime=self.runtime,
                workspace=self.workspace,
                policy=self.policy,
                action=action,
                varied_dimensions=action.varied_dimensions,
            )

    def test_every_accepted_target_is_inside_boundary(self) -> None:
        action = self.action()
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        for target in action.targets:
            self.assertEqual(
                target,
                self.policy.require_oiec_boundary_target(
                    self.workspace, prepared.boundary, target
                ),
            )

    def test_every_accepted_dimension_is_inside_budget(self) -> None:
        action = self.action()
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.assertTrue(set(action.varied_dimensions).issubset(prepared.budget.selected_dimensions))

    def test_observation_recomputes_bd_and_dl(self) -> None:
        action = self.action(evidence=("required",))
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        after = update_evidence(
            prepared.evidence,
            atom="required",
            artifact_id="e:new",
            quality_bp=1_000,
        )
        certificate = self.kernel.accept_observation(
            runtime=self.runtime,
            prepared=prepared,
            evidence_after=after,
            collision_severity_bp=0,
            metrics_before=TransitionMetrics(),
            metrics_after=TransitionMetrics(),
        )
        self.assertTrue(certificate.accepted)
        self.assertEqual(1, self.runtime.transition_index)
        self.assertIsNotNone(self.runtime.boundary_state)
        self.assertIsNotNone(self.runtime.dimension_budget)

    def test_critical_collision_is_categorical(self) -> None:
        self.assertEqual(
            SCORE_SCALE,
            collision_severity_bp(
                surprise_bp=0,
                invariant_bp=0,
                boundary_bp=0,
                dimension_bp=0,
                repeat_bp=0,
                conflict_bp=0,
                critical_boundary=True,
            ),
        )

    def test_cfel_registers_significant_pre_action_attempt_key(self) -> None:
        action = self.action()
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        record = record_collision(
            self.runtime,
            action_id=action.action_id,
            expected="success",
            observed="failure",
            objects=["parser"],
            boundary="execution",
            active_dimension="precedence",
            frozen_dimensions=["scope"],
            evidence_ids=[],
            severity_bp=5_000,
            attempt_key=prepared.attempt.digest,
            boundary_signature=prepared.boundary.signature,
            dimension_signature=prepared.budget.signature,
        )
        self.assertEqual(1, self.runtime.failed_attempts[prepared.attempt.digest])
        self.assertEqual(prepared.attempt.digest, record.attempt_key)

    def test_agent_apply_persists_oiec_projections(self) -> None:
        authority_path = self.fixture.authority(allowed_paths=["README.md"])
        with OURDAgent(self.fixture.root, authority_path=authority_path) as agent:
            agent.establish_governance(**governance_args())
            transaction = agent.prepare_write_file("README.md", "# Updated\n")
            action = agent.propose_eon_action(
                summary="Update one bounded file",
                operation="write_file",
                targets=["README.md"],
                preconditions=[],
                postconditions=[],
                preserve=[],
                evidence=["invariant", "boundary"],
                risk="L0",
                transaction_id=transaction["transaction_id"],
                command_capabilities=[],
                commands=[],
                required_tests=[],
                varied_dimensions=["policy correctness"],
                expires_at="",
                use_limit=1,
            )["eon_action"]
            first = agent.read_file("README.md")["evidence_id"]
            second = agent.search_text("Example", "README.md")["evidence_id"]
            agent.submit_evidence_gate(
                evidence_items=[
                    {
                        "artifact_id": first,
                        "category": "invariant",
                        "satisfies": ["invariant"],
                    },
                    {
                        "artifact_id": second,
                        "category": "boundary",
                        "satisfies": ["boundary"],
                    },
                ],
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )
            agent.apply_transaction(transaction["transaction_id"])
            self.assertEqual(action["action_id"], agent._last_oiec_prepared.attempt.action_id)
            self.assertIsNotNone(agent.state.boundary_state)
            self.assertIsNotNone(agent.state.dimension_budget)
            self.assertIsNotNone(agent.state.finite_evidence)
            self.assertTrue(agent.state.finite_evidence.present_mask)


class PersistenceMigrationTests(OIECFixture):
    def test_runtime_v1_migrates_to_v6(self) -> None:
        state_dir = self.fixture.root / ".ourd-agent"
        state_dir.mkdir()
        v1 = RuntimeState(authority=self.authority, governance=self.runtime.governance).to_dict()
        v1["schema_version"] = 1
        for key in (
            "boundary_state",
            "dimension_budget",
            "finite_evidence",
            "last_progress",
            "transition_index",
            "reasoning_problem",
            "hypothesis_pool",
            "hypothesis_updates",
            "hypothesis_state",
            "reasoning_hypothesis_state",
            "reasoning_hypothesis_pool",
            "reasoning_hypothesis_updates",
            "reasoning_topology",
            "reasoning_candidates",
            "last_reasoning_certificate",
            "reasoning_transition_index",
            "reasoning_budget",
            "reasoning_context",
            "reasoning_contradictions",
            "last_synthesis",
            "next_reasoning_operation",
        ):
            v1.pop(key, None)
        (state_dir / "state.json").write_text(json.dumps(v1), encoding="utf-8")
        store = StateStore(state_dir)
        try:
            migrated = store.load()
            self.assertEqual(6, migrated.schema_version)
            events = list(EventStore(state_dir / "events.jsonl").events())
            self.assertEqual(1, len(events))
            self.assertEqual(
                {"from_schema": 1, "to_schema": 6},
                events[0]["payload"]["migration"],
            )
        finally:
            store.close()


class SmallStateProofTests(OIECFixture):
    def test_small_state_reachability_is_finite(self) -> None:
        atoms = ("a", "b")
        states = set()
        for present in range(1 << len(atoms)):
            for conflict in range(1 << len(atoms)):
                if conflict & ~present:
                    continue
                states.add((present, conflict))
        self.assertEqual(9, len(states))

    def test_small_state_monotonic_evidence_property(self) -> None:
        for order in itertools.permutations(("a", "b")):
            state = empty_evidence_state(("a", "b"))
            masks = [state.present_mask]
            masses = [evidence_mass(state)]
            for index, atom in enumerate(order, 1):
                state = update_evidence(
                    state,
                    atom=atom,
                    artifact_id=f"e:{atom}",
                    quality_bp=index * 1_000,
                )
                masks.append(state.present_mask)
                masses.append(evidence_mass(state))
            self.assertTrue(all(left & right == left for left, right in zip(masks, masks[1:])))
            self.assertEqual(sorted(masses), masses)

    def test_cycle_detection_blocks_repeated_attempt(self) -> None:
        self.authority.max_retries_per_action = 0
        action = self.action()
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        self.runtime.failed_attempts[prepared.attempt.digest] = 1
        with self.assertRaises(PolicyError):
            for _ in range(2):
                self.kernel.prepare(
                    runtime=self.runtime,
                    workspace=self.workspace,
                    policy=self.policy,
                    action=action,
                    varied_dimensions=action.varied_dimensions,
                )

    def test_small_state_conditional_convergence_requires_progress(self) -> None:
        action = self.action()
        prepared = self.kernel.prepare(
            runtime=self.runtime,
            workspace=self.workspace,
            policy=self.policy,
            action=action,
            varied_dimensions=action.varied_dimensions,
        )
        with self.assertRaises(PolicyError):
            self.kernel.accept_observation(
                runtime=self.runtime,
                prepared=prepared,
                evidence_after=prepared.evidence,
                collision_severity_bp=0,
                metrics_before=TransitionMetrics(),
                metrics_after=TransitionMetrics(),
            )


if __name__ == "__main__":
    unittest.main()
