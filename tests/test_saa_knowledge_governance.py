from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.errors import EGCFError
from ourd.egcf.ids import sha256_json
from ourd.egcf.intelligence import (
    KnowledgeGovernanceStore,
    KnowledgeIntegrityPolicy,
    ImprovementSchedulingPolicy,
    OIEC_BENCH_TRACKS,
    OIECBenchGatePolicy,
    assess_canonical_promotion_governance,
    assess_integrity_trajectory,
    make_failure_observation,
    make_improvement_opportunity,
    make_integrity_snapshot,
    make_oiec_bench_profile,
    qualify_oiec_bench_gate,
    schedule_improvements,
)
from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.store import EGCFStore


CONTEXT = "a" * 64
BOUNDARY = "b" * 64
CANDIDATE = "adapted-candidate:sha256:" + "c" * 64


def evidence(requirements, group, label="evidence"):
    payload = {"requirements": list(requirements), "group": group, "label": label}
    return EvidenceArtifact(
        subject_id=f"knowledge-governance:{label}",
        claim_ids=[],
        requirement_ids=list(requirements),
        category="qualification",
        producer="deterministic-saa-12-governance-test",
        method="controlled-governance-fixture",
        source_snapshot_hash=sha256_json(payload),
        target=label,
        oracle="deterministic-test-oracle",
        environment={"suite": "saa-12.1-12.4"},
        command_id="assurance.generate@1",
        algorithm_id="saa-12-governance-fixture",
        created_at="2026-08-30T00:00:00Z",
        sha256=sha256_json(payload),
        success=True,
        limitations=[],
        independence_group=group,
        simulated=False,
    )


class SAA121FailureAlgebraTests(unittest.TestCase):
    def test_equivalent_failure_is_recognized_and_retry_blocked_after_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = KnowledgeGovernanceStore(egcf)
                e1 = egcf.register(evidence(("failure",), "failure-a", "first"))
                first = make_failure_observation(
                    source_kind="experiment",
                    component="mathematical algorithm",
                    failure_class="EXPERIMENT_REGRESSION",
                    mechanism="  Error increased after dynamics adaptation ",
                    semantic_roles=("prediction error",),
                    violated_invariants=("bounded",),
                    boundary_signature=BOUNDARY,
                    context_signature=CONTEXT,
                    evidence_ids=(e1,),
                    provenance_id="run-1",
                )
                pattern_ref, _, repeated = store.register_failure_observation(first)
                self.assertFalse(repeated)

                e2 = egcf.register(evidence(("failure",), "failure-b", "second"))
                second = make_failure_observation(
                    source_kind="EXPERIMENT",
                    component="MATHEMATICAL   ALGORITHM",
                    failure_class="EXPERIMENT_REGRESSION",
                    mechanism="error increased after DYNAMICS adaptation",
                    semantic_roles=("Prediction Error",),
                    violated_invariants=("bounded",),
                    boundary_signature=BOUNDARY,
                    context_signature=CONTEXT,
                    evidence_ids=(e2,),
                    provenance_id="run-2-new-uuid",
                )
                second_pattern_ref, _, repeated = store.register_failure_observation(second)
                self.assertEqual(pattern_ref, second_pattern_ref)
                self.assertTrue(repeated)
                match = store.assess_failure_retry(second)
                self.assertIsNotNone(match)
                self.assertTrue(match.exact_match)
                self.assertTrue(match.retry_blocked)

                store.rebuild_projection()
                rebuilt = store.assess_failure_retry(second)
                self.assertIsNotNone(rebuilt)
                self.assertTrue(rebuilt.retry_blocked)
                self.assertEqual(2, store.failure_occurrence_count(second_pattern_ref.split(":")[-1]))

    def test_same_mechanism_in_different_context_is_not_exact_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = KnowledgeGovernanceStore(egcf)
                e1 = egcf.register(evidence(("failure",), "a"))
                first = make_failure_observation(
                    source_kind="experiment", component="solver", failure_class="EXPERIMENT_REGRESSION",
                    mechanism="residual diverged", boundary_signature=BOUNDARY, context_signature=CONTEXT,
                    evidence_ids=(e1,), provenance_id="one",
                )
                store.register_failure_observation(first)
                e2 = egcf.register(evidence(("failure",), "b"))
                second = make_failure_observation(
                    source_kind="experiment", component="solver", failure_class="EXPERIMENT_REGRESSION",
                    mechanism="residual diverged", boundary_signature=BOUNDARY, context_signature="d" * 64,
                    evidence_ids=(e2,), provenance_id="two",
                )
                self.assertIsNone(store.assess_failure_retry(second))


class SAA122BenchmarkGateTests(unittest.TestCase):
    def policy(self):
        return OIECBenchGatePolicy(tuple((track, 8000) for track in OIEC_BENCH_TRACKS), minimum_independence_groups=2)

    def test_full_grounded_profile_passes_promotion_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                requirements_a = tuple(f"oiec-bench:{track.casefold()}" for track in OIEC_BENCH_TRACKS[:4])
                requirements_b = tuple(f"oiec-bench:{track.casefold()}" for track in OIEC_BENCH_TRACKS[4:])
                a = egcf.register(evidence(requirements_a, "bench-a", "bench-a"))
                b = egcf.register(evidence(requirements_b, "bench-b", "bench-b"))
                profile = make_oiec_bench_profile(
                    candidate_ref=CANDIDATE,
                    benchmark_context_signature=CONTEXT,
                    track_scores={track: 9000 for track in OIEC_BENCH_TRACKS},
                    evidence_ids=(a, b),
                )
                gate = qualify_oiec_bench_gate(egcf, profile, self.policy(), independent_review=True)
                self.assertEqual("OIEC_BENCH_PROMOTION_GATE_PASSED", gate.status)
                self.assertTrue(gate.canonical_promotion_eligible)
                store = KnowledgeGovernanceStore(egcf)
                self.assertTrue(store.register_benchmark_gate(gate).startswith("oiec-bench-gate:sha256:"))

    def test_one_weak_track_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                req = tuple(f"oiec-bench:{track.casefold()}" for track in OIEC_BENCH_TRACKS)
                a = egcf.register(evidence(req, "bench-a"))
                b = egcf.register(evidence(req, "bench-b"))
                scores = {track: 9000 for track in OIEC_BENCH_TRACKS}
                scores["PROGRESSCERT"] = 7000
                gate = qualify_oiec_bench_gate(
                    egcf,
                    make_oiec_bench_profile(
                        candidate_ref=CANDIDATE, benchmark_context_signature=CONTEXT,
                        track_scores=scores, evidence_ids=(a, b),
                    ),
                    self.policy(), independent_review=True,
                )
                self.assertEqual("OIEC_BENCH_THRESHOLD_FAILURE", gate.status)
                self.assertFalse(gate.canonical_promotion_eligible)


class SAA123IntegrityTests(unittest.TestCase):
    def test_improving_integrity_trajectory_passes(self):
        first = make_integrity_snapshot(
            generation=10, canonical_knowledge_count=100,
            semantic_contradictions=4, semantic_drift_events=4,
            corrected_error_opportunities=20, corrected_error_recurrences=2,
            retrieval_queries=20, retrieval_correct_selections=18,
            equivalent_failure_opportunities=10, equivalent_failure_retries=1,
        )
        second = make_integrity_snapshot(
            generation=11, canonical_knowledge_count=120,
            semantic_contradictions=2, semantic_drift_events=2,
            corrected_error_opportunities=30, corrected_error_recurrences=1,
            retrieval_queries=30, retrieval_correct_selections=29,
            equivalent_failure_opportunities=20, equivalent_failure_retries=1,
        )
        assessment = assess_integrity_trajectory((first, second), KnowledgeIntegrityPolicy())
        self.assertTrue(assessment.knowledge_integrity_qualified)
        self.assertEqual("KNOWLEDGE_INTEGRITY_QUALIFIED_IMPROVING", assessment.status)
        self.assertTrue(assessment.improved_dimensions)

    def test_false_canonical_admission_is_hard_policy_violation(self):
        snapshot = make_integrity_snapshot(
            generation=2, canonical_knowledge_count=100,
            false_canonical_admissions=1,
            retrieval_queries=10, retrieval_correct_selections=10,
            equivalent_failure_opportunities=10, equivalent_failure_retries=0,
        )
        assessment = assess_integrity_trajectory((snapshot,), KnowledgeIntegrityPolicy())
        self.assertFalse(assessment.knowledge_integrity_qualified)
        self.assertEqual("KNOWLEDGE_INTEGRITY_POLICY_VIOLATION", assessment.status)
        self.assertTrue(any("FALSE_ADMISSION_RATE" in item for item in assessment.policy_violations))

    def test_persistent_integrity_trajectory_rebuilds(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = KnowledgeGovernanceStore(egcf)
                a = make_integrity_snapshot(
                    generation=1, canonical_knowledge_count=20,
                    retrieval_queries=10, retrieval_correct_selections=10,
                    equivalent_failure_opportunities=10, equivalent_failure_retries=0,
                )
                b = make_integrity_snapshot(
                    generation=2, canonical_knowledge_count=30,
                    retrieval_queries=20, retrieval_correct_selections=20,
                    equivalent_failure_opportunities=20, equivalent_failure_retries=0,
                )
                store.register_integrity_snapshot(a)
                store.register_integrity_snapshot(b)
                trajectory = assess_integrity_trajectory((a, b), KnowledgeIntegrityPolicy())
                store.register_integrity_trajectory(trajectory)
                store.rebuild_projection()
                with store._connect() as connection:
                    self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM saa_integrity_snapshots").fetchone()[0])
                    self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM saa_integrity_trajectories").fetchone()[0])


class SAA124SchedulingTests(unittest.TestCase):
    def test_scheduler_prioritizes_evidence_value_but_respects_risk_and_cost(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                e1 = egcf.register(evidence(("schedule",), "schedule-a"))
                e2 = egcf.register(evidence(("schedule",), "schedule-b"))
                e3 = egcf.register(evidence(("schedule",), "schedule-c"))
                good = make_improvement_opportunity(
                    egcf, opportunity_id="fix-repeated-failure", kind="FAILURE_PATTERN",
                    source_signature="1" * 64, objective="investigate repeated solver failure",
                    evidence_value_bp=9500, expected_impact_bp=9000, uncertainty_reduction_bp=8000,
                    cost_bp=2500, risk_bp=2000, evidence_ids=(e1,),
                )
                risky = make_improvement_opportunity(
                    egcf, opportunity_id="high-risk-rewrite", kind="INTEGRITY_SIGNAL",
                    source_signature="2" * 64, objective="investigate whole-store rewrite",
                    evidence_value_bp=10000, expected_impact_bp=10000, uncertainty_reduction_bp=10000,
                    cost_bp=3000, risk_bp=9000, evidence_ids=(e2,),
                )
                modest = make_improvement_opportunity(
                    egcf, opportunity_id="benchmark-gap", kind="BENCHMARK_GAP",
                    source_signature="3" * 64, objective="investigate ProgressCert benchmark gap",
                    evidence_value_bp=8500, expected_impact_bp=7000, uncertainty_reduction_bp=7000,
                    cost_bp=2000, risk_bp=1500, evidence_ids=(e3,),
                )
                schedule = schedule_improvements(
                    (risky, modest, good),
                    ImprovementSchedulingPolicy(max_selected=2, total_cost_budget_bp=5000, maximum_risk_bp=6000),
                )
                self.assertEqual("IMPROVEMENT_INVESTIGATIONS_SCHEDULED", schedule.status)
                selected = [item.opportunity_id for item in schedule.selected]
                self.assertIn("fix-repeated-failure", selected)
                self.assertIn("benchmark-gap", selected)
                self.assertTrue(any(item[0] == "high-risk-rewrite" and item[1] == "RISK_CEILING_EXCEEDED" for item in schedule.deferred))

                store = KnowledgeGovernanceStore(egcf)
                for item in (good, risky, modest):
                    store.register_opportunity(item)
                store.register_schedule(schedule)
                store.rebuild_projection()
                with store._connect() as connection:
                    self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM saa_improvement_opportunities").fetchone()[0])
                    self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM saa_improvement_schedules").fetchone()[0])


class SAA12PromotionGovernanceTests(unittest.TestCase):
    def test_benchmark_and_integrity_both_required_for_strict_promotion(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                req = tuple(f"oiec-bench:{track.casefold()}" for track in OIEC_BENCH_TRACKS)
                a = egcf.register(evidence(req, "bench-a"))
                b = egcf.register(evidence(req, "bench-b"))
                profile = make_oiec_bench_profile(
                    candidate_ref=CANDIDATE, benchmark_context_signature=CONTEXT,
                    track_scores={track: 9000 for track in OIEC_BENCH_TRACKS}, evidence_ids=(a, b),
                )
                gate = qualify_oiec_bench_gate(
                    egcf, profile,
                    OIECBenchGatePolicy(tuple((track, 8000) for track in OIEC_BENCH_TRACKS), 2),
                    independent_review=True,
                )
                snapshot = make_integrity_snapshot(
                    generation=5, canonical_knowledge_count=100,
                    retrieval_queries=20, retrieval_correct_selections=20,
                    equivalent_failure_opportunities=20, equivalent_failure_retries=0,
                )
                integrity = assess_integrity_trajectory((snapshot,), KnowledgeIntegrityPolicy())
                result = assess_canonical_promotion_governance(
                    candidate_ref=CANDIDATE, benchmark_gate=gate, integrity_trajectory=integrity,
                )
                self.assertEqual("CANONICAL_PROMOTION_GOVERNANCE_PASSED", result.status)
                self.assertTrue(result.canonical_promotion_allowed)


if __name__ == "__main__":
    unittest.main()
