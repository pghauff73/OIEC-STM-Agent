from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import comb, factorial
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .jet import CanonicalTaylorJet
from .nonlinear_evidence import ExactPolynomialSystem, GovernedJetEvidence


NONLINEAR_REMAINDER_VERSION = "saa-nonlinear-remainder-v1"
MAX_REMAINDER_TERMS = 4096


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _fraction_tuple_payload(values: Sequence[Fraction]) -> list[list[int]]:
    return [_fraction_payload(value) for value in values]


def _degree(powers: Sequence[int]) -> int:
    return sum(int(value) for value in powers)


def _multi_factorial(powers: Sequence[int]) -> int:
    result = 1
    for power in powers:
        result *= factorial(int(power))
    return result


def _zero_powers(dimension: int) -> Tuple[int, ...]:
    return tuple(0 for _ in range(dimension))


def _powers_add(left: Sequence[int], right: Sequence[int]) -> Tuple[int, ...]:
    return tuple(int(a) + int(b) for a, b in zip(left, right))


def _poly_mul(
    left: Mapping[Tuple[int, ...], Fraction],
    right: Mapping[Tuple[int, ...], Fraction],
) -> dict[Tuple[int, ...], Fraction]:
    result: dict[Tuple[int, ...], Fraction] = {}
    for left_powers, left_coefficient in left.items():
        for right_powers, right_coefficient in right.items():
            powers = _powers_add(left_powers, right_powers)
            result[powers] = result.get(powers, Fraction(0)) + left_coefficient * right_coefficient
    result = {powers: value for powers, value in result.items() if value != 0}
    if len(result) > MAX_REMAINDER_TERMS:
        raise EGCFError("SAA-7.9 expansion exceeds bounded remainder term budget")
    return result


def _shift_monomial(
    powers: Sequence[int],
    center: Sequence[Fraction],
    coefficient: Fraction,
) -> dict[Tuple[int, ...], Fraction]:
    dimension = len(center)
    result: dict[Tuple[int, ...], Fraction] = {_zero_powers(dimension): coefficient}
    for index, exponent in enumerate(powers):
        factor: dict[Tuple[int, ...], Fraction] = {}
        for local_power in range(int(exponent) + 1):
            local = [0] * dimension
            local[index] = local_power
            factor[tuple(local)] = Fraction(comb(int(exponent), local_power)) * (
                center[index] ** (int(exponent) - local_power)
            )
        result = _poly_mul(result, factor)
    return result


def _shift_system(
    system: ExactPolynomialSystem,
    center: Sequence[Fraction],
) -> tuple[dict[Tuple[int, ...], Fraction], ...]:
    if system.input_count != len(center):
        raise EGCFError("SAA-7.9 polynomial system dimension differs from Taylor center")
    outputs: list[dict[Tuple[int, ...], Fraction]] = [
        {} for _ in range(system.output_count)
    ]
    for item in system.terms:
        if item.output_index < 0 or item.output_index >= system.output_count:
            raise EGCFError("SAA-7.9 polynomial output index outside output dimension")
        powers = tuple(int(value) for value in item.powers)
        if len(powers) != system.input_count or any(value < 0 for value in powers):
            raise EGCFError("SAA-7.9 invalid polynomial multi-index")
        coefficient = _exact_fraction(item.coefficient, label="SAA-7.9 polynomial coefficient")
        shifted = _shift_monomial(powers, center, coefficient)
        target = outputs[item.output_index]
        for local_powers, value in shifted.items():
            target[local_powers] = target.get(local_powers, Fraction(0)) + value
            if target[local_powers] == 0:
                del target[local_powers]
    return tuple(outputs)


def _jet_map(jet: CanonicalTaylorJet) -> tuple[dict[Tuple[int, ...], Fraction], ...]:
    result: list[dict[Tuple[int, ...], Fraction]] = [
        {} for _ in range(jet.output_count)
    ]
    for term in jet.terms:
        result[term.output_index][term.powers] = term.coefficient
    return tuple(result)


def _box_bound(poly: Mapping[Tuple[int, ...], Fraction], radius: Sequence[Fraction]) -> Fraction:
    bound = Fraction(0)
    for powers, coefficient in poly.items():
        term = abs(coefficient)
        for local_radius, power in zip(radius, powers):
            if power:
                term *= local_radius ** power
        bound += term
    return bound


@dataclass(frozen=True)
class DerivativeRemainderTerm:
    output_index: int
    powers: Tuple[int, ...]
    absolute_upper: Fraction

    def __post_init__(self) -> None:
        if self.absolute_upper < 0:
            raise EGCFError("SAA-7.9 derivative remainder bound cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_index": self.output_index,
            "powers": list(self.powers),
            "absolute_upper": _fraction_payload(self.absolute_upper),
        }


@dataclass(frozen=True)
class ValidatedTaylorRemainder:
    schema_version: int
    remainder_version: str
    proof_kind: str
    parent_jet_signature: str
    center: Tuple[Fraction, ...]
    validity_radius: Tuple[Fraction, ...]
    order: int
    output_absolute_upper: Tuple[Fraction, ...]
    exact_containment: bool
    source_snapshot_hash: str
    independent_validation: bool
    global_equivalence_eligible: bool
    certificate_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "remainder_version": self.remainder_version,
            "proof_kind": self.proof_kind,
            "parent_jet_signature": self.parent_jet_signature,
            "center": _fraction_tuple_payload(self.center),
            "validity_radius": _fraction_tuple_payload(self.validity_radius),
            "order": self.order,
            "output_absolute_upper": _fraction_tuple_payload(self.output_absolute_upper),
            "exact_containment": self.exact_containment,
            "source_snapshot_hash": self.source_snapshot_hash,
            "independent_validation": self.independent_validation,
            "global_equivalence_eligible": self.global_equivalence_eligible,
            "certificate_signature": self.certificate_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class LocalBehaviorDeltaBound:
    status: str
    center: Tuple[Fraction, ...]
    overlap_radius: Tuple[Fraction, ...]
    output_absolute_upper: Tuple[Fraction, ...]
    exact_zero_difference: bool
    local_equivalence_eligible: bool
    global_equivalence_eligible: bool
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "center": _fraction_tuple_payload(self.center),
            "overlap_radius": _fraction_tuple_payload(self.overlap_radius),
            "output_absolute_upper": _fraction_tuple_payload(self.output_absolute_upper),
            "exact_zero_difference": self.exact_zero_difference,
            "local_equivalence_eligible": self.local_equivalence_eligible,
            "global_equivalence_eligible": self.global_equivalence_eligible,
            "signature": self.signature,
        }


def certify_polynomial_remainder(
    evidence: GovernedJetEvidence,
    full_polynomial: ExactPolynomialSystem,
) -> ValidatedTaylorRemainder:
    if not isinstance(evidence, GovernedJetEvidence) or evidence.jet is None:
        raise EGCFError("SAA-7.9 polynomial remainder requires exact governed jet evidence")
    if not evidence.exact or not evidence.canonical_local_eligible:
        raise EGCFError("SAA-7.9 cannot certify exact remainder from non-qualified evidence")
    jet = evidence.jet
    if full_polynomial.input_count != jet.input_count or full_polynomial.output_count != jet.output_count:
        raise EGCFError("SAA-7.9 full polynomial dimensions differ from governed jet")
    shifted = _shift_system(full_polynomial, jet.center)
    retained = _jet_map(jet)
    residuals: list[dict[Tuple[int, ...], Fraction]] = []
    for output_index in range(jet.output_count):
        full = shifted[output_index]
        expected_low = {
            powers: coefficient
            for powers, coefficient in full.items()
            if _degree(powers) <= jet.order
        }
        actual_low = retained[output_index]
        keys = set(expected_low) | set(actual_low)
        if any(expected_low.get(key, Fraction(0)) != actual_low.get(key, Fraction(0)) for key in keys):
            raise EGCFError("SAA-7.9 governed jet does not match exact polynomial through retained order")
        residuals.append(
            {
                powers: coefficient
                for powers, coefficient in full.items()
                if _degree(powers) > jet.order and coefficient != 0
            }
        )
    bounds = tuple(_box_bound(poly, jet.validity_radius) for poly in residuals)
    material = {
        "version": NONLINEAR_REMAINDER_VERSION,
        "proof_kind": "EXACT_POLYNOMIAL_RESIDUAL_BOUND",
        "jet": jet.local_behavior_signature,
        "source": evidence.source_snapshot_hash,
        "bounds": _fraction_tuple_payload(bounds),
    }
    return ValidatedTaylorRemainder(
        schema_version=1,
        remainder_version=NONLINEAR_REMAINDER_VERSION,
        proof_kind="EXACT_POLYNOMIAL_RESIDUAL_BOUND",
        parent_jet_signature=jet.local_behavior_signature,
        center=jet.center,
        validity_radius=jet.validity_radius,
        order=jet.order,
        output_absolute_upper=bounds,
        exact_containment=True,
        source_snapshot_hash=evidence.source_snapshot_hash,
        independent_validation=evidence.independent_acquisition,
        global_equivalence_eligible=False,
        certificate_signature=sha256_json(material),
        warnings=(
            "The enclosure is rigorous for the certified local box but remains local unless a later coverage proof spans the full claimed domain.",
        ),
    )


def certify_derivative_remainder(
    jet: CanonicalTaylorJet,
    *,
    derivative_bounds: Sequence[DerivativeRemainderTerm],
    source_snapshot_hash: str,
    independent_validation: bool,
) -> ValidatedTaylorRemainder:
    if not isinstance(jet, CanonicalTaylorJet) or not jet.exact:
        raise EGCFError("SAA-7.9 derivative remainder requires an exact canonical Taylor jet")
    digest = str(source_snapshot_hash).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EGCFError("SAA-7.9 derivative remainder source snapshot must be SHA-256")
    if not independent_validation:
        raise EGCFError("SAA-7.9 derivative remainder requires independent validation")
    required_degree = jet.order + 1
    bounds = [Fraction(0) for _ in range(jet.output_count)]
    seen: set[tuple[int, Tuple[int, ...]]] = set()
    for item in derivative_bounds:
        if not isinstance(item, DerivativeRemainderTerm):
            raise EGCFError("SAA-7.9 derivative bounds must be DerivativeRemainderTerm")
        if item.output_index < 0 or item.output_index >= jet.output_count:
            raise EGCFError("SAA-7.9 derivative remainder output outside dimension")
        if len(item.powers) != jet.input_count or _degree(item.powers) != required_degree:
            raise EGCFError("SAA-7.9 derivative remainder requires complete order p+1 multi-indices")
        key = (item.output_index, item.powers)
        if key in seen:
            raise EGCFError("duplicate SAA-7.9 derivative remainder multi-index")
        seen.add(key)
        contribution = Fraction(item.absolute_upper, _multi_factorial(item.powers))
        for radius, power in zip(jet.validity_radius, item.powers):
            if power:
                contribution *= radius ** power
        bounds[item.output_index] += contribution
    bounds_tuple = tuple(bounds)
    material = {
        "version": NONLINEAR_REMAINDER_VERSION,
        "proof_kind": "VALIDATED_DERIVATIVE_ENVELOPE",
        "jet": jet.local_behavior_signature,
        "source": digest,
        "bounds": _fraction_tuple_payload(bounds_tuple),
    }
    return ValidatedTaylorRemainder(
        schema_version=1,
        remainder_version=NONLINEAR_REMAINDER_VERSION,
        proof_kind="VALIDATED_DERIVATIVE_ENVELOPE",
        parent_jet_signature=jet.local_behavior_signature,
        center=jet.center,
        validity_radius=jet.validity_radius,
        order=jet.order,
        output_absolute_upper=bounds_tuple,
        exact_containment=True,
        source_snapshot_hash=digest,
        independent_validation=True,
        global_equivalence_eligible=False,
        certificate_signature=sha256_json(material),
        warnings=(
            "Derivative envelopes must be valid throughout the entire certified local box; the certificate does not infer that validity from point samples.",
        ),
    )


def bound_local_behavior_difference(
    left: CanonicalTaylorJet,
    right: CanonicalTaylorJet,
    *,
    left_remainder: ValidatedTaylorRemainder,
    right_remainder: ValidatedTaylorRemainder,
) -> LocalBehaviorDeltaBound:
    if left.input_count != right.input_count or left.output_count != right.output_count:
        raise EGCFError("SAA-7.9 local comparison dimension mismatch")
    if left.center != right.center:
        raise EGCFError("SAA-7.9 local behavior bound currently requires a common exact expansion point")
    if left_remainder.parent_jet_signature != left.local_behavior_signature:
        raise EGCFError("left SAA-7.9 remainder does not belong to left jet")
    if right_remainder.parent_jet_signature != right.local_behavior_signature:
        raise EGCFError("right SAA-7.9 remainder does not belong to right jet")
    overlap = tuple(min(a, b) for a, b in zip(left.validity_radius, right.validity_radius))
    left_map = _jet_map(left)
    right_map = _jet_map(right)
    output_bounds: list[Fraction] = []
    for output_index in range(left.output_count):
        difference: dict[Tuple[int, ...], Fraction] = {}
        keys = set(left_map[output_index]) | set(right_map[output_index])
        for powers in keys:
            value = left_map[output_index].get(powers, Fraction(0)) - right_map[output_index].get(powers, Fraction(0))
            if value:
                difference[powers] = value
        polynomial_bound = _box_bound(difference, overlap)
        output_bounds.append(
            polynomial_bound
            + left_remainder.output_absolute_upper[output_index]
            + right_remainder.output_absolute_upper[output_index]
        )
    exact_zero = all(value == 0 for value in output_bounds)
    status = "EXACT_LOCAL_BEHAVIOR_MATCH_WITH_VALIDATED_REMAINDER" if exact_zero else "VALIDATED_LOCAL_BEHAVIOR_DELTA_BOUND"
    material = {
        "version": NONLINEAR_REMAINDER_VERSION,
        "left": left.local_behavior_signature,
        "right": right.local_behavior_signature,
        "overlap": _fraction_tuple_payload(overlap),
        "bounds": _fraction_tuple_payload(tuple(output_bounds)),
    }
    return LocalBehaviorDeltaBound(
        status=status,
        center=left.center,
        overlap_radius=overlap,
        output_absolute_upper=tuple(output_bounds),
        exact_zero_difference=exact_zero,
        local_equivalence_eligible=exact_zero,
        global_equivalence_eligible=False,
        signature=sha256_json(material),
    )
