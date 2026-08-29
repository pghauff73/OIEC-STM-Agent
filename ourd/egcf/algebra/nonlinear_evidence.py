from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import comb, factorial
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .jet import CanonicalTaylorJet, TaylorJetSpec, TaylorJetTerm, canonicalize_taylor_jet
from .representative_form import CanonicalRepresentativeAlgorithmForm


NONLINEAR_EVIDENCE_VERSION = "saa-nonlinear-evidence-v1"
EXACT_JET_EVIDENCE_KINDS = {
    "EXACT_SYMBOLIC_POLYNOMIAL",
    "EXACT_DERIVATIVE_TABLE",
}
ESTIMATED_JET_EVIDENCE_KINDS = {
    "BOUNDED_ESTIMATED_DERIVATIVES",
}


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
    value = 1
    for power in powers:
        value *= factorial(int(power))
    return value


def _validate_parent(form: CanonicalRepresentativeAlgorithmForm) -> None:
    if not isinstance(form, CanonicalRepresentativeAlgorithmForm):
        raise EGCFError("SAA-7.2 requires a SAA-6 canonical representative form")
    if not form.canonical_admission_eligible:
        raise EGCFError("SAA-7.2 requires a qualified SAA-6 representative form")


def _validate_digest(value: str, *, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EGCFError(f"{label} must be an exact SHA-256 digest")
    return digest


@dataclass(frozen=True)
class ExactDerivativeTerm:
    output_index: int
    powers: Tuple[int, ...]
    derivative: Fraction

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_index": self.output_index,
            "powers": list(self.powers),
            "derivative": _fraction_payload(self.derivative),
        }


@dataclass(frozen=True)
class ExactPolynomialTerm:
    output_index: int
    powers: Tuple[int, ...]
    coefficient: Fraction

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_index": self.output_index,
            "powers": list(self.powers),
            "coefficient": _fraction_payload(self.coefficient),
        }


@dataclass(frozen=True)
class ExactPolynomialSystem:
    input_count: int
    output_count: int
    terms: Tuple[ExactPolynomialTerm, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_count": self.input_count,
            "output_count": self.output_count,
            "terms": [item.to_dict() for item in self.terms],
        }


@dataclass(frozen=True)
class BoundedDerivativeEstimate:
    output_index: int
    powers: Tuple[int, ...]
    lower: Fraction
    upper: Fraction

    def __post_init__(self) -> None:
        if self.upper < self.lower:
            raise EGCFError("bounded derivative estimate upper bound is below lower bound")

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_index": self.output_index,
            "powers": list(self.powers),
            "lower": _fraction_payload(self.lower),
            "upper": _fraction_payload(self.upper),
        }


@dataclass(frozen=True)
class GovernedJetEvidence:
    schema_version: int
    evidence_version: str
    evidence_kind: str
    parent_representative_behavior_signature: str
    source_snapshot_hash: str
    producer: str
    method: str
    independent_acquisition: bool
    exact: bool
    canonical_local_eligible: bool
    center: Tuple[Fraction, ...]
    validity_radius: Tuple[Fraction, ...]
    order: int
    jet: CanonicalTaylorJet | None
    estimated_derivatives: Tuple[BoundedDerivativeEstimate, ...]
    evidence_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_version": self.evidence_version,
            "evidence_kind": self.evidence_kind,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "source_snapshot_hash": self.source_snapshot_hash,
            "producer": self.producer,
            "method": self.method,
            "independent_acquisition": self.independent_acquisition,
            "exact": self.exact,
            "canonical_local_eligible": self.canonical_local_eligible,
            "center": _fraction_tuple_payload(self.center),
            "validity_radius": _fraction_tuple_payload(self.validity_radius),
            "order": self.order,
            "jet": self.jet.to_dict() if self.jet is not None else None,
            "estimated_derivatives": [item.to_dict() for item in self.estimated_derivatives],
            "evidence_signature": self.evidence_signature,
            "warnings": list(self.warnings),
        }


def _normalize_center_radius(
    form: CanonicalRepresentativeAlgorithmForm,
    center: Sequence[Any],
    validity_radius: Sequence[Any],
) -> tuple[Tuple[Fraction, ...], Tuple[Fraction, ...]]:
    if len(center) != form.representative_input_count:
        raise EGCFError("SAA-7.2 evidence center dimension mismatch")
    if len(validity_radius) != form.representative_input_count:
        raise EGCFError("SAA-7.2 evidence radius dimension mismatch")
    exact_center = tuple(
        _exact_fraction(value, label=f"evidence center {index}")
        for index, value in enumerate(center)
    )
    radius = tuple(
        _exact_fraction(value, label=f"evidence radius {index}")
        for index, value in enumerate(validity_radius)
    )
    for index, (value, width) in enumerate(zip(exact_center, radius)):
        if value < 0 or value > 1:
            raise EGCFError("SAA-7.2 evidence center must lie in normalized [0,1]")
        if width <= 0:
            raise EGCFError("SAA-7.2 evidence radius must be positive")
        if value - width < 0 or value + width > 1:
            raise EGCFError(f"SAA-7.2 evidence box for coordinate {index} leaves [0,1]")
    return exact_center, radius


def _qualified_producer(producer: str, method: str, independent: bool) -> bool:
    normalized = str(producer).strip().lower()
    method_text = str(method).strip().lower()
    return bool(
        independent
        and normalized.startswith(("deterministic-", "human-"))
        and method_text
        and method_text not in {"reported", "model-claimed", "model-generated-claim"}
    )


def acquire_exact_derivative_jet(
    form: CanonicalRepresentativeAlgorithmForm,
    *,
    center: Sequence[Any],
    validity_radius: Sequence[Any],
    order: int,
    derivatives: Sequence[ExactDerivativeTerm],
    source_snapshot_hash: str,
    producer: str,
    method: str = "exact-derivative-table",
    independent_acquisition: bool = True,
) -> GovernedJetEvidence:
    _validate_parent(form)
    exact_center, radius = _normalize_center_radius(form, center, validity_radius)
    source_digest = _validate_digest(source_snapshot_hash, label="SAA-7.2 source snapshot hash")
    if order < 1 or order > 4:
        raise EGCFError("SAA-7.2 derivative acquisition order must lie in [1,4]")
    canonical_terms: list[TaylorJetTerm] = []
    evidence_rows: list[dict[str, Any]] = []
    for item in derivatives:
        if not isinstance(item, ExactDerivativeTerm):
            raise EGCFError("SAA-7.2 derivative records must be ExactDerivativeTerm")
        output = int(item.output_index)
        powers = tuple(int(value) for value in item.powers)
        if output < 0 or output >= form.output_count:
            raise EGCFError("SAA-7.2 derivative output index outside output dimension")
        if len(powers) != form.representative_input_count:
            raise EGCFError("SAA-7.2 derivative multi-index dimension mismatch")
        if any(value < 0 for value in powers) or _degree(powers) > order:
            raise EGCFError("SAA-7.2 derivative multi-index outside declared order")
        derivative = _exact_fraction(item.derivative, label="exact derivative")
        coefficient = derivative / _multi_factorial(powers)
        if coefficient:
            canonical_terms.append(TaylorJetTerm(output, powers, coefficient))
        evidence_rows.append(
            {
                "output_index": output,
                "powers": list(powers),
                "derivative": _fraction_payload(derivative),
            }
        )
    jet = canonicalize_taylor_jet(
        form,
        TaylorJetSpec(
            input_count=form.representative_input_count,
            output_count=form.output_count,
            order=order,
            center=exact_center,
            validity_radius=radius,
            terms=tuple(canonical_terms),
        ),
    )
    producer_text = str(producer).strip()
    method_text = str(method).strip()
    eligible = _qualified_producer(producer_text, method_text, independent_acquisition)
    payload = {
        "schema_version": 1,
        "evidence_version": NONLINEAR_EVIDENCE_VERSION,
        "evidence_kind": "EXACT_DERIVATIVE_TABLE",
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "source_snapshot_hash": source_digest,
        "producer": producer_text,
        "method": method_text,
        "independent_acquisition": bool(independent_acquisition),
        "center": _fraction_tuple_payload(exact_center),
        "validity_radius": _fraction_tuple_payload(radius),
        "order": order,
        "derivatives": evidence_rows,
        "jet_local_behavior_signature": jet.local_behavior_signature,
    }
    warnings = () if eligible else (
        "Exact coefficients were acquired, but provenance/independence is insufficient for canonical local admission.",
    )
    return GovernedJetEvidence(
        schema_version=1,
        evidence_version=NONLINEAR_EVIDENCE_VERSION,
        evidence_kind="EXACT_DERIVATIVE_TABLE",
        parent_representative_behavior_signature=form.representative_behavior_signature,
        source_snapshot_hash=source_digest,
        producer=producer_text,
        method=method_text,
        independent_acquisition=bool(independent_acquisition),
        exact=True,
        canonical_local_eligible=eligible,
        center=exact_center,
        validity_radius=radius,
        order=order,
        jet=jet,
        estimated_derivatives=(),
        evidence_signature=sha256_json(payload),
        warnings=warnings,
    )


def _validate_polynomial_system(
    form: CanonicalRepresentativeAlgorithmForm,
    system: ExactPolynomialSystem,
) -> Tuple[ExactPolynomialTerm, ...]:
    if not isinstance(system, ExactPolynomialSystem):
        raise EGCFError("SAA-7.2 symbolic acquisition requires ExactPolynomialSystem")
    if system.input_count != form.representative_input_count:
        raise EGCFError("symbolic polynomial input dimension mismatches representative form")
    if system.output_count != form.output_count:
        raise EGCFError("symbolic polynomial output dimension mismatches representative form")
    canonical: list[ExactPolynomialTerm] = []
    for raw in system.terms:
        if not isinstance(raw, ExactPolynomialTerm):
            raise EGCFError("symbolic polynomial terms must be ExactPolynomialTerm")
        output = int(raw.output_index)
        powers = tuple(int(value) for value in raw.powers)
        coefficient = _exact_fraction(raw.coefficient, label="symbolic polynomial coefficient")
        if output < 0 or output >= form.output_count:
            raise EGCFError("symbolic polynomial output index outside output dimension")
        if len(powers) != form.representative_input_count or any(value < 0 for value in powers):
            raise EGCFError("symbolic polynomial powers are invalid")
        if coefficient:
            canonical.append(ExactPolynomialTerm(output, powers, coefficient))
    canonical.sort(key=lambda item: (item.output_index, _degree(item.powers), item.powers, item.coefficient))
    return tuple(canonical)


def _expand_polynomial_at_center(
    terms: Sequence[ExactPolynomialTerm],
    center: Sequence[Fraction],
    *,
    input_count: int,
    order: int,
) -> Tuple[TaylorJetTerm, ...]:
    accumulator: dict[tuple[int, Tuple[int, ...]], Fraction] = {}
    for term in terms:
        choices: list[list[tuple[int, Fraction]]] = []
        for input_index, power in enumerate(term.powers):
            coordinate_choices: list[tuple[int, Fraction]] = []
            for alpha in range(power + 1):
                factor = Fraction(comb(power, alpha)) * (center[input_index] ** (power - alpha))
                coordinate_choices.append((alpha, factor))
            choices.append(coordinate_choices)

        partial: list[tuple[Tuple[int, ...], Fraction]] = [((), term.coefficient)]
        for coordinate_choices in choices:
            next_partial: list[tuple[Tuple[int, ...], Fraction]] = []
            for prefix, prefix_coefficient in partial:
                for alpha, factor in coordinate_choices:
                    powers = (*prefix, alpha)
                    if _degree(powers) <= order:
                        next_partial.append((powers, prefix_coefficient * factor))
            partial = next_partial
        for powers, coefficient in partial:
            if len(powers) != input_count or _degree(powers) > order or coefficient == 0:
                continue
            key = (term.output_index, powers)
            accumulator[key] = accumulator.get(key, Fraction(0)) + coefficient
    return tuple(
        TaylorJetTerm(output, powers, coefficient)
        for (output, powers), coefficient in sorted(
            accumulator.items(), key=lambda item: (item[0][0], _degree(item[0][1]), item[0][1])
        )
        if coefficient != 0
    )


def acquire_exact_polynomial_jet(
    form: CanonicalRepresentativeAlgorithmForm,
    system: ExactPolynomialSystem,
    *,
    center: Sequence[Any],
    validity_radius: Sequence[Any],
    order: int,
) -> GovernedJetEvidence:
    _validate_parent(form)
    exact_center, radius = _normalize_center_radius(form, center, validity_radius)
    if order < 1 or order > 4:
        raise EGCFError("SAA-7.2 symbolic acquisition order must lie in [1,4]")
    terms = _validate_polynomial_system(form, system)
    source_payload = {
        "schema_version": 1,
        "kind": "EXACT_POLYNOMIAL_SYSTEM",
        "input_count": form.representative_input_count,
        "output_count": form.output_count,
        "terms": [item.to_dict() for item in terms],
    }
    source_digest = sha256_json(source_payload)
    jet_terms = _expand_polynomial_at_center(
        terms,
        exact_center,
        input_count=form.representative_input_count,
        order=order,
    )
    jet = canonicalize_taylor_jet(
        form,
        TaylorJetSpec(
            input_count=form.representative_input_count,
            output_count=form.output_count,
            order=order,
            center=exact_center,
            validity_radius=radius,
            terms=jet_terms,
        ),
    )
    evidence_payload = {
        "schema_version": 1,
        "evidence_version": NONLINEAR_EVIDENCE_VERSION,
        "evidence_kind": "EXACT_SYMBOLIC_POLYNOMIAL",
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "source_snapshot_hash": source_digest,
        "producer": "deterministic-saa-polynomial-expander",
        "method": "exact-binomial-taylor-expansion",
        "center": _fraction_tuple_payload(exact_center),
        "validity_radius": _fraction_tuple_payload(radius),
        "order": order,
        "jet_local_behavior_signature": jet.local_behavior_signature,
    }
    return GovernedJetEvidence(
        schema_version=1,
        evidence_version=NONLINEAR_EVIDENCE_VERSION,
        evidence_kind="EXACT_SYMBOLIC_POLYNOMIAL",
        parent_representative_behavior_signature=form.representative_behavior_signature,
        source_snapshot_hash=source_digest,
        producer="deterministic-saa-polynomial-expander",
        method="exact-binomial-taylor-expansion",
        independent_acquisition=True,
        exact=True,
        canonical_local_eligible=True,
        center=exact_center,
        validity_radius=radius,
        order=order,
        jet=jet,
        estimated_derivatives=(),
        evidence_signature=sha256_json(evidence_payload),
        warnings=(
            "Exact symbolic acquisition certifies exact Taylor coefficients to the declared truncation order, not global equality to the truncated jet.",
        ),
    )


def acquire_bounded_estimated_derivatives(
    form: CanonicalRepresentativeAlgorithmForm,
    *,
    center: Sequence[Any],
    validity_radius: Sequence[Any],
    order: int,
    estimates: Sequence[BoundedDerivativeEstimate],
    source_snapshot_hash: str,
    producer: str,
    method: str,
) -> GovernedJetEvidence:
    _validate_parent(form)
    exact_center, radius = _normalize_center_radius(form, center, validity_radius)
    source_digest = _validate_digest(source_snapshot_hash, label="estimated evidence source hash")
    normalized: list[BoundedDerivativeEstimate] = []
    for item in estimates:
        if not isinstance(item, BoundedDerivativeEstimate):
            raise EGCFError("estimated derivative evidence must use BoundedDerivativeEstimate")
        output = int(item.output_index)
        powers = tuple(int(value) for value in item.powers)
        lower = _exact_fraction(item.lower, label="estimated derivative lower bound")
        upper = _exact_fraction(item.upper, label="estimated derivative upper bound")
        if output < 0 or output >= form.output_count:
            raise EGCFError("estimated derivative output index outside output dimension")
        if len(powers) != form.representative_input_count or any(value < 0 for value in powers):
            raise EGCFError("estimated derivative powers are invalid")
        if _degree(powers) > order:
            raise EGCFError("estimated derivative exceeds declared order")
        normalized.append(BoundedDerivativeEstimate(output, powers, lower, upper))
    normalized.sort(key=lambda item: (item.output_index, _degree(item.powers), item.powers))
    payload = {
        "schema_version": 1,
        "evidence_version": NONLINEAR_EVIDENCE_VERSION,
        "evidence_kind": "BOUNDED_ESTIMATED_DERIVATIVES",
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "source_snapshot_hash": source_digest,
        "producer": str(producer).strip(),
        "method": str(method).strip(),
        "center": _fraction_tuple_payload(exact_center),
        "validity_radius": _fraction_tuple_payload(radius),
        "order": int(order),
        "estimates": [item.to_dict() for item in normalized],
    }
    return GovernedJetEvidence(
        schema_version=1,
        evidence_version=NONLINEAR_EVIDENCE_VERSION,
        evidence_kind="BOUNDED_ESTIMATED_DERIVATIVES",
        parent_representative_behavior_signature=form.representative_behavior_signature,
        source_snapshot_hash=source_digest,
        producer=str(producer).strip(),
        method=str(method).strip(),
        independent_acquisition=False,
        exact=False,
        canonical_local_eligible=False,
        center=exact_center,
        validity_radius=radius,
        order=int(order),
        jet=None,
        estimated_derivatives=tuple(normalized),
        evidence_signature=sha256_json(payload),
        warnings=(
            "Estimated or interval derivative evidence is retained for comparison and falsification but cannot enter exact SAA nonlinear identity.",
        ),
    )
