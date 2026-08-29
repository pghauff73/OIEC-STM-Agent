from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .nonlinear_evidence import ExactPolynomialSystem


NONLINEAR_GLOBAL_VERSION = "saa-nonlinear-global-v1"
MAX_GLOBAL_DOMAIN_DIMENSION = 4
MAX_GLOBAL_COVER_CELLS = 128
MAX_GLOBAL_ELEMENTARY_CELLS = 4096


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _vector_payload(values: Sequence[Fraction]) -> list[list[int]]:
    return [_fraction_payload(value) for value in values]


def _canonical_polynomial(system: ExactPolynomialSystem) -> tuple[tuple[tuple[int, ...], Fraction], ...]:
    if not isinstance(system, ExactPolynomialSystem):
        raise EGCFError("SAA-7.10 requires exact polynomial systems")
    accumulated: dict[tuple[int, Tuple[int, ...]], Fraction] = {}
    for term in system.terms:
        output = int(term.output_index)
        if output < 0 or output >= system.output_count:
            raise EGCFError("SAA-7.10 polynomial output outside dimension")
        powers = tuple(int(value) for value in term.powers)
        if len(powers) != system.input_count or any(value < 0 for value in powers):
            raise EGCFError("SAA-7.10 invalid polynomial multi-index")
        coefficient = _exact_fraction(term.coefficient, label="SAA-7.10 polynomial coefficient")
        key = (output, powers)
        accumulated[key] = accumulated.get(key, Fraction(0)) + coefficient
    return tuple(
        ((output, *powers), coefficient)
        for (output, powers), coefficient in sorted(accumulated.items())
        if coefficient != 0
    )


def _polynomial_payload(canonical: Sequence[tuple[tuple[int, ...], Fraction]]) -> list[dict[str, Any]]:
    rows = []
    for key, coefficient in canonical:
        rows.append(
            {
                "output_index": key[0],
                "powers": list(key[1:]),
                "coefficient": _fraction_payload(coefficient),
            }
        )
    return rows


@dataclass(frozen=True)
class GlobalEquivalenceCell:
    lower: Tuple[Fraction, ...]
    upper: Tuple[Fraction, ...]
    output_delta_upper: Tuple[Fraction, ...]
    semantic_signature: str
    certificate_id: str

    def __post_init__(self) -> None:
        if len(self.lower) != len(self.upper):
            raise EGCFError("SAA-7.10 global cell dimension mismatch")
        if any(high <= low for low, high in zip(self.lower, self.upper)):
            raise EGCFError("SAA-7.10 global cell must have positive width")
        if any(value < 0 for value in self.output_delta_upper):
            raise EGCFError("SAA-7.10 behavior delta bounds cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower": _vector_payload(self.lower),
            "upper": _vector_payload(self.upper),
            "output_delta_upper": _vector_payload(self.output_delta_upper),
            "semantic_signature": self.semantic_signature,
            "certificate_id": self.certificate_id,
        }


@dataclass(frozen=True)
class GlobalNonlinearEquivalenceCertificate:
    schema_version: int
    global_version: str
    status: str
    claim_scope: str
    domain_lower: Tuple[Fraction, ...]
    domain_upper: Tuple[Fraction, ...]
    mathematical_equivalence: bool
    semantic_equivalence: bool
    complete_domain_coverage: bool
    output_delta_upper: Tuple[Fraction, ...]
    global_equivalence_eligible: bool
    proof_kind: str
    certificate_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "global_version": self.global_version,
            "status": self.status,
            "claim_scope": self.claim_scope,
            "domain_lower": _vector_payload(self.domain_lower),
            "domain_upper": _vector_payload(self.domain_upper),
            "mathematical_equivalence": self.mathematical_equivalence,
            "semantic_equivalence": self.semantic_equivalence,
            "complete_domain_coverage": self.complete_domain_coverage,
            "output_delta_upper": _vector_payload(self.output_delta_upper),
            "global_equivalence_eligible": self.global_equivalence_eligible,
            "proof_kind": self.proof_kind,
            "certificate_signature": self.certificate_signature,
            "warnings": list(self.warnings),
        }


def certify_exact_polynomial_global_equivalence(
    left: ExactPolynomialSystem,
    right: ExactPolynomialSystem,
    *,
    left_semantic_signature: str,
    right_semantic_signature: str,
    domain_lower: Sequence[Any],
    domain_upper: Sequence[Any],
) -> GlobalNonlinearEquivalenceCertificate:
    if left.input_count != right.input_count or left.output_count != right.output_count:
        raise EGCFError("SAA-7.10 exact polynomial systems have incompatible dimensions")
    dimension = left.input_count
    if dimension < 1 or dimension > MAX_GLOBAL_DOMAIN_DIMENSION:
        raise EGCFError("SAA-7.10 exact global proof dimension outside bounded range")
    if len(domain_lower) != dimension or len(domain_upper) != dimension:
        raise EGCFError("SAA-7.10 exact global domain dimension mismatch")
    lower = tuple(_exact_fraction(value, label="SAA-7.10 domain lower") for value in domain_lower)
    upper = tuple(_exact_fraction(value, label="SAA-7.10 domain upper") for value in domain_upper)
    if any(high <= low for low, high in zip(lower, upper)):
        raise EGCFError("SAA-7.10 exact global domain must have positive width")
    left_poly = _canonical_polynomial(left)
    right_poly = _canonical_polynomial(right)
    math_equal = left_poly == right_poly
    semantic_equal = str(left_semantic_signature) == str(right_semantic_signature) and bool(left_semantic_signature)
    if math_equal and semantic_equal:
        status = "EXACT_GLOBAL_POLYNOMIAL_EQUIVALENCE_ON_DOMAIN"
        eligible = True
    elif math_equal:
        status = "GLOBAL_MATHEMATICAL_MATCH_SEMANTIC_DIFFERENCE"
        eligible = False
    else:
        status = "GLOBAL_POLYNOMIAL_DIFFERENCE"
        eligible = False
    zeros = tuple(Fraction(0) for _ in range(left.output_count))
    material = {
        "version": NONLINEAR_GLOBAL_VERSION,
        "proof_kind": "EXACT_POLYNOMIAL_IDENTITY",
        "left": _polynomial_payload(left_poly),
        "right": _polynomial_payload(right_poly),
        "left_semantic": left_semantic_signature,
        "right_semantic": right_semantic_signature,
        "domain_lower": _vector_payload(lower),
        "domain_upper": _vector_payload(upper),
        "status": status,
    }
    return GlobalNonlinearEquivalenceCertificate(
        schema_version=1,
        global_version=NONLINEAR_GLOBAL_VERSION,
        status=status,
        claim_scope="EXACT_POLYNOMIAL_INPUT_OUTPUT_IDENTITY_ON_DECLARED_DOMAIN",
        domain_lower=lower,
        domain_upper=upper,
        mathematical_equivalence=math_equal,
        semantic_equivalence=semantic_equal,
        complete_domain_coverage=True,
        output_delta_upper=zeros,
        global_equivalence_eligible=eligible,
        proof_kind="EXACT_POLYNOMIAL_IDENTITY",
        certificate_signature=sha256_json(material),
        warnings=(
            "This certificate proves equality of the exact polynomial input-output maps and resolved semantics on the declared domain; it does not prove hidden-state realization equivalence outside that claim scope.",
        ),
    )


def make_global_equivalence_cell(
    *,
    lower: Sequence[Any],
    upper: Sequence[Any],
    output_delta_upper: Sequence[Any],
    semantic_signature: str,
    certificate_id: str,
) -> GlobalEquivalenceCell:
    return GlobalEquivalenceCell(
        lower=tuple(_exact_fraction(value, label="SAA-7.10 cell lower") for value in lower),
        upper=tuple(_exact_fraction(value, label="SAA-7.10 cell upper") for value in upper),
        output_delta_upper=tuple(
            _exact_fraction(value, label="SAA-7.10 cell behavior bound") for value in output_delta_upper
        ),
        semantic_signature=str(semantic_signature).strip(),
        certificate_id=str(certificate_id).strip(),
    )


def _complete_cover(
    cells: Sequence[GlobalEquivalenceCell],
    lower: Tuple[Fraction, ...],
    upper: Tuple[Fraction, ...],
) -> bool:
    dimension = len(lower)
    endpoints: list[list[Fraction]] = []
    for axis in range(dimension):
        values = {lower[axis], upper[axis]}
        for cell in cells:
            clipped_low = max(lower[axis], cell.lower[axis])
            clipped_high = min(upper[axis], cell.upper[axis])
            if clipped_low < clipped_high:
                values.add(clipped_low)
                values.add(clipped_high)
        ordered = sorted(values)
        endpoints.append(ordered)
    elementary_count = 1
    for values in endpoints:
        elementary_count *= max(0, len(values) - 1)
    if elementary_count > MAX_GLOBAL_ELEMENTARY_CELLS:
        raise EGCFError("SAA-7.10 regional coverage partition exceeds bounded cap")
    interval_lists = [list(zip(values[:-1], values[1:])) for values in endpoints]
    for elementary in product(*interval_lists):
        if any(high <= low for low, high in elementary):
            continue
        covered = any(
            all(cell.lower[axis] <= elementary[axis][0] and cell.upper[axis] >= elementary[axis][1] for axis in range(dimension))
            for cell in cells
        )
        if not covered:
            return False
    return True


def certify_regional_global_equivalence(
    cells: Sequence[GlobalEquivalenceCell],
    *,
    domain_lower: Sequence[Any],
    domain_upper: Sequence[Any],
) -> GlobalNonlinearEquivalenceCertificate:
    bounded_cells = tuple(cells)
    if not bounded_cells or len(bounded_cells) > MAX_GLOBAL_COVER_CELLS:
        raise EGCFError("SAA-7.10 regional proof requires a non-empty bounded cell set")
    dimension = len(bounded_cells[0].lower)
    if dimension < 1 or dimension > MAX_GLOBAL_DOMAIN_DIMENSION:
        raise EGCFError("SAA-7.10 regional domain dimension outside bounded range")
    if any(len(cell.lower) != dimension for cell in bounded_cells):
        raise EGCFError("SAA-7.10 regional cells have inconsistent dimensions")
    lower = tuple(_exact_fraction(value, label="SAA-7.10 regional domain lower") for value in domain_lower)
    upper = tuple(_exact_fraction(value, label="SAA-7.10 regional domain upper") for value in domain_upper)
    if len(lower) != dimension or len(upper) != dimension:
        raise EGCFError("SAA-7.10 regional target domain dimension mismatch")
    if any(high <= low for low, high in zip(lower, upper)):
        raise EGCFError("SAA-7.10 regional target domain must have positive width")
    coverage = _complete_cover(bounded_cells, lower, upper)
    semantics = {cell.semantic_signature for cell in bounded_cells}
    semantic_equal = len(semantics) == 1 and "" not in semantics
    output_count = len(bounded_cells[0].output_delta_upper)
    if any(len(cell.output_delta_upper) != output_count for cell in bounded_cells):
        raise EGCFError("SAA-7.10 regional behavior bound dimensions differ")
    worst = tuple(
        max(cell.output_delta_upper[index] for cell in bounded_cells)
        for index in range(output_count)
    )
    zero = all(value == 0 for value in worst)
    if coverage and semantic_equal and zero:
        status = "CERTIFIED_GLOBAL_EQUIVALENCE_ON_COVERED_DOMAIN"
        eligible = True
    elif coverage and semantic_equal:
        status = "CERTIFIED_GLOBAL_BEHAVIORAL_DELTA_BOUND"
        eligible = False
    elif not coverage:
        status = "GLOBAL_EQUIVALENCE_UNRESOLVED_INCOMPLETE_COVERAGE"
        eligible = False
    else:
        status = "GLOBAL_EQUIVALENCE_UNRESOLVED_SEMANTIC_CHANGE"
        eligible = False
    material = {
        "version": NONLINEAR_GLOBAL_VERSION,
        "proof_kind": "FINITE_VALIDATED_REGIONAL_COVER",
        "cells": [cell.to_dict() for cell in sorted(bounded_cells, key=lambda item: (item.lower, item.upper, item.certificate_id))],
        "domain_lower": _vector_payload(lower),
        "domain_upper": _vector_payload(upper),
        "coverage": coverage,
        "semantic_equal": semantic_equal,
        "worst": _vector_payload(worst),
        "status": status,
    }
    return GlobalNonlinearEquivalenceCertificate(
        schema_version=1,
        global_version=NONLINEAR_GLOBAL_VERSION,
        status=status,
        claim_scope="VALIDATED_BEHAVIORAL_EQUIVALENCE_ON_FINITE_CERTIFIED_DOMAIN_COVER",
        domain_lower=lower,
        domain_upper=upper,
        mathematical_equivalence=coverage and zero,
        semantic_equivalence=semantic_equal,
        complete_domain_coverage=coverage,
        output_delta_upper=worst,
        global_equivalence_eligible=eligible,
        proof_kind="FINITE_VALIDATED_REGIONAL_COVER",
        certificate_signature=sha256_json(material),
        warnings=(
            "Global eligibility is restricted to the explicitly covered finite domain. No extrapolation outside the cover is permitted.",
        ),
    )
