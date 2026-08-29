from __future__ import annotations

import cmath
import itertools
import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import canonical_json, sha256_json
from .dynamics import (
    CanonicalLinearDynamics,
    LinearTransferFunction,
    _reduce_exact_transfer,
    canonicalize_transfer_function,
)
from .models import CanonicalAlgorithmIR
from .normalize import NormalizationBinding, NormalizationContract


MIMO_VERSION = "saa-mimo-coupling-v1"
MAX_MIMO_INPUTS = 6
MAX_MIMO_OUTPUTS = 6
MAX_PORT_PERMUTATIONS = 4096
DEFAULT_CONTINUOUS_FREQUENCIES = (0.1, 1.0, 10.0)
DEFAULT_DISCRETE_ANGLES = (
    math.pi / 4.0,
    math.pi / 2.0,
    3.0 * math.pi / 4.0,
)


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _polynomial_payload(values: Sequence[Fraction]) -> list[list[int]]:
    return [_fraction_payload(value) for value in values]


def _matrix_fraction_payload(
    matrix: Sequence[Sequence[Fraction]],
) -> list[list[list[int]]]:
    return [[_fraction_payload(value) for value in row] for row in matrix]


def _channel_payload(channel: CanonicalLinearDynamics) -> dict[str, Any]:
    return {
        "domain": channel.domain,
        "variable": channel.variable,
        "numerator": _polynomial_payload(channel.numerator),
        "denominator": _polynomial_payload(channel.denominator),
        "dynamic_order": channel.dynamic_order,
        "relative_degree": channel.relative_degree,
        "proper": channel.proper,
        "normalized_sample_interval": (
            _fraction_payload(channel.normalized_sample_interval)
            if channel.normalized_sample_interval is not None
            else None
        ),
        "dynamic_strength": channel.dynamic_strength,
    }


def _is_zero_channel(channel: CanonicalLinearDynamics) -> bool:
    return all(value == 0 for value in channel.numerator)


def _contract_strength(
    bindings: Sequence[NormalizationBinding],
    normalization: NormalizationContract,
) -> str:
    strengths = {binding.strength for binding in bindings}
    if normalization.time is not None:
        strengths.add(normalization.time.strength)
    if not strengths or strengths == {"EXACT"}:
        return "EXACT_NORMALIZATION"
    if strengths == {"APPROXIMATE"}:
        return "APPROXIMATE_NORMALIZATION"
    return "MIXED_NORMALIZATION"


def _local_binding(source: NormalizationBinding, role: str) -> NormalizationBinding:
    return NormalizationBinding(
        role=role,
        position=0,
        data_type=source.data_type,
        shape=source.shape,
        bound=source.bound,
    )


def _channel_normalization(
    normalization: NormalizationContract,
    input_binding: NormalizationBinding,
    output_binding: NormalizationBinding,
) -> NormalizationContract:
    local_input = _local_binding(input_binding, "INPUT")
    local_output = _local_binding(output_binding, "OUTPUT")
    bindings = (local_input, local_output)
    strength = _contract_strength(bindings, normalization)
    audit_payload = {
        "schema_version": 1,
        "normalizer_version": normalization.normalizer_version,
        "bindings": [item.audit_payload() for item in bindings],
        "time": normalization.time.audit_payload() if normalization.time is not None else None,
        "normalization_strength": strength,
        "source_contract_hash": normalization.contract_hash,
        "source_positions": {
            "input": input_binding.position,
            "output": output_binding.position,
        },
    }
    canonical_payload = {
        "schema_version": 1,
        "normalizer_version": normalization.normalizer_version,
        "bindings": [item.canonical_payload() for item in bindings],
        "time": (
            normalization.time.canonical_payload()
            if normalization.time is not None
            else None
        ),
        "normalization_strength": strength,
        "claim_scope": "LOCAL_SISO_VIEW_OF_MIMO_NORMALIZATION",
    }
    warnings = ()
    if strength != "EXACT_NORMALIZATION":
        warnings = (
            "local MIMO channel normalization includes approximate/observed bounds",
        )
    return NormalizationContract(
        schema_version=1,
        normalizer_version=normalization.normalizer_version,
        bindings=bindings,
        time=normalization.time,
        normalization_strength=strength,
        contract_hash=sha256_json(audit_payload),
        canonical_signature=sha256_json(canonical_payload),
        warnings=warnings,
    )


@dataclass(frozen=True)
class MIMOTransferMatrix:
    domain: str
    channels: Tuple[Tuple[LinearTransferFunction, ...], ...]
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        rows = tuple(tuple(row) for row in self.channels)
        if not rows or not rows[0]:
            raise EGCFError("SAA-4 MIMO transfer matrix must be non-empty")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise EGCFError("SAA-4 MIMO transfer matrix must be rectangular")
        if len(rows) > MAX_MIMO_OUTPUTS or width > MAX_MIMO_INPUTS:
            raise EGCFError(
                f"SAA-4 MIMO dimensions exceed {MAX_MIMO_OUTPUTS} outputs x "
                f"{MAX_MIMO_INPUTS} inputs"
            )
        domain = str(self.domain).strip().upper()
        aliases = {
            "S": "CONTINUOUS",
            "S_DOMAIN": "CONTINUOUS",
            "CONTINUOUS_TIME": "CONTINUOUS",
            "Z": "DISCRETE",
            "Z_DOMAIN": "DISCRETE",
            "DISCRETE_TIME": "DISCRETE",
        }
        domain = aliases.get(domain, domain)
        if domain not in {"CONTINUOUS", "DISCRETE"}:
            raise EGCFError(f"unsupported SAA-4 MIMO domain: {self.domain!r}")
        for row in rows:
            for channel in row:
                if not isinstance(channel, LinearTransferFunction):
                    raise EGCFError(
                        "SAA-4 channels must be LinearTransferFunction values"
                    )
                if channel.domain != domain:
                    raise EGCFError(
                        "all SAA-4 channels must share the matrix domain"
                    )
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "channels", rows)


@dataclass(frozen=True)
class RationalChannel:
    numerator: Tuple[Fraction, ...]
    denominator: Tuple[Fraction, ...]

    @property
    def zero(self) -> bool:
        return all(value == 0 for value in self.numerator)

    def payload(self) -> dict[str, Any]:
        return {
            "numerator": _polynomial_payload(self.numerator),
            "denominator": _polynomial_payload(self.denominator),
        }


@dataclass(frozen=True)
class StaticDecouplingResult:
    decoupler: Tuple[Tuple[Fraction, ...], ...]
    decoupled_channels: Tuple[Tuple[RationalChannel, ...], ...]
    canonical_signature: str
    residual_coupling_samples: Tuple[Tuple[float, float], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decoupler": _matrix_fraction_payload(self.decoupler),
            "decoupled_channels": [
                [channel.payload() for channel in row]
                for row in self.decoupled_channels
            ],
            "canonical_signature": self.canonical_signature,
            "residual_coupling_samples": [
                [frequency, ratio]
                for frequency, ratio in self.residual_coupling_samples
            ],
        }


@dataclass(frozen=True)
class CanonicalMIMOCoupling:
    schema_version: int
    mimo_version: str
    domain: str
    variable: str
    output_count: int
    input_count: int
    channels: Tuple[Tuple[CanonicalLinearDynamics, ...], ...]
    dynamic_strength: str
    coupling_strength: str
    normalized_sample_interval: Fraction | None
    ordered_signature: str
    permutation_invariant_signature: str | None
    permutation_strength: str
    canonical_output_permutation: Tuple[int, ...] | None
    canonical_input_permutation: Tuple[int, ...] | None
    nonzero_pattern: Tuple[Tuple[bool, ...], ...]
    permutation_decoupled: bool
    exact_diagonal_input_permutation: Tuple[int, ...] | None
    steady_gain: Tuple[Tuple[Fraction | None, ...], ...]
    relative_gain_array: Tuple[Tuple[Fraction, ...], ...] | None
    preferred_rga_pairing: Tuple[int, ...] | None
    rga_off_pairing_mass: Fraction | None
    static_decoupling: StaticDecouplingResult | None
    audit_hash: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mimo_version": self.mimo_version,
            "domain": self.domain,
            "variable": self.variable,
            "output_count": self.output_count,
            "input_count": self.input_count,
            "channels": [
                [_channel_payload(channel) for channel in row]
                for row in self.channels
            ],
            "dynamic_strength": self.dynamic_strength,
            "coupling_strength": self.coupling_strength,
            "normalized_sample_interval": (
                _fraction_payload(self.normalized_sample_interval)
                if self.normalized_sample_interval is not None
                else None
            ),
            "ordered_signature": self.ordered_signature,
            "permutation_invariant_signature": self.permutation_invariant_signature,
            "permutation_strength": self.permutation_strength,
            "canonical_output_permutation": (
                list(self.canonical_output_permutation)
                if self.canonical_output_permutation is not None
                else None
            ),
            "canonical_input_permutation": (
                list(self.canonical_input_permutation)
                if self.canonical_input_permutation is not None
                else None
            ),
            "nonzero_pattern": [list(row) for row in self.nonzero_pattern],
            "permutation_decoupled": self.permutation_decoupled,
            "exact_diagonal_input_permutation": (
                list(self.exact_diagonal_input_permutation)
                if self.exact_diagonal_input_permutation is not None
                else None
            ),
            "steady_gain": [
                [
                    (_fraction_payload(value) if value is not None else None)
                    for value in row
                ]
                for row in self.steady_gain
            ],
            "relative_gain_array": (
                _matrix_fraction_payload(self.relative_gain_array)
                if self.relative_gain_array is not None
                else None
            ),
            "preferred_rga_pairing": (
                list(self.preferred_rga_pairing)
                if self.preferred_rga_pairing is not None
                else None
            ),
            "rga_off_pairing_mass": (
                _fraction_payload(self.rga_off_pairing_mass)
                if self.rga_off_pairing_mass is not None
                else None
            ),
            "static_decoupling": (
                self.static_decoupling.to_dict()
                if self.static_decoupling is not None
                else None
            ),
            "audit_hash": self.audit_hash,
            "warnings": list(self.warnings),
        }


def _validate_normalization(
    normalization: NormalizationContract,
    *,
    outputs: int,
    inputs: int,
) -> tuple[list[NormalizationBinding], list[NormalizationBinding]]:
    if not isinstance(normalization, NormalizationContract):
        raise EGCFError("SAA-4 requires a NormalizationContract from SAA-2")
    input_bindings = sorted(
        (
            binding
            for binding in normalization.bindings
            if binding.role == "INPUT"
        ),
        key=lambda binding: binding.position,
    )
    output_bindings = sorted(
        (
            binding
            for binding in normalization.bindings
            if binding.role == "OUTPUT"
        ),
        key=lambda binding: binding.position,
    )
    if len(input_bindings) != inputs or len(output_bindings) != outputs:
        raise EGCFError(
            "SAA-4 normalization input/output counts must match transfer-matrix dimensions"
        )
    if normalization.time is None:
        raise EGCFError("SAA-4 requires SAA-2 characteristic time")
    for binding in input_bindings + output_bindings:
        if binding.canonical_data_type != "CONTINUOUS_SCALAR":
            raise EGCFError(
                "SAA-4 v1 requires continuous scalar input/output coordinates"
            )
        if binding.shape:
            raise EGCFError(
                "SAA-4 v1 does not support shaped input/output coordinates"
            )
    return input_bindings, output_bindings


def _matrix_payload(
    channels: Sequence[Sequence[CanonicalLinearDynamics]],
    output_permutation: Sequence[int],
    input_permutation: Sequence[int],
) -> list[list[dict[str, Any]]]:
    return [
        [
            _channel_payload(channels[output_index][input_index])
            for input_index in input_permutation
        ]
        for output_index in output_permutation
    ]


def _permutation_count(outputs: int, inputs: int) -> int:
    return math.factorial(outputs) * math.factorial(inputs)


def _canonical_permutation(
    channels: Sequence[Sequence[CanonicalLinearDynamics]],
    *,
    domain: str,
    variable: str,
    normalized_sample_interval: Fraction | None,
    dynamic_strength: str,
    max_permutations: int,
) -> tuple[
    str | None,
    str,
    Tuple[int, ...] | None,
    Tuple[int, ...] | None,
    int,
]:
    outputs = len(channels)
    inputs = len(channels[0])
    count = _permutation_count(outputs, inputs)
    if count > max_permutations:
        return (
            None,
            "ORDERED_ONLY_PERMUTATION_BUDGET_EXCEEDED",
            None,
            None,
            0,
        )

    best_key: str | None = None
    best_payload: dict[str, Any] | None = None
    best_output: Tuple[int, ...] | None = None
    best_input: Tuple[int, ...] | None = None
    considered = 0
    for output_perm in itertools.permutations(range(outputs)):
        for input_perm in itertools.permutations(range(inputs)):
            payload = {
                "schema_version": 1,
                "mimo_version": MIMO_VERSION,
                "claim_scope": (
                    "NORMALIZED_MIMO_LINEAR_IO_DYNAMICS_UP_TO_PORT_PERMUTATION"
                ),
                "domain": domain,
                "variable": variable,
                "outputs": outputs,
                "inputs": inputs,
                "normalized_sample_interval": (
                    _fraction_payload(normalized_sample_interval)
                    if normalized_sample_interval is not None
                    else None
                ),
                "dynamic_strength": dynamic_strength,
                "matrix": _matrix_payload(
                    channels, output_perm, input_perm
                ),
            }
            key = canonical_json(payload)
            considered += 1
            if best_key is None or key < best_key:
                best_key = key
                best_payload = payload
                best_output = tuple(output_perm)
                best_input = tuple(input_perm)
    if best_payload is None:
        raise EGCFError("internal SAA-4 canonical permutation search failed")
    return (
        sha256_json(best_payload),
        "EXACT_PORT_PERMUTATION",
        best_output,
        best_input,
        considered,
    )


def _steady_gain(channel: CanonicalLinearDynamics) -> Fraction | None:
    if _is_zero_channel(channel):
        return Fraction(0)
    if channel.domain == "CONTINUOUS":
        numerator = channel.numerator[-1]
        denominator = channel.denominator[-1]
    else:
        numerator = sum(channel.numerator, Fraction(0))
        denominator = sum(channel.denominator, Fraction(0))
    if denominator == 0:
        return None
    return numerator / denominator


def _matrix_inverse(
    matrix: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[Fraction, ...], ...] | None:
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        return None
    work = [
        list(row)
        + [
            Fraction(1 if row_index == column else 0)
            for column in range(size)
        ]
        for row_index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = next(
            (
                row
                for row in range(column, size)
                if work[row][column] != 0
            ),
            None,
        )
        if pivot is None:
            return None
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
        pivot_value = work[column][column]
        work[column] = [value / pivot_value for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            if factor == 0:
                continue
            work[row] = [
                left - factor * right
                for left, right in zip(work[row], work[column])
            ]
    return tuple(tuple(row[size:]) for row in work)


def _relative_gain_array(
    steady_gain: Sequence[Sequence[Fraction | None]],
) -> tuple[
    Tuple[Tuple[Fraction, ...], ...] | None,
    Tuple[Tuple[Fraction, ...], ...] | None,
]:
    size = len(steady_gain)
    if size == 0 or any(len(row) != size for row in steady_gain):
        return None, None
    if any(value is None for row in steady_gain for value in row):
        return None, None
    matrix = tuple(
        tuple(value for value in row if value is not None)
        for row in steady_gain
    )
    inverse = _matrix_inverse(matrix)
    if inverse is None:
        return None, None
    rga = tuple(
        tuple(
            matrix[row][column] * inverse[column][row]
            for column in range(size)
        )
        for row in range(size)
    )
    return rga, inverse


def _preferred_pairing(
    rga: Sequence[Sequence[Fraction]],
) -> tuple[Tuple[int, ...], Fraction]:
    size = len(rga)
    best: Tuple[int, ...] | None = None
    best_score: Fraction | None = None
    for permutation in itertools.permutations(range(size)):
        score = sum(
            (abs(rga[row][permutation[row]]) for row in range(size)),
            Fraction(0),
        )
        if (
            best_score is None
            or score > best_score
            or (
                score == best_score
                and best is not None
                and tuple(permutation) < best
            )
        ):
            best = tuple(permutation)
            best_score = score
    if best is None or best_score is None:
        raise EGCFError("internal SAA-4 RGA pairing search failed")
    total = sum(
        (abs(value) for row in rga for value in row),
        Fraction(0),
    )
    off = sum(
        (
            abs(rga[row][column])
            for row in range(size)
            for column in range(size)
            if column != best[row]
        ),
        Fraction(0),
    )
    mass = Fraction(0) if total == 0 else off / total
    return best, mass


def _exact_diagonal_permutation(
    channels: Sequence[Sequence[CanonicalLinearDynamics]],
) -> Tuple[int, ...] | None:
    size = len(channels)
    if size == 0 or any(len(row) != size for row in channels):
        return None
    for permutation in itertools.permutations(range(size)):
        if all(
            _is_zero_channel(channels[row][column])
            for row in range(size)
            for column in range(size)
            if column != permutation[row]
        ):
            return tuple(permutation)
    return None


def _poly_add_desc(
    first: Sequence[Fraction],
    second: Sequence[Fraction],
) -> Tuple[Fraction, ...]:
    size = max(len(first), len(second))
    left = [Fraction(0)] * (size - len(first)) + list(first)
    right = [Fraction(0)] * (size - len(second)) + list(second)
    result = tuple(a + b for a, b in zip(left, right))
    index = 0
    while index < len(result) - 1 and result[index] == 0:
        index += 1
    return tuple(result[index:])


def _poly_mul_desc(
    first: Sequence[Fraction],
    second: Sequence[Fraction],
) -> Tuple[Fraction, ...]:
    result = [Fraction(0)] * (len(first) + len(second) - 1)
    for i, left in enumerate(first):
        for j, right in enumerate(second):
            result[i + j] += left * right
    index = 0
    while index < len(result) - 1 and result[index] == 0:
        index += 1
    return tuple(result[index:])


def _rational_scaled(
    channel: RationalChannel,
    scalar: Fraction,
) -> RationalChannel:
    if scalar == 0 or channel.zero:
        return RationalChannel((Fraction(0),), (Fraction(1),))
    numerator = tuple(value * scalar for value in channel.numerator)
    numerator, denominator, _ = _reduce_exact_transfer(
        numerator, channel.denominator
    )
    return RationalChannel(tuple(numerator), tuple(denominator))


def _rational_add(
    first: RationalChannel,
    second: RationalChannel,
) -> RationalChannel:
    if first.zero:
        return second
    if second.zero:
        return first
    numerator = _poly_add_desc(
        _poly_mul_desc(first.numerator, second.denominator),
        _poly_mul_desc(second.numerator, first.denominator),
    )
    denominator = _poly_mul_desc(
        first.denominator, second.denominator
    )
    numerator, denominator, _ = _reduce_exact_transfer(
        numerator, denominator
    )
    return RationalChannel(tuple(numerator), tuple(denominator))


def _to_rational(channel: CanonicalLinearDynamics) -> RationalChannel:
    return RationalChannel(
        tuple(channel.numerator), tuple(channel.denominator)
    )


def _apply_static_decoupler(
    channels: Sequence[Sequence[CanonicalLinearDynamics]],
    decoupler: Sequence[Sequence[Fraction]],
) -> Tuple[Tuple[RationalChannel, ...], ...]:
    outputs = len(channels)
    inputs = len(channels[0])
    if inputs != len(decoupler) or any(
        len(row) != inputs for row in decoupler
    ):
        raise EGCFError("internal SAA-4 decoupler dimension mismatch")
    result: list[tuple[RationalChannel, ...]] = []
    for output in range(outputs):
        row: list[RationalChannel] = []
        for virtual_input in range(inputs):
            accumulated = RationalChannel(
                (Fraction(0),), (Fraction(1),)
            )
            for physical_input in range(inputs):
                term = _rational_scaled(
                    _to_rational(channels[output][physical_input]),
                    decoupler[physical_input][virtual_input],
                )
                accumulated = _rational_add(accumulated, term)
            row.append(accumulated)
        result.append(tuple(row))
    return tuple(result)


def _evaluate_rational(
    channel: RationalChannel,
    q: complex,
) -> complex | None:
    numerator = complex(0.0, 0.0)
    denominator = complex(0.0, 0.0)
    for coefficient in channel.numerator:
        numerator = numerator * q + float(coefficient)
    for coefficient in channel.denominator:
        denominator = denominator * q + float(coefficient)
    if abs(denominator) <= 1e-14:
        return None
    return numerator / denominator


def _coupling_energy_ratio(
    channels: Sequence[Sequence[RationalChannel]],
    q: complex,
) -> float:
    outputs = len(channels)
    inputs = len(channels[0])
    if outputs != inputs:
        return math.nan
    total = 0.0
    off = 0.0
    for row in range(outputs):
        for column in range(inputs):
            value = _evaluate_rational(channels[row][column], q)
            if value is None:
                return math.nan
            energy = abs(value) ** 2
            total += energy
            if row != column:
                off += energy
    if total == 0.0:
        return 0.0
    return off / total


def _residual_samples(
    domain: str,
    channels: Sequence[Sequence[RationalChannel]],
) -> Tuple[Tuple[float, float], ...]:
    if len(channels) != len(channels[0]):
        return ()
    result: list[tuple[float, float]] = []
    if domain == "CONTINUOUS":
        for frequency in DEFAULT_CONTINUOUS_FREQUENCIES:
            ratio = _coupling_energy_ratio(
                channels, complex(0.0, frequency)
            )
            result.append((frequency, ratio))
    else:
        for angle in DEFAULT_DISCRETE_ANGLES:
            ratio = _coupling_energy_ratio(
                channels, cmath.exp(complex(0.0, angle))
            )
            result.append((angle, ratio))
    return tuple(result)


def _static_decoupling(
    channels: Sequence[Sequence[CanonicalLinearDynamics]],
    inverse_steady_gain: Sequence[Sequence[Fraction]] | None,
    *,
    exact: bool,
    domain: str,
) -> StaticDecouplingResult | None:
    if not exact or inverse_steady_gain is None:
        return None
    decoupler = tuple(
        tuple(value for value in row)
        for row in inverse_steady_gain
    )
    transformed = _apply_static_decoupler(channels, decoupler)
    payload = {
        "schema_version": 1,
        "mimo_version": MIMO_VERSION,
        "claim_scope": (
            "EXACT_DC_STATIC_DECOUPLING_IN_NORMALIZED_DEVIATION_COORDINATES"
        ),
        "decoupler": _matrix_fraction_payload(decoupler),
        "decoupled_channels": [
            [channel.payload() for channel in row]
            for row in transformed
        ],
    }
    return StaticDecouplingResult(
        decoupler=decoupler,
        decoupled_channels=transformed,
        canonical_signature=sha256_json(payload),
        residual_coupling_samples=_residual_samples(domain, transformed),
    )


def canonicalize_mimo_transfer_matrix(
    transfer_matrix: MIMOTransferMatrix,
    normalization: NormalizationContract,
    *,
    max_port_permutations: int = MAX_PORT_PERMUTATIONS,
) -> CanonicalMIMOCoupling:
    if not isinstance(transfer_matrix, MIMOTransferMatrix):
        raise EGCFError(
            "canonicalize_mimo_transfer_matrix requires MIMOTransferMatrix"
        )
    outputs = len(transfer_matrix.channels)
    inputs = len(transfer_matrix.channels[0])
    if max_port_permutations < 1:
        raise EGCFError("max_port_permutations must be positive")
    input_bindings, output_bindings = _validate_normalization(
        normalization, outputs=outputs, inputs=inputs
    )

    canonical_rows: list[tuple[CanonicalLinearDynamics, ...]] = []
    for output_index, row in enumerate(transfer_matrix.channels):
        canonical_row: list[CanonicalLinearDynamics] = []
        for input_index, channel in enumerate(row):
            local_normalization = _channel_normalization(
                normalization,
                input_bindings[input_index],
                output_bindings[output_index],
            )
            canonical_row.append(
                canonicalize_transfer_function(
                    channel, local_normalization
                )
            )
        canonical_rows.append(tuple(canonical_row))
    channels = tuple(canonical_rows)

    domains = {
        channel.domain for row in channels for channel in row
    }
    if domains != {transfer_matrix.domain}:
        raise EGCFError(
            "SAA-4 channel domains are inconsistent after canonicalization"
        )
    sample_intervals = {
        channel.normalized_sample_interval
        for row in channels
        for channel in row
    }
    if len(sample_intervals) != 1:
        raise EGCFError(
            "all SAA-4 channels must share one normalized discrete sample interval"
        )
    normalized_sample_interval = next(iter(sample_intervals))
    variable = channels[0][0].variable

    exact = all(
        channel.dynamic_strength == "EXACT_LINEAR_DYNAMICS"
        for row in channels
        for channel in row
    )
    dynamic_strength = (
        "EXACT_MIMO_LINEAR_DYNAMICS"
        if exact
        else "APPROXIMATE_MIMO_LINEAR_DYNAMICS"
    )
    coupling_strength = (
        "EXACT_COUPLING_ANALYSIS"
        if exact
        else "APPROXIMATE_COUPLING_ANALYSIS"
    )
    warnings: list[str] = []
    if not exact:
        warnings.append(
            "one or more SAA-4 channels are approximate; equality of matrix "
            "signatures does not prove exact MIMO equivalence"
        )

    ordered_payload = {
        "schema_version": 1,
        "mimo_version": MIMO_VERSION,
        "claim_scope": (
            "NORMALIZED_ORDERED_MIMO_LINEAR_INPUT_OUTPUT_DYNAMICS"
        ),
        "domain": transfer_matrix.domain,
        "variable": variable,
        "outputs": outputs,
        "inputs": inputs,
        "normalized_sample_interval": (
            _fraction_payload(normalized_sample_interval)
            if normalized_sample_interval is not None
            else None
        ),
        "dynamic_strength": dynamic_strength,
        "matrix": _matrix_payload(
            channels, range(outputs), range(inputs)
        ),
    }
    ordered_signature = sha256_json(ordered_payload)

    (
        permutation_signature,
        permutation_strength,
        output_permutation,
        input_permutation,
        permutations_considered,
    ) = _canonical_permutation(
        channels,
        domain=transfer_matrix.domain,
        variable=variable,
        normalized_sample_interval=normalized_sample_interval,
        dynamic_strength=dynamic_strength,
        max_permutations=max_port_permutations,
    )
    if permutation_signature is None:
        warnings.append(
            "port permutation search exceeded the configured bound; no "
            "permutation-invariant equivalence signature was asserted"
        )

    nonzero_pattern = tuple(
        tuple(not _is_zero_channel(channel) for channel in row)
        for row in channels
    )
    diagonal_input_permutation = _exact_diagonal_permutation(channels)
    permutation_decoupled = diagonal_input_permutation is not None

    steady_gain = tuple(
        tuple(_steady_gain(channel) for channel in row)
        for row in channels
    )
    rga, inverse_steady_gain = _relative_gain_array(steady_gain)
    preferred_pairing = None
    rga_mass = None
    if rga is not None:
        preferred_pairing, rga_mass = _preferred_pairing(rga)
    elif outputs == inputs:
        warnings.append(
            "steady-state RGA unavailable because the normalized steady-gain "
            "matrix is singular or contains a pole at the evaluation point"
        )

    static_decoupling = _static_decoupling(
        channels,
        inverse_steady_gain,
        exact=exact,
        domain=transfer_matrix.domain,
    )
    if static_decoupling is not None:
        warnings.append(
            "static decoupler is a normalized deviation-coordinate transform "
            "that diagonalizes steady-state gain only; it is not a physical "
            "actuator map and does not imply dynamic decoupling at other frequencies"
        )

    audit_payload = {
        "schema_version": 1,
        "mimo_version": MIMO_VERSION,
        "source_metadata": dict(transfer_matrix.metadata),
        "normalization_contract_hash": normalization.contract_hash,
        "normalization_signature": normalization.canonical_signature,
        "ordered_signature": ordered_signature,
        "permutation_signature": permutation_signature,
        "permutation_strength": permutation_strength,
        "permutations_considered": permutations_considered,
    }

    return CanonicalMIMOCoupling(
        schema_version=1,
        mimo_version=MIMO_VERSION,
        domain=transfer_matrix.domain,
        variable=variable,
        output_count=outputs,
        input_count=inputs,
        channels=channels,
        dynamic_strength=dynamic_strength,
        coupling_strength=coupling_strength,
        normalized_sample_interval=normalized_sample_interval,
        ordered_signature=ordered_signature,
        permutation_invariant_signature=permutation_signature,
        permutation_strength=permutation_strength,
        canonical_output_permutation=output_permutation,
        canonical_input_permutation=input_permutation,
        nonzero_pattern=nonzero_pattern,
        permutation_decoupled=permutation_decoupled,
        exact_diagonal_input_permutation=diagonal_input_permutation,
        steady_gain=steady_gain,
        relative_gain_array=rga,
        preferred_rga_pairing=preferred_pairing,
        rga_off_pairing_mass=rga_mass,
        static_decoupling=static_decoupling,
        audit_hash=sha256_json(audit_payload),
        warnings=tuple(warnings),
    )


def mimo_algorithm_signature(
    structural_ir: CanonicalAlgorithmIR,
    normalization: NormalizationContract,
    mimo: CanonicalMIMOCoupling,
    *,
    ignore_port_order: bool = False,
) -> str:
    if not isinstance(structural_ir, CanonicalAlgorithmIR):
        raise EGCFError(
            "mimo_algorithm_signature requires CanonicalAlgorithmIR"
        )
    if not isinstance(normalization, NormalizationContract):
        raise EGCFError(
            "mimo_algorithm_signature requires NormalizationContract"
        )
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError(
            "mimo_algorithm_signature requires CanonicalMIMOCoupling"
        )
    if ignore_port_order:
        if mimo.permutation_invariant_signature is None:
            raise EGCFError(
                "SAA-4 permutation-invariant signature is unavailable under "
                "the current budget"
            )
        dynamic_signature = mimo.permutation_invariant_signature
        claim_scope = (
            "STRUCTURE_PLUS_NORMALIZED_MIMO_DYNAMICS_UP_TO_PORT_PERMUTATION"
        )
    else:
        dynamic_signature = mimo.ordered_signature
        claim_scope = "STRUCTURE_PLUS_NORMALIZED_ORDERED_MIMO_DYNAMICS"
    return sha256_json(
        {
            "schema_version": 1,
            "mimo_version": mimo.mimo_version,
            "claim_scope": claim_scope,
            "structural_hash": structural_ir.structural_hash,
            "structural_strength": structural_ir.canonicalization_strength,
            "normalization_signature": normalization.canonical_signature,
            "normalization_strength": normalization.normalization_strength,
            "mimo_dynamic_signature": dynamic_signature,
            "mimo_dynamic_strength": mimo.dynamic_strength,
        }
    )
