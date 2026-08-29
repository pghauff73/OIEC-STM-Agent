from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .nonlinear_evidence import ExactPolynomialSystem


NONLINEAR_LIFT_VERSION = "saa-nonlinear-lift-v1"
MAX_LIFT_STATE_DIMENSION = 5
MAX_LIFT_DEGREE = 5
MAX_LIFT_OBSERVABLES = 256
MAX_LIFT_REMAINDER_TERMS = 1024


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _matrix_payload(matrix: Sequence[Sequence[Fraction]]) -> list[list[list[int]]]:
    return [[_fraction_payload(value) for value in row] for row in matrix]


def _degree(powers: Sequence[int]) -> int:
    return sum(int(value) for value in powers)


def _powers_add(left: Sequence[int], right: Sequence[int]) -> Tuple[int, ...]:
    return tuple(int(a) + int(b) for a, b in zip(left, right))


def _monomial_basis(dimension: int, max_degree: int) -> Tuple[Tuple[int, ...], ...]:
    basis = [
        powers
        for powers in product(range(max_degree + 1), repeat=dimension)
        if _degree(powers) <= max_degree
    ]
    basis.sort(key=lambda powers: (_degree(powers), powers))
    if len(basis) > MAX_LIFT_OBSERVABLES:
        raise EGCFError("SAA-7.11 monomial lift exceeds bounded observable cap")
    return tuple(basis)


def _vector_field(system: ExactPolynomialSystem) -> tuple[dict[Tuple[int, ...], Fraction], ...]:
    if system.input_count != system.output_count:
        raise EGCFError("SAA-7.11 autonomous polynomial dynamics must be square")
    dimension = system.input_count
    components: list[dict[Tuple[int, ...], Fraction]] = [
        {} for _ in range(dimension)
    ]
    for term in system.terms:
        if term.output_index < 0 or term.output_index >= dimension:
            raise EGCFError("SAA-7.11 dynamic component outside state dimension")
        powers = tuple(int(value) for value in term.powers)
        if len(powers) != dimension or any(value < 0 for value in powers):
            raise EGCFError("SAA-7.11 invalid dynamic monomial")
        coefficient = _exact_fraction(term.coefficient, label="SAA-7.11 dynamic coefficient")
        component = components[term.output_index]
        component[powers] = component.get(powers, Fraction(0)) + coefficient
        if component[powers] == 0:
            del component[powers]
    return tuple(components)


def _monomial_derivative_along_field(
    powers: Tuple[int, ...],
    field: Sequence[Mapping[Tuple[int, ...], Fraction]],
) -> dict[Tuple[int, ...], Fraction]:
    dimension = len(powers)
    result: dict[Tuple[int, ...], Fraction] = {}
    for variable, exponent in enumerate(powers):
        if exponent == 0:
            continue
        reduced = list(powers)
        reduced[variable] -= 1
        reduced_powers = tuple(reduced)
        for field_powers, field_coefficient in field[variable].items():
            target = _powers_add(reduced_powers, field_powers)
            result[target] = result.get(target, Fraction(0)) + exponent * field_coefficient
            if result[target] == 0:
                del result[target]
    if len(result) > MAX_LIFT_REMAINDER_TERMS:
        raise EGCFError("SAA-7.11 lifted derivative exceeds bounded term cap")
    return result


@dataclass(frozen=True)
class LiftRemainderTerm:
    observable_index: int
    powers: Tuple[int, ...]
    coefficient: Fraction

    def to_dict(self) -> dict[str, Any]:
        return {
            "observable_index": self.observable_index,
            "powers": list(self.powers),
            "coefficient": _fraction_payload(self.coefficient),
        }


@dataclass(frozen=True)
class CarlemanKoopmanLift:
    schema_version: int
    lift_version: str
    state_dimension: int
    lift_degree: int
    basis: Tuple[Tuple[int, ...], ...]
    generator_matrix: Tuple[Tuple[Fraction, ...], ...]
    state_reconstruction_indices: Tuple[int, ...]
    remainder_terms: Tuple[LiftRemainderTerm, ...]
    exact_finite_closure: bool
    status: str
    discovery_aid_only: bool
    canonical_equivalence_eligible: bool
    lift_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lift_version": self.lift_version,
            "state_dimension": self.state_dimension,
            "lift_degree": self.lift_degree,
            "basis": [list(item) for item in self.basis],
            "generator_matrix": _matrix_payload(self.generator_matrix),
            "state_reconstruction_indices": list(self.state_reconstruction_indices),
            "remainder_terms": [item.to_dict() for item in self.remainder_terms],
            "exact_finite_closure": self.exact_finite_closure,
            "status": self.status,
            "discovery_aid_only": self.discovery_aid_only,
            "canonical_equivalence_eligible": self.canonical_equivalence_eligible,
            "lift_signature": self.lift_signature,
            "warnings": list(self.warnings),
        }


def build_carleman_koopman_lift(
    dynamics: ExactPolynomialSystem,
    *,
    lift_degree: int,
) -> CarlemanKoopmanLift:
    if not isinstance(dynamics, ExactPolynomialSystem):
        raise EGCFError("SAA-7.11 requires ExactPolynomialSystem dynamics")
    if dynamics.input_count != dynamics.output_count:
        raise EGCFError("SAA-7.11 requires autonomous square polynomial dynamics")
    dimension = dynamics.input_count
    if dimension < 1 or dimension > MAX_LIFT_STATE_DIMENSION:
        raise EGCFError("SAA-7.11 state dimension outside bounded range")
    degree = int(lift_degree)
    if degree < 1 or degree > MAX_LIFT_DEGREE:
        raise EGCFError("SAA-7.11 lift degree outside bounded range")
    field = _vector_field(dynamics)
    basis = _monomial_basis(dimension, degree)
    index = {powers: position for position, powers in enumerate(basis)}
    matrix = [
        [Fraction(0) for _ in range(len(basis))]
        for _ in range(len(basis))
    ]
    remainder: list[LiftRemainderTerm] = []
    for row, powers in enumerate(basis):
        derivative = _monomial_derivative_along_field(powers, field)
        for target_powers, coefficient in derivative.items():
            column = index.get(target_powers)
            if column is None:
                remainder.append(
                    LiftRemainderTerm(
                        observable_index=row,
                        powers=target_powers,
                        coefficient=coefficient,
                    )
                )
            else:
                matrix[row][column] += coefficient
    if len(remainder) > MAX_LIFT_REMAINDER_TERMS:
        raise EGCFError("SAA-7.11 lift remainder exceeds bounded cap")
    reconstruction: list[int] = []
    for state_index in range(dimension):
        powers = tuple(1 if index_ == state_index else 0 for index_ in range(dimension))
        reconstruction.append(index[powers])
    exact_closed = not remainder
    status = "EXACT_FINITE_CARLEMAN_KOOPMAN_CLOSURE" if exact_closed else "TRUNCATED_CARLEMAN_KOOPMAN_DISCOVERY_AID"
    matrix_tuple = tuple(tuple(row) for row in matrix)
    material = {
        "version": NONLINEAR_LIFT_VERSION,
        "state_dimension": dimension,
        "lift_degree": degree,
        "basis": [list(item) for item in basis],
        "generator_matrix": _matrix_payload(matrix_tuple),
        "remainder_terms": [item.to_dict() for item in remainder],
        "state_reconstruction_indices": reconstruction,
        "status": status,
    }
    warnings = (
        (
            "The finite monomial basis is exactly invariant under the polynomial generator and contains the original state coordinates; within this exact model the lift is a finite linear representation."
            if exact_closed
            else "The finite lift omits generated monomials outside the retained basis. It is a representation-discovery aid only and cannot establish nonlinear equivalence without a remainder/closure proof."
        ),
    )
    return CarlemanKoopmanLift(
        schema_version=1,
        lift_version=NONLINEAR_LIFT_VERSION,
        state_dimension=dimension,
        lift_degree=degree,
        basis=basis,
        generator_matrix=matrix_tuple,
        state_reconstruction_indices=tuple(reconstruction),
        remainder_terms=tuple(remainder),
        exact_finite_closure=exact_closed,
        status=status,
        discovery_aid_only=not exact_closed,
        canonical_equivalence_eligible=exact_closed,
        lift_signature=sha256_json(material),
        warnings=warnings,
    )
