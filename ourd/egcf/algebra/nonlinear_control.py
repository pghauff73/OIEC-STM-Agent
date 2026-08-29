from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .jet import CanonicalTaylorJet
from .nonlinear_geometry import (
    DifferentialGeometryAssessment,
    assess_nonlinear_geometry,
    exact_matrix_rank,
)
from .representative_form import CanonicalRepresentativeAlgorithmForm


NONLINEAR_CONTROL_VERSION = "saa-nonlinear-observability-controllability-v1"
MAX_LOCAL_STATE_DIMENSION = 12


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


def _exact_matrix(
    matrix: Sequence[Sequence[Any]],
    rows: int,
    columns: int,
    *,
    label: str,
) -> Tuple[Tuple[Fraction, ...], ...]:
    if len(matrix) != rows:
        raise EGCFError(f"{label} row count mismatch")
    result: list[Tuple[Fraction, ...]] = []
    for row_index, row in enumerate(matrix):
        if len(row) != columns:
            raise EGCFError(f"{label} column count mismatch")
        result.append(
            tuple(
                _exact_fraction(value, label=f"{label}[{row_index},{column_index}]")
                for column_index, value in enumerate(row)
            )
        )
    return tuple(result)


def _identity(size: int) -> Tuple[Tuple[Fraction, ...], ...]:
    return tuple(
        tuple(Fraction(1 if row == column else 0) for column in range(size))
        for row in range(size)
    )


def _matmul(
    left: Sequence[Sequence[Fraction]],
    right: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[Fraction, ...], ...]:
    if not left:
        return ()
    if not right:
        return tuple(() for _ in left)
    shared = len(left[0])
    if any(len(row) != shared for row in left) or len(right) != shared:
        raise EGCFError("matrix multiplication dimension mismatch")
    columns = len(right[0])
    if any(len(row) != columns for row in right):
        raise EGCFError("matrix multiplication right operand is not rectangular")
    return tuple(
        tuple(
            sum((Fraction(left[row][k]) * Fraction(right[k][column]) for k in range(shared)), Fraction(0))
            for column in range(columns)
        )
        for row in range(len(left))
    )


def _hstack(blocks: Sequence[Sequence[Sequence[Fraction]]]) -> Tuple[Tuple[Fraction, ...], ...]:
    if not blocks:
        return ()
    row_count = len(blocks[0])
    if any(len(block) != row_count for block in blocks):
        raise EGCFError("horizontal matrix stack row mismatch")
    return tuple(
        tuple(value for block in blocks for value in block[row])
        for row in range(row_count)
    )


def _vstack(blocks: Sequence[Sequence[Sequence[Fraction]]]) -> Tuple[Tuple[Fraction, ...], ...]:
    rows: list[Tuple[Fraction, ...]] = []
    width: int | None = None
    for block in blocks:
        for row in block:
            if width is None:
                width = len(row)
            elif len(row) != width:
                raise EGCFError("vertical matrix stack column mismatch")
            rows.append(tuple(row))
    return tuple(rows)


@dataclass(frozen=True)
class ExactLocalDynamicLinearization:
    schema_version: int
    control_version: str
    parent_representative_behavior_signature: str
    state_count: int
    control_count: int
    output_count: int
    state_meanings: Tuple[str, ...]
    a: Tuple[Tuple[Fraction, ...], ...]
    b: Tuple[Tuple[Fraction, ...], ...]
    c: Tuple[Tuple[Fraction, ...], ...]
    linearization_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "control_version": self.control_version,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "state_count": self.state_count,
            "control_count": self.control_count,
            "output_count": self.output_count,
            "state_meanings": list(self.state_meanings),
            "a": _matrix_payload(self.a),
            "b": _matrix_payload(self.b),
            "c": _matrix_payload(self.c),
            "linearization_signature": self.linearization_signature,
        }


def make_local_dynamic_linearization(
    form: CanonicalRepresentativeAlgorithmForm,
    *,
    a: Sequence[Sequence[Any]],
    b: Sequence[Sequence[Any]],
    c: Sequence[Sequence[Any]],
    state_meanings: Sequence[str],
) -> ExactLocalDynamicLinearization:
    state_count = len(a)
    if state_count < 1 or state_count > MAX_LOCAL_STATE_DIMENSION:
        raise EGCFError("SAA-7.7 local state dimension outside bounded range")
    if len(state_meanings) != state_count or any(not str(value).strip() for value in state_meanings):
        raise EGCFError("SAA-7.7 requires one non-empty meaning for every dynamic state")
    exact_a = _exact_matrix(a, state_count, state_count, label="A")
    exact_b = _exact_matrix(
        b,
        state_count,
        form.representative_input_count,
        label="B",
    )
    exact_c = _exact_matrix(
        c,
        form.output_count,
        state_count,
        label="C",
    )
    normalized_meanings = tuple(" ".join(str(value).strip().split()).casefold() for value in state_meanings)
    payload = {
        "schema_version": 1,
        "control_version": NONLINEAR_CONTROL_VERSION,
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "state_count": state_count,
        "control_count": form.representative_input_count,
        "output_count": form.output_count,
        "state_meanings": list(normalized_meanings),
        "a": _matrix_payload(exact_a),
        "b": _matrix_payload(exact_b),
        "c": _matrix_payload(exact_c),
    }
    return ExactLocalDynamicLinearization(
        schema_version=1,
        control_version=NONLINEAR_CONTROL_VERSION,
        parent_representative_behavior_signature=form.representative_behavior_signature,
        state_count=state_count,
        control_count=form.representative_input_count,
        output_count=form.output_count,
        state_meanings=normalized_meanings,
        a=exact_a,
        b=exact_b,
        c=exact_c,
        linearization_signature=sha256_json(payload),
    )


def controllability_matrix(
    linearization: ExactLocalDynamicLinearization,
) -> Tuple[Tuple[Fraction, ...], ...]:
    blocks: list[Tuple[Tuple[Fraction, ...], ...]] = []
    a_power = _identity(linearization.state_count)
    for _ in range(linearization.state_count):
        blocks.append(_matmul(a_power, linearization.b))
        a_power = _matmul(a_power, linearization.a)
    return _hstack(blocks)


def observability_matrix(
    linearization: ExactLocalDynamicLinearization,
) -> Tuple[Tuple[Fraction, ...], ...]:
    blocks: list[Tuple[Tuple[Fraction, ...], ...]] = []
    a_power = _identity(linearization.state_count)
    for _ in range(linearization.state_count):
        blocks.append(_matmul(linearization.c, a_power))
        a_power = _matmul(a_power, linearization.a)
    return _vstack(blocks)


@dataclass(frozen=True)
class RepresentativeControlAssessment:
    schema_version: int
    control_version: str
    parent_representative_behavior_signature: str
    jet_local_behavior_signature: str
    input_observability_rank: int
    representative_input_count: int
    representative_inputs_locally_observable: bool
    invariant_unobservable_direction_count: int
    dynamic_model_supplied: bool
    dynamic_linearization_signature: str
    state_count: int
    controllability_rank: int
    observability_rank: int
    dynamically_controllable: bool | None
    dynamically_observable: bool | None
    status: str
    canonical_control_eligible: bool
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "control_version": self.control_version,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "jet_local_behavior_signature": self.jet_local_behavior_signature,
            "input_observability_rank": self.input_observability_rank,
            "representative_input_count": self.representative_input_count,
            "representative_inputs_locally_observable": self.representative_inputs_locally_observable,
            "invariant_unobservable_direction_count": self.invariant_unobservable_direction_count,
            "dynamic_model_supplied": self.dynamic_model_supplied,
            "dynamic_linearization_signature": self.dynamic_linearization_signature,
            "state_count": self.state_count,
            "controllability_rank": self.controllability_rank,
            "observability_rank": self.observability_rank,
            "dynamically_controllable": self.dynamically_controllable,
            "dynamically_observable": self.dynamically_observable,
            "status": self.status,
            "canonical_control_eligible": self.canonical_control_eligible,
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


def assess_representative_observability_controllability(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    *,
    geometry: DifferentialGeometryAssessment | None = None,
    dynamic_linearization: ExactLocalDynamicLinearization | None = None,
) -> RepresentativeControlAssessment:
    if jet.parent_representative_behavior_signature != form.representative_behavior_signature:
        raise EGCFError("SAA-7.7 jet belongs to a different representative form")
    geometry = geometry or assess_nonlinear_geometry(form, jet)
    if geometry.jet_local_behavior_signature != jet.local_behavior_signature:
        raise EGCFError("SAA-7.7 geometry assessment belongs to a different jet")
    input_rank = geometry.jacobian_rank
    input_observable = (
        form.representative_input_count <= form.output_count
        and input_rank == form.representative_input_count
        and geometry.invariant_distribution_dimension == 0
    )

    state_count = 0
    controllability_rank = 0
    observability_rank = 0
    controllable: bool | None = None
    observable: bool | None = None
    linearization_signature = ""
    if dynamic_linearization is not None:
        if not isinstance(dynamic_linearization, ExactLocalDynamicLinearization):
            raise EGCFError("SAA-7.7 dynamic evidence must be ExactLocalDynamicLinearization")
        if dynamic_linearization.parent_representative_behavior_signature != form.representative_behavior_signature:
            raise EGCFError("SAA-7.7 dynamic linearization belongs to a different representative form")
        state_count = dynamic_linearization.state_count
        controllability_rank = exact_matrix_rank(controllability_matrix(dynamic_linearization))
        observability_rank = exact_matrix_rank(observability_matrix(dynamic_linearization))
        controllable = controllability_rank == state_count
        observable = observability_rank == state_count
        linearization_signature = dynamic_linearization.linearization_signature

    if not input_observable:
        status = "REPRESENTATIVE_INPUT_NOT_LOCALLY_OBSERVABLE"
        eligible = False
    elif dynamic_linearization is None:
        status = "OBSERVABLE_CONTROLLABILITY_REQUIRES_DYNAMIC_MODEL"
        eligible = False
    elif not observable and not controllable:
        status = "DYNAMIC_UNOBSERVABLE_AND_UNCONTROLLABLE"
        eligible = False
    elif not observable:
        status = "DYNAMIC_UNOBSERVABLE"
        eligible = False
    elif not controllable:
        status = "DYNAMIC_UNCONTROLLABLE"
        eligible = False
    else:
        status = "LOCALLY_OBSERVABLE_AND_CONTROLLABLE"
        eligible = True

    payload = {
        "schema_version": 1,
        "control_version": NONLINEAR_CONTROL_VERSION,
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "jet_local_behavior_signature": jet.local_behavior_signature,
        "geometry_signature": geometry.assessment_signature,
        "input_observability_rank": input_rank,
        "representative_input_count": form.representative_input_count,
        "invariant_unobservable_direction_count": geometry.invariant_distribution_dimension,
        "dynamic_linearization_signature": linearization_signature,
        "state_count": state_count,
        "controllability_rank": controllability_rank,
        "observability_rank": observability_rank,
        "status": status,
    }
    warnings = [
        "SAA-7.7 observability of representative inputs is a local differential property of the qualified finite jet.",
    ]
    if dynamic_linearization is None:
        warnings.append(
            "Controllability is not inferred from a static input-output equation; an exact local dynamic model is required."
        )
    else:
        warnings.append(
            "Dynamic controllability/observability uses exact Kalman ranks of the supplied local linearization. This is a bounded local gate, not a proof of global nonlinear accessibility or observability."
        )
    return RepresentativeControlAssessment(
        schema_version=1,
        control_version=NONLINEAR_CONTROL_VERSION,
        parent_representative_behavior_signature=form.representative_behavior_signature,
        jet_local_behavior_signature=jet.local_behavior_signature,
        input_observability_rank=input_rank,
        representative_input_count=form.representative_input_count,
        representative_inputs_locally_observable=input_observable,
        invariant_unobservable_direction_count=geometry.invariant_distribution_dimension,
        dynamic_model_supplied=dynamic_linearization is not None,
        dynamic_linearization_signature=linearization_signature,
        state_count=state_count,
        controllability_rank=controllability_rank,
        observability_rank=observability_rank,
        dynamically_controllable=controllable,
        dynamically_observable=observable,
        status=status,
        canonical_control_eligible=eligible,
        assessment_signature=sha256_json(payload),
        warnings=tuple(warnings),
    )
