from __future__ import annotations

import unittest

from ourd.egcf.algebra import (
    LinearTransferFunction,
    MIMOTransferMatrix,
    assess_mimo_representation,
    assess_mimo_semantics,
    assess_representative_candidate_semantics,
    build_normalization_contract,
    canonical_semantic_admission,
    canonicalize_mimo_transfer_matrix,
    discover_representative_inputs,
    evaluate_semantic_candidate,
    make_semantic_candidate,
    propagate_semantic_issues,
    semantic_followup_questions,
    SemanticFalsifierResult,
    structure_from_mapping,
)


def algorithm_mapping(inputs: int, outputs: int):
    nodes = [
        {
            "id": f"out{index}",
            "primitive": "CONST",
            "operands": [{"constant": 0}],
        }
        for index in range(outputs)
    ]
    return {
        "name": "semantic-fixture",
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
    matrix = MIMOTransferMatrix("CONTINUOUS", tuple(tuple(row) for row in rows))
    return canonicalize_mimo_transfer_matrix(
        matrix,
        normalization(len(rows[0]), len(rows)),
    )


class SemanticMisrepresentationTests(unittest.TestCase):
    def test_coupled_inputs_are_semantic_misrepresentations(self) -> None:
        mimo = canonical(((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))))
        math = assess_mimo_representation(mimo)
        semantic = assess_mimo_semantics(
            mimo,
            mathematical_assessment=math,
            input_semantics={0: "confidence", 1: "support"},
            output_semantics={0: "acceptance", 1: "termination"},
        )
        self.assertEqual("SEMANTIC_MISREPRESENTATION", semantic.semantic_status)
        self.assertFalse(semantic.canonical_admission_eligible)
        self.assertEqual(2, len(semantic.issues))
        self.assertTrue(all(issue.status == "SEMANTIC_MISREPRESENTATION" for issue in semantic.issues))
        self.assertTrue(all(issue.issue_kind == "COUPLED_INPUT" for issue in semantic.issues))
        self.assertTrue(all(len(issue.affected_output_indices) == 2 for issue in semantic.issues))
        questions = semantic_followup_questions(semantic.issues)
        self.assertTrue(any("independent quantity" in question for question in questions))
        self.assertTrue(any("confidence" in question for question in questions))

    def test_crossed_but_decoupled_ports_are_not_called_semantic_misrepresentation(self) -> None:
        mimo = canonical(((ctf(0), ctf(2)), (ctf(3), ctf(0))))
        semantic = assess_mimo_semantics(mimo)
        self.assertNotEqual("SEMANTIC_MISREPRESENTATION", semantic.semantic_status)
        self.assertEqual("UNRESOLVED_SEMANTICS", semantic.semantic_status)
        self.assertTrue(all(issue.status == "UNRESOLVED_SEMANTICS" for issue in semantic.issues))

    def test_declared_meaning_does_not_equal_resolved_meaning(self) -> None:
        mimo = canonical(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        semantic = assess_mimo_semantics(
            mimo,
            input_semantics={0: "temperature error", 1: "pressure error"},
        )
        self.assertTrue(semantic.mathematical_admission_eligible)
        self.assertFalse(semantic.canonical_admission_eligible)
        self.assertEqual("DECLARED_SEMANTICS", semantic.semantic_status)
        self.assertTrue(all(issue.status == "DECLARED_SEMANTICS" for issue in semantic.issues))

    def test_redundant_input_is_semantically_misrepresented(self) -> None:
        mimo = canonical(((ctf(1), ctf(2), ctf(0)), (ctf(0), ctf(0), ctf(1))))
        semantic = assess_mimo_semantics(mimo, input_semantics={1: "duplicate gain"})
        self.assertEqual("SEMANTIC_MISREPRESENTATION", semantic.semantic_status)
        self.assertEqual(1, len(semantic.issues))
        self.assertEqual("REDUNDANT_INPUT", semantic.issues[0].issue_kind)
        self.assertEqual(1, semantic.issues[0].coordinate_index)


class SemanticRepresentativeCoordinateTests(unittest.TestCase):
    def test_new_linear_basis_requires_new_semantic_resolution(self) -> None:
        mimo = canonical(((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))))
        search = discover_representative_inputs(mimo)
        self.assertTrue(search.representative_found)
        issues = assess_representative_candidate_semantics(
            mimo,
            search,
            input_semantics={0: "confidence", 1: "support"},
            output_semantics={0: "acceptance", 1: "termination"},
        )
        self.assertEqual(2, len(issues))
        self.assertTrue(all(issue.coordinate_kind == "REPRESENTATIVE_INPUT" for issue in issues))
        self.assertTrue(all(issue.status == "UNRESOLVED_SEMANTICS" for issue in issues))
        self.assertTrue(any(len(issue.source_input_indices) > 1 for issue in issues))
        self.assertTrue(any("newly discovered representative coordinate" in q for issue in issues for q in issue.questions))


class SemanticResolutionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mimo = canonical(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        self.semantic = assess_mimo_semantics(
            self.mimo,
            input_semantics={0: "temperature error", 1: "pressure error"},
        )
        self.issue = self.semantic.issues[0]

    def candidate(self, *, expected=(0,), excluded=(1,)):
        return make_semantic_candidate(
            self.issue,
            meaning="temperature deviation",
            expected_output_indices=expected,
            excluded_output_indices=excluded,
            assumptions=("pressure state remains fixed",),
            falsifiers=("temperature coordinate changes pressure output",),
        )

    def test_model_proposed_semantics_cannot_self_resolve(self) -> None:
        candidate = self.candidate()
        result = evaluate_semantic_candidate(self.issue, candidate)
        self.assertEqual("MODEL_PROPOSED_SEMANTICS", candidate.epistemic_status)
        self.assertEqual("CANDIDATE_REPRESENTATIVE_SEMANTICS", result.status)
        self.assertFalse(result.canonical_semantic_eligible)

    def test_wrong_output_footprint_is_contradicted(self) -> None:
        candidate = self.candidate(expected=(1,), excluded=(0,))
        result = evaluate_semantic_candidate(
            self.issue,
            candidate,
            evidence_ids=("evidence:1",),
            independent_review=True,
        )
        self.assertEqual("SEMANTICALLY_CONTRADICTED", result.status)
        self.assertEqual(0, result.semantic_fit_bp)

    def test_evidence_without_falsifier_survival_is_not_resolved(self) -> None:
        candidate = self.candidate()
        result = evaluate_semantic_candidate(
            self.issue,
            candidate,
            evidence_ids=("evidence:1",),
            falsifier_results=(
                SemanticFalsifierResult(
                    "temperature coordinate changes pressure output",
                    "UNTESTED",
                ),
            ),
            independent_review=True,
        )
        self.assertEqual("EVIDENCE_SUPPORTED_SEMANTICS", result.status)
        self.assertFalse(result.canonical_semantic_eligible)

    def test_resolution_requires_evidence_falsifier_survival_and_independent_review(self) -> None:
        candidate = self.candidate()
        result = evaluate_semantic_candidate(
            self.issue,
            candidate,
            evidence_ids=("evidence:1", "evidence:2"),
            falsifier_results=(
                SemanticFalsifierResult(
                    "temperature coordinate changes pressure output",
                    "SURVIVED",
                    "evidence:2",
                ),
            ),
            independent_review=True,
        )
        self.assertEqual("SEMANTICALLY_RESOLVED", result.status)
        self.assertEqual(10000, result.semantic_fit_bp)
        self.assertTrue(result.canonical_semantic_eligible)

    def test_final_canonical_gate_requires_every_issue_resolved(self) -> None:
        resolutions = []
        for index, issue in enumerate(self.semantic.issues):
            expected = issue.affected_output_indices
            excluded = tuple(value for value in range(self.mimo.output_count) if value not in expected)
            candidate = make_semantic_candidate(
                issue,
                meaning=f"resolved dimension {index}",
                expected_output_indices=expected,
                excluded_output_indices=excluded,
                falsifiers=(f"falsifier {index}",),
            )
            resolutions.append(
                evaluate_semantic_candidate(
                    issue,
                    candidate,
                    evidence_ids=(f"evidence:{index}",),
                    falsifier_results=(
                        SemanticFalsifierResult(f"falsifier {index}", "SURVIVED"),
                    ),
                    independent_review=True,
                )
            )
        self.assertTrue(
            canonical_semantic_admission(
                mathematical_eligible=self.semantic.mathematical_admission_eligible,
                issues=self.semantic.issues,
                resolutions=resolutions,
            )
        )
        self.assertFalse(
            canonical_semantic_admission(
                mathematical_eligible=False,
                issues=self.semantic.issues,
                resolutions=resolutions,
            )
        )


class SemanticPropagationTests(unittest.TestCase):
    def test_every_issue_is_questioned_across_governance_subsystems(self) -> None:
        mimo = canonical(((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))))
        semantic = assess_mimo_semantics(mimo)
        directives = propagate_semantic_issues(semantic.issues)
        expected_subsystems = {
            "EON",
            "OURD",
            "IURM",
            "CFEL",
            "BD_DL",
            "HYPOTHESIS_STATE",
            "ALGORITHM_STORE",
        }
        for issue in semantic.issues:
            local = [directive for directive in directives if directive.issue_id == issue.issue_id]
            self.assertEqual(expected_subsystems, {directive.subsystem for directive in local})
            self.assertTrue(all(directive.question_required for directive in local))
            blocking = {directive.subsystem for directive in local if directive.blocking}
            self.assertEqual({"IURM", "ALGORITHM_STORE"}, blocking)
            self.assertTrue(all(directive.payload["questions"] for directive in local))


if __name__ == "__main__":
    unittest.main()
