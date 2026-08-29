from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json


SEMANTIC_UNITS_VERSION = "saa-semantic-units-v1"
SI_BASE_DIMENSIONS = (
    "length",
    "mass",
    "time",
    "electric_current",
    "thermodynamic_temperature",
    "amount_of_substance",
    "luminous_intensity",
)
DIMENSION_COUNT = len(SI_BASE_DIMENSIONS)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Iterable[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


def _fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


@dataclass(frozen=True)
class PhysicalDimensionVector:
    exponents: Tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.exponents) != DIMENSION_COUNT:
            raise EGCFError(f"physical dimension vector requires {DIMENSION_COUNT} SI exponents")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in self.exponents):
            raise EGCFError("physical dimension exponents must be exact integers")

    def __mul__(self, other: "PhysicalDimensionVector") -> "PhysicalDimensionVector":
        return PhysicalDimensionVector(tuple(a + b for a, b in zip(self.exponents, other.exponents)))

    def __truediv__(self, other: "PhysicalDimensionVector") -> "PhysicalDimensionVector":
        return PhysicalDimensionVector(tuple(a - b for a, b in zip(self.exponents, other.exponents)))

    def __pow__(self, exponent: int) -> "PhysicalDimensionVector":
        if isinstance(exponent, bool) or not isinstance(exponent, int):
            raise EGCFError("physical dimension powers must be integer")
        return PhysicalDimensionVector(tuple(exponent * value for value in self.exponents))

    @property
    def dimensionless(self) -> bool:
        return all(value == 0 for value in self.exponents)

    @property
    def signature(self) -> str:
        return sha256_json(
            {
                "version": SEMANTIC_UNITS_VERSION,
                "base_dimensions": list(SI_BASE_DIMENSIONS),
                "exponents": list(self.exponents),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_dimensions": list(SI_BASE_DIMENSIONS),
            "exponents": list(self.exponents),
            "dimensionless": self.dimensionless,
            "signature": self.signature,
        }


DIMENSIONLESS = PhysicalDimensionVector((0, 0, 0, 0, 0, 0, 0))
LENGTH = PhysicalDimensionVector((1, 0, 0, 0, 0, 0, 0))
MASS = PhysicalDimensionVector((0, 1, 0, 0, 0, 0, 0))
TIME = PhysicalDimensionVector((0, 0, 1, 0, 0, 0, 0))
ELECTRIC_CURRENT = PhysicalDimensionVector((0, 0, 0, 1, 0, 0, 0))
TEMPERATURE = PhysicalDimensionVector((0, 0, 0, 0, 1, 0, 0))
AMOUNT = PhysicalDimensionVector((0, 0, 0, 0, 0, 1, 0))
LUMINOUS_INTENSITY = PhysicalDimensionVector((0, 0, 0, 0, 0, 0, 1))


@dataclass(frozen=True)
class PhysicalUnit:
    symbol: str
    name: str
    dimension: PhysicalDimensionVector
    scale_to_si: Fraction = Fraction(1)
    offset_to_si: Fraction = Fraction(0)

    def __post_init__(self) -> None:
        if not str(self.symbol).strip() or not str(self.name).strip():
            raise EGCFError("physical unit symbol and name must be non-empty")
        if not isinstance(self.dimension, PhysicalDimensionVector):
            raise EGCFError("physical unit requires PhysicalDimensionVector")
        if self.scale_to_si <= 0:
            raise EGCFError("physical unit scale must be positive")

    @property
    def canonical_symbol(self) -> str:
        return str(self.symbol).strip()

    @property
    def signature(self) -> str:
        return sha256_json(
            {
                "version": SEMANTIC_UNITS_VERSION,
                "symbol": self.canonical_symbol,
                "name": _text(self.name),
                "dimension": list(self.dimension.exponents),
                "scale_to_si": _fraction_payload(self.scale_to_si),
                "offset_to_si": _fraction_payload(self.offset_to_si),
            }
        )

    def to_si(self, value: Any) -> Fraction:
        exact = _fraction(value, label=f"value in {self.canonical_symbol}")
        return exact * self.scale_to_si + self.offset_to_si

    def from_si(self, value: Any) -> Fraction:
        exact = _fraction(value, label="SI value")
        return (exact - self.offset_to_si) / self.scale_to_si

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.canonical_symbol,
            "name": _text(self.name),
            "dimension": self.dimension.to_dict(),
            "scale_to_si": _fraction_payload(self.scale_to_si),
            "offset_to_si": _fraction_payload(self.offset_to_si),
            "signature": self.signature,
        }


_BUILTIN_UNITS: dict[str, PhysicalUnit] = {}


def _register(unit: PhysicalUnit, *aliases: str) -> PhysicalUnit:
    for key in (unit.symbol, unit.name, *aliases):
        _BUILTIN_UNITS[_text(key)] = unit
    return unit


ONE = _register(PhysicalUnit("1", "dimensionless", DIMENSIONLESS), "unitless")
METRE = _register(PhysicalUnit("m", "metre", LENGTH), "meter")
MILLIMETRE = _register(PhysicalUnit("mm", "millimetre", LENGTH, Fraction(1, 1000)), "millimeter")
CENTIMETRE = _register(PhysicalUnit("cm", "centimetre", LENGTH, Fraction(1, 100)), "centimeter")
KILOMETRE = _register(PhysicalUnit("km", "kilometre", LENGTH, Fraction(1000)), "kilometer")
SECOND = _register(PhysicalUnit("s", "second", TIME))
KILOGRAM = _register(PhysicalUnit("kg", "kilogram", MASS))
AMPERE = _register(PhysicalUnit("A", "ampere", ELECTRIC_CURRENT))
KELVIN = _register(PhysicalUnit("K", "kelvin", TEMPERATURE))
CELSIUS = _register(PhysicalUnit("degC", "degree celsius", TEMPERATURE, Fraction(1), Fraction(27315, 100)), "celsius")
MOLE = _register(PhysicalUnit("mol", "mole", AMOUNT))
CANDELA = _register(PhysicalUnit("cd", "candela", LUMINOUS_INTENSITY))
HERTZ = _register(PhysicalUnit("Hz", "hertz", TIME ** -1))
NEWTON = _register(PhysicalUnit("N", "newton", MASS * LENGTH / (TIME ** 2)))
PASCAL = _register(PhysicalUnit("Pa", "pascal", MASS / LENGTH / (TIME ** 2)))
JOULE = _register(PhysicalUnit("J", "joule", MASS * (LENGTH ** 2) / (TIME ** 2)))
WATT = _register(PhysicalUnit("W", "watt", MASS * (LENGTH ** 2) / (TIME ** 3)))
COULOMB = _register(PhysicalUnit("C", "coulomb", ELECTRIC_CURRENT * TIME))
VOLT = _register(PhysicalUnit("V", "volt", MASS * (LENGTH ** 2) / (TIME ** 3) / ELECTRIC_CURRENT))
OHM = _register(PhysicalUnit("ohm", "ohm", MASS * (LENGTH ** 2) / (TIME ** 3) / (ELECTRIC_CURRENT ** 2)), "Ω")


def physical_unit(identifier: str) -> PhysicalUnit:
    try:
        return _BUILTIN_UNITS[_text(identifier)]
    except KeyError as exc:
        raise EGCFError(f"unknown physical unit: {identifier!r}") from exc


def convert_exact_value(value: Any, source_unit: str | PhysicalUnit, target_unit: str | PhysicalUnit) -> Fraction:
    source = physical_unit(source_unit) if isinstance(source_unit, str) else source_unit
    target = physical_unit(target_unit) if isinstance(target_unit, str) else target_unit
    if not isinstance(source, PhysicalUnit) or not isinstance(target, PhysicalUnit):
        raise EGCFError("exact conversion requires PhysicalUnit")
    if source.dimension != target.dimension:
        raise EGCFError("cannot convert between dimensionally incompatible units")
    return target.from_si(source.to_si(value))


@dataclass(frozen=True)
class SemanticConcept:
    canonical_name: str
    meaning: str
    domain: str
    quantity_kind: str
    aliases: Tuple[str, ...]
    physical_dimension: PhysicalDimensionVector | None
    canonical_unit: PhysicalUnit | None
    evidence_ids: Tuple[str, ...]
    semantic_status: str
    concept_signature: str
    canonical_eligible: bool

    @property
    def physical(self) -> bool:
        return self.physical_dimension is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "meaning": self.meaning,
            "domain": self.domain,
            "quantity_kind": self.quantity_kind,
            "aliases": list(self.aliases),
            "physical_dimension": self.physical_dimension.to_dict() if self.physical_dimension else None,
            "canonical_unit": self.canonical_unit.to_dict() if self.canonical_unit else None,
            "evidence_ids": list(self.evidence_ids),
            "semantic_status": self.semantic_status,
            "concept_signature": self.concept_signature,
            "canonical_eligible": self.canonical_eligible,
            "physical": self.physical,
        }


def make_semantic_concept(
    *,
    name: str,
    meaning: str,
    domain: str,
    quantity_kind: str,
    aliases: Sequence[str] = (),
    physical_dimension: PhysicalDimensionVector | None = None,
    canonical_unit: str | PhysicalUnit | None = None,
    evidence_ids: Sequence[str] = (),
    semantic_status: str = "SEMANTICALLY_RESOLVED",
) -> SemanticConcept:
    canonical_name = _text(name)
    canonical_meaning = _text(meaning)
    canonical_domain = _text(domain)
    canonical_quantity = _text(quantity_kind)
    if not canonical_name or not canonical_meaning or not canonical_domain or not canonical_quantity:
        raise EGCFError("semantic concept name, meaning, domain and quantity kind are required")
    unit: PhysicalUnit | None
    if isinstance(canonical_unit, str):
        unit = physical_unit(canonical_unit)
    else:
        unit = canonical_unit
    if unit is not None and physical_dimension is None:
        physical_dimension = unit.dimension
    if unit is not None and unit.dimension != physical_dimension:
        raise EGCFError("semantic concept unit contradicts declared physical dimension")
    if physical_dimension is not None and not isinstance(physical_dimension, PhysicalDimensionVector):
        raise EGCFError("semantic concept physical dimension is invalid")
    normalized_aliases = _texts(aliases)
    normalized_evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    status = str(semantic_status).strip().upper()
    eligible = status == "SEMANTICALLY_RESOLVED" and bool(normalized_evidence)
    payload = {
        "version": SEMANTIC_UNITS_VERSION,
        "canonical_name": canonical_name,
        "meaning": canonical_meaning,
        "domain": canonical_domain,
        "quantity_kind": canonical_quantity,
        "aliases": list(normalized_aliases),
        "physical_dimension": list(physical_dimension.exponents) if physical_dimension else None,
        "canonical_unit_signature": unit.signature if unit else None,
        "evidence_ids": list(normalized_evidence),
        "semantic_status": status,
    }
    return SemanticConcept(
        canonical_name=canonical_name,
        meaning=canonical_meaning,
        domain=canonical_domain,
        quantity_kind=canonical_quantity,
        aliases=normalized_aliases,
        physical_dimension=physical_dimension,
        canonical_unit=unit,
        evidence_ids=normalized_evidence,
        semantic_status=status,
        concept_signature=sha256_json(payload),
        canonical_eligible=eligible,
    )


@dataclass(frozen=True)
class DimensionalConstraintAssessment:
    status: str
    expected_dimension: PhysicalDimensionVector
    observed_dimension: PhysicalDimensionVector
    quantity_kind_consistent: bool
    canonical_semantic_eligible: bool
    signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "expected_dimension": self.expected_dimension.to_dict(),
            "observed_dimension": self.observed_dimension.to_dict(),
            "quantity_kind_consistent": self.quantity_kind_consistent,
            "canonical_semantic_eligible": self.canonical_semantic_eligible,
            "signature": self.signature,
            "warnings": list(self.warnings),
        }


def assess_product_dimension(
    output: SemanticConcept,
    factors: Sequence[tuple[SemanticConcept, int]],
) -> DimensionalConstraintAssessment:
    if output.physical_dimension is None:
        raise EGCFError("SAA-9.1 dimensional product assessment requires physical output concept")
    observed = DIMENSIONLESS
    for concept, power in factors:
        if concept.physical_dimension is None:
            raise EGCFError("SAA-9.1 dimensional product factor is not physically dimensioned")
        observed = observed * (concept.physical_dimension ** int(power))
    expected = output.physical_dimension
    dimension_match = observed == expected
    payload = {
        "version": SEMANTIC_UNITS_VERSION,
        "output": output.concept_signature,
        "factors": [[item.concept_signature, int(power)] for item, power in factors],
        "expected": list(expected.exponents),
        "observed": list(observed.exponents),
        "quantity_kind": output.quantity_kind,
    }
    status = "DIMENSIONALLY_COHERENT" if dimension_match else "DIMENSIONAL_SEMANTIC_MISREPRESENTATION"
    warnings: list[str] = []
    if dimension_match:
        warnings.append(
            "Dimensional coherence is necessary but not sufficient for semantic equivalence; equal dimensions can represent different quantity kinds."
        )
    return DimensionalConstraintAssessment(
        status=status,
        expected_dimension=expected,
        observed_dimension=observed,
        quantity_kind_consistent=True,
        canonical_semantic_eligible=dimension_match and output.canonical_eligible,
        signature=sha256_json(payload),
        warnings=tuple(warnings),
    )


def assess_additive_compatibility(concepts: Sequence[SemanticConcept]) -> DimensionalConstraintAssessment:
    if len(concepts) < 2:
        raise EGCFError("additive semantic compatibility requires at least two concepts")
    if any(item.physical_dimension is None for item in concepts):
        raise EGCFError("additive semantic compatibility requires physical concepts")
    expected = concepts[0].physical_dimension
    assert expected is not None
    dimensions_match = all(item.physical_dimension == expected for item in concepts)
    quantity_match = all(item.quantity_kind == concepts[0].quantity_kind for item in concepts)
    status = (
        "ADDITIVELY_SEMANTICALLY_COHERENT"
        if dimensions_match and quantity_match
        else "ADDITIVE_SEMANTIC_MISREPRESENTATION"
    )
    payload = {
        "version": SEMANTIC_UNITS_VERSION,
        "concepts": [item.concept_signature for item in concepts],
        "dimensions_match": dimensions_match,
        "quantity_match": quantity_match,
    }
    observed = expected if dimensions_match else DIMENSIONLESS
    return DimensionalConstraintAssessment(
        status=status,
        expected_dimension=expected,
        observed_dimension=observed,
        quantity_kind_consistent=quantity_match,
        canonical_semantic_eligible=dimensions_match and quantity_match and all(item.canonical_eligible for item in concepts),
        signature=sha256_json(payload),
        warnings=(
            "Matching physical dimensions do not make different quantity kinds additive.",
        ) if dimensions_match and not quantity_match else (),
    )


def physical_semantic_relation(left: SemanticConcept, right: SemanticConcept) -> str:
    if left.physical_dimension is None or right.physical_dimension is None:
        return "NONPHYSICAL_OR_UNRESOLVED_DIMENSION"
    if left.physical_dimension != right.physical_dimension:
        return "DIMENSIONALLY_INCOMPATIBLE"
    if left.quantity_kind != right.quantity_kind:
        return "SAME_DIMENSION_DIFFERENT_QUANTITY_KIND"
    if left.meaning == right.meaning:
        return "PHYSICALLY_AND_SEMANTICALLY_COMPATIBLE"
    return "PHYSICALLY_COMPATIBLE_MEANING_UNRESOLVED"
