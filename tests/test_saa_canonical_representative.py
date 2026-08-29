from __future__ import annotations

import unittest
from fractions import Fraction

from ourd.egcf.algebra import (
    LinearTransferFunction,
    MIMOTransferMatrix,
    SemanticFalsifierResult,
    assess_representative_candidate_semantics,
    build_normalization_contract,
    canonicalize_mapping,
    canonicalize_mimo_transfer_matrix,
    canonicalize_representative_algorithm,
    denormalize_representative_value,
    discover_representative_inputs,
    evaluate_semantic_candidate,
    make_semantic_candidate,
    normalize_representative_value,
    structure_from_mapping,
)
from ourd.egcf.errors import EGCFError


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
        "name": "saa6-fixture",
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


def normalization(inputs: int, outputs: int, *, approximate: bool = False):
    bound = (
        {"minimum": 0, "maximum": 1, "kind": "ENGINEERING_BOUND"}
        if approximate
        else [0, 1]
    )
    return build_normalization_contract(
        structure_from_mapping(algorithm_mapping(inputs, outputs)),
        input_bounds={index: bound for index in range(inputs)},
        output_bounds={index: bound for index in range(outputs)},
        time=1,
    )


def ctf(value):
    return LinearTransferFunction(
        "CONTINUOUS",
        numerator=(str(value),),
        denominator=(1,),
    )


def canonical(rows, *, contract=None):
    outputs = len(rows)
    inputs = len(rows[0])
    contract = contract or normalization(inputs, outputs)
    matrix = MIMOTransferMatrix("CONTINUOUS", tuple(tuple(row) for row in rows))
    return canonicalize_mimo_transfer_matrix(matrix, contract), contract


def resolved_representative_semantics(mimo, search, meanings=None):
    issues = assess_representative_candidate_semantics(mimo, search)
    candidates = []
    resolutions = []
    for issue in issues:
        expected = issue.affected_output_indices
        excluded = tuple(
            output
            for output in range(mimo.output_count)
            if output not in expected
        )
        meaning = (
            meanings.get(issue.coordinate_index)
            if meanings is not None
            else f"representative effect on y{expected[0] if expected else 'none'}"
        )
        falsifier = f"coordinate {issue.coordinate_index} changes an excluded output"
        semantic_candidate = make_semantic_candidate(
            issue,
            meaning=meaning,
            expected_output_indices=expected,
            excluded_output_indices=excluded,
            falsifiers=(falsifier,),
        )
        resolution = evaluate_semantic_candidate(
            issue,
            semantic_candidate,
            evidence_ids=(f"evidence:{issue.coordinate_index}",),
            falsifier_results=(
                SemanticFalsifierResult(
                    falsifier,
                    "SURVIVED",
                    f"evidence:{issue.coordinate_index}",
                ),
            ),
            independent_review=True,
        )
        candidates.append(semantic_candidate)
        resolutions.append(resolution)
    return issues, tuple(candidates), tuple(resolutions)


def build_form(rows, *, meanings=None, structural_extra=False):
    mimo, contract = canonical(rows)
    search = discover_representative_inputs(mimo)
    issues, semantic_candidates, resolutions = resolved_representative_semantics(
        mimo, search, meanings=meanings
    )
    ir = canonicalize_mapping(
        algorithm_mapping(len(rows[0]), len(rows), extra_node=structural_extra)
    )
    form = canonicalize_representative_algorithm(
        structural_ir=ir,
        source_normalization=contract,
        mimo=mimo,
        representative_search=search,
        semantic_issues=issues,
        semantic_candidates=semantic_candidates,
        semantic_resolutions=resolutions,
    )
    return form, mimo, search, contract


class SAA6BoundaryTests(unittest.TestCase):
    def test_mixed_representative_coordinates_get_exact_source_box_bounds(self) -> None:
        form, _, search, _ = build_form(
            ((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1)))
        )
        candidate = search.best_candidate
        assert candidate is not None
        self.assertTrue(form.canonical_admission_eligible)
        self.assertEqual("ELIGIBLE_CANONICAL_REPRESENTATIVE_FORM", form.store_status)
        self.assertEqual(2, len(form.inputs))
        by_original = {item.candidate_input_index: item for item in form.inputs}
        for original_index in range(candidate.representative_input_count):
            coefficients = candidate.source_to_representative_projection[original_index]
            expected_minimum = sum(
                (min(Fraction(0), value) for value in coefficients), Fraction(0)
            )
            expected_maximum = sum(
                (max(Fraction(0), value) for value in coefficients), Fraction(0)
            )
            boundary = by_original[original_index].boundary
            self.assertEqual(expected_minimum, boundary.raw_minimum)
            self.assertEqual(expected_maximum, boundary.raw_maximum)
            self.assertEqual(Fraction(0), normalize_representative_value(boundary, expected_minimum))
            self.assertEqual(Fraction(1), normalize_representative_value(boundary, expected_maximum))
            self.assertEqual(
                expected_minimum,
                denormalize_representative_value(boundary, Fraction(0)),
            )
            self.assertEqual(
                expected_maximum,
                denormalize_representative_value(boundary, Fraction(1)),
            )

    def test_selector_coordinates_retain_unit_interval(self) -> None:
        form, _, _, _ = build_form(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        self.assertEqual(2, len(form.inputs))
        for item in form.inputs:
            self.assertEqual(Fraction(0), item.boundary.raw_minimum)
            self.assertEqual(Fraction(1), item.boundary.raw_maximum)
            self.assertEqual(Fraction(1), item.boundary.raw_width)

    def test_out_of_range_representative_values_fail_closed(self) -> None:
        form, _, _, _ = build_form(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        boundary = form.inputs[0].boundary
        with self.assertRaises(EGCFError):
            normalize_representative_value(boundary, Fraction(2))
        with self.assertRaises(EGCFError):
            denormalize_representative_value(boundary, Fraction(3, 2))


class SAA6AdmissionTests(unittest.TestCase):
    def test_unresolved_semantics_block_canonical_representative_form(self) -> None:
        mimo, contract = canonical(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        search = discover_representative_inputs(mimo)
        issues = assess_representative_candidate_semantics(mimo, search)
        semantic_candidates = []
        resolutions = []
        for issue in issues:
            candidate = make_semantic_candidate(
                issue,
                meaning=f"meaning {issue.coordinate_index}",
                expected_output_indices=issue.affected_output_indices,
            )
            semantic_candidates.append(candidate)
            resolutions.append(evaluate_semantic_candidate(issue, candidate))
        with self.assertRaises(EGCFError):
            canonicalize_representative_algorithm(
                structural_ir=canonicalize_mapping(algorithm_mapping(2, 2)),
                source_normalization=contract,
                mimo=mimo,
                representative_search=search,
                semantic_issues=issues,
                semantic_candidates=semantic_candidates,
                semantic_resolutions=resolutions,
            )

    def test_approximate_source_normalization_is_rejected(self) -> None:
        form_mimo, _ = canonical(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        search = discover_representative_inputs(form_mimo)
        issues, semantic_candidates, resolutions = resolved_representative_semantics(
            form_mimo, search
        )
        with self.assertRaises(EGCFError):
            canonicalize_representative_algorithm(
                structural_ir=canonicalize_mapping(algorithm_mapping(2, 2)),
                source_normalization=normalization(2, 2, approximate=True),
                mimo=form_mimo,
                representative_search=search,
                semantic_issues=issues,
                semantic_candidates=semantic_candidates,
                semantic_resolutions=resolutions,
            )

    def test_zero_effective_input_form_is_admissible(self) -> None:
        mimo, contract = canonical(((ctf(0), ctf(0)), (ctf(0), ctf(0))))
        search = discover_representative_inputs(mimo)
        issues = assess_representative_candidate_semantics(mimo, search)
        self.assertEqual((), issues)
        form = canonicalize_representative_algorithm(
            structural_ir=canonicalize_mapping(algorithm_mapping(2, 2)),
            source_normalization=contract,
            mimo=mimo,
            representative_search=search,
            semantic_issues=(),
            semantic_candidates=(),
            semantic_resolutions=(),
        )
        self.assertEqual(0, form.representative_input_count)
        self.assertEqual((), form.inputs)
        self.assertTrue(all(len(row) == 0 for row in form.normalized_channels))
        self.assertTrue(form.canonical_admission_eligible)


class SAA6CanonicalIdentityTests(unittest.TestCase):
    def test_crossed_port_order_collapses_in_representative_behavior_identity(self) -> None:
        diagonal, _, _, _ = build_form(
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings={0: "effect zero", 1: "effect one"},
        )
        crossed, _, crossed_search, _ = build_form(
            ((ctf(0), ctf(2)), (ctf(3), ctf(0))),
            meanings={0: "effect one", 1: "effect zero"},
        )
        candidate = crossed_search.best_candidate
        assert candidate is not None
        self.assertEqual((1, 0), candidate.preferred_input_to_output_pairing)
        self.assertEqual(
            diagonal.mathematical_representative_signature,
            crossed.mathematical_representative_signature,
        )
        self.assertEqual(
            diagonal.semantic_representative_signature,
            crossed.semantic_representative_signature,
        )
        self.assertEqual(
            diagonal.representative_behavior_signature,
            crossed.representative_behavior_signature,
        )

    def test_semantic_identity_casefolds_superficial_text_case(self) -> None:
        upper, _, _, _ = build_form(
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings={0: "Temperature Deviation", 1: "Pressure Deviation"},
        )
        lower, _, _, _ = build_form(
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings={0: "temperature deviation", 1: "pressure deviation"},
        )
        self.assertEqual(
            upper.semantic_representative_signature,
            lower.semantic_representative_signature,
        )
        self.assertEqual(
            upper.representative_behavior_signature,
            lower.representative_behavior_signature,
        )

    def test_source_structure_is_conservative_outer_identity_only(self) -> None:
        ordinary, _, _, _ = build_form(
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings={0: "dimension zero", 1: "dimension one"},
            structural_extra=False,
        )
        extra, _, _, _ = build_form(
            ((ctf(2), ctf(0)), (ctf(0), ctf(3))),
            meanings={0: "dimension zero", 1: "dimension one"},
            structural_extra=True,
        )
        self.assertEqual(
            ordinary.representative_behavior_signature,
            extra.representative_behavior_signature,
        )
        self.assertNotEqual(ordinary.source_structural_hash, extra.source_structural_hash)
        self.assertNotEqual(
            ordinary.canonical_algorithm_signature,
            extra.canonical_algorithm_signature,
        )
        self.assertEqual(
            "CONSERVATIVE_SOURCE_STRUCTURE_BINDING",
            ordinary.structural_binding_policy,
        )

    def test_representative_form_is_deterministic(self) -> None:
        left, _, _, _ = build_form(
            ((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))),
            meanings={0: "first latent dimension", 1: "second latent dimension"},
        )
        right, _, _, _ = build_form(
            ((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))),
            meanings={0: "first latent dimension", 1: "second latent dimension"},
        )
        self.assertEqual(left.audit_hash, right.audit_hash)
        self.assertEqual(left.canonical_algorithm_signature, right.canonical_algorithm_signature)
        self.assertEqual(left.to_dict(), right.to_dict())


if __name__ == "__main__":
    unittest.main()
