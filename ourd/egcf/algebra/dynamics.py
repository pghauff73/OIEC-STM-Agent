from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .models import CanonicalAlgorithmIR
from .normalize import NormalizationContract


DYNAMICS_VERSION = "saa-linear-dynamics-v1"
LINEAR_DOMAINS = {"CONTINUOUS", "DISCRETE"}
MAX_STATE_ORDER = 12
MAX_POLYNOMIAL_DEGREE = 64


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _domain(value: str) -> str:
    domain = str(value).strip().upper()
    aliases = {
        "S": "CONTINUOUS",
        "S_DOMAIN": "CONTINUOUS",
        "CONTINUOUS_TIME": "CONTINUOUS",
        "Z": "DISCRETE",
        "Z_DOMAIN": "DISCRETE",
        "DISCRETE_TIME": "DISCRETE",
    }
    domain = aliases.get(domain, domain)
    if domain not in LINEAR_DOMAINS:
        raise EGCFError(f"unsupported SAA-3 linear domain: {value!r}")
    return domain


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _coerce_scalar(value: Any, label: str) -> tuple[Fraction, bool, str]:
    if isinstance(value, bool):
        raise EGCFError(f"{label} must be numeric, not bool")
    if isinstance(value, Fraction):
        return value, True, f"{value.numerator}/{value.denominator}"
    if isinstance(value, int):
        return Fraction(value, 1), True, str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise EGCFError(f"{label} must be finite")
        return Fraction(value), True, str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise EGCFError(f"{label} must be non-empty")
        try:
            parsed = Fraction(text)
        except (ValueError, ZeroDivisionError) as exc:
            raise EGCFError(f"invalid exact {label}: {value!r}") from exc
        return parsed, True, text
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EGCFError(f"{label} must be finite")
        if value == 0.0:
            value = 0.0
        return Fraction(str(value)), False, repr(value)
    raise EGCFError(
        f"{label} must be int, Fraction, Decimal, exact numeric string, or finite float"
    )


def _trim_descending(poly: Sequence[Fraction]) -> tuple[Fraction, ...]:
    values = list(poly)
    if not values:
        return (Fraction(0),)
    index = 0
    while index < len(values) - 1 and values[index] == 0:
        index += 1
    return tuple(values[index:])


def _is_zero_poly(poly: Sequence[Fraction]) -> bool:
    return all(value == 0 for value in poly)


def _coerce_polynomial(
    values: Sequence[Any],
    label: str,
) -> tuple[tuple[Fraction, ...], bool, list[dict[str, str]]]:
    if not _is_sequence(values) or not values:
        raise EGCFError(f"{label} must be a non-empty coefficient sequence")
    result: list[Fraction] = []
    exact = True
    audit: list[dict[str, str]] = []
    for index, value in enumerate(values):
        coefficient, item_exact, source = _coerce_scalar(value, f"{label}[{index}]")
        result.append(coefficient)
        exact = exact and item_exact
        audit.append(
            {
                "source": source,
                "inferred_strength": "EXACT" if item_exact else "APPROXIMATE",
            }
        )
    trimmed = _trim_descending(result)
    if len(trimmed) - 1 > MAX_POLYNOMIAL_DEGREE:
        raise EGCFError(
            f"{label} degree exceeds SAA-3 limit {MAX_POLYNOMIAL_DEGREE}"
        )
    return trimmed, exact, audit


def _trim_ascending(poly: Sequence[Fraction]) -> tuple[Fraction, ...]:
    values = list(poly)
    if not values:
        return (Fraction(0),)
    while len(values) > 1 and values[-1] == 0:
        values.pop()
    return tuple(values)


def _poly_divmod_ascending(
    dividend: Sequence[Fraction],
    divisor: Sequence[Fraction],
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    left = list(_trim_ascending(dividend))
    right = list(_trim_ascending(divisor))
    if _is_zero_poly(right):
        raise EGCFError("internal SAA-3 polynomial division by zero")
    if len(left) < len(right):
        return (Fraction(0),), tuple(left)
    quotient = [Fraction(0)] * (len(left) - len(right) + 1)
    while len(left) >= len(right) and not _is_zero_poly(left):
        shift = len(left) - len(right)
        factor = left[-1] / right[-1]
        quotient[shift] += factor
        for index, coefficient in enumerate(right):
            left[index + shift] -= factor * coefficient
        left = list(_trim_ascending(left))
    return _trim_ascending(quotient), _trim_ascending(left)


def _poly_gcd_ascending(
    first: Sequence[Fraction],
    second: Sequence[Fraction],
) -> tuple[Fraction, ...]:
    left = _trim_ascending(first)
    right = _trim_ascending(second)
    while not _is_zero_poly(right):
        _, remainder = _poly_divmod_ascending(left, right)
        left, right = right, remainder
    if _is_zero_poly(left):
        return (Fraction(1),)
    lead = left[-1]
    return tuple(value / lead for value in left)


def _normalize_denominator(
    numerator: Sequence[Fraction],
    denominator: Sequence[Fraction],
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    num = _trim_descending(numerator)
    den = _trim_descending(denominator)
    if _is_zero_poly(den):
        raise EGCFError("SAA-3 transfer denominator cannot be zero")
    if _is_zero_poly(num):
        return (Fraction(0),), (Fraction(1),)
    lead = den[0]
    return tuple(value / lead for value in num), tuple(value / lead for value in den)


def _reduce_exact_transfer(
    numerator: Sequence[Fraction],
    denominator: Sequence[Fraction],
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...], tuple[str, ...]]:
    num = _trim_descending(numerator)
    den = _trim_descending(denominator)
    if _is_zero_poly(den):
        raise EGCFError("SAA-3 transfer denominator cannot be zero")
    if _is_zero_poly(num):
        return (Fraction(0),), (Fraction(1),), ("ZERO_TRANSFER_CANONICALIZATION",)

    num_ascending = tuple(reversed(num))
    den_ascending = tuple(reversed(den))
    gcd = _poly_gcd_ascending(num_ascending, den_ascending)
    reductions: list[str] = []
    if len(gcd) > 1:
        num_q, num_r = _poly_divmod_ascending(num_ascending, gcd)
        den_q, den_r = _poly_divmod_ascending(den_ascending, gcd)
        if not _is_zero_poly(num_r) or not _is_zero_poly(den_r):
            raise EGCFError("internal SAA-3 exact factor cancellation failed")
        num = tuple(reversed(num_q))
        den = tuple(reversed(den_q))
        reductions.append("EXACT_COMMON_FACTOR_CANCELLATION")
    num, den = _normalize_denominator(num, den)
    reductions.append("MONIC_DENOMINATOR")
    return num, den, tuple(reductions)


def _scale_time_polynomial(
    coefficients: Sequence[Fraction],
    characteristic_time: Fraction,
) -> tuple[Fraction, ...]:
    degree = len(coefficients) - 1
    return tuple(
        coefficient / (characteristic_time ** (degree - index))
        for index, coefficient in enumerate(coefficients)
    )


def _polynomial_payload(poly: Sequence[Fraction]) -> list[list[int]]:
    return [_fraction_payload(value) for value in poly]


def _role_bindings(contract: NormalizationContract, role: str) -> list[Any]:
    return [item for item in contract.bindings if item.role == role]


def _normalization_scales(
    contract: NormalizationContract,
) -> tuple[Fraction, Fraction, Fraction, bool]:
    if not isinstance(contract, NormalizationContract):
        raise EGCFError("SAA-3 requires a NormalizationContract from SAA-2")
    inputs = _role_bindings(contract, "INPUT")
    outputs = _role_bindings(contract, "OUTPUT")
    if len(inputs) != 1 or len(outputs) != 1:
        raise EGCFError("SAA-3 v1 supports SISO normalization contracts only")
    if inputs[0].canonical_data_type != "CONTINUOUS_SCALAR":
        raise EGCFError("SAA-3 v1 requires a continuous scalar input coordinate")
    if outputs[0].canonical_data_type != "CONTINUOUS_SCALAR":
        raise EGCFError("SAA-3 v1 requires a continuous scalar output coordinate")
    if contract.time is None:
        raise EGCFError(
            "SAA-3 requires SAA-2 characteristic time so dynamic time scale is canonical"
        )
    input_width = Fraction(str(inputs[0].bound.width))
    output_width = Fraction(str(outputs[0].bound.width))
    characteristic_time = Fraction(str(contract.time.characteristic_time))
    exact = contract.normalization_strength == "EXACT_NORMALIZATION"
    return input_width, output_width, characteristic_time, exact


@dataclass(frozen=True)
class LinearTransferFunction:
    domain: str
    numerator: Tuple[Any, ...]
    denominator: Tuple[Any, ...]
    sample_period: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", _domain(self.domain))
        object.__setattr__(self, "numerator", tuple(self.numerator))
        object.__setattr__(self, "denominator", tuple(self.denominator))


@dataclass(frozen=True)
class LinearStateSpace:
    domain: str
    a: Tuple[Tuple[Any, ...], ...]
    b: Tuple[Any, ...]
    c: Tuple[Any, ...]
    d: Any = 0
    sample_period: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", _domain(self.domain))
        object.__setattr__(self, "a", tuple(tuple(row) for row in self.a))
        object.__setattr__(self, "b", tuple(self.b))
        object.__setattr__(self, "c", tuple(self.c))


@dataclass(frozen=True)
class CanonicalLinearDynamics:
    schema_version: int
    dynamics_version: str
    domain: str
    variable: str
    numerator: Tuple[Fraction, ...]
    denominator: Tuple[Fraction, ...]
    dynamic_order: int
    relative_degree: int | None
    proper: bool
    normalized_sample_interval: Fraction | None
    dynamic_strength: str
    normalization_signature: str
    audit_hash: str
    canonical_signature: str
    reductions: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dynamics_version": self.dynamics_version,
            "domain": self.domain,
            "variable": self.variable,
            "numerator": _polynomial_payload(self.numerator),
            "denominator": _polynomial_payload(self.denominator),
            "dynamic_order": self.dynamic_order,
            "relative_degree": self.relative_degree,
            "proper": self.proper,
            "normalized_sample_interval": (
                _fraction_payload(self.normalized_sample_interval)
                if self.normalized_sample_interval is not None
                else None
            ),
            "dynamic_strength": self.dynamic_strength,
            "normalization_signature": self.normalization_signature,
            "audit_hash": self.audit_hash,
            "canonical_signature": self.canonical_signature,
            "reductions": list(self.reductions),
            "warnings": list(self.warnings),
        }


def _canonicalize_fraction_transfer(
    *,
    domain: str,
    numerator: Sequence[Fraction],
    denominator: Sequence[Fraction],
    coefficient_exact: bool,
    sample_period: Fraction | None,
    sample_period_exact: bool,
    normalization: NormalizationContract,
    source_kind: str,
    source_audit: Mapping[str, Any],
) -> CanonicalLinearDynamics:
    domain = _domain(domain)
    num = _trim_descending(numerator)
    den = _trim_descending(denominator)
    if _is_zero_poly(den):
        raise EGCFError("SAA-3 transfer denominator cannot be zero")
    if len(num) - 1 > MAX_POLYNOMIAL_DEGREE or len(den) - 1 > MAX_POLYNOMIAL_DEGREE:
        raise EGCFError(
            f"SAA-3 transfer degree exceeds limit {MAX_POLYNOMIAL_DEGREE}"
        )

    input_width, output_width, characteristic_time, normalization_exact = (
        _normalization_scales(normalization)
    )
    interface_gain = input_width / output_width
    num = tuple(value * interface_gain for value in num)

    normalized_sample_interval: Fraction | None = None
    if domain == "CONTINUOUS":
        if sample_period is not None:
            raise EGCFError("continuous SAA-3 transfer must not declare sample_period")
        num = _scale_time_polynomial(num, characteristic_time)
        den = _scale_time_polynomial(den, characteristic_time)
        variable = "SIGMA"
        sample_exact = True
    else:
        if sample_period is None:
            raise EGCFError("discrete SAA-3 transfer requires sample_period")
        if sample_period <= 0:
            raise EGCFError("discrete SAA-3 sample_period must be positive")
        normalized_sample_interval = sample_period / characteristic_time
        variable = "Z"
        sample_exact = sample_period_exact

    exact = coefficient_exact and normalization_exact and sample_exact
    warnings: list[str] = []
    if _is_zero_poly(num):
        reduced_num = (Fraction(0),)
        reduced_den = (Fraction(1),)
        reductions = ("ZERO_TRANSFER_CANONICALIZATION",)
    elif exact:
        reduced_num, reduced_den, reductions = _reduce_exact_transfer(num, den)
    else:
        reduced_num, reduced_den = _normalize_denominator(num, den)
        reductions = ("MONIC_DENOMINATOR", "NO_APPROXIMATE_POLE_ZERO_CANCELLATION")
        warnings.append(
            "approximate SAA-3 dynamics are not pole-zero cancelled; near cancellation "
            "cannot establish exact dynamic equivalence"
        )

    denominator_degree = len(reduced_den) - 1
    if _is_zero_poly(reduced_num):
        numerator_degree: int | None = None
        relative_degree: int | None = None
        proper = True
    else:
        numerator_degree = len(reduced_num) - 1
        relative_degree = denominator_degree - numerator_degree
        proper = numerator_degree <= denominator_degree
    if not proper:
        warnings.append(
            "improper transfer form retained; SAA-3 signature is algebraic and does not "
            "claim a standard proper finite-dimensional realization"
        )

    strength = "EXACT_LINEAR_DYNAMICS" if exact else "APPROXIMATE_LINEAR_DYNAMICS"
    audit_payload = {
        "schema_version": 1,
        "dynamics_version": DYNAMICS_VERSION,
        "source_kind": source_kind,
        "source": dict(source_audit),
        "normalization_contract_hash": normalization.contract_hash,
        "normalization_signature": normalization.canonical_signature,
        "coefficient_strength": "EXACT" if coefficient_exact else "APPROXIMATE",
        "sample_period_strength": (
            None
            if domain == "CONTINUOUS"
            else ("EXACT" if sample_period_exact else "APPROXIMATE")
        ),
    }
    canonical_payload = {
        "schema_version": 1,
        "dynamics_version": DYNAMICS_VERSION,
        "claim_scope": "NORMALIZED_SISO_LINEAR_INPUT_OUTPUT_DYNAMICS",
        "linearization_coordinate": "DEVIATION_DYNAMICS",
        "domain": domain,
        "variable": variable,
        "numerator": _polynomial_payload(reduced_num),
        "denominator": _polynomial_payload(reduced_den),
        "dynamic_order": denominator_degree,
        "relative_degree": relative_degree,
        "proper": proper,
        "normalized_sample_interval": (
            _fraction_payload(normalized_sample_interval)
            if normalized_sample_interval is not None
            else None
        ),
        "dynamic_strength": strength,
        "normalization_signature": normalization.canonical_signature,
        "reduction_policy": (
            "EXACT_RATIONAL_POLYNOMIAL_REDUCTION"
            if exact
            else "MONIC_ONLY_NO_APPROXIMATE_FACTOR_CANCELLATION"
        ),
    }
    return CanonicalLinearDynamics(
        schema_version=1,
        dynamics_version=DYNAMICS_VERSION,
        domain=domain,
        variable=variable,
        numerator=tuple(reduced_num),
        denominator=tuple(reduced_den),
        dynamic_order=denominator_degree,
        relative_degree=relative_degree,
        proper=proper,
        normalized_sample_interval=normalized_sample_interval,
        dynamic_strength=strength,
        normalization_signature=normalization.canonical_signature,
        audit_hash=sha256_json(audit_payload),
        canonical_signature=sha256_json(canonical_payload),
        reductions=tuple(reductions),
        warnings=tuple(warnings),
    )


def canonicalize_transfer_function(
    transfer: LinearTransferFunction,
    normalization: NormalizationContract,
) -> CanonicalLinearDynamics:
    if not isinstance(transfer, LinearTransferFunction):
        raise EGCFError("canonicalize_transfer_function requires LinearTransferFunction")
    numerator, numerator_exact, numerator_audit = _coerce_polynomial(
        transfer.numerator, "transfer numerator"
    )
    denominator, denominator_exact, denominator_audit = _coerce_polynomial(
        transfer.denominator, "transfer denominator"
    )
    if _is_zero_poly(denominator):
        raise EGCFError("SAA-3 transfer denominator cannot be zero")

    sample_period: Fraction | None = None
    sample_period_exact = True
    sample_period_source: str | None = None
    if transfer.domain == "DISCRETE":
        if transfer.sample_period is None:
            raise EGCFError("discrete SAA-3 transfer requires sample_period")
        sample_period, sample_period_exact, sample_period_source = _coerce_scalar(
            transfer.sample_period, "sample_period"
        )
    elif transfer.sample_period is not None:
        raise EGCFError("continuous SAA-3 transfer must not declare sample_period")

    return _canonicalize_fraction_transfer(
        domain=transfer.domain,
        numerator=numerator,
        denominator=denominator,
        coefficient_exact=numerator_exact and denominator_exact,
        sample_period=sample_period,
        sample_period_exact=sample_period_exact,
        normalization=normalization,
        source_kind="TRANSFER_FUNCTION",
        source_audit={
            "domain": transfer.domain,
            "numerator": numerator_audit,
            "denominator": denominator_audit,
            "sample_period": sample_period_source,
        },
    )


def _coerce_matrix(
    values: Sequence[Sequence[Any]],
    label: str,
) -> tuple[tuple[tuple[Fraction, ...], ...], bool, list[list[dict[str, str]]]]:
    if not _is_sequence(values) or not values:
        raise EGCFError(f"{label} must be a non-empty matrix")
    rows: list[tuple[Fraction, ...]] = []
    audit_rows: list[list[dict[str, str]]] = []
    exact = True
    width: int | None = None
    for row_index, row in enumerate(values):
        if not _is_sequence(row) or not row:
            raise EGCFError(f"{label}[{row_index}] must be a non-empty row")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise EGCFError(f"{label} rows must have equal width")
        parsed_row: list[Fraction] = []
        audit_row: list[dict[str, str]] = []
        for column_index, value in enumerate(row):
            parsed, item_exact, source = _coerce_scalar(
                value, f"{label}[{row_index}][{column_index}]"
            )
            parsed_row.append(parsed)
            exact = exact and item_exact
            audit_row.append(
                {
                    "source": source,
                    "inferred_strength": "EXACT" if item_exact else "APPROXIMATE",
                }
            )
        rows.append(tuple(parsed_row))
        audit_rows.append(audit_row)
    return tuple(rows), exact, audit_rows


def _coerce_vector(
    values: Sequence[Any],
    label: str,
    length: int,
    *,
    allow_column: bool,
    allow_row: bool,
) -> tuple[tuple[Fraction, ...], bool, Any]:
    if not _is_sequence(values) or not values:
        raise EGCFError(f"{label} must be a non-empty SISO vector")
    flattened: Sequence[Any]
    if all(not _is_sequence(item) for item in values):
        flattened = values
    elif allow_column and len(values) == length and all(
        _is_sequence(item) and len(item) == 1 for item in values
    ):
        flattened = [item[0] for item in values]
    elif allow_row and len(values) == 1 and _is_sequence(values[0]):
        flattened = values[0]
    else:
        raise EGCFError(f"{label} must be a SISO vector of length {length}")
    if len(flattened) != length:
        raise EGCFError(f"{label} must contain exactly {length} values")
    result: list[Fraction] = []
    audit: list[dict[str, str]] = []
    exact = True
    for index, value in enumerate(flattened):
        parsed, item_exact, source = _coerce_scalar(value, f"{label}[{index}]")
        result.append(parsed)
        exact = exact and item_exact
        audit.append(
            {
                "source": source,
                "inferred_strength": "EXACT" if item_exact else "APPROXIMATE",
            }
        )
    return tuple(result), exact, audit


def _identity(size: int) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(
        tuple(Fraction(1 if row == column else 0) for column in range(size))
        for row in range(size)
    )


def _matrix_multiply(
    left: Sequence[Sequence[Fraction]],
    right: Sequence[Sequence[Fraction]],
) -> tuple[tuple[Fraction, ...], ...]:
    rows = len(left)
    inner = len(left[0])
    if len(right) != inner:
        raise EGCFError("internal SAA-3 matrix dimension mismatch")
    columns = len(right[0])
    return tuple(
        tuple(
            sum((left[row][index] * right[index][column] for index in range(inner)), Fraction(0))
            for column in range(columns)
        )
        for row in range(rows)
    )


def _matrix_add_identity(
    matrix: Sequence[Sequence[Fraction]],
    scalar: Fraction,
) -> tuple[tuple[Fraction, ...], ...]:
    size = len(matrix)
    return tuple(
        tuple(
            matrix[row][column] + (scalar if row == column else 0)
            for column in range(size)
        )
        for row in range(size)
    )


def _trace(matrix: Sequence[Sequence[Fraction]]) -> Fraction:
    return sum((matrix[index][index] for index in range(len(matrix))), Fraction(0))


def _row_matrix_column(
    row: Sequence[Fraction],
    matrix: Sequence[Sequence[Fraction]],
    column: Sequence[Fraction],
) -> Fraction:
    size = len(row)
    return sum(
        (
            row[i] * matrix[i][j] * column[j]
            for i in range(size)
            for j in range(size)
        ),
        Fraction(0),
    )


def _state_space_transfer(
    a: Sequence[Sequence[Fraction]],
    b: Sequence[Fraction],
    c: Sequence[Fraction],
    d: Fraction,
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    size = len(a)
    identity = _identity(size)
    b_previous = identity
    adjugate_coefficients: list[tuple[tuple[Fraction, ...], ...]] = [identity]
    denominator: list[Fraction] = [Fraction(1)]

    for order in range(1, size + 1):
        a_times_b = _matrix_multiply(a, b_previous)
        coefficient = -_trace(a_times_b) / order
        denominator.append(coefficient)
        if order < size:
            b_previous = _matrix_add_identity(a_times_b, coefficient)
            adjugate_coefficients.append(b_previous)

    numerator = [d * coefficient for coefficient in denominator]
    for index, matrix in enumerate(adjugate_coefficients):
        numerator[index + 1] += _row_matrix_column(c, matrix, b)
    return tuple(numerator), tuple(denominator)


def canonicalize_state_space(
    state_space: LinearStateSpace,
    normalization: NormalizationContract,
) -> CanonicalLinearDynamics:
    if not isinstance(state_space, LinearStateSpace):
        raise EGCFError("canonicalize_state_space requires LinearStateSpace")
    a, a_exact, a_audit = _coerce_matrix(state_space.a, "A")
    size = len(a)
    if size < 1 or size > MAX_STATE_ORDER:
        raise EGCFError(f"SAA-3 state order must lie in [1, {MAX_STATE_ORDER}]")
    if any(len(row) != size for row in a):
        raise EGCFError("SAA-3 A matrix must be square")
    b, b_exact, b_audit = _coerce_vector(
        state_space.b, "B", size, allow_column=True, allow_row=False
    )
    c, c_exact, c_audit = _coerce_vector(
        state_space.c, "C", size, allow_column=False, allow_row=True
    )
    d, d_exact, d_source = _coerce_scalar(state_space.d, "D")

    sample_period: Fraction | None = None
    sample_period_exact = True
    sample_period_source: str | None = None
    if state_space.domain == "DISCRETE":
        if state_space.sample_period is None:
            raise EGCFError("discrete SAA-3 state space requires sample_period")
        sample_period, sample_period_exact, sample_period_source = _coerce_scalar(
            state_space.sample_period, "sample_period"
        )
    elif state_space.sample_period is not None:
        raise EGCFError("continuous SAA-3 state space must not declare sample_period")

    numerator, denominator = _state_space_transfer(a, b, c, d)
    return _canonicalize_fraction_transfer(
        domain=state_space.domain,
        numerator=numerator,
        denominator=denominator,
        coefficient_exact=a_exact and b_exact and c_exact and d_exact,
        sample_period=sample_period,
        sample_period_exact=sample_period_exact,
        normalization=normalization,
        source_kind="STATE_SPACE",
        source_audit={
            "domain": state_space.domain,
            "A": a_audit,
            "B": b_audit,
            "C": c_audit,
            "D": {
                "source": d_source,
                "inferred_strength": "EXACT" if d_exact else "APPROXIMATE",
            },
            "sample_period": sample_period_source,
        },
    )


def dynamic_algorithm_signature(
    structural_ir: CanonicalAlgorithmIR,
    normalization: NormalizationContract,
    dynamics: CanonicalLinearDynamics,
) -> str:
    if not isinstance(structural_ir, CanonicalAlgorithmIR):
        raise EGCFError("SAA-3 combined signature requires CanonicalAlgorithmIR")
    if not isinstance(normalization, NormalizationContract):
        raise EGCFError("SAA-3 combined signature requires NormalizationContract")
    if not isinstance(dynamics, CanonicalLinearDynamics):
        raise EGCFError("SAA-3 combined signature requires CanonicalLinearDynamics")
    if dynamics.normalization_signature != normalization.canonical_signature:
        raise EGCFError(
            "SAA-3 dynamics were canonicalized against a different normalization contract"
        )
    return sha256_json(
        {
            "schema_version": 1,
            "claim_scope": "STRUCTURE_PLUS_NORMALIZED_LINEAR_IO_DYNAMICS",
            "canonicalizer_version": structural_ir.canonicalizer_version,
            "structural_hash": structural_ir.structural_hash,
            "structural_strength": structural_ir.canonicalization_strength,
            "normalizer_version": normalization.normalizer_version,
            "normalization_signature": normalization.canonical_signature,
            "normalization_strength": normalization.normalization_strength,
            "dynamics_version": dynamics.dynamics_version,
            "dynamic_signature": dynamics.canonical_signature,
            "dynamic_strength": dynamics.dynamic_strength,
        }
    )
