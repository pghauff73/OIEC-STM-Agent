from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.canonical_store_api import CanonicalAlgorithmStore
from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.reasoning import CanonicalReasoningStore, canonicalize_reasoning_algorithm
from ourd.egcf.retrieval import UnifiedProblemRequirements, retrieve_unified_solution
from ourd.egcf.semantics import (
    LENGTH,
    TIME,
    SemanticAlignmentFalsifierResult,
    SemanticOntologyStore,
    assess_semantic_alignment,
    make_semantic_concept,
    propose_semantic_alignment,
)
from ourd.egcf.store import EGCFStore
from ourd.egcf.ids import sha256_json
from ourd.errors import PolicyError
from ourd.retrieve_first import RetrieveFirstController
from ourd.retrieve_first_agent import RetrieveFirstProductionOURDAgent
from tests.helpers import RepoFixture
from tests.test_production_agent import FinalOnlyProvider
from tests.test_saa_canonical_store import build_form, ctf
from tests.test_saa_reasoning import base_spec
from tests.test_saa_reasoning_operational import qualify_base


def semantic_evidence(label: str, group: str) -> EvidenceArtifact:
    payload = {"label": label, "group": group}
    return EvidenceArtifact(
        subject_id=f"semantic:{label}",
        claim_ids=[],
        requirement_ids=[],
        category="semantic-grounding",
        producer="human-unified-retrieval-test",
        method="independent-semantic-review",
        source_snapshot_hash=sha256_json(payload),
        target=label,
        oracle="semantic-retrieval-oracle",
        environment={"suite": "saa-10"},
        command_id="semantic.qualify",
        algorithm_id="semantic-retrieval-test",
        created_at="2026-08-29T00:00:00Z",
        sha256=sha256_json({"evidence": payload}),
        success=True,
        limitations=[],
        independence_group=group,
        simulated=False,
        content=payload,
    )


def admit_math(egcf: EGCFStore, store: CanonicalAlgorithmStore, meaning: str):
    form, issues, candidates, resolutions = build_form(
        egcf,
        ((ctf(1),),),
        meanings_by_output={0: meaning},
        suffix="unified",
    )
    return store.admit(
        form,
        semantic_issues=issues,
        semantic_candidates=candidates,
        semantic_resolutions=resolutions,
    )


def setup_known_pair(egcf: EGCFStore):
    math_store = CanonicalAlgorithmStore(egcf)
    math_admission = admit_math(egcf, math_store, "problem evidence")
    reasoning_store = CanonicalReasoningStore(egcf)
    reasoning = canonicalize_reasoning_algorithm(base_spec())
    _, qualification = qualify_base(egcf, reasoning)
    reasoning_admission = reasoning_store.admit(reasoning, qualification)
    concept_evidence = egcf.register(semantic_evidence("problem-evidence", "problem"))
    problem_concept = make_semantic_concept(
        name="problem evidence",
        meaning="problem evidence",
        domain="general reasoning",
        quantity_kind="evidence",
        evidence_ids=(concept_evidence,),
    )
    return math_store, reasoning_store, math_admission, reasoning_admission, problem_concept


class SAA10UnifiedRetrievalTests(unittest.TestCase):
    def test_unified_retrieval_finds_complete_known_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                math_store, reasoning_store, math_admission, reasoning_admission, problem_concept = setup_known_pair(egcf)
                requirements = UnifiedProblemRequirements(
                    problem_id="known-pair",
                    input_concepts=(problem_concept,),
                    desired_mathematical_output_count=1,
                    mathematical_domain="continuous",
                    reasoning_desired_outputs=("qualified conclusion",),
                    reasoning_applicability=("evidence-backed factual reasoning",),
                    required_invariants=("unverified claims do not become facts without evidence",),
                    available_evidence_requirements=("source snapshot", "independent verification"),
                    max_reasoning_steps=8,
                )
                decision = retrieve_unified_solution(math_store, reasoning_store, requirements)
                self.assertEqual("QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND", decision.status)
                self.assertEqual(math_admission.canonical_id, decision.selected_mathematical_algorithm_id)
                self.assertEqual(reasoning_admission.reasoning_id, decision.selected_reasoning_id)
                self.assertTrue(decision.required_components_satisfied)

    def test_qualified_ontology_alignment_bridges_mathematical_input_meaning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                math_store = CanonicalAlgorithmStore(egcf)
                math_admission = admit_math(egcf, math_store, "translational speed")
                ontology = SemanticOntologyStore(egcf)
                left_e = egcf.register(semantic_evidence("road-speed", "vehicle"))
                right_e = egcf.register(semantic_evidence("translational-speed", "mechanics"))
                align_e = egcf.register(semantic_evidence("speed-equivalence", "alignment"))
                dimension = LENGTH / TIME
                road_speed = make_semantic_concept(
                    name="road speed",
                    meaning="vehicle road speed",
                    domain="vehicle dynamics",
                    quantity_kind="speed",
                    aliases=("vehicle speed",),
                    physical_dimension=dimension,
                    evidence_ids=(left_e,),
                )
                translational = make_semantic_concept(
                    name="translational speed",
                    meaning="magnitude of translational velocity",
                    domain="mechanics",
                    quantity_kind="speed",
                    physical_dimension=dimension,
                    evidence_ids=(right_e,),
                )
                ontology.admit_concept(road_speed)
                ontology.admit_concept(translational)
                falsifier = "same frame and value yield different displacement rate"
                proposal = propose_semantic_alignment(
                    road_speed,
                    translational,
                    relation="EXACT_EQUIVALENT",
                    shared_meaning="magnitude of translational velocity in a specified frame",
                    expected_effects_match=True,
                    evidence_ids=(align_e,),
                    falsifiers=(falsifier,),
                    independent_review=True,
                )
                alignment = assess_semantic_alignment(
                    egcf,
                    road_speed,
                    translational,
                    proposal,
                    falsifier_results=(SemanticAlignmentFalsifierResult(falsifier, "SURVIVED", align_e),),
                )
                ontology.admit_alignment(alignment)
                requirements = UnifiedProblemRequirements(
                    problem_id="aligned-speed",
                    input_concepts=(road_speed,),
                    desired_mathematical_output_count=1,
                    mathematical_domain="continuous",
                    require_reasoning_algorithm=False,
                )
                decision = retrieve_unified_solution(math_store, None, requirements, ontology=ontology)
                self.assertEqual(math_admission.canonical_id, decision.selected_mathematical_algorithm_id)
                self.assertEqual("QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND", decision.status)


class SAA101RetrieveFirstTests(unittest.TestCase):
    def test_complete_known_pair_disables_novel_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                math_store, reasoning_store, _, _, problem_concept = setup_known_pair(egcf)
                controller = RetrieveFirstController(
                    canonical_algorithm_store=math_store,
                    reasoning_store=reasoning_store,
                )
                requirements = UnifiedProblemRequirements(
                    problem_id="retrieve-first-known",
                    input_concepts=(problem_concept,),
                    desired_mathematical_output_count=1,
                    mathematical_domain="continuous",
                    reasoning_desired_outputs=("qualified conclusion",),
                    reasoning_applicability=("evidence-backed factual reasoning",),
                    required_invariants=("unverified claims do not become facts without evidence",),
                    available_evidence_requirements=("source snapshot", "independent verification"),
                    max_reasoning_steps=8,
                )
                receipt = controller.evaluate(requirements)
                self.assertEqual("REUSE_QUALIFIED_KNOWN_SOLUTION", receipt.status)
                self.assertTrue(receipt.required_search_completed)
                self.assertFalse(receipt.new_algorithm_generation_allowed)

    def test_missing_required_store_blocks_novelty_claim(self) -> None:
        evidence_id = "evidence:fixture"
        problem_concept = make_semantic_concept(
            name="problem evidence",
            meaning="problem evidence",
            domain="general reasoning",
            quantity_kind="evidence",
            evidence_ids=(evidence_id,),
        )
        controller = RetrieveFirstController(canonical_algorithm_store=None, reasoning_store=None)
        receipt = controller.evaluate(
            UnifiedProblemRequirements(problem_id="no-stores", input_concepts=(problem_concept,))
        )
        self.assertEqual("RETRIEVAL_INFRASTRUCTURE_MISSING", receipt.status)
        self.assertFalse(receipt.required_search_completed)
        self.assertFalse(receipt.new_algorithm_generation_allowed)

    def test_production_agent_requires_explicit_contract_and_surfaces_receipt(self) -> None:
        fixture = RepoFixture()
        try:
            with EGCFStore(fixture.root) as egcf:
                math_store, reasoning_store, _, _, problem_concept = setup_known_pair(egcf)
                controller = RetrieveFirstController(
                    canonical_algorithm_store=math_store,
                    reasoning_store=reasoning_store,
                )
                requirements = UnifiedProblemRequirements(
                    problem_id="production-known",
                    input_concepts=(problem_concept,),
                    desired_mathematical_output_count=1,
                    mathematical_domain="continuous",
                    reasoning_desired_outputs=("qualified conclusion",),
                    reasoning_applicability=("evidence-backed factual reasoning",),
                    required_invariants=("unverified claims do not become facts without evidence",),
                    available_evidence_requirements=("source snapshot", "independent verification"),
                    max_reasoning_steps=8,
                )
                with RetrieveFirstProductionOURDAgent(
                    fixture.root,
                    retrieve_first_controller=controller,
                    provider=FinalOnlyProvider(),
                ) as agent:
                    with self.assertRaises(PolicyError):
                        agent.run_task("Do work without a retrieval contract")
                    result = agent.run_task(
                        "Use the qualified known solution",
                        retrieval_requirements=requirements,
                    )
                    self.assertEqual("A model conclusion.", result)
                    self.assertEqual("REUSE_QUALIFIED_KNOWN_SOLUTION", agent.retrieve_first_receipt.status)
                    self.assertIn("REUSE_QUALIFIED_KNOWN_SOLUTION", agent.instructions())
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
