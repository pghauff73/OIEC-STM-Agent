from __future__ import annotations

from fractions import Fraction
from typing import Any

from ..errors import EGCFError
from ..ids import sha256_json
from .mimo import CanonicalMIMOCoupling
from .representative import (
    MAX_RANK_VECTOR_TERMS,
    MAX_REPRESENTATIVE_TRANSFORMS,
    MAX_TRANSFORM_COEFFICIENT_BITS,
    REPRESENTATION_VERSION,
    MinimalityAssessment,
    RepresentationAssessment,
    RepresentativeInputCandidate,
    RepresentativeInputSearch,
    TransformAdmissibility,
    assess_mimo_representation as _assess_mimo_representation,
    discover_representative_inputs as _discover_representative_inputs,
)


def _all_zero(mimo: CanonicalMIMOCoupling) -> bool:
    return all(
        all(value == 0 for value in channel.numerator)
        for row in mimo.channels
        for channel in row
    )


def _zero_minimality(mimo: CanonicalMIMOCoupling) -> MinimalityAssessment:
    return MinimalityAssessment(
        source_input_count=mimo.input_count,
        effective_input_rank=0,
        redundant_input_count=mimo.input_count,
        pivot_input_positions=(),
        nonpivot_input_positions=tuple(range(mimo.input_count)),
        source_to_basis_projection=(),
        status="EXACT_ZERO_EFFECTIVE_INPUT_RANK",
        exact=True,
    )


def assess_mimo_representation(
    mimo: CanonicalMIMOCoupling,
    *,
    max_rank_terms: int = MAX_RANK_VECTOR_TERMS,
) -> RepresentationAssessment:
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError("SAA-4.1 assessment requires CanonicalMIMOCoupling")
    if (
        mimo.dynamic_strength == "EXACT_MIMO_LINEAR_DYNAMICS"
        and _all_zero(mimo)
    ):
        minimality = _zero_minimality(mimo)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "representation_version": REPRESENTATION_VERSION,
            "mimo_ordered_signature": mimo.ordered_signature,
            "status": "NON_REPRESENTATIVE_REDUNDANT_INPUTS",
            "reason": "all declared inputs have zero observable effect and collapse to the zero-input behavioral quotient",
            "coupling_bp": 0,
            "pairing": [],
            "canonical_admission_eligible": False,
            "minimality": minimality.to_dict(),
        }
        return RepresentationAssessment(
            schema_version=1,
            representation_version=REPRESENTATION_VERSION,
            status="NON_REPRESENTATIVE_REDUNDANT_INPUTS",
            reason=(
                "all declared inputs have zero observable effect and collapse to the "
                "zero-input behavioral quotient"
            ),
            coupling_bp=0,
            preferred_input_to_output_pairing=(),
            canonical_admission_eligible=False,
            requires_representative_search=True,
            minimality=minimality,
            assessment_signature=sha256_json(payload),
        )
    return _assess_mimo_representation(mimo, max_rank_terms=max_rank_terms)


def discover_representative_inputs(
    mimo: CanonicalMIMOCoupling,
    *,
    max_rank_terms: int = MAX_RANK_VECTOR_TERMS,
    max_transforms: int = MAX_REPRESENTATIVE_TRANSFORMS,
    max_transform_coefficient_bits: int = MAX_TRANSFORM_COEFFICIENT_BITS,
) -> RepresentativeInputSearch:
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError("SAA-5 discovery requires CanonicalMIMOCoupling")
    if (
        mimo.dynamic_strength == "EXACT_MIMO_LINEAR_DYNAMICS"
        and _all_zero(mimo)
    ):
        minimality = _zero_minimality(mimo)
        assessment = assess_mimo_representation(mimo, max_rank_terms=max_rank_terms)
        admissibility = TransformAdmissibility(
            status="ADMISSIBLE_BEHAVIORAL_ZERO_INPUT_QUOTIENT",
            admissible=True,
            causal=True,
            stable=True,
            finite_real=True,
            invertibility_status="INVERTIBLE_ON_BEHAVIORAL_QUOTIENT",
            coefficient_bits=1,
            coefficient_bit_limit=max_transform_coefficient_bits,
        )
        candidate_payload = {
            "schema_version": 1,
            "representation_version": REPRESENTATION_VERSION,
            "claim_scope": "ZERO_EFFECTIVE_INPUT_REPRESENTATIVE_CANDIDATE",
            "source_signature": mimo.ordered_signature,
        }
        signature = sha256_json(candidate_payload)
        candidate = RepresentativeInputCandidate(
            candidate_id=f"rep-candidate:sha256:{signature}",
            status="REPRESENTATIVE_FORM_CANDIDATE",
            transform_class="BEHAVIORAL_ZERO_INPUT_QUOTIENT",
            algebraic_probe=None,
            selected_output_rows=(),
            source_input_count=mimo.input_count,
            representative_input_count=0,
            source_to_representative_projection=(),
            representative_to_source_section=tuple(() for _ in range(mimo.input_count)),
            basis_transform=(),
            representative_channels=tuple(() for _ in range(mimo.output_count)),
            coupling_before_bp=0,
            coupling_after_bp=0,
            preferred_input_to_output_pairing=(),
            exact_decoupled=True,
            independent=True,
            minimal=True,
            requires_renormalization=False,
            admissibility=admissibility,
            canonical_signature=signature,
        )
        audit_payload = {
            "schema_version": 1,
            "representation_version": REPRESENTATION_VERSION,
            "source_assessment": assessment.assessment_signature,
            "minimality": minimality.to_dict(),
            "search_status": "REPRESENTATIVE_FORM_FOUND",
            "candidates_considered": 1,
            "candidate_signatures": [signature],
            "best_candidate": signature,
            "zero_input_quotient": True,
        }
        return RepresentativeInputSearch(
            schema_version=1,
            representation_version=REPRESENTATION_VERSION,
            source_assessment=assessment,
            minimality=minimality,
            search_status="REPRESENTATIVE_FORM_FOUND",
            candidates_considered=1,
            candidates=(candidate,),
            best_candidate=candidate,
            audit_hash=sha256_json(audit_payload),
        )
    return _discover_representative_inputs(
        mimo,
        max_rank_terms=max_rank_terms,
        max_transforms=max_transforms,
        max_transform_coefficient_bits=max_transform_coefficient_bits,
    )
