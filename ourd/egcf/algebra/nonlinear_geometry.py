from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .jet import CanonicalTaylorJet
from .representative_form import CanonicalRepresentativeAlgorithmForm


NONLINEAR_GEOMETRY_VERSION = "saa-nonlinear-geometry-v1"


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _matrix_payload(matrix: Sequence[Sequence[Fraction]]) -> list[list[list[int]]]:
    return [[_fraction_payload(value) for value in row] for row in matrix]


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _rref(matrix: Sequence[Sequence[Fraction]]) -> tuple[list[list[Fraction]], list[int]]:
    rows = [list(map(Fraction, row)) for row in matrix]
    if not rows:
        return rows, []
    column_count = len(rows[0])
    if any(len(row) != column_count for row in rows):
        raise EGCFError("geometry matrix is not rectangular")
    pivot_columns: list[int] = []
    pivot_row = 0
    for column in range(column_count):
        selected = next((row for row in range(pivot_row, len(rows)) if rows[row][column] != 0), None)
        if selected is None:
            continue
        rows[pivot_row], rows[selected] = rows[selected], rows[pivot_row]
        pivot = rows[pivot_row][column]
        rows[pivot_row] = [value / pivot for value in rows[pivot_row]]
        for row in range(len(rows)):
            if row == pivot_row:
                continue
            factor = rows[row][column]
            if factor:
                rows[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(rows[row], rows[pivot_row])
                ]
        pivot_columns.append(column)
        pivot_row += 1
        if pivot_row == len(rows):
            break
    return rows, pivot_columns


def exact_matrix_rank(matrix: Sequence[Sequence[Fraction]]) -> int:
    if not matrix:
        return 0
    _, pivots = _rref(matrix)
    return len(pivots)


def exact_nullspace(matrix: Sequence[Sequence[Fraction]], column_count: int | None = None) -> Tuple[Tuple[Fraction, ...], ...]:
    if matrix:
        width = len(matrix[0])
    elif column_count is not None:
        width = int(column_count)
    else:
        width = 0
    if width < 0:
        raise EGCFError("nullspace column count cannot be negative")
    if not matrix:
        return tuple(
            tuple(Fraction(1 if index == free else 0) for index in range(width))
            for free in range(width)
        )
    rref, pivots = _rref(matrix)
    free_columns = [column for column in range(width) if column not in pivots]
    basis: list[Tuple[Fraction, ...]] = []
    for free in free_columns:
        vector = [Fraction(0) for _ in range(width)]
        vector[free] = Fraction(1)
        for row_index, pivot_column in enumerate(pivots):
            vector[pivot_column] = -rref[row_index][free]
        basis.append(tuple(vector))
    return tuple(basis)


def _delta_at(jet: CanonicalTaylorJet, point: Sequence[Any]) -> Tuple[Fraction, ...]:
    if len(point) != jet.input_count:
        raise EGCFError("SAA-7.6 geometry point dimension mismatch")
    exact_point = tuple(
        _exact_fraction(value, label=f"geometry point {index}")
        for index, value in enumerate(point)
    )
    for index, (value, center, radius) in enumerate(zip(exact_point, jet.center, jet.validity_radius)):
        if abs(value - center) > radius:
            raise EGCFError(f"SAA-7.6 geometry point coordinate {index} lies outside certified box")
    return tuple(value - center for value, center in zip(exact_point, jet.center))


def _monomial_value(delta: Sequence[Fraction], powers: Sequence[int]) -> Fraction:
    value = Fraction(1)
    for coordinate, power in zip(delta, powers):
        if power:
            value *= coordinate ** int(power)
    return value


def jacobian_at(jet: CanonicalTaylorJet, point: Sequence[Any]) -> Tuple[Tuple[Fraction, ...], ...]:
    delta = _delta_at(jet, point)
    matrix = [[Fraction(0) for _ in range(jet.input_count)] for _ in range(jet.output_count)]
    for term in jet.terms:
        for input_index, power in enumerate(term.powers):
            if power == 0:
                continue
            derivative_powers = list(term.powers)
            derivative_powers[input_index] -= 1
            matrix[term.output_index][input_index] += (
                term.coefficient
                * int(power)
                * _monomial_value(delta, derivative_powers)
            )
    return tuple(tuple(row) for row in matrix)


def hessian_at(
    jet: CanonicalTaylorJet,
    point: Sequence[Any],
) -> Tuple[Tuple[Tuple[Fraction, ...], ...], ...]:
    delta = _delta_at(jet, point)
    tensor = [
        [[Fraction(0) for _ in range(jet.input_count)] for _ in range(jet.input_count)]
        for _ in range(jet.output_count)
    ]
    for term in jet.terms:
        for left in range(jet.input_count):
            for right in range(jet.input_count):
                left_power = int(term.powers[left])
                right_power = int(term.powers[right])
                if left == right:
                    if left_power < 2:
                        continue
                    factor = left_power * (left_power - 1)
                    powers = list(term.powers)
                    powers[left] -= 2
                else:
                    if left_power < 1 or right_power < 1:
                        continue
                    factor = left_power * right_power
                    powers = list(term.powers)
                    powers[left] -= 1
                    powers[right] -= 1
                tensor[term.output_index][left][right] += (
                    term.coefficient * factor * _monomial_value(delta, powers)
                )
    return tuple(tuple(tuple(row) for row in output) for output in tensor)


def _derivative_coefficient_matrix(jet: CanonicalTaylorJet) -> tuple[Tuple[Tuple[Fraction, ...], ...], Tuple[tuple[int, Tuple[int, ...]], ...]]:
    accumulator: dict[tuple[int, Tuple[int, ...]], list[Fraction]] = {}
    for term in jet.terms:
        for input_index, power in enumerate(term.powers):
            if power == 0:
                continue
            derivative_powers = list(term.powers)
            derivative_powers[input_index] -= 1
            key = (term.output_index, tuple(derivative_powers))
            row = accumulator.setdefault(
                key, [Fraction(0) for _ in range(jet.input_count)]
            )
            row[input_index] += term.coefficient * int(power)
    keys = tuple(sorted(accumulator, key=lambda item: (item[0], sum(item[1]), item[1])))
    matrix = tuple(tuple(accumulator[key]) for key in keys)
    return matrix, keys


@dataclass(frozen=True)
class DifferentialGeometryAssessment:
    schema_version: int
    geometry_version: str
    parent_representative_behavior_signature: str
    jet_local_behavior_signature: str
    point: Tuple[Fraction, ...]
    jacobian: Tuple[Tuple[Fraction, ...], ...]
    jacobian_rank: int
    tangent_nullspace: Tuple[Tuple[Fraction, ...], ...]
    local_manifold_dimension: int
    local_diffeomorphism: bool
    hessian: Tuple[Tuple[Tuple[Fraction, ...], ...], ...]
    cross_curvature_count: int
    invariant_distribution_basis: Tuple[Tuple[Fraction, ...], ...]
    invariant_distribution_dimension: int
    invariant_distribution_integrable: bool
    behavioral_input_dimension: int
    status: str
    canonical_geometry_eligible: bool
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "geometry_version": self.geometry_version,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "jet_local_behavior_signature": self.jet_local_behavior_signature,
            "point": [_fraction_payload(value) for value in self.point],
            "jacobian": _matrix_payload(self.jacobian),
            "jacobian_rank": self.jacobian_rank,
            "tangent_nullspace": _matrix_payload(self.tangent_nullspace),
            "local_manifold_dimension": self.local_manifold_dimension,
            "local_diffeomorphism": self.local_diffeomorphism,
            "hessian": [
                _matrix_payload(output) for output in self.hessian
            ],
            "cross_curvature_count": self.cross_curvature_count,
            "invariant_distribution_basis": _matrix_payload(self.invariant_distribution_basis),
            "invariant_distribution_dimension": self.invariant_distribution_dimension,
            "invariant_distribution_integrable": self.invariant_distribution_integrable,
            "behavioral_input_dimension": self.behavioral_input_dimension,
            "status": self.status,
            "canonical_geometry_eligible": self.canonical_geometry_eligible,
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


def assess_nonlinear_geometry(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    *,
    point: Sequence[Any] | None = None,
) -> DifferentialGeometryAssessment:
    if jet.parent_representative_behavior_signature != form.representative_behavior_signature:
        raise EGCFError("SAA-7.6 jet belongs to a different representative form")
    selected_point = tuple(jet.center if point is None else point)
    exact_point = tuple(
        _exact_fraction(value, label=f"geometry point {index}")
        for index, value in enumerate(selected_point)
    )
    jacobian = jacobian_at(jet, exact_point)
    rank = exact_matrix_rank(jacobian)
    tangent_nullspace = exact_nullspace(jacobian, jet.input_count)
    hessian = hessian_at(jet, exact_point)
    cross_curvature = sum(
        1
        for output in range(jet.output_count)
        for left in range(jet.input_count)
        for right in range(left + 1, jet.input_count)
        if hessian[output][left][right] != 0
    )
    derivative_matrix, _ = _derivative_coefficient_matrix(jet)
    invariant_basis = exact_nullspace(derivative_matrix, jet.input_count)
    invariant_dimension = len(invariant_basis)
    behavioral_dimension = jet.input_count - invariant_dimension
    local_diffeomorphism = (
        jet.input_count == jet.output_count
        and rank == jet.input_count
    )
    if invariant_dimension:
        status = "INVARIANT_REDUNDANT_DIRECTION_DETECTED"
        eligible = False
    elif rank < min(jet.input_count, jet.output_count):
        status = "LOCAL_SINGULAR_REPRESENTATION"
        eligible = False
    elif jet.output_count < jet.input_count:
        status = "OUTPUT_DIMENSION_LIMITED_REPRESENTATION"
        eligible = False
    else:
        status = "FULL_RANK_LOCAL_GEOMETRY"
        eligible = True
    payload = {
        "schema_version": 1,
        "geometry_version": NONLINEAR_GEOMETRY_VERSION,
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "jet_local_behavior_signature": jet.local_behavior_signature,
        "point": [_fraction_payload(value) for value in exact_point],
        "jacobian": _matrix_payload(jacobian),
        "jacobian_rank": rank,
        "tangent_nullspace": _matrix_payload(tangent_nullspace),
        "local_diffeomorphism": local_diffeomorphism,
        "cross_curvature_count": cross_curvature,
        "invariant_distribution_basis": _matrix_payload(invariant_basis),
        "behavioral_input_dimension": behavioral_dimension,
        "status": status,
    }
    warnings: list[str] = [
        "SAA-7.6 differential geometry is exact for the finite jet polynomial within its certified local scope, not for unknown higher-order/global behavior."
    ]
    if invariant_dimension:
        warnings.append(
            "The invariant distribution consists of constant exact directions annihilating every derivative polynomial in the retained jet; constant vector fields commute, so this detected distribution is integrable."
        )
    if rank < jet.input_count and not invariant_dimension:
        warnings.append(
            "A rank loss at one point may be a local singularity rather than global redundancy; OIEC does not collapse dimensions from this point test alone."
        )
    return DifferentialGeometryAssessment(
        schema_version=1,
        geometry_version=NONLINEAR_GEOMETRY_VERSION,
        parent_representative_behavior_signature=form.representative_behavior_signature,
        jet_local_behavior_signature=jet.local_behavior_signature,
        point=exact_point,
        jacobian=jacobian,
        jacobian_rank=rank,
        tangent_nullspace=tangent_nullspace,
        local_manifold_dimension=rank,
        local_diffeomorphism=local_diffeomorphism,
        hessian=hessian,
        cross_curvature_count=cross_curvature,
        invariant_distribution_basis=invariant_basis,
        invariant_distribution_dimension=invariant_dimension,
        invariant_distribution_integrable=True,
        behavioral_input_dimension=behavioral_dimension,
        status=status,
        canonical_geometry_eligible=eligible,
        assessment_signature=sha256_json(payload),
        warnings=tuple(warnings),
    )
