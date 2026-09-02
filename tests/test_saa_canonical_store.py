from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ourd.egcf.algebra import (
    LinearTransferFunction,
    MIMOTransferMatrix,
    SemanticFalsifierResult,
    assess_representative_candidate_semantics,
    build_normalization_contract,
    canonicalize_mapping,
    canonicalize_mimo_transfer_matrix,
    canonicalize_representative_algorithm,
    discover_representative_inputs,
    evaluate_semantic_candidate,
    make_semantic_candidate,
    structure_from_mapping,
)
from ourd.egcf.canonical_store_api import CanonicalAlgorithmStore
from ourd.egcf.errors import EGCFError
from ourd.egcf.ids import sha256_json, utc_now
from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.store import EGCFStore


def algorithm_mapping(inputs: int, outputs: int, *, extra_node: bool = False):
    nodes = [
        {
            "id": f"out{index}",
            "primitive": "CONST",
            "operands": [{"constant": 0}],
        }
        for index in range(outputs)
    ]
    if extra_node:
        nodes.append(
            {
                "id": "extra",
                "primitive": "CONST",
                "operands": [{"constant": 1}],
            }
        )
    return {
        "name": "canonical-store-fixture",
        "inputs": [
            {"position": index, "name": f"u{index}", "data_type": "scalar"}
            for index in range(inputs)
        ],
        "outputs": [
            {
                "position": index,
                "name": f"y{index}",
                "data_type": "scalar",
                "source": {"node": f"out{index}"},
            }
            for index in range(outputs)
        ],
        "nodes": nodes,
        "entry_nodes": [node["id"] for node in nodes],
    }


def normalization(inputs: int, outputs: int):
    return build_normalization_contract(
        structure_from_mapping(algorithm_mapping(inputs, outputs)),
        input_bounds={index: [0, 1] for index in range(inputs)},
        output_bounds={index: [0, 1] for index in range(outputs)},
        time=1,
    )


def ctf(value):
    return LinearTransferFunction(
        "CONTINUOUS",
        numerator=(str(value),),
        denominator=(1,),
    )


def canonical(rows):
    outputs = len(rows)
    inputs = len(rows[0])
    contract = normalization(inputs, outputs)
    matrix = MIMOTransferMatrix("CONTINUOUS", tuple(tuple(row) for row in rows))
    return canonicalize_mimo_transfer_matrix(matrix, contract), contract


def semantic_evidence(store: EGCFStore, issue, candidate, *, suffix: str):
    content = {
        "issue_id": issue.issue_id,
        "candidate_id": candidate.candidate_id,
        "meaning": candidate.meaning,
        "expected_output_indices": list(candidate.expected_output_indices),
        "excluded_output_indices": list(candidate.excluded_output_indices),
        "review": suffix,
    }
    record = EvidenceArtifact(
        subject_id=candidate.candidate_id,
        claim_ids=[issue.issue_id],
        requirement_ids=[],
        category="semantic-grounding",
        producer="human-canonical-store-test",
        method="independent-semantic-review",
        source_snapshot_hash=sha256_json(content),
        target=issue.coordinate_label,
        oracle="meaning-output-footprint-and-falsifier-review",
        environment={"suite": "saa-6.1-6.4"},
        command_id="algorithm.qualify@1",
        algorithm_id="saa-canonical-store-test@1",
        created_at=utc_now(),
        sha256=sha256_json(content),
        success=True,
        limitations=[],
        independence_group=f"semantic-review:{suffix}",
        simulated=False,
        content=content,
    )
    return store.register(record)


def build_form(
    store: EGCFStore,
    rows,
    *,
    meanings_by_output=None,
    structural_extra: bool = False,
    grounded: bool = True,
    suffix: str = "a",
):
    mimo, contract = canonical(rows)
    search = discover_representative_inputs(mimo)
    issues = assess_representative_candidate_semantics(mimo, search)
    candidates = []
    resolutions = []
    for issue in issues:
        expected = issue.affected_output_indices
        excluded = tuple(output for output in range(mimo.output_count) if output not in expected)
        output_key = expected[0] if expected else -1
        meaning = (
            meanings_by_output.get(output_key)
            if meanings_by_output is not None
            else f"representative effect on output {output_key}"
        )
        falsifier = f"coordinate {issue.coordinate_index} changes an excluded output"
        candidate = make_semantic_candidate(
            issue,
            meaning=meaning,
            expected_output_indices=expected,
            excluded_output_indices=excluded,
            falsifiers=(falsifier,),
        )
        evidence_id = (
            semantic_evidence(store, issue, candidate, suffix=f"{suffix}-{issue.coordinate_index}")
            if grounded
            else f"missing-evidence:{suffix}:{issue.coordinate_index}"
        )
        resolution = evaluate_semantic_candidate(
            issue,
            candidate,
            evidence_ids=(evidence_id,),
            falsifier_results=(
                SemanticFalsifierResult(falsifier, "SURVIVED", evidence_id),
            ),
            independent_review=True,
        )
        candidates.append(candidate)
        resolutions.append(resolution)
    ir = canonicalize_mapping(
        algorithm_mapping(len(rows[0]), len(rows), extra_node=structural_extra)
    )
    form = canonicalize_representative_algorithm(
        structural_ir=ir,
        source_normalization=contract,
        mimo=mimo,
        representative_search=search,
        semantic_issues=issues,
        semantic_candidates=candidates,
        semantic_resolutions=resolutions,
    )
    return form, tuple(issues), tuple(candidates), tuple(resolutions)


class CanonicalStoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.egcf = EGCFStore(self.root)
        self.store = CanonicalAlgorithmStore(self.egcf)

    def tearDown(self) -> None:
        self.egcf.close()
        self.temp.cleanup()


class SAA61PersistenceTests(CanonicalStoreFixture):
    def test_new_form_is_persisted_once_with_source_provenance(self) -> None:
        form, issues, candidates, resolutions = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
        )
        result = self.store.admit(
            form,
            semantic_issues=issues,
            semantic_candidates=candidates,
            semantic_resolutions=resolutions,
        )
        self.assertEqual("ADMITTED_NEW_CANONICAL", result.status)
        self.assertEqual(1, result.store_generation)
        self.assertEqual(1, len(self.store.list()))
        self.assertEqual(1, len(self.store.sources(result.canonical_id)))
        envelope = self.store.get(result.canonical_id)
        self.assertEqual(
            form.representative_behavior_signature,
            envelope["payload"]["representative_behavior_signature"],
        )
        self.assertNotIn("source_structural_hash", envelope["payload"])
        self.assertEqual(
            "DERIVED_FROM",
            self.store.relations(result.canonical_id)[0].relation_type,
        )

    def test_projection_rebuild_recovers_canonical_indexes(self) -> None:
        form, issues, candidates, resolutions = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
        )
        admitted = self.store.admit(
            form,
            semantic_issues=issues,
            semantic_candidates=candidates,
            semantic_resolutions=resolutions,
        )
        self.egcf.rebuild_projection()
        rebuilt = CanonicalAlgorithmStore(self.egcf)
        self.assertEqual(1, len(rebuilt.list()))
        lookup = rebuilt.lookup(form)
        self.assertEqual("REPRESENTATIVE_EQUIVALENT_ALREADY_STORED", lookup.status)
        self.assertEqual((admitted.canonical_id,), lookup.exact_equivalent_ids)
        self.assertEqual((admitted.canonical_id,), lookup.source_bound_match_ids)


class SAA62IndexTests(CanonicalStoreFixture):
    def test_math_and_semantic_indexes_distinguish_meaning_from_equation(self) -> None:
        first, issues1, candidates1, resolutions1 = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
            suffix="first",
        )
        first_result = self.store.admit(
            first,
            semantic_issues=issues1,
            semantic_candidates=candidates1,
            semantic_resolutions=resolutions1,
        )
        second, issues2, candidates2, resolutions2 = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "thermal demand", 1: "pressure deviation"},
            suffix="second",
        )
        lookup = self.store.lookup(second)
        self.assertEqual("MATHEMATICAL_MATCH_SEMANTIC_DIFFERENCE", lookup.status)
        self.assertEqual((first_result.canonical_id,), lookup.mathematical_match_ids)
        second_result = self.store.admit(
            second,
            semantic_issues=issues2,
            semantic_candidates=candidates2,
            semantic_resolutions=resolutions2,
        )
        self.assertNotEqual(first_result.canonical_id, second_result.canonical_id)
        self.assertEqual(2, second_result.store_generation)
        self.assertEqual(2, len(self.store.list()))
        near = self.store.relations(second_result.canonical_id, relation_type="NEAR_VARIANT_OF")
        self.assertEqual(1, len(near))

    def test_same_semantics_different_dynamics_remain_distinct(self) -> None:
        meanings = {0: "temperature deviation", 1: "pressure deviation"}
        first, i1, c1, r1 = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output=meanings,
            suffix="first",
        )
        first_result = self.store.admit(first, semantic_issues=i1, semantic_candidates=c1, semantic_resolutions=r1)
        second, i2, c2, r2 = build_form(
            self.egcf,
            ((ctf(4), ctf(0)), (ctf(0), ctf(5))),
            meanings_by_output=meanings,
            suffix="second",
        )
        lookup = self.store.lookup(second)
        self.assertEqual("SEMANTIC_MATCH_MATHEMATICAL_DIFFERENCE", lookup.status)
        self.assertEqual((first_result.canonical_id,), lookup.semantic_match_ids)
        second_result = self.store.admit(second, semantic_issues=i2, semantic_candidates=c2, semantic_resolutions=r2)
        self.assertNotEqual(first_result.canonical_id, second_result.canonical_id)


class SAA63UniquenessTests(CanonicalStoreFixture):
    def test_equivalent_source_structure_reuses_existing_canonical_node(self) -> None:
        meanings = {0: "temperature deviation", 1: "pressure deviation"}
        first, i1, c1, r1 = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output=meanings,
            structural_extra=False,
            suffix="plain",
        )
        first_result = self.store.admit(first, semantic_issues=i1, semantic_candidates=c1, semantic_resolutions=r1)
        second, i2, c2, r2 = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output=meanings,
            structural_extra=True,
            suffix="extra",
        )
        self.assertNotEqual(first.canonical_algorithm_signature, second.canonical_algorithm_signature)
        self.assertEqual(first.representative_behavior_signature, second.representative_behavior_signature)
        second_result = self.store.admit(second, semantic_issues=i2, semantic_candidates=c2, semantic_resolutions=r2)
        self.assertEqual("REUSED_EQUIVALENT_CANONICAL", second_result.status)
        self.assertEqual(first_result.canonical_id, second_result.canonical_id)
        self.assertEqual(1, len(self.store.list()))
        self.assertEqual(2, len(self.store.sources(first_result.canonical_id)))
        equivalences = self.store.relations(first_result.canonical_id, relation_type="EQUIVALENT_TO")
        self.assertEqual(1, len(equivalences))

    def test_ungrounded_semantic_evidence_is_rejected_at_store_boundary(self) -> None:
        form, issues, candidates, resolutions = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
            grounded=False,
        )
        with self.assertRaises(EGCFError):
            self.store.admit(
                form,
                semantic_issues=issues,
                semantic_candidates=candidates,
                semantic_resolutions=resolutions,
            )

    def test_tampered_saa6_signature_is_rejected(self) -> None:
        form, issues, candidates, resolutions = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
        )
        tampered = replace(form, representative_behavior_signature="0" * 64)
        with self.assertRaises(EGCFError):
            self.store.admit(
                tampered,
                semantic_issues=issues,
                semantic_candidates=candidates,
                semantic_resolutions=resolutions,
            )


class SAA64RelationGraphTests(CanonicalStoreFixture):
    def test_evidence_backed_generalization_relation_is_queryable(self) -> None:
        first, i1, c1, r1 = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
            suffix="first",
        )
        first_result = self.store.admit(first, semantic_issues=i1, semantic_candidates=c1, semantic_resolutions=r1)
        second, i2, c2, r2 = build_form(
            self.egcf,
            ((ctf(4), ctf(0)), (ctf(0), ctf(5))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
            suffix="second",
        )
        second_result = self.store.admit(second, semantic_issues=i2, semantic_candidates=c2, semantic_resolutions=r2)
        issue = i1[0]
        candidate = c1[0]
        evidence_id = semantic_evidence(self.egcf, issue, candidate, suffix="relation")
        relation_id = self.store.add_relation(
            first_result.canonical_id,
            second_result.canonical_id,
            "GENERALIZES",
            basis="verified domain inclusion under a shared semantic contract",
            evidence_ids=(evidence_id,),
        )
        relations = self.store.relations(first_result.canonical_id, relation_type="GENERALIZES")
        self.assertEqual(1, len(relations))
        self.assertEqual(relation_id, relations[0].relation_id)
        neighbors = self.store.neighbors(first_result.canonical_id)
        self.assertTrue(any(item["neighbor_ref"] == second_result.canonical_id for item in neighbors))

    def test_manual_equivalence_assertion_is_forbidden(self) -> None:
        form, issues, candidates, resolutions = build_form(
            self.egcf,
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings_by_output={0: "temperature deviation", 1: "pressure deviation"},
        )
        result = self.store.admit(form, semantic_issues=issues, semantic_candidates=candidates, semantic_resolutions=resolutions)
        with self.assertRaises(EGCFError):
            self.store.add_relation(
                result.canonical_id,
                result.canonical_id,
                "EQUIVALENT_TO",
                basis="someone says so",
                evidence_ids=(),
            )


if __name__ == "__main__":
    unittest.main()
