from __future__ import annotations

import unittest
from fractions import Fraction

from ourd.egcf.algebra import (
    SemanticFalsifierResult,
    TaylorJetSpec,
    TaylorJetTerm,
    canonicalize_nonlinear_representative,
    canonicalize_taylor_jet,
    compare_taylor_jets,
    evaluate_semantic_candidate,
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


def jet(terms, *, radius=(Fraction(1, 4), Fraction(1, 4)), order=2):
    form = parent_form()
    return form, canonicalize_taylor_jet(
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


class SAA7TaylorJetTests(unittest.TestCase):
    def test_exact_local_jet_evaluates_and_never_claims_global_equivalence(self):
        form, value = jet((
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (2, 0), Fraction(2)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        ))
        self.assertEqual((Fraction(3, 8), Fraction(0)), value.evaluate((Fraction(3, 4), Fraction(1, 2))))
        self.assertEqual("NONLINEAR_REPRESENTATIVE", value.coupling.status)
        self.assertFalse(value.global_equivalence_eligible)
        self.assertEqual(form.representative_behavior_signature, value.parent_representative_behavior_signature)

    def test_term_order_and_duplicate_splitting_do_not_change_identity(self):
        _, left = jet((
            TaylorJetTerm(0, (0, 2), Fraction(1, 2)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (0, 2), Fraction(1, 2)),
        ))
        _, right = jet((
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (0, 2), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        ))
        self.assertEqual(left.coefficient_signature, right.coefficient_signature)
        self.assertEqual(left.terms, right.terms)

    def test_same_jet_different_radius_is_only_local_match_on_intersection(self):
        terms = (
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (2, 0), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        )
        _, wide = jet(terms)
        _, narrow = jet(terms, radius=(Fraction(1, 8), Fraction(1, 8)))
        result = compare_taylor_jets(wide, narrow)
        self.assertEqual("EXACT_LOCAL_JET_MATCH_ON_INTERSECTION", result.status)
        self.assertEqual((Fraction(1, 8), Fraction(1, 8)), result.overlap_radius)
        self.assertFalse(result.global_equivalence_eligible)

    def test_float_and_out_of_bounds_scope_fail_closed(self):
        form = parent_form()
        with self.assertRaises(EGCFError):
            canonicalize_taylor_jet(form, TaylorJetSpec(2, 2, 2, (0.5, Fraction(1, 2)), (Fraction(1, 4), Fraction(1, 4)), ()))
        with self.assertRaises(EGCFError):
            canonicalize_taylor_jet(form, TaylorJetSpec(2, 2, 2, (Fraction(1, 10), Fraction(1, 2)), (Fraction(1, 4), Fraction(1, 4)), ()))

    def test_cross_and_wrong_output_terms_mark_semantic_misrepresentation(self):
        _, value = jet((
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (1, 1), Fraction(1)),
            TaylorJetTerm(0, (0, 2), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        ))
        self.assertEqual("NONLINEAR_SEMANTIC_MISREPRESENTATION", value.coupling.status)
        self.assertTrue(value.coupling.cross_terms)
        self.assertTrue(value.coupling.off_pair_terms)


class SAA71SearchTests(unittest.TestCase):
    def coupled_fixture(self):
        return jet((
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (0, 2), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        ))

    def test_exact_quadratic_shear_finds_decoupled_local_coordinates(self):
        form, source = self.coupled_fixture()
        result = search_nonlinear_representative_coordinates(form, source)
        self.assertEqual("NONLINEAR_REPRESENTATIVE_FORM_FOUND", result.status)
        candidate = result.best_candidate
        assert candidate is not None
        self.assertEqual(0, candidate.coupling_score)
        self.assertEqual(1, len(candidate.transforms))
        self.assertEqual((0, 2), candidate.transforms[0].monomial_powers)
        self.assertEqual(Fraction(1), candidate.transforms[0].coefficient)
        self.assertEqual(Fraction(3, 16), candidate.transformed_jet.validity_radius[0])
        self.assertTrue(candidate.semantic_issues)
        self.assertFalse(candidate.local_canonical_eligible)

    def test_cross_term_containing_target_remains_unresolved(self):
        form, source = jet((
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (1, 1), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
        ))
        result = search_nonlinear_representative_coordinates(form, source)
        self.assertEqual("NONLINEAR_REPRESENTATION_UNRESOLVED", result.status)
        self.assertFalse(result.representative_found)

    def test_decoupled_self_nonlinearity_inherits_existing_semantics(self):
        form, source = jet((
            TaylorJetTerm(0, (1, 0), Fraction(1)),
            TaylorJetTerm(0, (2, 0), Fraction(1)),
            TaylorJetTerm(1, (0, 1), Fraction(1)),
            TaylorJetTerm(1, (0, 3), Fraction(1, 2)),
        ), order=3)
        result = search_nonlinear_representative_coordinates(form, source)
        self.assertEqual("NONLINEAR_REPRESENTATIVE_ALREADY_FOUND", result.status)
        canonical = canonicalize_nonlinear_representative(form, result)
        self.assertTrue(canonical.local_canonical_eligible)
        self.assertFalse(canonical.global_equivalence_eligible)

    def test_new_nonlinear_coordinate_requires_new_evidence_backed_meaning(self):
        form, source = self.coupled_fixture()
        result = search_nonlinear_representative_coordinates(form, source)
        candidate = result.best_candidate
        assert candidate is not None
        issue = candidate.semantic_issues[0]
        with self.assertRaises(EGCFError):
            canonicalize_nonlinear_representative(form, result)

        falsifier = "new coordinate changes excluded pressure output"
        meaning = make_semantic_candidate(
            issue,
            meaning="temperature command corrected for pressure curvature",
            expected_output_indices=issue.affected_output_indices,
            excluded_output_indices=(1,),
            falsifiers=(falsifier,),
        )
        resolution = evaluate_semantic_candidate(
            issue,
            meaning,
            evidence_ids=("evidence:nonlinear-coordinate",),
            falsifier_results=(SemanticFalsifierResult(falsifier, "SURVIVED", "evidence:nonlinear-coordinate"),),
            independent_review=True,
        )
        canonical = canonicalize_nonlinear_representative(
            form,
            result,
            semantic_candidates=(meaning,),
            semantic_resolutions=(resolution,),
        )
        self.assertEqual("temperature command corrected for pressure curvature", canonical.resolved_input_meanings[0])
        self.assertEqual("ELIGIBLE_LOCAL_NONLINEAR_REPRESENTATIVE_FORM", canonical.store_status)
        self.assertFalse(canonical.global_equivalence_eligible)

    def test_new_semantic_issue_propagates_to_all_oiec_governance_consumers(self):
        form, source = self.coupled_fixture()
        result = search_nonlinear_representative_coordinates(form, source)
        candidate = result.best_candidate
        assert candidate is not None
        directives = propagate_semantic_issues(candidate.semantic_issues)
        self.assertEqual(7, len(directives))
        self.assertTrue(next(item for item in directives if item.subsystem == "IURM").blocking)
        self.assertTrue(next(item for item in directives if item.subsystem == "ALGORITHM_STORE").blocking)

    def test_search_is_deterministic(self):
        form, source = self.coupled_fixture()
        left = search_nonlinear_representative_coordinates(form, source)
        right = search_nonlinear_representative_coordinates(form, source)
        self.assertEqual(left.audit_hash, right.audit_hash)
        self.assertEqual(left.to_dict(), right.to_dict())


if __name__ == "__main__":
    unittest.main()
