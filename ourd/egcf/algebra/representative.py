from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .mimo import (
    CanonicalMIMOCoupling,
    RationalChannel,
    _matrix_inverse,
    _poly_mul_desc,
    _rational_add,
    _rational_scaled,
)


REPRESENTATION_VERSION = "saa-representative-inputs-v1"
MAX_RANK_VECTOR_TERMS = 16384
MAX_REPRESENTATIVE_TRANSFORMS = 4096
MAX_TRANSFORM_COEFFICIENT_BITS = 256
CONTINUOUS_ALGEBRAIC_PROBES = (
    Fraction(0),
    Fraction(1),
    Fraction(-1),
    Fraction(2),
    Fraction(-2),
)
DISCRETE_ALGEBRAIC_PROBES = (
    Fraction(1),
    Fraction(-1),
    Fraction(0),
    Fraction(2),
    Fraction(-2),
)


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _matrix_payload(matrix: Sequence[Sequence[Fraction]]) -> list[list[list[int]]]:
    return [[_fraction_payload(value) for value in row] for row in matrix]


def _rational_payload(matrix: Sequence[Sequence[RationalChannel]]) -> list[list[dict[str, Any]]]:
    return [[channel.payload() for channel in row] for row in matrix]


def _source_rational_matrix(
    mimo: CanonicalMIMOCoupling,
) -> Tuple[Tuple[RationalChannel, ...], ...]:
    return tuple(
        tuple(
            RationalChannel(tuple(channel.numerator), tuple(channel.denominator))
            for channel in row
        )
        for row in mimo.channels
    )


def _identity(size: int) -> Tuple[Tuple[Fraction, ...], ...]:
    return tuple(
        tuple(Fraction(1 if row == column else 0) for column in range(size))
        for row in range(size)
    )


def _matrix_multiply(
    left: Sequence[Sequence[Fraction]],
    right: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[Fraction, ...], ...]:
    if not left:
        return ()
    if not right:
        return tuple(() for _ in left)
    inner = len(left[0])
    if any(len(row) != inner for row in left) or len(right) != inner:
        raise EGCFError("SAA-5 matrix dimension mismatch")
    columns = len(right[0])
    if any(len(row) != columns for row in right):
        raise EGCFError("SAA-5 matrix rows must have equal width")
    return tuple(
        tuple(
            sum(
                (left[row][index] * right[index][column] for index in range(inner)),
                Fraction(0),
            )
            for column in range(columns)
        )
        for row in range(len(left))
    )


def _matrix_rank(matrix: Sequence[Sequence[Fraction]]) -> int:
    if not matrix:
        return 0
    work = [list(row) for row in matrix]
    width = len(work[0])
    if any(len(row) != width for row in work):
        raise EGCFError("SAA-5 rank matrix rows must have equal width")
    pivot_row = 0
    for column in range(width):
        pivot = next(
            (row for row in range(pivot_row, len(work)) if work[row][column] != 0),
            None,
        )
        if pivot is None:
            continue
        work[pivot_row], work[pivot] = work[pivot], work[pivot_row]
        scale = work[pivot_row][column]
        work[pivot_row] = [value / scale for value in work[pivot_row]]
        for row in range(len(work)):
            if row == pivot_row:
                continue
            factor = work[row][column]
            if factor == 0:
                continue
            work[row] = [
                left - factor * right
                for left, right in zip(work[row], work[pivot_row])
            ]
        pivot_row += 1
        if pivot_row == len(work):
            break
    return pivot_row


def _coefficient_bits(matrix: Sequence[Sequence[Fraction]]) -> int:
    maximum = 1
    for row in matrix:
        for value in row:
            maximum = max(
                maximum,
                abs(int(value.numerator)).bit_length(),
                abs(int(value.denominator)).bit_length(),
            )
    return maximum


def _poly_product(polynomials: Sequence[Sequence[Fraction]]) -> Tuple[Fraction, ...]:
    result: Tuple[Fraction, ...] = (Fraction(1),)
    for poly in polynomials:
        result = _poly_mul_desc(result, poly)
    return result


def _constant_column_vectors(
    channels: Sequence[Sequence[RationalChannel]],
    *,
    max_terms: int,
) -> Tuple[Tuple[Fraction, ...], ...]:
    outputs = len(channels)
    inputs = len(channels[0]) if outputs else 0
    vectors = [[] for _ in range(inputs)]
    terms = 0
    for output in range(outputs):
        denominators = [channels[output][column].denominator for column in range(inputs)]
        row_polys: list[Tuple[Fraction, ...]] = []
        for column in range(inputs):
            multiplier = _poly_product(
                [denominators[index] for index in range(inputs) if index != column]
            )
            row_polys.append(
                _poly_mul_desc(channels[output][column].numerator, multiplier)
            )
        width = max((len(poly) for poly in row_polys), default=1)
        terms += width * max(inputs, 1)
        if terms > max_terms:
            raise EGCFError(
                f"SAA-5 exact rank vector exceeds bounded term budget {max_terms}"
            )
        for column, poly in enumerate(row_polys):
            vectors[column].extend([Fraction(0)] * (width - len(poly)))
            vectors[column].extend(poly)
    return tuple(tuple(vector) for vector in vectors)


def _column_rref(
    vectors: Sequence[Sequence[Fraction]],
) -> tuple[Tuple[int, ...], Tuple[Tuple[Fraction, ...], ...]]:
    columns = len(vectors)
    if columns == 0:
        return (), ()
    height = len(vectors[0])
    if any(len(vector) != height for vector in vectors):
        raise EGCFError("SAA-5 column vectors have inconsistent lengths")
    matrix = [
        [vectors[column][row] for column in range(columns)]
        for row in range(height)
    ]
    pivot_columns: list[int] = []
    pivot_rows: list[int] = []
    row_index = 0
    for column in range(columns):
        pivot = next(
            (row for row in range(row_index, height) if matrix[row][column] != 0),
            None,
        )
        if pivot is None:
            continue
        matrix[row_index], matrix[pivot] = matrix[pivot], matrix[row_index]
        scale = matrix[row_index][column]
        matrix[row_index] = [value / scale for value in matrix[row_index]]
        for row in range(height):
            if row == row_index:
                continue
            factor = matrix[row][column]
            if factor == 0:
                continue
            matrix[row] = [
                left - factor * right
                for left, right in zip(matrix[row], matrix[row_index])
            ]
        pivot_columns.append(column)
        pivot_rows.append(row_index)
        row_index += 1
        if row_index == height:
            break

    rank = len(pivot_columns)
    projection = [[Fraction(0) for _ in range(columns)] for _ in range(rank)]
    for basis_index, (pivot_column, pivot_row) in enumerate(
        zip(pivot_columns, pivot_rows)
    ):
        for column in range(columns):
            projection[basis_index][column] = matrix[pivot_row][column]
        projection[basis_index][pivot_column] = Fraction(1)
    return tuple(pivot_columns), tuple(tuple(row) for row in projection)


def _apply_constant_transform(
    channels: Sequence[Sequence[RationalChannel]],
    transform: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[RationalChannel, ...], ...]:
    outputs = len(channels)
    source_inputs = len(channels[0]) if outputs else 0
    if source_inputs != len(transform):
        raise EGCFError("SAA-5 transform source dimension mismatch")
    target_inputs = len(transform[0]) if transform else 0
    if any(len(row) != target_inputs for row in transform):
        raise EGCFError("SAA-5 transform rows must have equal width")
    result: list[tuple[RationalChannel, ...]] = []
    for output in range(outputs):
        row: list[RationalChannel] = []
        for target in range(target_inputs):
            accumulated = RationalChannel((Fraction(0),), (Fraction(1),))
            for source in range(source_inputs):
                accumulated = _rational_add(
                    accumulated,
                    _rational_scaled(channels[output][source], transform[source][target]),
                )
            row.append(accumulated)
        result.append(tuple(row))
    return tuple(result)


def _factorization_matches(
    source: Sequence[Sequence[RationalChannel]],
    basis: Sequence[Sequence[RationalChannel]],
    projection: Sequence[Sequence[Fraction]],
) -> bool:
    reconstructed = _apply_constant_transform(basis, projection)
    return tuple(tuple(row) for row in source) == reconstructed


def _evaluate_exact(channel: RationalChannel, q: Fraction) -> Fraction | None:
    numerator = Fraction(0)
    denominator = Fraction(0)
    for coefficient in channel.numerator:
        numerator = numerator * q + coefficient
    for coefficient in channel.denominator:
        denominator = denominator * q + coefficient
    if denominator == 0:
        return None
    return numerator / denominator


def _normalize_transform_columns(
    transform: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[Fraction, ...], ...]:
    if not transform:
        return ()
    rows = len(transform)
    columns = len(transform[0])
    work = [list(row) for row in transform]
    for column in range(columns):
        first = next(
            (work[row][column] for row in range(rows) if work[row][column] != 0),
            None,
        )
        if first is None:
            raise EGCFError("SAA-5 candidate transform has a zero column")
        for row in range(rows):
            work[row][column] /= first
    return tuple(tuple(row) for row in work)


def _support_coupling(
    channels: Sequence[Sequence[RationalChannel]],
) -> tuple[int, Tuple[int, ...] | None, bool]:
    outputs = len(channels)
    inputs = len(channels[0]) if outputs else 0
    if inputs == 0:
        return 0, (), True
    pattern = [
        [not channels[output][input_index].zero for input_index in range(inputs)]
        for output in range(outputs)
    ]
    total = sum(1 for row in pattern for value in row if value)
    if total == 0:
        return 0, (), True
    if inputs > outputs:
        return 10000, None, False
    best_pairing: Tuple[int, ...] | None = None
    best_matched = -1
    for pairing in itertools.permutations(range(outputs), inputs):
        matched = sum(
            1 for input_index, output in enumerate(pairing) if pattern[output][input_index]
        )
        if matched > best_matched or (
            matched == best_matched
            and (best_pairing is None or tuple(pairing) < best_pairing)
        ):
            best_pairing = tuple(pairing)
            best_matched = matched
    off = total - max(best_matched, 0)
    coupling_bp = int(round(10000.0 * off / total))
    decoupled = best_pairing is not None and best_matched == inputs and off == 0
    return coupling_bp, best_pairing, decoupled


def _selector_projection(projection: Sequence[Sequence[Fraction]]) -> bool:
    selected: set[int] = set()
    for row in projection:
        positions = [index for index, value in enumerate(row) if value != 0]
        if len(positions) != 1 or row[positions[0]] != 1 or positions[0] in selected:
            return False
        selected.add(positions[0])
    return True


@dataclass(frozen=True)
class MinimalityAssessment:
    source_input_count: int
    effective_input_rank: int
    redundant_input_count: int
    pivot_input_positions: Tuple[int, ...]
    nonpivot_input_positions: Tuple[int, ...]
    source_to_basis_projection: Tuple[Tuple[Fraction, ...], ...]
    status: str
    exact: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_input_count": self.source_input_count,
            "effective_input_rank": self.effective_input_rank,
            "redundant_input_count": self.redundant_input_count,
            "pivot_input_positions": list(self.pivot_input_positions),
            "nonpivot_input_positions": list(self.nonpivot_input_positions),
            "source_to_basis_projection": _matrix_payload(self.source_to_basis_projection),
            "status": self.status,
            "exact": self.exact,
        }


@dataclass(frozen=True)
class RepresentationAssessment:
    schema_version: int
    representation_version: str
    status: str
    reason: str
    coupling_bp: int | None
    preferred_input_to_output_pairing: Tuple[int, ...] | None
    canonical_admission_eligible: bool
    requires_representative_search: bool
    minimality: MinimalityAssessment | None
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "representation_version": self.representation_version,
            "status": self.status,
            "reason": self.reason,
            "coupling_bp": self.coupling_bp,
            "preferred_input_to_output_pairing": (
                list(self.preferred_input_to_output_pairing)
                if self.preferred_input_to_output_pairing is not None
                else None
            ),
            "canonical_admission_eligible": self.canonical_admission_eligible,
            "requires_representative_search": self.requires_representative_search,
            "minimality": self.minimality.to_dict() if self.minimality is not None else None,
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class TransformAdmissibility:
    status: str
    admissible: bool
    causal: bool
    stable: bool
    finite_real: bool
    invertibility_status: str
    coefficient_bits: int
    coefficient_bit_limit: int
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "admissible": self.admissible,
            "causal": self.causal,
            "stable": self.stable,
            "finite_real": self.finite_real,
            "invertibility_status": self.invertibility_status,
            "coefficient_bits": self.coefficient_bits,
            "coefficient_bit_limit": self.coefficient_bit_limit,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RepresentativeInputCandidate:
    candidate_id: str
    status: str
    transform_class: str
    algebraic_probe: Fraction | None
    selected_output_rows: Tuple[int, ...]
    source_input_count: int
    representative_input_count: int
    source_to_representative_projection: Tuple[Tuple[Fraction, ...], ...]
    representative_to_source_section: Tuple[Tuple[Fraction, ...], ...]
    basis_transform: Tuple[Tuple[Fraction, ...], ...]
    representative_channels: Tuple[Tuple[RationalChannel, ...], ...]
    coupling_before_bp: int
    coupling_after_bp: int
    preferred_input_to_output_pairing: Tuple[int, ...] | None
    exact_decoupled: bool
    independent: bool
    minimal: bool
    requires_renormalization: bool
    admissibility: TransformAdmissibility
    canonical_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "transform_class": self.transform_class,
            "algebraic_probe": (
                _fraction_payload(self.algebraic_probe)
                if self.algebraic_probe is not None
                else None
            ),
            "selected_output_rows": list(self.selected_output_rows),
            "source_input_count": self.source_input_count,
            "representative_input_count": self.representative_input_count,
            "source_to_representative_projection": _matrix_payload(
                self.source_to_representative_projection
            ),
            "representative_to_source_section": _matrix_payload(
                self.representative_to_source_section
            ),
            "basis_transform": _matrix_payload(self.basis_transform),
            "representative_channels": _rational_payload(self.representative_channels),
            "coupling_before_bp": self.coupling_before_bp,
            "coupling_after_bp": self.coupling_after_bp,
            "preferred_input_to_output_pairing": (
                list(self.preferred_input_to_output_pairing)
                if self.preferred_input_to_output_pairing is not None
                else None
            ),
            "exact_decoupled": self.exact_decoupled,
            "independent": self.independent,
            "minimal": self.minimal,
            "requires_renormalization": self.requires_renormalization,
            "admissibility": self.admissibility.to_dict(),
            "canonical_signature": self.canonical_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RepresentativeInputSearch:
    schema_version: int
    representation_version: str
    source_assessment: RepresentationAssessment
    minimality: MinimalityAssessment | None
    search_status: str
    candidates_considered: int
    candidates: Tuple[RepresentativeInputCandidate, ...]
    best_candidate: RepresentativeInputCandidate | None
    audit_hash: str
    warnings: Tuple[str, ...] = ()

    @property
    def representative_found(self) -> bool:
        return bool(
            self.best_candidate is not None
            and self.best_candidate.status == "REPRESENTATIVE_FORM_CANDIDATE"
            and self.best_candidate.admissibility.admissible
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "representation_version": self.representation_version,
            "source_assessment": self.source_assessment.to_dict(),
            "minimality": self.minimality.to_dict() if self.minimality is not None else None,
            "search_status": self.search_status,
            "candidates_considered": self.candidates_considered,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "best_candidate": (
                self.best_candidate.to_dict() if self.best_candidate is not None else None
            ),
            "audit_hash": self.audit_hash,
            "warnings": list(self.warnings),
        }


def _minimality(
    mimo: CanonicalMIMOCoupling,
    *,
    max_rank_terms: int,
) -> tuple[
    MinimalityAssessment,
    Tuple[Tuple[RationalChannel, ...], ...],
    Tuple[Tuple[RationalChannel, ...], ...],
]:
    source = _source_rational_matrix(mimo)
    vectors = _constant_column_vectors(source, max_terms=max_rank_terms)
    pivots, projection = _column_rref(vectors)
    inputs = mimo.input_count
    rank = len(pivots)
    nonpivots = tuple(index for index in range(inputs) if index not in pivots)
    basis = tuple(
        tuple(row[index] for index in pivots)
        for row in source
    )
    if not _factorization_matches(source, basis, projection):
        raise EGCFError("internal SAA-5 constant-input factorization failed")
    if rank == inputs:
        status = "EXACT_FULL_CONSTANT_INPUT_RANK"
    elif rank == 0:
        status = "EXACT_ZERO_EFFECTIVE_INPUT_RANK"
    else:
        status = "EXACT_REDUNDANT_INPUTS_QUOTIENTED"
    return (
        MinimalityAssessment(
            source_input_count=inputs,
            effective_input_rank=rank,
            redundant_input_count=inputs - rank,
            pivot_input_positions=pivots,
            nonpivot_input_positions=nonpivots,
            source_to_basis_projection=projection,
            status=status,
            exact=True,
        ),
        source,
        basis,
    )


def assess_mimo_representation(
    mimo: CanonicalMIMOCoupling,
    *,
    max_rank_terms: int = MAX_RANK_VECTOR_TERMS,
) -> RepresentationAssessment:
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError("SAA-4.1 assessment requires CanonicalMIMOCoupling")
    if max_rank_terms < 1:
        raise EGCFError("max_rank_terms must be positive")
    warnings: list[str] = []
    if mimo.dynamic_strength != "EXACT_MIMO_LINEAR_DYNAMICS":
        status = "REPRESENTATION_UNRESOLVED_APPROXIMATE"
        reason = (
            "coupling or independence cannot be promoted to representative-form evidence "
            "because one or more transfer channels are approximate"
        )
        minimality = None
        coupling_bp = None
        pairing = None
        eligible = False
        requires = True
    else:
        try:
            minimality, source, _ = _minimality(mimo, max_rank_terms=max_rank_terms)
        except EGCFError as exc:
            status = "REPRESENTATION_UNRESOLVED_RANK_BUDGET"
            reason = str(exc)
            minimality = None
            coupling_bp = None
            pairing = None
            eligible = False
            requires = True
            warnings.append(str(exc))
        else:
            coupling_bp, pairing, decoupled = _support_coupling(source)
            if minimality.effective_input_rank < minimality.source_input_count:
                status = "NON_REPRESENTATIVE_REDUNDANT_INPUTS"
                reason = (
                    "declared inputs contain exact constant linear redundancy and therefore "
                    "do not form a minimal representative input basis"
                )
                eligible = False
                requires = True
            elif decoupled:
                status = "REPRESENTATIVE_EXACT"
                reason = (
                    "the exact normalized input basis is full-rank and has no residual "
                    "cross-output coupling up to one-to-one port pairing"
                )
                eligible = True
                requires = False
            else:
                status = "NON_REPRESENTATIVE_COUPLED"
                reason = (
                    "exact normalized inputs remain coupled, so the current input coordinates "
                    "are treated as a non-representative source description"
                )
                eligible = False
                requires = True
    payload = {
        "schema_version": 1,
        "representation_version": REPRESENTATION_VERSION,
        "mimo_ordered_signature": mimo.ordered_signature,
        "status": status,
        "reason": reason,
        "coupling_bp": coupling_bp,
        "pairing": list(pairing) if pairing is not None else None,
        "canonical_admission_eligible": eligible,
        "minimality": minimality.to_dict() if minimality is not None else None,
    }
    return RepresentationAssessment(
        schema_version=1,
        representation_version=REPRESENTATION_VERSION,
        status=status,
        reason=reason,
        coupling_bp=coupling_bp,
        preferred_input_to_output_pairing=pairing,
        canonical_admission_eligible=eligible,
        requires_representative_search=requires,
        minimality=minimality,
        assessment_signature=sha256_json(payload),
        warnings=tuple(warnings),
    )


def _admissibility(
    *,
    source_to_representative: Sequence[Sequence[Fraction]],
    representative_to_source: Sequence[Sequence[Fraction]],
    source_inputs: int,
    representative_inputs: int,
    coefficient_bit_limit: int,
) -> TransformAdmissibility:
    bits = max(
        _coefficient_bits(source_to_representative),
        _coefficient_bits(representative_to_source),
    )
    warnings: list[str] = []
    if representative_inputs == source_inputs:
        inverse_status = "FULLY_INVERTIBLE"
        invertible = (
            _matrix_inverse(source_to_representative) is not None
            and _matrix_inverse(representative_to_source) is not None
        )
    else:
        inverse_status = "INVERTIBLE_ON_BEHAVIORAL_QUOTIENT"
        invertible = (
            _matrix_rank(source_to_representative) == representative_inputs
            and _matrix_rank(tuple(zip(*representative_to_source))) == representative_inputs
            and _matrix_multiply(source_to_representative, representative_to_source)
            == _identity(representative_inputs)
        )
    if bits > coefficient_bit_limit:
        warnings.append(
            "representative transform exceeds configured exact coefficient bit budget"
        )
    admissible = invertible and bits <= coefficient_bit_limit
    status = "ADMISSIBLE_CONSTANT_REAL_TRANSFORM" if admissible else "INADMISSIBLE_TRANSFORM"
    return TransformAdmissibility(
        status=status,
        admissible=admissible,
        causal=True,
        stable=True,
        finite_real=True,
        invertibility_status=inverse_status if invertible else "NOT_INVERTIBLE",
        coefficient_bits=bits,
        coefficient_bit_limit=coefficient_bit_limit,
        warnings=tuple(warnings),
    )


def _source_section(
    source_inputs: int,
    pivots: Sequence[int],
    basis_transform: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[Fraction, ...], ...]:
    representative_inputs = len(basis_transform[0]) if basis_transform else 0
    section = [
        [Fraction(0) for _ in range(representative_inputs)]
        for _ in range(source_inputs)
    ]
    for basis_row, source_position in enumerate(pivots):
        section[source_position] = list(basis_transform[basis_row])
    return tuple(tuple(row) for row in section)


def _candidate(
    *,
    source: Sequence[Sequence[RationalChannel]],
    basis: Sequence[Sequence[RationalChannel]],
    minimality: MinimalityAssessment,
    basis_transform: Sequence[Sequence[Fraction]],
    transform_class: str,
    probe: Fraction | None,
    selected_output_rows: Sequence[int],
    coupling_before_bp: int,
    coefficient_bit_limit: int,
) -> RepresentativeInputCandidate:
    representative_inputs = minimality.effective_input_rank
    transform = tuple(tuple(row) for row in basis_transform)
    inverse = _matrix_inverse(transform) if representative_inputs else ()
    if representative_inputs and inverse is None:
        raise EGCFError("SAA-5 candidate basis transform must be invertible")
    projection = minimality.source_to_basis_projection
    source_to_representative = (
        _matrix_multiply(inverse, projection) if representative_inputs else ()
    )
    representative_to_source = _source_section(
        minimality.source_input_count,
        minimality.pivot_input_positions,
        transform,
    )
    representative_channels = _apply_constant_transform(basis, transform)
    if representative_inputs:
        reconstructed = _apply_constant_transform(
            representative_channels, source_to_representative
        )
        if tuple(tuple(row) for row in source) != reconstructed:
            raise EGCFError("SAA-5 representative transform failed exact behavior preservation")
    coupling_after_bp, pairing, decoupled = _support_coupling(representative_channels)
    admissibility = _admissibility(
        source_to_representative=source_to_representative,
        representative_to_source=representative_to_source,
        source_inputs=minimality.source_input_count,
        representative_inputs=representative_inputs,
        coefficient_bit_limit=coefficient_bit_limit,
    )
    minimal = representative_inputs == minimality.effective_input_rank
    independent = True
    if decoupled and admissibility.admissible and minimal:
        status = "REPRESENTATIVE_FORM_CANDIDATE"
    elif decoupled:
        status = "DECOUPLED_INADMISSIBLE_CANDIDATE"
    elif coupling_after_bp < coupling_before_bp:
        status = "IMPROVED_NON_REPRESENTATIVE_CANDIDATE"
    else:
        status = "NON_REPRESENTATIVE_CANDIDATE"
    requires_renormalization = not _selector_projection(source_to_representative)
    payload = {
        "schema_version": 1,
        "representation_version": REPRESENTATION_VERSION,
        "claim_scope": "REPRESENTATIVE_INPUT_CANDIDATE_NOT_CANONICAL_STORE_ID",
        "transform_class": transform_class,
        "probe": _fraction_payload(probe) if probe is not None else None,
        "selected_output_rows": list(selected_output_rows),
        "source_to_representative_projection": _matrix_payload(source_to_representative),
        "representative_to_source_section": _matrix_payload(representative_to_source),
        "representative_channels": _rational_payload(representative_channels),
        "coupling_after_bp": coupling_after_bp,
        "minimal": minimal,
        "admissibility": admissibility.to_dict(),
    }
    signature = sha256_json(payload)
    return RepresentativeInputCandidate(
        candidate_id=f"rep-candidate:sha256:{signature}",
        status=status,
        transform_class=transform_class,
        algebraic_probe=probe,
        selected_output_rows=tuple(selected_output_rows),
        source_input_count=minimality.source_input_count,
        representative_input_count=representative_inputs,
        source_to_representative_projection=source_to_representative,
        representative_to_source_section=representative_to_source,
        basis_transform=transform,
        representative_channels=representative_channels,
        coupling_before_bp=coupling_before_bp,
        coupling_after_bp=coupling_after_bp,
        preferred_input_to_output_pairing=pairing,
        exact_decoupled=decoupled,
        independent=independent,
        minimal=minimal,
        requires_renormalization=requires_renormalization,
        admissibility=admissibility,
        canonical_signature=signature,
        warnings=admissibility.warnings,
    )


def _probe_transform(
    basis: Sequence[Sequence[RationalChannel]],
    output_rows: Sequence[int],
    q: Fraction,
) -> Tuple[Tuple[Fraction, ...], ...] | None:
    size = len(basis[0]) if basis else 0
    matrix: list[tuple[Fraction, ...]] = []
    for output in output_rows:
        row: list[Fraction] = []
        for input_index in range(size):
            value = _evaluate_exact(basis[output][input_index], q)
            if value is None:
                return None
            row.append(value)
        matrix.append(tuple(row))
    inverse = _matrix_inverse(tuple(matrix))
    if inverse is None:
        return None
    return _normalize_transform_columns(inverse)


def discover_representative_inputs(
    mimo: CanonicalMIMOCoupling,
    *,
    max_rank_terms: int = MAX_RANK_VECTOR_TERMS,
    max_transforms: int = MAX_REPRESENTATIVE_TRANSFORMS,
    max_transform_coefficient_bits: int = MAX_TRANSFORM_COEFFICIENT_BITS,
) -> RepresentativeInputSearch:
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError("SAA-5 discovery requires CanonicalMIMOCoupling")
    if max_transforms < 1:
        raise EGCFError("max_transforms must be positive")
    if max_transform_coefficient_bits < 1:
        raise EGCFError("max_transform_coefficient_bits must be positive")
    assessment = assess_mimo_representation(mimo, max_rank_terms=max_rank_terms)
    warnings: list[str] = list(assessment.warnings)
    if mimo.dynamic_strength != "EXACT_MIMO_LINEAR_DYNAMICS":
        payload = {
            "representation_version": REPRESENTATION_VERSION,
            "source_assessment": assessment.assessment_signature,
            "search_status": "REPRESENTATIVE_FORM_UNRESOLVED_APPROXIMATE",
        }
        return RepresentativeInputSearch(
            schema_version=1,
            representation_version=REPRESENTATION_VERSION,
            source_assessment=assessment,
            minimality=None,
            search_status="REPRESENTATIVE_FORM_UNRESOLVED_APPROXIMATE",
            candidates_considered=0,
            candidates=(),
            best_candidate=None,
            audit_hash=sha256_json(payload),
            warnings=tuple(warnings),
        )

    minimality, source, basis = _minimality(mimo, max_rank_terms=max_rank_terms)
    source_coupling_bp, _, _ = _support_coupling(source)
    rank = minimality.effective_input_rank
    candidates: list[RepresentativeInputCandidate] = []
    seen: set[str] = set()
    considered = 0
    budget_exhausted = False

    if rank == 0:
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
        payload = {
            "representation_version": REPRESENTATION_VERSION,
            "claim_scope": "ZERO_EFFECTIVE_INPUT_REPRESENTATIVE_CANDIDATE",
            "source_signature": mimo.ordered_signature,
        }
        signature = sha256_json(payload)
        candidate = RepresentativeInputCandidate(
            candidate_id=f"rep-candidate:sha256:{signature}",
            status="REPRESENTATIVE_FORM_CANDIDATE",
            transform_class="BEHAVIORAL_ZERO_INPUT_QUOTIENT",
            algebraic_probe=None,
            selected_output_rows=(),
            source_input_count=minimality.source_input_count,
            representative_input_count=0,
            source_to_representative_projection=(),
            representative_to_source_section=tuple(() for _ in range(minimality.source_input_count)),
            basis_transform=(),
            representative_channels=tuple(() for _ in range(mimo.output_count)),
            coupling_before_bp=source_coupling_bp,
            coupling_after_bp=0,
            preferred_input_to_output_pairing=(),
            exact_decoupled=True,
            independent=True,
            minimal=True,
            requires_renormalization=False,
            admissibility=admissibility,
            canonical_signature=signature,
        )
        candidates.append(candidate)
    else:
        identity_candidate = _candidate(
            source=source,
            basis=basis,
            minimality=minimality,
            basis_transform=_identity(rank),
            transform_class=(
                "IDENTITY_AFTER_REDUNDANCY_QUOTIENT"
                if rank < minimality.source_input_count
                else "IDENTITY"
            ),
            probe=None,
            selected_output_rows=(),
            coupling_before_bp=source_coupling_bp,
            coefficient_bit_limit=max_transform_coefficient_bits,
        )
        candidates.append(identity_candidate)
        seen.add(identity_candidate.canonical_signature)
        considered = 1

        if not identity_candidate.exact_decoupled and rank <= mimo.output_count:
            probes = (
                CONTINUOUS_ALGEBRAIC_PROBES
                if mimo.domain == "CONTINUOUS"
                else DISCRETE_ALGEBRAIC_PROBES
            )
            for output_rows in itertools.permutations(range(mimo.output_count), rank):
                for probe in probes:
                    if considered >= max_transforms:
                        budget_exhausted = True
                        break
                    transform = _probe_transform(basis, output_rows, probe)
                    if transform is None:
                        continue
                    candidate = _candidate(
                        source=source,
                        basis=basis,
                        minimality=minimality,
                        basis_transform=transform,
                        transform_class="CONSTANT_LINEAR_ALGEBRAIC_PROBE",
                        probe=probe,
                        selected_output_rows=output_rows,
                        coupling_before_bp=source_coupling_bp,
                        coefficient_bit_limit=max_transform_coefficient_bits,
                    )
                    considered += 1
                    if candidate.canonical_signature in seen:
                        continue
                    seen.add(candidate.canonical_signature)
                    candidates.append(candidate)
                if budget_exhausted:
                    break

    def ranking(candidate: RepresentativeInputCandidate) -> tuple[Any, ...]:
        representative_rank = 0 if (
            candidate.status == "REPRESENTATIVE_FORM_CANDIDATE"
            and candidate.admissibility.admissible
        ) else 1
        return (
            representative_rank,
            candidate.coupling_after_bp,
            candidate.admissibility.coefficient_bits,
            candidate.representative_input_count,
            candidate.canonical_signature,
        )

    candidates_sorted = tuple(sorted(candidates, key=ranking))
    best = candidates_sorted[0] if candidates_sorted else None
    if best is not None and best.status == "REPRESENTATIVE_FORM_CANDIDATE" and best.admissibility.admissible:
        search_status = "REPRESENTATIVE_FORM_FOUND"
    elif budget_exhausted:
        search_status = "REPRESENTATIVE_SEARCH_BUDGET_EXHAUSTED"
        warnings.append(
            "bounded SAA-5 transform search exhausted before a representative form was found"
        )
    else:
        search_status = "REPRESENTATIVE_FORM_UNRESOLVED_CONSTANT_LINEAR_SEARCH"
        warnings.append(
            "no admissible exact constant input transform removed all residual coupling; "
            "a stronger dynamic or nonlinear representation search is required"
        )
    audit_payload = {
        "schema_version": 1,
        "representation_version": REPRESENTATION_VERSION,
        "source_assessment": assessment.assessment_signature,
        "minimality": minimality.to_dict(),
        "search_status": search_status,
        "candidates_considered": considered,
        "candidate_signatures": [candidate.canonical_signature for candidate in candidates_sorted],
        "best_candidate": best.canonical_signature if best is not None else None,
        "max_transforms": max_transforms,
        "max_transform_coefficient_bits": max_transform_coefficient_bits,
    }
    return RepresentativeInputSearch(
        schema_version=1,
        representation_version=REPRESENTATION_VERSION,
        source_assessment=assessment,
        minimality=minimality,
        search_status=search_status,
        candidates_considered=considered,
        candidates=candidates_sorted,
        best_candidate=best,
        audit_hash=sha256_json(audit_payload),
        warnings=tuple(warnings),
    )
