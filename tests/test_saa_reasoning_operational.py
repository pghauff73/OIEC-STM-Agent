from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.reasoning import (
    CanonicalReasoningStore,
    ReasoningAlgorithmSpec,
    ReasoningEdgeSpec,
    ReasoningNodeSpec,
    ReasoningTaskRequirements,
    ReasoningTerminationSpec,
    assess_reasoning_composition,
    canonicalize_reasoning_algorithm,
    compose_reasoning_algorithms,
    make_reasoning_execution_outcome,
    qualify_reasoning_outcome,
    retrieve_reasoning_algorithms,
)
from ourd.egcf.store import EGCFStore
from ourd.egcf.errors import EGCFError
from tests.test_saa_reasoning import base_spec


def evidence(requirements, group, *, label="evidence"):
    return EvidenceArtifact(
        subject_id="reasoning-outcome",
        claim_ids=[],
        requirement_ids=list(requirements),
        category="reasoning-qualification",
        producer="deterministic-test-oracle",
        method="qualified-fixture",
        source_snapshot_hash="1" * 64,
        target=label,
        oracle="test-oracle",
        environment={"suite": "saa-8.3-8.6"},
        command_id="reasoning.qualify",
        algorithm_id="reasoning-fixture",
        created_at="2026-08-29T00:00:00Z",
        sha256="2" * 64,
        success=True,
        limitations=[],
        independence_group=group,
        simulated=False,
    )


def qualify_base(store: EGCFStore, algorithm, *, execution_id="run-1"):
    source_id = store.register(evidence(("source snapshot",), "source"))
    verify_id = store.register(evidence(("independent verification",), "verification"))
    outcome = make_reasoning_execution_outcome(
        algorithm,
        execution_id=execution_id,
        observed_output_semantics=("qualified conclusion",),
        evidence_ids=(source_id, verify_id),
        invariant_results={
            "unverified claims do not become facts without evidence": True,
        },
        falsifier_results={"counterexample exists": "SURVIVED"},
        termination_satisfied=True,
        steps_used=3,
        execution_success=True,
        independent_review=True,
    )
    return outcome, qualify_reasoning_outcome(store, algorithm, outcome)


def decision_spec():
    return ReasoningAlgorithmSpec(
        name="qualified conclusion to action",
        inputs=("qualified conclusion",),
        outputs=("action decision",),
        nodes=(
            ReasoningNodeSpec(
                "classify",
                "CLASSIFY",
                semantic_inputs=("qualified conclusion",),
                semantic_outputs=("candidate action",),
            ),
            ReasoningNodeSpec(
                "verify",
                "VERIFY",
                semantic_inputs=("candidate action",),
                semantic_outputs=("action decision",),
                evidence_requirements=("decision verification",),
            ),
        ),
        edges=(ReasoningEdgeSpec("classify", "verify", "NEXT"),),
        invariants=("action follows qualified conclusion",),
        termination=ReasoningTerminationSpec(
            "bounded decision",
            "action verified or budget exhausted",
            5,
        ),
        applicability=("evidence-backed factual reasoning",),
    )


def qualify_decision(store: EGCFStore, algorithm):
    evidence_id = store.register(evidence(("decision verification",), "decision"))
    outcome = make_reasoning_execution_outcome(
        algorithm,
        execution_id="decision-run",
        observed_output_semantics=("action decision",),
        evidence_ids=(evidence_id,),
        invariant_results={"action follows qualified conclusion": True},
        falsifier_results={},
        termination_satisfied=True,
        steps_used=2,
        execution_success=True,
        independent_review=True,
    )
    return outcome, qualify_reasoning_outcome(store, algorithm, outcome)


class SAA85OutcomeQualificationTests(unittest.TestCase):
    def test_grounded_reviewed_execution_becomes_reuse_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as store:
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                _, qualification = qualify_base(store, algorithm)
                self.assertEqual("QUALIFIED_REASONING_OUTCOME", qualification.status)
                self.assertTrue(qualification.canonical_reuse_eligible)
                self.assertEqual(10000, qualification.evidence_requirement_coverage_bp)
                self.assertEqual(("source", "verification"), qualification.independence_groups)

    def test_triggered_falsifier_blocks_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as store:
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                source_id = store.register(evidence(("source snapshot",), "source"))
                verify_id = store.register(evidence(("independent verification",), "verification"))
                outcome = make_reasoning_execution_outcome(
                    algorithm,
                    execution_id="bad-run",
                    observed_output_semantics=("qualified conclusion",),
                    evidence_ids=(source_id, verify_id),
                    invariant_results={
                        "unverified claims do not become facts without evidence": True,
                    },
                    falsifier_results={"counterexample exists": "TRIGGERED"},
                    termination_satisfied=True,
                    steps_used=3,
                    execution_success=True,
                    independent_review=True,
                )
                qualification = qualify_reasoning_outcome(store, algorithm, outcome)
                self.assertEqual("UNQUALIFIED_REASONING_FALSIFIER", qualification.status)
                self.assertFalse(qualification.canonical_reuse_eligible)


class SAA83ReasoningStoreTests(unittest.TestCase):
    def test_store_deduplicates_reasoning_and_accumulates_qualification_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                reasoning_store = CanonicalReasoningStore(egcf)
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                _, first_qualification = qualify_base(egcf, algorithm, execution_id="run-1")
                first = reasoning_store.admit(algorithm, first_qualification)
                self.assertTrue(first.admitted_new)
                self.assertEqual(1, first.store_generation)

                _, second_qualification = qualify_base(egcf, algorithm, execution_id="run-2")
                second = reasoning_store.admit(algorithm, second_qualification)
                self.assertEqual("REUSED_EXISTING_CANONICAL_REASONING", second.status)
                self.assertEqual(first.reasoning_id, second.reasoning_id)
                self.assertEqual(1, reasoning_store.current_generation())
                self.assertEqual(2, len(reasoning_store.qualifications(first.reasoning_id)))

    def test_projection_rebuild_recovers_canonical_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                reasoning_store = CanonicalReasoningStore(egcf)
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                _, qualification = qualify_base(egcf, algorithm)
                admission = reasoning_store.admit(algorithm, qualification)
                reasoning_store.rebuild_projection()
                self.assertEqual(1, len(reasoning_store.list()))
                restored = reasoning_store.load_algorithm(admission.reasoning_id)
                self.assertEqual(
                    algorithm.canonical_reasoning_signature,
                    restored.canonical_reasoning_signature,
                )

    def test_unqualified_outcome_cannot_enter_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                reasoning_store = CanonicalReasoningStore(egcf)
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                source_id = egcf.register(evidence(("source snapshot",), "source"))
                outcome = make_reasoning_execution_outcome(
                    algorithm,
                    execution_id="incomplete",
                    observed_output_semantics=("qualified conclusion",),
                    evidence_ids=(source_id,),
                    invariant_results={
                        "unverified claims do not become facts without evidence": True,
                    },
                    falsifier_results={"counterexample exists": "SURVIVED"},
                    termination_satisfied=True,
                    steps_used=3,
                    execution_success=True,
                    independent_review=True,
                )
                qualification = qualify_reasoning_outcome(egcf, algorithm, outcome)
                self.assertFalse(qualification.canonical_reuse_eligible)
                with self.assertRaises(EGCFError):
                    reasoning_store.admit(algorithm, qualification)


class SAA84ReasoningRetrievalTests(unittest.TestCase):
    def test_retrieve_selects_qualified_algorithm_by_contract_fit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = CanonicalReasoningStore(egcf)
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                _, qualification = qualify_base(egcf, algorithm)
                admission = store.admit(algorithm, qualification)
                result = retrieve_reasoning_algorithms(
                    store,
                    ReasoningTaskRequirements(
                        available_inputs=("problem evidence",),
                        desired_outputs=("qualified conclusion",),
                        required_applicability=("evidence-backed factual reasoning",),
                        required_invariants=(
                            "unverified claims do not become facts without evidence",
                        ),
                        available_evidence_requirements=(
                            "source snapshot",
                            "independent verification",
                        ),
                        max_steps=8,
                    ),
                )
                self.assertEqual(admission.reasoning_id, result.selected_reasoning_id)
                self.assertEqual(10000, result.selected_fit_score_bp)
                self.assertEqual("GOOD_REASONING_FIT", result.candidates[0].status)

    def test_fit_blocks_algorithm_when_evidence_capability_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = CanonicalReasoningStore(egcf)
                algorithm = canonicalize_reasoning_algorithm(base_spec())
                _, qualification = qualify_base(egcf, algorithm)
                store.admit(algorithm, qualification)
                result = retrieve_reasoning_algorithms(
                    store,
                    ReasoningTaskRequirements(
                        available_inputs=("problem evidence",),
                        desired_outputs=("qualified conclusion",),
                        available_evidence_requirements=("source snapshot",),
                        max_steps=8,
                    ),
                    include_ineligible=True,
                )
                self.assertIsNone(result.selected_reasoning_id)
                self.assertEqual("INELIGIBLE_REASONING_FIT", result.candidates[0].status)
                self.assertTrue(result.candidates[0].blocking_gaps)


class SAA86ReasoningCompositionTests(unittest.TestCase):
    def test_qualified_components_compose_but_composite_requires_new_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                left = canonicalize_reasoning_algorithm(base_spec())
                right = canonicalize_reasoning_algorithm(decision_spec())
                _, left_q = qualify_base(egcf, left)
                _, right_q = qualify_decision(egcf, right)
                composition = compose_reasoning_algorithms(
                    left,
                    right,
                    left_qualification=left_q,
                    right_qualification=right_q,
                )
                self.assertTrue(composition.qualification_required)
                self.assertFalse(composition.canonical_reuse_eligible)
                self.assertEqual(("qualified conclusion",), composition.interface_semantics)
                self.assertEqual(("action decision",), composition.composed_algorithm.output_semantics)

                source_id = egcf.register(evidence(("source snapshot",), "source"))
                independent_id = egcf.register(evidence(("independent verification",), "verification"))
                decision_id = egcf.register(evidence(("decision verification",), "decision"))
                composite_outcome = make_reasoning_execution_outcome(
                    composition.composed_algorithm,
                    execution_id="composite-run",
                    observed_output_semantics=("action decision",),
                    evidence_ids=(source_id, independent_id, decision_id),
                    invariant_results={
                        "unverified claims do not become facts without evidence": True,
                        "action follows qualified conclusion": True,
                    },
                    falsifier_results={"counterexample exists": "SURVIVED"},
                    termination_satisfied=True,
                    steps_used=6,
                    execution_success=True,
                    independent_review=True,
                )
                composite_q = qualify_reasoning_outcome(
                    egcf,
                    composition.composed_algorithm,
                    composite_outcome,
                )
                self.assertTrue(composite_q.canonical_reuse_eligible)
                store = CanonicalReasoningStore(egcf)
                admission = store.admit(composition.composed_algorithm, composite_q)
                self.assertTrue(admission.admitted_new)

    def test_semantic_interface_mismatch_blocks_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                left = canonicalize_reasoning_algorithm(base_spec())
                incompatible = canonicalize_reasoning_algorithm(
                    ReasoningAlgorithmSpec(
                        name="wrong interface",
                        inputs=("unrelated signal",),
                        outputs=("action decision",),
                        nodes=(
                            ReasoningNodeSpec(
                                "observe",
                                "OBSERVE",
                                semantic_inputs=("unrelated signal",),
                                semantic_outputs=("action decision",),
                            ),
                        ),
                        edges=(),
                        invariants=(),
                        termination=ReasoningTerminationSpec("bounded", "done", 2),
                    )
                )
                _, left_q = qualify_base(egcf, left)
                unrelated_id = egcf.register(evidence(("unrelated proof",), "unrelated"))
                unrelated_outcome = make_reasoning_execution_outcome(
                    incompatible,
                    execution_id="unrelated",
                    observed_output_semantics=("action decision",),
                    evidence_ids=(unrelated_id,),
                    invariant_results={},
                    falsifier_results={},
                    termination_satisfied=True,
                    steps_used=1,
                    execution_success=True,
                    independent_review=True,
                )
                unrelated_q = qualify_reasoning_outcome(egcf, incompatible, unrelated_outcome)
                assessment = assess_reasoning_composition(
                    left,
                    incompatible,
                    left_qualification=left_q,
                    right_qualification=unrelated_q,
                )
                self.assertFalse(assessment.composition_eligible)
                self.assertFalse(assessment.interface_eligible)


if __name__ == "__main__":
    unittest.main()
