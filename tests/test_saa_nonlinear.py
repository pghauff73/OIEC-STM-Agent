from __future__ import annotations

import unittest
from fractions import Fraction

from ourd.egcf.algebra import (
    SemanticFalsifierResult,
    TaylorJetSpec,
    TaylorJetTerm,
    apply_nonlinear_shear,
    canonicalize_nonlinear_representative,
    canonicalize_taylor_jet,
    compare_taylor_jets,
    evaluate_semantic_candidate,
    make_nonlinear_shear,
    make_semantic_candidate,
    propagate_semantic_issues,
    search_nonlinear_representative_coordinates,
)
from ourd.egcf.errors import EGCFError
from tests.test_saa_canonical_representative import build_form, ctf


def parent_form():
    form, _, _, _ = build_form(
        ((ctf(1), ctf(0)), (ctf(0), ctf(1))),
        meanings={0: "temperature control", 1: "pressure control"},
    )
    return form


def make_jet(
    terms,
    *,
    order=2,
    radius=(Fraction(1, 4), Fraction(1, 4)),
):
    form = parent_form()
    jet = canonicalize_taylor_jet(
        form,
        TaylorJetSpec(
            input_count=2,
            output_count=2,
            order=order,
            center=(Fraction(1, 2), Fraction(1, 2)),
            validity_radius=radius,
            terms=tuple(terms),
        ),
    )
    return form, jet


class SAA7TaylorJetTests(unittest.TestCase):
    def test_exact_jet_is_local_only_and_evaluates_exactly(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (2, 0), Fraction(2)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        self.assertFalse(jet.global_equivalence_eligible)
        self.assertEqual("LOCAL_TRUNCATED_JET_ONLY", jet.local_equivalence_scope)
        self.assertEqual("NONLINEAR_REPRESENTATIVE", jet.coupling.status)
        self.assertEqual(
            (Fraction(3, 16), Fraction(0)),
            jet.evaluate((Fraction(3, 4), Fraction(1, 2))),
        )
        self.assertEqual(form.representative_behavior_signature, jet.parent_representative_behavior_signature)

    def test_duplicate_terms_collapse_and_order_is_canonical(self) -> None:
        _, left = make_jet(
            (
                TaylorJetTerm(1, (0, 1), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1, 2)),
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1, 2)),
            )
        )
        _, right = make_jet(
            (
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        self.assertEqual(left.coefficient_signature, right.coefficient_signature)
        self.assertEqual(left.terms, right.terms)

    def test_float_coefficients_and_invalid_local_box_fail_closed(self) -> None:
        form = parent_form()
        with self.assertRaises(EGCFError):
            canonicalize_taylor_jet(
                form,
                TaylorJetSpec(
                    input_count=2,
                    output_count=2,
                    order=2,
                    center=(0.5, Fraction(1, 2)),
                    validity_radius=(Fraction(1, 4), Fraction(1, 4)),
                    terms=(TaylorJetTerm(0, (1, 0), Fraction(1)),),
                ),
            )
        with self.assertRaises(EGCFError):
            canonicalize_taylor_jet(
                form,
                TaylorJetSpec(
                    input_count=2,
                    output_count=2,
                    order=2,
                    center=(Fraction(1, 10), Fraction(1, 2)),
                    validity_radius=(Fraction(1, 4), Fraction(1, 4)),
                    terms=(TaylorJetTerm(0, (1, 0), Fraction(1)),),
                ),
            )

    def test_same_coefficients_different_scope_match_only_on_local_intersection(self) -> None:
        terms = (
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (2, 0), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        )
        _, wide = make_jet(terms, radius=(Fraction(1, 4), Fraction(1, 4)))
        _, narrow = make_jet(terms, radius=(Fraction(1, 8), Fraction(1, 8)))
        comparison = compare_taylor_jets(wide, narrow)
        self.assertEqual(wide.coefficient_signature, narrow.coefficient_signature)
        self.assertNotEqual(wide.scope_signature, narrow.scope_signature)
        self.assertEqual("EXACT_LOCAL_JET_MATCH_ON_INTERSECTION", comparison.status)
        self.assertEqual((Fraction(1, 8), Fraction(1, 8)), comparison.overlap_radius)
        self.assertFalse(comparison.global_equivalence_eligible)

    def test_cross_and_off_pair_terms_are_semantic_misrepresentation(self) -> None:
        _, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (1, 1), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        self.assertEqual("NONLINEAR_SEMANTIC_MISREPRESENTATION", jet.coupling.status)
        self.assertGreaterEqual(jet.coupling.coupling_score, 2)
        self.assertTrue(jet.coupling.cross_terms)
        self.assertTrue(jet.coupling.off_pair_terms)


class SAA71RepresentativeSearchTests(unittest.TestCase):
    def test_exact_quadratic_shear_recovers_decoupled_local_coordinates(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        search = search_nonlinear_representative_coordinates(form, jet)
        self.assertTrue(search.representative_found)
        self.assertEqual("NONLINEAR_REPRESENTATIVE_FORM_FOUND", search.status)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertEqual(0, candidate.coupling_score)
        self.assertEqual(1, len(candidate.transforms))
        transform = candidate.transforms[0]
        self.assertEqual(0, transform.target_input_index)
        self.assertEqual((0, 2), transform.monomial_powers)
        self.assertEqual(Fraction(1), transform.coefficient)
        self.assertEqual(Fraction(3, 16), candidate.transformed_jet.validity_radius[0])
        self.assertTrue(candidate.semantic_issues)
        self.assertFalse(candidate.local_canonical_eligible)

    def test_manual_exact_shear_is_invertible_to_truncation_order(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        transform = make_nonlinear_shear(
            target_input_index=0,
            monomial_powers=(0, 2),
            coefficient=1,
        )
        transformed = apply_nonlinear_shear(form, jet, transform)
        self.assertEqual("NONLINEAR_REPRESENTATIVE", transformed.coupling.status)
        self.assertEqual(
            {
                (term.output_index, term.powers, term.coefficient)
                for term in transformed.terms
            },
            {
                (0, (1, 0), Fraction(1)),
                (1, (0, 1), Fraction(1)),
            },
        )

    def test_cross_term_containing_target_remains_unresolved_conservatively(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (1, 1), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        search = search_nonlinear_representative_coordinates(form, jet)
        self.assertFalse(search.representative_found)
        self.assertEqual("NONLINEAR_REPRESENTATION_UNRESOLVED", search.status)
        self.assertFalse(search.budget_exhausted)

    def test_already_decoupled_nonlinearity_inherits_saa6_semantics(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (2, 0), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
                TaylorJetTerm(1, (0, 3), Fraction(1, 2)),
            ),
            order=3,
        )
        search = search_nonlinear_representative_coordinates(form, jet)
        self.assertEqual("NONLINEAR_REPRESENTATIVE_ALREADY_FOUND", search.status)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertEqual((), candidate.transforms)
        self.assertEqual((), candidate.semantic_issues)
        self.assertTrue(candidate.local_canonical_eligible)
        canonical = canonicalize_nonlinear_representative(form, search)
        self.assertTrue(canonical.local_canonical_eligible)
        self.assertFalse(canonical.global_equivalence_eligible)

    def test_transformed_coordinate_cannot_inherit_meaning_without_new_evidence(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        search = search_nonlinear_representative_coordinates(form, jet)
        candidate = search.best_candidate
        assert candidate is not None
        issue = candidate.semantic_issues[0]
        self.assertEqual("UNRESOLVED_NONLINEAR_SEMANTICS", issue.status)
        with self.assertRaises(EGCFError):
            canonicalize_nonlinear_representative(form, search)

        falsifier = "combined coordinate changes pressure output"
        semantic_candidate = make_semantic_candidate(
            issue,
            meaning="temperature command corrected for pressure curvature",
            expected_output_indices=issue.affected_output_indices,
            excluded_output_indices=(1,),
            falsifiers=(falsifier,),
        )
        resolution = evaluate_semantic_candidate(
            issue,
            semantic_candidate,
            evidence_ids=("evidence:nonlinear-coordinate-0",),
            falsifier_results=(
                SemanticFalsifierResult(
                    falsifier=falsifier,
                    outcome="SURVIVED",
                    evidence_id="evidence:nonlinear-coordinate-0",
                ),
            ),
            independent_review=True,
        )
        canonical = canonicalize_nonlinear_representative(
            form,
            search,
            semantic_candidates=(semantic_candidate,),
            semantic_resolutions=(resolution,),
        )
        self.assertEqual(
            "temperature command corrected for pressure curvature",
            canonical.resolved_input_meanings[0],
        )
        self.assertTrue(canonical.local_canonical_eligible)
        self.assertFalse(canonical.global_equivalence_eligible)
        self.assertEqual(
            "ELIGIBLE_LOCAL_NONLINEAR_REPRESENTATIVE_FORM",
            canonical.store_status,
        )

    def test_nonlinear_semantic_issues_propagate_to_governance(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        search = search_nonlinear_representative_coordinates(form, jet)
        candidate = search.best_candidate
        assert candidate is not None
        directives = propagate_semantic_issues(candidate.semantic_issues)
        self.assertEqual(7, len(directives))
        iurm = [item for item in directives if item.subsystem == "IURM"]
        store = [item for item in directives if item.subsystem == "ALGORITHM_STORE"]
        self.assertTrue(iurm[0].blocking)
        self.assertTrue(store[0].blocking)

    def test_search_is_deterministic(self) -> None:
        form, jet = make_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            )
        )
        left = search_nonlinear_representative_coordinates(form, jet)
        right = search_nonlinear_representative_coordinates(form, jet)
        self.assertEqual(left.audit_hash, right.audit_hash)
        self.assertEqual(left.to_dict(), right.to_dict())


if __name__ == "__main__":
    unittest.main()
