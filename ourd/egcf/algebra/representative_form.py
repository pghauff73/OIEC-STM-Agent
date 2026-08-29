from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .mimo import CanonicalMIMOCoupling, RationalChannel, _rational_scaled
from .models import CanonicalAlgorithmIR
from .normalize import NormalizationContract
from .representative import RepresentativeInputCandidate, RepresentativeInputSearch
from .semantic import (
    SemanticCandidateMeaning,
    SemanticRepresentationIssue,
    SemanticResolution,
    canonical_semantic_admission,
)


CANONICAL_REPRESENTATIVE_VERSION = "saa-canonical-representative-v1"
REPRESENTATIVE_BOUND_POLICY = "EXACT_LINEAR_IMAGE_OF_NORMALIZED_SOURCE_BOX"
STRUCTURAL_BINDING_POLICY = "CONSERVATIVE_SOURCE_STRUCTURE_BINDING"


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _fraction_matrix_payload(
    matrix: Sequence[Sequence[Fraction]],
) -> list[list[list[int]]]:
    return [[_fraction_payload(value) for value in row] for row in matrix]


def _rational_matrix_payload(
    matrix: Sequence[Sequence[RationalChannel]],
) -> list[list[dict[str, Any]]]:
    return [[channel.payload() for channel in row] for row in matrix]


def _canonical_text(value: str) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _input_bindings(contract: NormalizationContract) -> tuple[Any, ...]:
    return tuple(
        sorted(
            (item for item in contract.bindings if item.role == "INPUT"),
            key=lambda item: item.position,
        )
    )


def _output_bindings(contract: NormalizationContract) -> tuple[Any, ...]:
    return tuple(
        sorted(
            (item for item in contract.bindings if item.role == "OUTPUT"),
            key=lambda item: item.position,
        )
    )


def _validate_source_normalization(
    normalization: NormalizationContract,
    candidate: RepresentativeInputCandidate,
    mimo: CanonicalMIMOCoupling,
) -> None:
    if not isinstance(normalization, NormalizationContract):
        raise EGCFError("SAA-6 requires the SAA-2 source NormalizationContract")
    if normalization.normalization_strength != "EXACT_NORMALIZATION":
        raise EGCFError(
            "SAA-6 canonical representative admission requires exact source normalization"
        )
    inputs = _input_bindings(normalization)
    outputs = _output_bindings(normalization)
    if len(inputs) != candidate.source_input_count:
        raise EGCFError(
            "SAA-6 source normalization input count does not match representative candidate"
        )
    if len(outputs) != mimo.output_count:
        raise EGCFError(
            "SAA-6 source normalization output count does not match MIMO representation"
        )
    if normalization.time is None:
        raise EGCFError("SAA-6 requires the canonical characteristic-time contract")
    if any(item.strength != "EXACT" for item in inputs + outputs):
        raise EGCFError("SAA-6 source input/output bounds must be exact/domain bounds")


def _validate_candidate(
    search: RepresentativeInputSearch,
) -> RepresentativeInputCandidate:
    if not isinstance(search, RepresentativeInputSearch):
        raise EGCFError("SAA-6 requires a RepresentativeInputSearch from SAA-5")
    if not search.representative_found or search.best_candidate is None:
        raise EGCFError("SAA-6 requires an admissible representative form from SAA-5")
    candidate = search.best_candidate
    if candidate.status != "REPRESENTATIVE_FORM_CANDIDATE":
        raise EGCFError("SAA-6 best candidate is not a representative-form candidate")
    if not candidate.exact_decoupled:
        raise EGCFError("SAA-6 representative candidate must be exactly decoupled")
    if not candidate.independent or not candidate.minimal:
        raise EGCFError("SAA-6 representative candidate must be independent and minimal")
    if not candidate.admissibility.admissible:
        raise EGCFError("SAA-6 representative candidate must pass SAA-5.2 admissibility")
    return candidate


def _representative_raw_bound(
    coefficients: Sequence[Fraction],
) -> tuple[Fraction, Fraction]:
    minimum = sum((min(Fraction(0), value) for value in coefficients), Fraction(0))
    maximum = sum((max(Fraction(0), value) for value in coefficients), Fraction(0))
    return minimum, maximum


@dataclass(frozen=True)
class RepresentativeCoordinateBoundary:
    candidate_input_index: int
    raw_minimum: Fraction
    raw_maximum: Fraction
    raw_width: Fraction
    normalized_minimum: Fraction
    normalized_maximum: Fraction
    bound_policy: str
    source_normalization_signature: str
    semantic_resolution_signature: str
    boundary_signature: str

    def __post_init__(self) -> None:
        if self.raw_maximum <= self.raw_minimum:
            raise EGCFError("SAA-6 representative boundary must have positive width")
        if self.raw_width != self.raw_maximum - self.raw_minimum:
            raise EGCFError("SAA-6 representative boundary width is inconsistent")
        if self.normalized_minimum != 0 or self.normalized_maximum != 1:
            raise EGCFError("SAA-6 representative target range must be exactly [0,1]")

    def normalize(self, value: Fraction | int) -> Fraction:
        observed = Fraction(value)
        if observed < self.raw_minimum or observed > self.raw_maximum:
            raise EGCFError("representative value lies outside its SAA-6 boundary")
        return (observed - self.raw_minimum) / self.raw_width

    def denormalize(self, value: Fraction | int) -> Fraction:
        normalized = Fraction(value)
        if normalized < 0 or normalized > 1:
            raise EGCFError("SAA-6 normalized representative value must lie in [0,1]")
        return self.raw_minimum + normalized * self.raw_width

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_input_index": self.candidate_input_index,
            "raw_minimum": _fraction_payload(self.raw_minimum),
            "raw_maximum": _fraction_payload(self.raw_maximum),
            "raw_width": _fraction_payload(self.raw_width),
            "normalized_minimum": _fraction_payload(self.normalized_minimum),
            "normalized_maximum": _fraction_payload(self.normalized_maximum),
            "bound_policy": self.bound_policy,
            "source_normalization_signature": self.source_normalization_signature,
            "semantic_resolution_signature": self.semantic_resolution_signature,
            "boundary_signature": self.boundary_signature,
        }


@dataclass(frozen=True)
class CanonicalRepresentativeInput:
    canonical_position: int
    candidate_input_index: int
    paired_output_index: int
    meaning: str
    canonical_meaning: str
    expected_output_indices: Tuple[int, ...]
    excluded_output_indices: Tuple[int, ...]
    source_input_indices: Tuple[int, ...]
    source_coefficients: Tuple[Fraction, ...]
    semantic_issue_id: str
    semantic_candidate_id: str
    semantic_candidate_signature: str
    semantic_resolution_signature: str
    semantic_evidence_ids: Tuple[str, ...]
    boundary: RepresentativeCoordinateBoundary

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_position": self.canonical_position,
            "candidate_input_index": self.candidate_input_index,
            "paired_output_index": self.paired_output_index,
            "meaning": self.meaning,
            "canonical_meaning": self.canonical_meaning,
            "expected_output_indices": list(self.expected_output_indices),
            "excluded_output_indices": list(self.excluded_output_indices),
            "source_input_indices": list(self.source_input_indices),
            "source_coefficients": [_fraction_payload(value) for value in self.source_coefficients],
            "semantic_issue_id": self.semantic_issue_id,
            "semantic_candidate_id": self.semantic_candidate_id,
            "semantic_candidate_signature": self.semantic_candidate_signature,
            "semantic_resolution_signature": self.semantic_resolution_signature,
            "semantic_evidence_ids": list(self.semantic_evidence_ids),
            "boundary": self.boundary.to_dict(),
        }


@dataclass(frozen=True)
class CanonicalRepresentativeAlgorithmForm:
    schema_version: int
    representative_version: str
    domain: str
    variable: str
    output_count: int
    representative_input_count: int
    normalized_sample_interval: Fraction | None
    source_mimo_signature: str
    source_normalization_signature: str
    source_structural_hash: str
    source_structural_strength: str
    representative_search_audit_hash: str
    representative_candidate_signature: str
    canonical_input_permutation: Tuple[int, ...]
    inputs: Tuple[CanonicalRepresentativeInput, ...]
    normalized_channels: Tuple[Tuple[RationalChannel, ...], ...]
    mathematical_representative_signature: str
    semantic_representative_signature: str
    representative_behavior_signature: str
    canonical_algorithm_signature: str
    structural_binding_policy: str
    canonical_admission_eligible: bool
    store_status: str
    audit_hash: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "representative_version": self.representative_version,
            "domain": self.domain,
            "variable": self.variable,
            "output_count": self.output_count,
            "representative_input_count": self.representative_input_count,
            "normalized_sample_interval": (
                _fraction_payload(self.normalized_sample_interval)
                if self.normalized_sample_interval is not None
                else None
            ),
            "source_mimo_signature": self.source_mimo_signature,
            "source_normalization_signature": self.source_normalization_signature,
            "source_structural_hash": self.source_structural_hash,
            "source_structural_strength": self.source_structural_strength,
            "representative_search_audit_hash": self.representative_search_audit_hash,
            "representative_candidate_signature": self.representative_candidate_signature,
            "canonical_input_permutation": list(self.canonical_input_permutation),
            "inputs": [item.to_dict() for item in self.inputs],
            "normalized_channels": _rational_matrix_payload(self.normalized_channels),
            "mathematical_representative_signature": self.mathematical_representative_signature,
            "semantic_representative_signature": self.semantic_representative_signature,
            "representative_behavior_signature": self.representative_behavior_signature,
            "canonical_algorithm_signature": self.canonical_algorithm_signature,
            "structural_binding_policy": self.structural_binding_policy,
            "canonical_admission_eligible": self.canonical_admission_eligible,
            "store_status": self.store_status,
            "audit_hash": self.audit_hash,
            "warnings": list(self.warnings),
        }


def _semantic_maps(
    issues: Sequence[SemanticRepresentationIssue],
    semantic_candidates: Sequence[SemanticCandidateMeaning],
    resolutions: Sequence[SemanticResolution],
    representative_inputs: int,
) -> tuple[
    dict[int, SemanticRepresentationIssue],
    dict[str, SemanticCandidateMeaning],
    dict[str, SemanticResolution],
]:
    issue_by_index: dict[int, SemanticRepresentationIssue] = {}
    for issue in issues:
        if issue.coordinate_kind != "REPRESENTATIVE_INPUT":
            raise EGCFError(
                "SAA-6 semantic issues must describe the representative coordinates, not the source representation"
            )
        if issue.coordinate_index in issue_by_index:
            raise EGCFError("duplicate SAA-6 semantic issue for representative coordinate")
        issue_by_index[issue.coordinate_index] = issue
    if set(issue_by_index) != set(range(representative_inputs)):
        raise EGCFError("SAA-6 requires exactly one semantic issue per representative input")

    candidate_by_issue: dict[str, SemanticCandidateMeaning] = {}
    for semantic_candidate in semantic_candidates:
        if semantic_candidate.issue_id in candidate_by_issue:
            raise EGCFError("duplicate semantic candidate for one SAA-6 issue")
        candidate_by_issue[semantic_candidate.issue_id] = semantic_candidate

    resolution_by_issue: dict[str, SemanticResolution] = {}
    for resolution in resolutions:
        if resolution.issue_id in resolution_by_issue:
            raise EGCFError("duplicate semantic resolution for one SAA-6 issue")
        resolution_by_issue[resolution.issue_id] = resolution

    if not canonical_semantic_admission(
        mathematical_eligible=True,
        issues=issues,
        resolutions=resolutions,
    ):
        raise EGCFError(
            "SAA-6 canonical representative form requires every representative semantic issue to be resolved"
        )

    for issue in issues:
        semantic_candidate = candidate_by_issue.get(issue.issue_id)
        resolution = resolution_by_issue.get(issue.issue_id)
        if semantic_candidate is None or resolution is None:
            raise EGCFError("SAA-6 requires candidate meaning and resolution for every semantic issue")
        if resolution.candidate_id != semantic_candidate.candidate_id:
            raise EGCFError("SAA-6 semantic resolution references a different candidate meaning")
        if resolution.status != "SEMANTICALLY_RESOLVED" or not resolution.canonical_semantic_eligible:
            raise EGCFError("SAA-6 semantic resolution is not canonical-admission eligible")
        if resolution.semantic_fit_bp != 10000:
            raise EGCFError("SAA-6 requires complete semantic output-footprint fit")
    return issue_by_index, candidate_by_issue, resolution_by_issue


def _canonical_input_order(candidate: RepresentativeInputCandidate) -> Tuple[int, ...]:
    count = candidate.representative_input_count
    if count == 0:
        return ()
    pairing = candidate.preferred_input_to_output_pairing
    if pairing is None or len(pairing) != count:
        raise EGCFError("SAA-6 representative form requires one-to-one input/output pairing")
    if len(set(pairing)) != len(pairing):
        raise EGCFError("SAA-6 representative input/output pairing must be injective")
    return tuple(sorted(range(count), key=lambda index: (pairing[index], index)))


def _boundary_for_input(
    *,
    candidate: RepresentativeInputCandidate,
    candidate_input_index: int,
    normalization: NormalizationContract,
    resolution: SemanticResolution,
) -> RepresentativeCoordinateBoundary:
    coefficients = candidate.source_to_representative_projection[candidate_input_index]
    minimum, maximum = _representative_raw_bound(coefficients)
    if maximum <= minimum:
        raise EGCFError("SAA-6 nonzero representative coordinate has zero reachable width")
    width = maximum - minimum
    material = {
        "schema_version": 1,
        "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
        "candidate_input_index": candidate_input_index,
        "raw_minimum": _fraction_payload(minimum),
        "raw_maximum": _fraction_payload(maximum),
        "target": [[0, 1], [1, 1]],
        "bound_policy": REPRESENTATIVE_BOUND_POLICY,
        "source_normalization_signature": normalization.canonical_signature,
        "semantic_resolution_signature": resolution.resolution_signature,
    }
    return RepresentativeCoordinateBoundary(
        candidate_input_index=candidate_input_index,
        raw_minimum=minimum,
        raw_maximum=maximum,
        raw_width=width,
        normalized_minimum=Fraction(0),
        normalized_maximum=Fraction(1),
        bound_policy=REPRESENTATIVE_BOUND_POLICY,
        source_normalization_signature=normalization.canonical_signature,
        semantic_resolution_signature=resolution.resolution_signature,
        boundary_signature=sha256_json(material),
    )


def _renormalized_channels(
    candidate: RepresentativeInputCandidate,
    canonical_input_order: Sequence[int],
    boundaries: Mapping[int, RepresentativeCoordinateBoundary],
) -> Tuple[Tuple[RationalChannel, ...], ...]:
    result: list[tuple[RationalChannel, ...]] = []
    for row in candidate.representative_channels:
        normalized_row = []
        for original_index in canonical_input_order:
            width = boundaries[original_index].raw_width
            # v = v_min + width * r. SAA-3/SAA-4 dynamics are deviation dynamics,
            # so the affine offset disappears and the input transfer column scales by width.
            normalized_row.append(_rational_scaled(row[original_index], width))
        result.append(tuple(normalized_row))
    return tuple(result)


def canonicalize_representative_algorithm(
    *,
    structural_ir: CanonicalAlgorithmIR,
    source_normalization: NormalizationContract,
    mimo: CanonicalMIMOCoupling,
    representative_search: RepresentativeInputSearch,
    semantic_issues: Sequence[SemanticRepresentationIssue],
    semantic_candidates: Sequence[SemanticCandidateMeaning],
    semantic_resolutions: Sequence[SemanticResolution],
) -> CanonicalRepresentativeAlgorithmForm:
    if not isinstance(structural_ir, CanonicalAlgorithmIR):
        raise EGCFError("SAA-6 requires the SAA-1 CanonicalAlgorithmIR")
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError("SAA-6 requires the SAA-4 CanonicalMIMOCoupling")

    candidate = _validate_candidate(representative_search)
    _validate_source_normalization(source_normalization, candidate, mimo)
    if candidate.source_input_count != mimo.input_count:
        raise EGCFError("SAA-6 representative candidate source dimension mismatches MIMO input count")
    if len(candidate.representative_channels) != mimo.output_count:
        raise EGCFError("SAA-6 representative candidate output dimension mismatches MIMO output count")
    if any(len(row) != candidate.representative_input_count for row in candidate.representative_channels):
        raise EGCFError("SAA-6 representative channel matrix dimensions are inconsistent")

    issue_by_index, semantic_candidate_by_issue, resolution_by_issue = _semantic_maps(
        semantic_issues,
        semantic_candidates,
        semantic_resolutions,
        candidate.representative_input_count,
    )

    input_order = _canonical_input_order(candidate)
    pairing = candidate.preferred_input_to_output_pairing or ()
    boundaries: dict[int, RepresentativeCoordinateBoundary] = {}
    for representative_index in range(candidate.representative_input_count):
        issue = issue_by_index[representative_index]
        resolution = resolution_by_issue[issue.issue_id]
        boundaries[representative_index] = _boundary_for_input(
            candidate=candidate,
            candidate_input_index=representative_index,
            normalization=source_normalization,
            resolution=resolution,
        )

    normalized_channels = _renormalized_channels(candidate, input_order, boundaries)

    canonical_inputs: list[CanonicalRepresentativeInput] = []
    semantic_identity_rows: list[dict[str, Any]] = []
    for canonical_position, original_index in enumerate(input_order):
        issue = issue_by_index[original_index]
        semantic_candidate = semantic_candidate_by_issue[issue.issue_id]
        resolution = resolution_by_issue[issue.issue_id]
        coefficients = tuple(
            candidate.source_to_representative_projection[original_index][source_index]
            for source_index in range(candidate.source_input_count)
        )
        sources = tuple(index for index, value in enumerate(coefficients) if value != 0)
        source_coefficients = tuple(coefficients[index] for index in sources)
        canonical_meaning = _canonical_text(semantic_candidate.meaning)
        boundary = boundaries[original_index]
        canonical_inputs.append(
            CanonicalRepresentativeInput(
                canonical_position=canonical_position,
                candidate_input_index=original_index,
                paired_output_index=int(pairing[original_index]),
                meaning=semantic_candidate.meaning,
                canonical_meaning=canonical_meaning,
                expected_output_indices=semantic_candidate.expected_output_indices,
                excluded_output_indices=semantic_candidate.excluded_output_indices,
                source_input_indices=sources,
                source_coefficients=source_coefficients,
                semantic_issue_id=issue.issue_id,
                semantic_candidate_id=semantic_candidate.candidate_id,
                semantic_candidate_signature=semantic_candidate.signature,
                semantic_resolution_signature=resolution.resolution_signature,
                semantic_evidence_ids=resolution.evidence_ids,
                boundary=boundary,
            )
        )
        semantic_identity_rows.append(
            {
                "canonical_position": canonical_position,
                "paired_output_index": int(pairing[original_index]),
                "meaning": canonical_meaning,
                "expected_output_indices": list(semantic_candidate.expected_output_indices),
                "excluded_output_indices": list(semantic_candidate.excluded_output_indices),
            }
        )

    mathematical_payload = {
        "schema_version": 1,
        "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
        "claim_scope": "EXACT_MINIMAL_DECOUPLED_RENORMALIZED_REPRESENTATIVE_DYNAMICS",
        "domain": mimo.domain,
        "variable": mimo.variable,
        "output_count": mimo.output_count,
        "representative_input_count": candidate.representative_input_count,
        "normalized_sample_interval": (
            _fraction_payload(mimo.normalized_sample_interval)
            if mimo.normalized_sample_interval is not None
            else None
        ),
        "target_input_domain": [0, 1],
        "input_order_policy": "ORDER_BY_UNIQUE_PAIRED_OUTPUT",
        "normalized_channels": _rational_matrix_payload(normalized_channels),
    }
    mathematical_signature = sha256_json(mathematical_payload)

    semantic_payload = {
        "schema_version": 1,
        "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
        "claim_scope": "RESOLVED_REPRESENTATIVE_INPUT_SEMANTICS",
        "inputs": semantic_identity_rows,
    }
    semantic_signature = sha256_json(semantic_payload)

    behavior_payload = {
        "schema_version": 1,
        "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
        "claim_scope": "CANONICAL_REPRESENTATIVE_BEHAVIOR_AND_SEMANTICS",
        "mathematical_representative_signature": mathematical_signature,
        "semantic_representative_signature": semantic_signature,
    }
    behavior_signature = sha256_json(behavior_payload)

    algorithm_payload = {
        "schema_version": 1,
        "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
        "claim_scope": "CANONICAL_REPRESENTATIVE_ALGORITHM_WITH_CONSERVATIVE_SOURCE_STRUCTURE",
        "representative_behavior_signature": behavior_signature,
        "source_structural_hash": structural_ir.structural_hash,
        "source_structural_strength": structural_ir.canonicalization_strength,
        "structural_binding_policy": STRUCTURAL_BINDING_POLICY,
    }
    algorithm_signature = sha256_json(algorithm_payload)

    audit_payload = {
        "schema_version": 1,
        "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
        "source_mimo_signature": mimo.ordered_signature,
        "source_normalization_contract_hash": source_normalization.contract_hash,
        "source_normalization_signature": source_normalization.canonical_signature,
        "source_structural_hash": structural_ir.structural_hash,
        "representative_search_audit_hash": representative_search.audit_hash,
        "representative_candidate_signature": candidate.canonical_signature,
        "canonical_input_permutation": list(input_order),
        "source_to_representative_projection": _fraction_matrix_payload(
            candidate.source_to_representative_projection
        ),
        "boundary_signatures": [boundaries[index].boundary_signature for index in input_order],
        "semantic_issue_signatures": [issue_by_index[index].signature for index in input_order],
        "semantic_candidate_signatures": [
            semantic_candidate_by_issue[issue_by_index[index].issue_id].signature
            for index in input_order
        ],
        "semantic_resolution_signatures": [
            resolution_by_issue[issue_by_index[index].issue_id].resolution_signature
            for index in input_order
        ],
        "representative_behavior_signature": behavior_signature,
        "canonical_algorithm_signature": algorithm_signature,
    }

    warnings = (
        "SAA-6 canonical algorithm identity conservatively binds the source SAA-1 structural hash; a future representative structural rewrite may merge additional equivalent implementations.",
    )
    return CanonicalRepresentativeAlgorithmForm(
        schema_version=1,
        representative_version=CANONICAL_REPRESENTATIVE_VERSION,
        domain=mimo.domain,
        variable=mimo.variable,
        output_count=mimo.output_count,
        representative_input_count=candidate.representative_input_count,
        normalized_sample_interval=mimo.normalized_sample_interval,
        source_mimo_signature=mimo.ordered_signature,
        source_normalization_signature=source_normalization.canonical_signature,
        source_structural_hash=structural_ir.structural_hash,
        source_structural_strength=structural_ir.canonicalization_strength,
        representative_search_audit_hash=representative_search.audit_hash,
        representative_candidate_signature=candidate.canonical_signature,
        canonical_input_permutation=input_order,
        inputs=tuple(canonical_inputs),
        normalized_channels=normalized_channels,
        mathematical_representative_signature=mathematical_signature,
        semantic_representative_signature=semantic_signature,
        representative_behavior_signature=behavior_signature,
        canonical_algorithm_signature=algorithm_signature,
        structural_binding_policy=STRUCTURAL_BINDING_POLICY,
        canonical_admission_eligible=True,
        store_status="ELIGIBLE_CANONICAL_REPRESENTATIVE_FORM",
        audit_hash=sha256_json(audit_payload),
        warnings=warnings,
    )


def normalize_representative_value(
    boundary: RepresentativeCoordinateBoundary,
    value: Fraction | int,
) -> Fraction:
    if not isinstance(boundary, RepresentativeCoordinateBoundary):
        raise EGCFError("normalize_representative_value requires SAA-6 boundary")
    return boundary.normalize(value)


def denormalize_representative_value(
    boundary: RepresentativeCoordinateBoundary,
    value: Fraction | int,
) -> Fraction:
    if not isinstance(boundary, RepresentativeCoordinateBoundary):
        raise EGCFError("denormalize_representative_value requires SAA-6 boundary")
    return boundary.denormalize(value)
