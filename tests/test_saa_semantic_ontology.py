from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.semantics import (
    JOULE if False else LENGTH,
)
from ourd.egcf.semantics import (
    LENGTH,
    MASS,
    TIME,
    SemanticAlignmentFalsifierResult,
    SemanticOntologyStore,
    SemanticRevisionFalsifierResult,
    assess_additive_compatibility,
    assess_product_dimension,
    assess_semantic_alignment,
    convert_exact_value,
    detect_semantic_contradiction,
    make_semantic_concept,
    physical_semantic_relation,
    propose_semantic_alignment,
    propose_semantic_revision,
    propagate_semantic_contradiction,
    requalify_semantic_revision,
)
from ourd.egcf.store import EGCFStore
from ourd.egcf.ids import sha256_json
from ourd.egcf.errors import EGCFError


def evidence(label: str, group: str = "semantic") -> EvidenceArtifact:
    payload = {"label": label, "group": group}
    return EvidenceArtifact(
        subject_id=f"semantic:{label}",
        claim_ids=[],
        requirement_ids=[],
        category="semantic-grounding",
        producer="human-semantic-test",
        method="independent-semantic-review",
        source_snapshot_hash=sha256_json(payload),
        target=label,
        oracle="semantic-test-oracle",
        environment={"suite": "saa-9"},
        command_id="semantic.qualify",
        algorithm_id="semantic-test",
        created_at="2026-08-29T00:00:00Z",
        sha256=sha256_json({"evidence": payload}),
        success=True,
        limitations=[],
        independence_group=group,
        simulated=False,
        content=payload,
    )


def concept(evidence_id: str, *, name: str, meaning: str, quantity: str, dimension, domain="mechanics", unit=None, aliases=()):
    return make_semantic_concept(
        name=name,
        meaning=meaning,
        domain=domain,
        quantity_kind=quantity,
        aliases=aliases,
        physical_dimension=dimension,
        canonical_unit=unit,
        evidence_ids=(evidence_id,),
    )


class SAA91PhysicalSemanticTests(unittest.TestCase):
    def test_exact_unit_conversion_and_force_dimension(self) -> None:
        self.assertEqual(1, convert_exact_value(1000, "mm", "m"))
        force = concept("e:f", name="force", meaning="net force", quantity="force", dimension=MASS * LENGTH / (TIME ** 2), unit="N")
        mass = concept("e:m", name="mass", meaning="inertial mass", quantity="mass", dimension=MASS, unit="kg")
        acceleration = concept("e:a", name="acceleration", meaning="rate of change of velocity", quantity="acceleration", dimension=LENGTH / (TIME ** 2))
        assessment = assess_product_dimension(force, ((mass, 1), (acceleration, 1)))
        self.assertEqual("DIMENSIONALLY_COHERENT", assessment.status)
        self.assertTrue(assessment.canonical_semantic_eligible)

    def test_energy_and_torque_share_dimensions_but_not_meaning(self) -> None:
        shared_dimension = MASS * (LENGTH ** 2) / (TIME ** 2)
        energy = concept("e:energy", name="energy", meaning="capacity to perform work", quantity="energy", dimension=shared_dimension, unit="J")
        torque = concept("e:torque", name="torque", meaning="moment of force about an axis", quantity="torque", dimension=shared_dimension)
        self.assertEqual("SAME_DIMENSION_DIFFERENT_QUANTITY_KIND", physical_semantic_relation(energy, torque))
        assessment = assess_additive_compatibility((energy, torque))
        self.assertEqual("ADDITIVE_SEMANTIC_MISREPRESENTATION", assessment.status)
        self.assertFalse(assessment.canonical_semantic_eligible)


class SAA92RevisionTests(unittest.TestCase):
    def test_contradiction_requires_new_grounded_requalification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                old_evidence = egcf.register(evidence("old-pressure"))
                new_evidence = egcf.register(evidence("new-pressure", "semantic-revision"))
                old = concept(
                    old_evidence,
                    name="pressure command",
                    meaning="absolute pressure command",
                    quantity="pressure",
                    dimension=MASS / LENGTH / (TIME ** 2),
                    domain="fluid control",
                    unit="Pa",
                )
                contradiction = detect_semantic_contradiction(
                    old,
                    observed_statement="Experiments show the coordinate is pressure deviation from ambient",
                    observed_meaning="pressure deviation from ambient",
                    evidence_ids=(new_evidence,),
                )
                self.assertEqual("SEMANTIC_CONTRADICTION_OPEN", contradiction.status)
                directives = propagate_semantic_contradiction(contradiction)
                self.assertTrue(any(item.subsystem == "ALGORITHM_STORE" and item.blocking for item in directives))
                falsifier = "coordinate remains unchanged when ambient pressure shifts"
                proposal = propose_semantic_revision(
                    old,
                    (contradiction,),
                    meaning="pressure deviation from ambient",
                    falsifiers=(falsifier,),
                )
                blocked = requalify_semantic_revision(
                    egcf,
                    old,
                    proposal,
                    evidence_ids=(new_evidence,),
                    falsifier_results=(SemanticRevisionFalsifierResult(falsifier, "SURVIVED", new_evidence),),
                    independent_review=False,
                )
                self.assertEqual("SEMANTIC_REQUALIFICATION_BLOCKED", blocked.status)
                qualified = requalify_semantic_revision(
                    egcf,
                    old,
                    proposal,
                    evidence_ids=(new_evidence,),
                    falsifier_results=(SemanticRevisionFalsifierResult(falsifier, "SURVIVED", new_evidence),),
                    independent_review=True,
                )
                self.assertEqual("SEMANTIC_REQUALIFIED", qualified.status)
                self.assertNotEqual(old.concept_signature, qualified.replacement_concept.concept_signature)


class SAA93AlignmentAndStoreTests(unittest.TestCase):
    def test_cross_domain_equivalence_requires_evidence_review_and_surviving_falsifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                left_evidence = egcf.register(evidence("vehicle-speed", "vehicle"))
                right_evidence = egcf.register(evidence("particle-speed", "physics"))
                alignment_evidence = egcf.register(evidence("speed-alignment", "alignment"))
                velocity_dimension = LENGTH / TIME
                left = concept(left_evidence, name="vehicle speed", meaning="magnitude of vehicle translational velocity", quantity="speed", dimension=velocity_dimension, domain="vehicle dynamics", aliases=("road speed",))
                right = concept(right_evidence, name="translational speed", meaning="magnitude of translational velocity", quantity="speed", dimension=velocity_dimension, domain="mechanics")
                falsifier = "equal numeric values under the same frame predict different translational displacement rates"
                proposal = propose_semantic_alignment(
                    left,
                    right,
                    relation="EXACT_EQUIVALENT",
                    shared_meaning="magnitude of translational velocity in a specified frame",
                    expected_effects_match=True,
                    evidence_ids=(alignment_evidence,),
                    falsifiers=(falsifier,),
                    independent_review=True,
                )
                assessment = assess_semantic_alignment(
                    egcf,
                    left,
                    right,
                    proposal,
                    falsifier_results=(SemanticAlignmentFalsifierResult(falsifier, "SURVIVED", alignment_evidence),),
                )
                self.assertEqual("EXACT_CROSS_DOMAIN_SEMANTIC_EQUIVALENCE", assessment.status)
                self.assertTrue(assessment.exact_substitution_eligible)

                ontology = SemanticOntologyStore(egcf)
                left_id = ontology.admit_concept(left)
                right_id = ontology.admit_concept(right)
                ontology.admit_alignment(assessment)
                self.assertIn(right_id, ontology.equivalent_concept_ids(left_id))
                self.assertTrue(ontology.meanings_equivalent("road speed", "translational speed"))
                ontology.rebuild_projection()
                self.assertTrue(ontology.meanings_equivalent("vehicle speed", "translational speed"))

    def test_dimension_mismatch_blocks_forced_exact_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                e1 = egcf.register(evidence("length"))
                e2 = egcf.register(evidence("time"))
                ea = egcf.register(evidence("bad-alignment"))
                length = concept(e1, name="length", meaning="spatial extent", quantity="length", dimension=LENGTH, unit="m")
                duration = concept(e2, name="duration", meaning="elapsed time", quantity="duration", dimension=TIME, unit="s")
                proposal = propose_semantic_alignment(
                    length,
                    duration,
                    relation="EXACT_EQUIVALENT",
                    shared_meaning="same thing",
                    expected_effects_match=True,
                    evidence_ids=(ea,),
                    independent_review=True,
                )
                assessment = assess_semantic_alignment(egcf, length, duration, proposal)
                self.assertEqual("SEMANTIC_ALIGNMENT_CONTRADICTED", assessment.status)
                self.assertFalse(assessment.exact_substitution_eligible)

    def test_ontology_rejects_forged_evidence_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                ontology = SemanticOntologyStore(egcf)
                forged = concept("missing:evidence", name="temperature", meaning="thermodynamic temperature", quantity="temperature", dimension=None)
                with self.assertRaises(EGCFError):
                    ontology.admit_concept(forged)


if __name__ == "__main__":
    unittest.main()
