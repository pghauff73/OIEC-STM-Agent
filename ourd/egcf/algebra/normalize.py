from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .graph import validate_structure
from .models import AlgorithmStructureSpec, CanonicalAlgorithmIR


NORMALIZER_VERSION = "saa-normalization-v1"
BOUND_KINDS = {
    "EXACT_BOUND",
    "DOMAIN_BOUND",
    "ENGINEERING_BOUND",
    "OBSERVED_BOUND",
    "APPROXIMATE_BOUND",
}
EXACT_BOUND_KINDS = {"EXACT_BOUND", "DOMAIN_BOUND"}
NUMERIC_DATA_TYPE_CLASSES = {
    "scalar": "CONTINUOUS_SCALAR",
    "number": "CONTINUOUS_SCALAR",
    "float": "CONTINUOUS_SCALAR",
    "real": "CONTINUOUS_SCALAR",
    "int": "INTEGER_SCALAR",
    "integer": "INTEGER_SCALAR",
}
ROLE_ORDER = {"INPUT": 0, "PARAMETER": 1, "STATE": 2, "OUTPUT": 3}


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise EGCFError(f"{label} must be finite")
    if number == 0.0:
        number = 0.0
    return number


def _provenance_items(
    values: Mapping[str, Any] | Iterable[tuple[str, Any]] = (),
) -> Tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized = []
    for key, value in items:
        name = str(key).strip()
        if not name:
            raise EGCFError("normalization provenance keys must be non-empty")
        normalized.append((name, str(value)))
    return tuple(sorted(normalized))


def _strength_for_kind(kind: str) -> str:
    return "EXACT" if kind in EXACT_BOUND_KINDS else "APPROXIMATE"


@dataclass(frozen=True)
class NumericBound:
    minimum: float
    maximum: float
    kind: str = "EXACT_BOUND"
    unit: str = ""
    provenance: Tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        minimum = _finite(self.minimum, "normalization minimum")
        maximum = _finite(self.maximum, "normalization maximum")
        kind = str(self.kind).strip().upper()
        if kind not in BOUND_KINDS:
            raise EGCFError(f"unsupported normalization bound kind: {self.kind!r}")
        if maximum <= minimum:
            raise EGCFError("normalization maximum must be greater than minimum")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "unit", str(self.unit).strip())
        object.__setattr__(self, "provenance", _provenance_items(self.provenance))

    @property
    def width(self) -> float:
        return self.maximum - self.minimum

    @property
    def strength(self) -> str:
        return _strength_for_kind(self.kind)

    def audit_payload(self) -> dict[str, Any]:
        return {
            "minimum": self.minimum,
            "maximum": self.maximum,
            "kind": self.kind,
            "unit": self.unit,
            "provenance": [list(item) for item in self.provenance],
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "target": [0.0, 1.0],
            "transform": "AFFINE_REVERSIBLE",
            "strength": self.strength,
        }


@dataclass(frozen=True)
class NormalizationBinding:
    role: str
    position: int
    data_type: str
    shape: Tuple[int, ...]
    bound: NumericBound

    def __post_init__(self) -> None:
        role = str(self.role).strip().upper()
        if role not in ROLE_ORDER:
            raise EGCFError(f"unsupported normalization role: {self.role!r}")
        if int(self.position) < 0:
            raise EGCFError("normalization binding position cannot be negative")
        data_type = str(self.data_type).strip().lower()
        shape = tuple(int(value) for value in self.shape)
        if data_type not in NUMERIC_DATA_TYPE_CLASSES:
            raise EGCFError(
                f"SAA-2 supports scalar numeric coordinates only, not {self.data_type!r}"
            )
        if shape:
            raise EGCFError("SAA-2 scalar normalization does not yet support shaped/vector ports")
        if not isinstance(self.bound, NumericBound):
            raise EGCFError("normalization binding requires a NumericBound")
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "position", int(self.position))
        object.__setattr__(self, "data_type", data_type)
        object.__setattr__(self, "shape", shape)

    @property
    def canonical_data_type(self) -> str:
        return NUMERIC_DATA_TYPE_CLASSES[self.data_type]

    @property
    def strength(self) -> str:
        return self.bound.strength

    def audit_payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "position": self.position,
            "source_data_type": self.data_type,
            "canonical_data_type": self.canonical_data_type,
            "shape": list(self.shape),
            "bound": self.bound.audit_payload(),
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "position": self.position,
            "data_type": self.canonical_data_type,
            "shape": list(self.shape),
            "normalization": self.bound.canonical_payload(),
        }


@dataclass(frozen=True)
class TimeNormalization:
    characteristic_time: float
    kind: str = "EXACT_BOUND"
    unit: str = ""
    provenance: Tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        characteristic_time = _finite(
            self.characteristic_time, "normalization characteristic_time"
        )
        if characteristic_time <= 0.0:
            raise EGCFError("normalization characteristic_time must be positive")
        kind = str(self.kind).strip().upper()
        if kind not in BOUND_KINDS:
            raise EGCFError(f"unsupported time normalization kind: {self.kind!r}")
        object.__setattr__(self, "characteristic_time", characteristic_time)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "unit", str(self.unit).strip())
        object.__setattr__(self, "provenance", _provenance_items(self.provenance))

    @property
    def strength(self) -> str:
        return _strength_for_kind(self.kind)

    def audit_payload(self) -> dict[str, Any]:
        return {
            "characteristic_time": self.characteristic_time,
            "kind": self.kind,
            "unit": self.unit,
            "provenance": [list(item) for item in self.provenance],
            "transform": "TAU_EQUALS_T_OVER_TC",
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "dimensionless_time": True,
            "transform": "TAU_EQUALS_T_OVER_TC",
            "strength": self.strength,
        }


@dataclass(frozen=True)
class NormalizationContract:
    schema_version: int
    normalizer_version: str
    bindings: Tuple[NormalizationBinding, ...]
    time: TimeNormalization | None
    normalization_strength: str
    contract_hash: str
    canonical_signature: str
    warnings: Tuple[str, ...] = ()

    def binding(self, role: str, position: int) -> NormalizationBinding:
        role = str(role).strip().upper()
        if role not in ROLE_ORDER:
            raise EGCFError(f"unsupported normalization role: {role!r}")
        for item in self.bindings:
            if item.role == role and item.position == int(position):
                return item
        raise EGCFError(f"normalization contract has no {role} position {position}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "normalizer_version": self.normalizer_version,
            "bindings": [item.audit_payload() for item in self.bindings],
            "time": self.time.audit_payload() if self.time is not None else None,
            "normalization_strength": self.normalization_strength,
            "contract_hash": self.contract_hash,
            "canonical_signature": self.canonical_signature,
            "warnings": list(self.warnings),
        }


def numeric_bound(value: NumericBound | Mapping[str, Any] | Sequence[Any]) -> NumericBound:
    if isinstance(value, NumericBound):
        return value
    if isinstance(value, Mapping):
        unknown = sorted(
            set(value) - {"minimum", "maximum", "kind", "unit", "provenance"}
        )
        if unknown:
            raise EGCFError(f"unknown normalization bound fields: {unknown}")
        if "minimum" not in value or "maximum" not in value:
            raise EGCFError("normalization bound requires minimum and maximum")
        return NumericBound(
            minimum=value["minimum"],
            maximum=value["maximum"],
            kind=value.get("kind", "EXACT_BOUND"),
            unit=value.get("unit", ""),
            provenance=_provenance_items(value.get("provenance", {})),
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) != 2:
            raise EGCFError("normalization bound sequence must contain [minimum, maximum]")
        return NumericBound(value[0], value[1])
    raise EGCFError("normalization bound must be NumericBound, mapping, or [minimum, maximum]")


def time_normalization(
    value: TimeNormalization | Mapping[str, Any] | float | int | None,
) -> TimeNormalization | None:
    if value is None:
        return None
    if isinstance(value, TimeNormalization):
        return value
    if isinstance(value, Mapping):
        unknown = sorted(
            set(value) - {"characteristic_time", "kind", "unit", "provenance"}
        )
        if unknown:
            raise EGCFError(f"unknown time normalization fields: {unknown}")
        if "characteristic_time" not in value:
            raise EGCFError("time normalization requires characteristic_time")
        return TimeNormalization(
            characteristic_time=value["characteristic_time"],
            kind=value.get("kind", "EXACT_BOUND"),
            unit=value.get("unit", ""),
            provenance=_provenance_items(value.get("provenance", {})),
        )
    return TimeNormalization(float(value))


def normalize_value(bound: NumericBound, value: float) -> float:
    observed = _finite(value, "normalization source value")
    if observed < bound.minimum or observed > bound.maximum:
        raise EGCFError(
            f"source value {observed!r} lies outside [{bound.minimum}, {bound.maximum}]"
        )
    if observed == bound.minimum:
        return 0.0
    if observed == bound.maximum:
        return 1.0
    return (observed - bound.minimum) / bound.width


def denormalize_value(bound: NumericBound, value: float) -> float:
    normalized = _finite(value, "normalized value")
    if normalized < 0.0 or normalized > 1.0:
        raise EGCFError("normalized value must lie in [0, 1]")
    if normalized == 0.0:
        return bound.minimum
    if normalized == 1.0:
        return bound.maximum
    return bound.minimum + normalized * bound.width


def normalize_time(contract: TimeNormalization, value: float) -> float:
    observed = _finite(value, "time value")
    return observed / contract.characteristic_time


def denormalize_time(contract: TimeNormalization, value: float) -> float:
    normalized = _finite(value, "dimensionless time value")
    return normalized * contract.characteristic_time


def _coerce_bound_map(
    values: Mapping[int, NumericBound | Mapping[str, Any] | Sequence[Any]] | None,
) -> dict[int, NumericBound]:
    result: dict[int, NumericBound] = {}
    for raw_position, value in (values or {}).items():
        try:
            position = int(raw_position)
        except (TypeError, ValueError) as exc:
            raise EGCFError(f"invalid normalization position: {raw_position!r}") from exc
        if position < 0:
            raise EGCFError("normalization positions cannot be negative")
        if position in result:
            raise EGCFError(f"duplicate normalization position: {position}")
        result[position] = numeric_bound(value)
    return result


def _build_role_bindings(
    *,
    role: str,
    specs: Sequence[Any],
    bounds: Mapping[int, NumericBound],
) -> list[NormalizationBinding]:
    expected = {int(item.position) for item in specs}
    extra = sorted(set(bounds) - expected)
    missing = sorted(expected - set(bounds))
    if extra:
        raise EGCFError(f"normalization contains unknown {role} positions: {extra}")
    if missing:
        raise EGCFError(f"normalization is missing {role} positions: {missing}")
    return [
        NormalizationBinding(
            role=role,
            position=int(item.position),
            data_type=str(item.data_type),
            shape=tuple(item.shape),
            bound=bounds[int(item.position)],
        )
        for item in sorted(specs, key=lambda item: item.position)
    ]


def _contract_strength(
    bindings: Sequence[NormalizationBinding],
    time: TimeNormalization | None,
) -> str:
    strengths = {item.strength for item in bindings}
    if time is not None:
        strengths.add(time.strength)
    if not strengths or strengths == {"EXACT"}:
        return "EXACT_NORMALIZATION"
    if strengths == {"APPROXIMATE"}:
        return "APPROXIMATE_NORMALIZATION"
    return "MIXED_NORMALIZATION"


def build_normalization_contract(
    spec: AlgorithmStructureSpec,
    *,
    input_bounds: Mapping[int, NumericBound | Mapping[str, Any] | Sequence[Any]] | None = None,
    parameter_bounds: Mapping[int, NumericBound | Mapping[str, Any] | Sequence[Any]] | None = None,
    state_bounds: Mapping[int, NumericBound | Mapping[str, Any] | Sequence[Any]] | None = None,
    output_bounds: Mapping[int, NumericBound | Mapping[str, Any] | Sequence[Any]] | None = None,
    time: TimeNormalization | Mapping[str, Any] | float | int | None = None,
) -> NormalizationContract:
    validate_structure(spec)
    role_inputs = {
        "INPUT": (spec.inputs, _coerce_bound_map(input_bounds)),
        "PARAMETER": (spec.parameters, _coerce_bound_map(parameter_bounds)),
        "STATE": (spec.states, _coerce_bound_map(state_bounds)),
        "OUTPUT": (spec.outputs, _coerce_bound_map(output_bounds)),
    }
    bindings: list[NormalizationBinding] = []
    for role in ("INPUT", "PARAMETER", "STATE", "OUTPUT"):
        specs, bounds = role_inputs[role]
        bindings.extend(_build_role_bindings(role=role, specs=specs, bounds=bounds))
    bindings_tuple = tuple(
        sorted(bindings, key=lambda item: (ROLE_ORDER[item.role], item.position))
    )
    time_contract = time_normalization(time)
    strength = _contract_strength(bindings_tuple, time_contract)
    warnings = []
    if strength != "EXACT_NORMALIZATION":
        warnings.append(
            "normalization uses one or more approximate/observed engineering bounds; "
            "canonical equality is weaker than exact bounded normalization"
        )

    audit_payload = {
        "schema_version": 1,
        "normalizer_version": NORMALIZER_VERSION,
        "bindings": [item.audit_payload() for item in bindings_tuple],
        "time": time_contract.audit_payload() if time_contract is not None else None,
        "normalization_strength": strength,
    }
    canonical_payload = {
        "schema_version": 1,
        "normalizer_version": NORMALIZER_VERSION,
        "bindings": [item.canonical_payload() for item in bindings_tuple],
        "time": time_contract.canonical_payload() if time_contract is not None else None,
        "normalization_strength": strength,
    }
    return NormalizationContract(
        schema_version=1,
        normalizer_version=NORMALIZER_VERSION,
        bindings=bindings_tuple,
        time=time_contract,
        normalization_strength=strength,
        contract_hash=sha256_json(audit_payload),
        canonical_signature=sha256_json(canonical_payload),
        warnings=tuple(warnings),
    )


def _role_bindings(contract: NormalizationContract, role: str) -> list[NormalizationBinding]:
    normalized_role = str(role).strip().upper()
    if normalized_role not in ROLE_ORDER:
        raise EGCFError(f"unsupported normalization role: {role!r}")
    return [item for item in contract.bindings if item.role == normalized_role]


def normalize_role(
    contract: NormalizationContract,
    role: str,
    values: Sequence[float],
) -> Tuple[float, ...]:
    bindings = _role_bindings(contract, role)
    if len(values) != len(bindings):
        raise EGCFError(
            f"normalization value count {len(values)} does not match {len(bindings)} bindings"
        )
    return tuple(
        normalize_value(binding.bound, value)
        for binding, value in zip(bindings, values)
    )


def denormalize_role(
    contract: NormalizationContract,
    role: str,
    values: Sequence[float],
) -> Tuple[float, ...]:
    bindings = _role_bindings(contract, role)
    if len(values) != len(bindings):
        raise EGCFError(
            f"denormalization value count {len(values)} does not match {len(bindings)} bindings"
        )
    return tuple(
        denormalize_value(binding.bound, value)
        for binding, value in zip(bindings, values)
    )


def normalized_algorithm_signature(
    structural_ir: CanonicalAlgorithmIR,
    contract: NormalizationContract,
) -> str:
    """Bind SAA-1 structure to SAA-2 interface coordinates without dynamic claims."""

    return sha256_json(
        {
            "signature_version": "saa-structural-interface-normalized-v1",
            "claim_scope": "STRUCTURE_PLUS_INTERFACE_COORDINATES_ONLY",
            "structural": {
                "canonicalizer_version": structural_ir.canonicalizer_version,
                "hash": structural_ir.structural_hash,
                "strength": structural_ir.canonicalization_strength,
            },
            "normalization": {
                "normalizer_version": contract.normalizer_version,
                "signature": contract.canonical_signature,
                "strength": contract.normalization_strength,
            },
        }
    )
