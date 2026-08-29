from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .nonlinear_evidence import ExactPolynomialSystem, ExactPolynomialTerm
from .nonlinear_geometry import exact_matrix_rank


NONLINEAR_LIE_VERSION = "saa-nonlinear-lie-v1"
MAX_LIE_STATE_DIMENSION = 6
MAX_LIE_CONTROL_FIELDS = 6
MAX_LIE_DEPTH = 4
MAX_LIE_GENERATED_OBJECTS = 256
MAX_LIE_POLYNOMIAL_TERMS = 1024

Polynomial = Dict[Tuple[int, ...], Fraction]
VectorField = Tuple[Polynomial, ...]


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _point_payload(values: Sequence[Fraction]) -> list[list[int]]:
    return [_fraction_payload(value) for value in values]


def _degree(powers: Sequence[int]) -> int:
    return sum(int(value) for value in powers)


def _zero_powers(dimension: int) -> Tuple[int, ...]:
    return tuple(0 for _ in range(dimension))


def _poly_normalize(poly: Mapping[Tuple[int, ...], Fraction]) -> Polynomial:
    result = {tuple(key): Fraction(value) for key, value in poly.items() if Fraction(value) != 0}
    if len(result) > MAX_LIE_POLYNOMIAL_TERMS:
        raise EGCFError("SAA-7.8 polynomial term budget exceeded")
    return result


def _poly_add(left: Mapping[Tuple[int, ...], Fraction], right: Mapping[Tuple[int, ...], Fraction]) -> Polynomial:
    result: Polynomial = dict(left)
    for powers, coefficient in right.items():
        result[powers] = result.get(powers, Fraction(0)) + coefficient
        if result[powers] == 0:
            del result[powers]
    return _poly_normalize(result)


def _poly_scale(poly: Mapping[Tuple[int, ...], Fraction], scale: Fraction) -> Polynomial:
    return _poly_normalize({powers: coefficient * scale for powers, coefficient in poly.items()})


def _powers_add(left: Sequence[int], right: Sequence[int]) -> Tuple[int, ...]:
    return tuple(int(a) + int(b) for a, b in zip(left, right))


def _poly_mul(left: Mapping[Tuple[int, ...], Fraction], right: Mapping[Tuple[int, ...], Fraction]) -> Polynomial:
    result: Polynomial = {}
    for left_powers, left_coefficient in left.items():
        for right_powers, right_coefficient in right.items():
            powers = _powers_add(left_powers, right_powers)
            result[powers] = result.get(powers, Fraction(0)) + left_coefficient * right_coefficient
    return _poly_normalize(result)


def _poly_derivative(poly: Mapping[Tuple[int, ...], Fraction], variable: int) -> Polynomial:
    result: Polynomial = {}
    for powers, coefficient in poly.items():
        exponent = powers[variable]
        if exponent == 0:
            continue
        reduced = list(powers)
        reduced[variable] -= 1
        key = tuple(reduced)
        result[key] = result.get(key, Fraction(0)) + coefficient * exponent
    return _poly_normalize(result)


def _poly_evaluate(poly: Mapping[Tuple[int, ...], Fraction], point: Sequence[Fraction]) -> Fraction:
    total = Fraction(0)
    for powers, coefficient in poly.items():
        value = coefficient
        for coordinate, power in zip(point, powers):
            if power:
                value *= coordinate ** power
        total += value
    return total


def _poly_payload(poly: Mapping[Tuple[int, ...], Fraction]) -> list[dict[str, Any]]:
    return [
        {"powers": list(powers), "coefficient": _fraction_payload(coefficient)}
        for powers, coefficient in sorted(poly.items(), key=lambda item: (_degree(item[0]), item[0]))
    ]


def _poly_signature(poly: Mapping[Tuple[int, ...], Fraction]) -> str:
    return sha256_json(_poly_payload(poly))


def _vector_payload(field: Sequence[Mapping[Tuple[int, ...], Fraction]]) -> list[list[dict[str, Any]]]:
    return [_poly_payload(component) for component in field]


def _vector_signature(field: Sequence[Mapping[Tuple[int, ...], Fraction]]) -> str:
    return sha256_json(_vector_payload(field))


def _system_to_vector(system: ExactPolynomialSystem, *, state_dimension: int) -> VectorField:
    if not isinstance(system, ExactPolynomialSystem):
        raise EGCFError("SAA-7.8 vector fields require ExactPolynomialSystem")
    if system.input_count != state_dimension or system.output_count != state_dimension:
        raise EGCFError("SAA-7.8 vector field dimensions must match state dimension")
    components: list[Polynomial] = [{} for _ in range(state_dimension)]
    for item in system.terms:
        if len(item.powers) != state_dimension:
            raise EGCFError("SAA-7.8 vector-field monomial dimension mismatch")
        if item.output_index < 0 or item.output_index >= state_dimension:
            raise EGCFError("SAA-7.8 vector-field component outside state dimension")
        coefficient = _exact_fraction(item.coefficient, label="SAA-7.8 polynomial coefficient")
        powers = tuple(int(value) for value in item.powers)
        if any(value < 0 for value in powers):
            raise EGCFError("SAA-7.8 polynomial powers cannot be negative")
        target = components[item.output_index]
        target[powers] = target.get(powers, Fraction(0)) + coefficient
    return tuple(_poly_normalize(component) for component in components)


def _system_to_scalars(system: ExactPolynomialSystem, *, state_dimension: int) -> Tuple[Polynomial, ...]:
    if not isinstance(system, ExactPolynomialSystem):
        raise EGCFError("SAA-7.8 outputs require ExactPolynomialSystem")
    if system.input_count != state_dimension:
        raise EGCFError("SAA-7.8 output input dimension must match state dimension")
    outputs: list[Polynomial] = [{} for _ in range(system.output_count)]
    for item in system.terms:
        if item.output_index < 0 or item.output_index >= system.output_count:
            raise EGCFError("SAA-7.8 output component outside output dimension")
        powers = tuple(int(value) for value in item.powers)
        if len(powers) != state_dimension:
            raise EGCFError("SAA-7.8 output monomial dimension mismatch")
        coefficient = _exact_fraction(item.coefficient, label="SAA-7.8 output coefficient")
        target = outputs[item.output_index]
        target[powers] = target.get(powers, Fraction(0)) + coefficient
    return tuple(_poly_normalize(component) for component in outputs)


def _directional_derivative(poly: Mapping[Tuple[int, ...], Fraction], field: VectorField) -> Polynomial:
    result: Polynomial = {}
    for index, component in enumerate(field):
        result = _poly_add(result, _poly_mul(_poly_derivative(poly, index), component))
    return result


def lie_bracket(left: VectorField, right: VectorField) -> VectorField:
    if len(left) != len(right):
        raise EGCFError("Lie bracket vector-field dimensions differ")
    result: list[Polynomial] = []
    for component_index in range(len(left)):
        # [left,right] = D(right) left - D(left) right.
        first = _directional_derivative(right[component_index], left)
        second = _directional_derivative(left[component_index], right)
        result.append(_poly_add(first, _poly_scale(second, Fraction(-1))))
    return tuple(result)


def lie_derivative(poly: Mapping[Tuple[int, ...], Fraction], field: VectorField) -> Polynomial:
    return _directional_derivative(poly, field)


def _vector_at(field: VectorField, point: Sequence[Fraction]) -> Tuple[Fraction, ...]:
    return tuple(_poly_evaluate(component, point) for component in field)


def _gradient_at(poly: Mapping[Tuple[int, ...], Fraction], point: Sequence[Fraction]) -> Tuple[Fraction, ...]:
    return tuple(_poly_evaluate(_poly_derivative(poly, index), point) for index in range(len(point)))


def _is_zero_vector(field: VectorField) -> bool:
    return all(not component for component in field)


def _is_zero_poly(poly: Mapping[Tuple[int, ...], Fraction]) -> bool:
    return not poly


@dataclass(frozen=True)
class ExactControlAffinePolynomialSystem:
    state_dimension: int
    drift: ExactPolynomialSystem
    control_fields: Tuple[ExactPolynomialSystem, ...]
    outputs: ExactPolynomialSystem
    domain_center: Tuple[Fraction, ...]
    domain_radius: Tuple[Fraction, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_dimension": self.state_dimension,
            "drift": self.drift.to_dict(),
            "control_fields": [item.to_dict() for item in self.control_fields],
            "outputs": self.outputs.to_dict(),
            "domain_center": _point_payload(self.domain_center),
            "domain_radius": _point_payload(self.domain_radius),
        }


@dataclass(frozen=True)
class LieAccessibilityAssessment:
    status: str
    state_dimension: int
    rank: int
    generated_field_count: int
    depth_reached: int
    full_rank: bool
    exact: bool
    local_only: bool
    global_accessibility_eligible: bool
    field_signatures: Tuple[str, ...]
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "state_dimension": self.state_dimension,
            "rank": self.rank,
            "generated_field_count": self.generated_field_count,
            "depth_reached": self.depth_reached,
            "full_rank": self.full_rank,
            "exact": self.exact,
            "local_only": self.local_only,
            "global_accessibility_eligible": self.global_accessibility_eligible,
            "field_signatures": list(self.field_signatures),
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class LieObservabilityAssessment:
    status: str
    state_dimension: int
    rank: int
    generated_function_count: int
    depth_reached: int
    full_rank: bool
    exact: bool
    local_only: bool
    global_observability_eligible: bool
    function_signatures: Tuple[str, ...]
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "state_dimension": self.state_dimension,
            "rank": self.rank,
            "generated_function_count": self.generated_function_count,
            "depth_reached": self.depth_reached,
            "full_rank": self.full_rank,
            "exact": self.exact,
            "local_only": self.local_only,
            "global_observability_eligible": self.global_observability_eligible,
            "function_signatures": list(self.function_signatures),
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class NonlinearLieAssessment:
    schema_version: int
    lie_version: str
    operating_point: Tuple[Fraction, ...]
    accessibility: LieAccessibilityAssessment
    observability: LieObservabilityAssessment
    locally_accessible_and_observable: bool
    global_claim_eligible: bool
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lie_version": self.lie_version,
            "operating_point": _point_payload(self.operating_point),
            "accessibility": self.accessibility.to_dict(),
            "observability": self.observability.to_dict(),
            "locally_accessible_and_observable": self.locally_accessible_and_observable,
            "global_claim_eligible": self.global_claim_eligible,
            "assessment_signature": self.assessment_signature,
        }


def make_control_affine_polynomial_system(
    *,
    state_dimension: int,
    drift: ExactPolynomialSystem,
    control_fields: Sequence[ExactPolynomialSystem],
    outputs: ExactPolynomialSystem,
    domain_center: Sequence[Any],
    domain_radius: Sequence[Any],
) -> ExactControlAffinePolynomialSystem:
    dimension = int(state_dimension)
    if dimension < 1 or dimension > MAX_LIE_STATE_DIMENSION:
        raise EGCFError(f"SAA-7.8 state dimension must lie in [1,{MAX_LIE_STATE_DIMENSION}]")
    controls = tuple(control_fields)
    if len(controls) > MAX_LIE_CONTROL_FIELDS:
        raise EGCFError("SAA-7.8 control-field count exceeds bounded cap")
    _system_to_vector(drift, state_dimension=dimension)
    for field in controls:
        _system_to_vector(field, state_dimension=dimension)
    _system_to_scalars(outputs, state_dimension=dimension)
    if len(domain_center) != dimension or len(domain_radius) != dimension:
        raise EGCFError("SAA-7.8 domain dimension mismatch")
    center = tuple(_exact_fraction(value, label="SAA-7.8 domain center") for value in domain_center)
    radius = tuple(_exact_fraction(value, label="SAA-7.8 domain radius") for value in domain_radius)
    if any(value <= 0 for value in radius):
        raise EGCFError("SAA-7.8 domain radii must be positive")
    return ExactControlAffinePolynomialSystem(
        state_dimension=dimension,
        drift=drift,
        control_fields=controls,
        outputs=outputs,
        domain_center=center,
        domain_radius=radius,
    )


def _validate_point(system: ExactControlAffinePolynomialSystem, point: Sequence[Any]) -> Tuple[Fraction, ...]:
    if len(point) != system.state_dimension:
        raise EGCFError("SAA-7.8 operating-point dimension mismatch")
    exact_point = tuple(_exact_fraction(value, label="SAA-7.8 operating point") for value in point)
    for value, center, radius in zip(exact_point, system.domain_center, system.domain_radius):
        if abs(value - center) > radius:
            raise EGCFError("SAA-7.8 operating point lies outside certified local domain")
    return exact_point


def assess_lie_accessibility(
    system: ExactControlAffinePolynomialSystem,
    *,
    operating_point: Sequence[Any],
    max_depth: int = MAX_LIE_DEPTH,
    max_generated: int = MAX_LIE_GENERATED_OBJECTS,
) -> LieAccessibilityAssessment:
    if not isinstance(system, ExactControlAffinePolynomialSystem):
        raise EGCFError("SAA-7.8 accessibility requires ExactControlAffinePolynomialSystem")
    if max_depth < 0 or max_depth > MAX_LIE_DEPTH:
        raise EGCFError("SAA-7.8 Lie depth outside bounded range")
    if max_generated < 1 or max_generated > MAX_LIE_GENERATED_OBJECTS:
        raise EGCFError("SAA-7.8 generated-field budget outside bounded range")
    point = _validate_point(system, operating_point)
    drift = _system_to_vector(system.drift, state_dimension=system.state_dimension)
    controls = tuple(_system_to_vector(item, state_dimension=system.state_dimension) for item in system.control_fields)
    generators = (drift, *controls)
    fields: list[VectorField] = []
    frontier: list[VectorField] = []
    seen: set[str] = set()
    for field in controls:
        if _is_zero_vector(field):
            continue
        signature = _vector_signature(field)
        if signature not in seen:
            seen.add(signature)
            fields.append(field)
            frontier.append(field)
    depth_reached = 0
    for depth in range(1, max_depth + 1):
        if not frontier or len(fields) >= max_generated:
            break
        next_frontier: list[VectorField] = []
        for base in generators:
            for field in frontier:
                bracket = lie_bracket(base, field)
                if _is_zero_vector(bracket):
                    continue
                signature = _vector_signature(bracket)
                if signature in seen:
                    continue
                seen.add(signature)
                fields.append(bracket)
                next_frontier.append(bracket)
                if len(fields) >= max_generated:
                    break
            if len(fields) >= max_generated:
                break
        frontier = next_frontier
        depth_reached = depth
    vectors = [_vector_at(field, point) for field in fields]
    rank = exact_matrix_rank(vectors) if vectors else 0
    full = rank == system.state_dimension
    status = "FULL_LOCAL_ACCESSIBILITY_RANK" if full else "PARTIAL_LOCAL_ACCESSIBILITY_RANK"
    material = {
        "version": NONLINEAR_LIE_VERSION,
        "point": _point_payload(point),
        "rank": rank,
        "depth": depth_reached,
        "fields": sorted(seen),
    }
    return LieAccessibilityAssessment(
        status=status,
        state_dimension=system.state_dimension,
        rank=rank,
        generated_field_count=len(fields),
        depth_reached=depth_reached,
        full_rank=full,
        exact=True,
        local_only=True,
        global_accessibility_eligible=False,
        field_signatures=tuple(sorted(seen)),
        assessment_signature=sha256_json(material),
        warnings=(
            "Full Lie rank is a bounded local accessibility result at the supplied operating point; it is not global controllability.",
        ),
    )


def assess_lie_observability(
    system: ExactControlAffinePolynomialSystem,
    *,
    operating_point: Sequence[Any],
    max_depth: int = MAX_LIE_DEPTH,
    max_generated: int = MAX_LIE_GENERATED_OBJECTS,
) -> LieObservabilityAssessment:
    if not isinstance(system, ExactControlAffinePolynomialSystem):
        raise EGCFError("SAA-7.8 observability requires ExactControlAffinePolynomialSystem")
    if max_depth < 0 or max_depth > MAX_LIE_DEPTH:
        raise EGCFError("SAA-7.8 Lie depth outside bounded range")
    point = _validate_point(system, operating_point)
    drift = _system_to_vector(system.drift, state_dimension=system.state_dimension)
    controls = tuple(_system_to_vector(item, state_dimension=system.state_dimension) for item in system.control_fields)
    generators = (drift, *controls)
    initial = list(_system_to_scalars(system.outputs, state_dimension=system.state_dimension))
    functions: list[Polynomial] = []
    frontier: list[Polynomial] = []
    seen: set[str] = set()
    for poly in initial:
        if _is_zero_poly(poly):
            continue
        signature = _poly_signature(poly)
        if signature not in seen:
            seen.add(signature)
            functions.append(poly)
            frontier.append(poly)
    depth_reached = 0
    for depth in range(1, max_depth + 1):
        if not frontier or len(functions) >= max_generated:
            break
        next_frontier: list[Polynomial] = []
        for field in generators:
            for poly in frontier:
                derived = lie_derivative(poly, field)
                if _is_zero_poly(derived):
                    continue
                signature = _poly_signature(derived)
                if signature in seen:
                    continue
                seen.add(signature)
                functions.append(derived)
                next_frontier.append(derived)
                if len(functions) >= max_generated:
                    break
            if len(functions) >= max_generated:
                break
        frontier = next_frontier
        depth_reached = depth
    gradients = [_gradient_at(poly, point) for poly in functions]
    rank = exact_matrix_rank(gradients) if gradients else 0
    full = rank == system.state_dimension
    status = "FULL_LOCAL_NONLINEAR_OBSERVABILITY_RANK" if full else "PARTIAL_LOCAL_NONLINEAR_OBSERVABILITY_RANK"
    material = {
        "version": NONLINEAR_LIE_VERSION,
        "point": _point_payload(point),
        "rank": rank,
        "depth": depth_reached,
        "functions": sorted(seen),
    }
    return LieObservabilityAssessment(
        status=status,
        state_dimension=system.state_dimension,
        rank=rank,
        generated_function_count=len(functions),
        depth_reached=depth_reached,
        full_rank=full,
        exact=True,
        local_only=True,
        global_observability_eligible=False,
        function_signatures=tuple(sorted(seen)),
        assessment_signature=sha256_json(material),
        warnings=(
            "The Lie-derivative rank result is local to the supplied exact polynomial model and operating point; it does not establish global injectivity.",
        ),
    )


def assess_nonlinear_lie_structure(
    system: ExactControlAffinePolynomialSystem,
    *,
    operating_point: Sequence[Any],
    max_depth: int = MAX_LIE_DEPTH,
) -> NonlinearLieAssessment:
    point = _validate_point(system, operating_point)
    accessibility = assess_lie_accessibility(system, operating_point=point, max_depth=max_depth)
    observability = assess_lie_observability(system, operating_point=point, max_depth=max_depth)
    combined = accessibility.full_rank and observability.full_rank
    material = {
        "version": NONLINEAR_LIE_VERSION,
        "point": _point_payload(point),
        "accessibility": accessibility.assessment_signature,
        "observability": observability.assessment_signature,
    }
    return NonlinearLieAssessment(
        schema_version=1,
        lie_version=NONLINEAR_LIE_VERSION,
        operating_point=point,
        accessibility=accessibility,
        observability=observability,
        locally_accessible_and_observable=combined,
        global_claim_eligible=False,
        assessment_signature=sha256_json(material),
    )
