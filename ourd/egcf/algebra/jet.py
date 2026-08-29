from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .representative_form import CanonicalRepresentativeAlgorithmForm


NONLINEAR_JET_VERSION = "saa-nonlinear-jet-v1"
MAX_JET_ORDER = 4
MAX_JET_INPUTS = 8
MAX_JET_OUTPUTS = 8
MAX_JET_TERMS = 512


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must use an exact integer/Fraction/rational string, not float")
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


def _validate_parent(form: CanonicalRepresentativeAlgorithmForm) -> None:
    if not isinstance(form, CanonicalRepresentativeAlgorithmForm):
        raise EGCFError("SAA-7 requires a SAA-6 CanonicalRepresentativeAlgorithmForm")
    if not form.canonical_admission_eligible:
        raise EGCFError("SAA-7 requires a canonically eligible SAA-6 representative form")
    if form.store_status != "ELIGIBLE_CANONICAL_REPRESENTATIVE_FORM":
        raise EGCFError("SAA-7 parent form is not eligible canonical representative knowledge")


@dataclass(frozen=True)
class TaylorJetTerm:
    output_index: int
    powers: Tuple[int, ...]
    coefficient: Fraction

    @property
    def degree(self) -> int:
        return _degree(self.powers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_index": self.output_index,
            "powers": list(self.powers),
            "degree": self.degree,
            "coefficient": _fraction_payload(self.coefficient),
        }


@dataclass(frozen=True)
class TaylorJetSpec:
    input_count: int
    output_count: int
    order: int
    center: Tuple[Any, ...]
    validity_radius: Tuple[Any, ...]
    terms: Tuple[TaylorJetTerm, ...]


@dataclass(frozen=True)
class NonlinearCouplingTerm:
    output_index: int
    powers: Tuple[int, ...]
    coefficient: Fraction
    input_support: Tuple[int, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_index": self.output_index,
            "powers": list(self.powers),
            "coefficient": _fraction_payload(self.coefficient),
            "input_support": list(self.input_support),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class NonlinearCouplingAssessment:
    status: str
    dependency_by_input: Tuple[Tuple[int, ...], ...]
    cross_terms: Tuple[NonlinearCouplingTerm, ...]
    off_pair_terms: Tuple[NonlinearCouplingTerm, ...]
    coupling_score: int
    representative: bool
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dependency_by_input": [list(item) for item in self.dependency_by_input],
            "cross_terms": [item.to_dict() for item in self.cross_terms],
            "off_pair_terms": [item.to_dict() for item in self.off_pair_terms],
            "coupling_score": self.coupling_score,
            "representative": self.representative,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class CanonicalTaylorJet:
    schema_version: int
    jet_version: str
    parent_representative_behavior_signature: str
    parent_semantic_signature: str
    input_count: int
    output_count: int
    order: int
    center: Tuple[Fraction, ...]
    validity_radius: Tuple[Fraction, ...]
    terms: Tuple[TaylorJetTerm, ...]
    coefficient_signature: str
    scope_signature: str
    local_behavior_signature: str
    coupling: NonlinearCouplingAssessment
    local_equivalence_scope: str
    global_equivalence_eligible: bool
    exact: bool
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "jet_version": self.jet_version,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "parent_semantic_signature": self.parent_semantic_signature,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "order": self.order,
            "center": _fraction_tuple_payload(self.center),
            "validity_radius": _fraction_tuple_payload(self.validity_radius),
            "terms": [item.to_dict() for item in self.terms],
            "coefficient_signature": self.coefficient_signature,
            "scope_signature": self.scope_signature,
            "local_behavior_signature": self.local_behavior_signature,
            "coupling": self.coupling.to_dict(),
            "local_equivalence_scope": self.local_equivalence_scope,
            "global_equivalence_eligible": self.global_equivalence_eligible,
            "exact": self.exact,
            "warnings": list(self.warnings),
        }

    def evaluate(self, values: Sequence[Any]) -> Tuple[Fraction, ...]:
        if len(values) != self.input_count:
            raise EGCFError("Taylor jet evaluation input dimension mismatch")
        exact_values = tuple(
            _exact_fraction(value, label=f"Taylor jet input {index}")
            for index, value in enumerate(values)
        )
        for index, (value, center, radius) in enumerate(
            zip(exact_values, self.center, self.validity_radius)
        ):
            if abs(value - center) > radius:
                raise EGCFError(
                    f"Taylor jet input {index} lies outside the qualified local validity box"
                )
        delta = tuple(value - center for value, center in zip(exact_values, self.center))
        outputs = [Fraction(0) for _ in range(self.output_count)]
        for term in self.terms:
            monomial = term.coefficient
            for value, power in zip(delta, term.powers):
                if power:
                    monomial *= value ** power
            outputs[term.output_index] += monomial
        return tuple(outputs)


@dataclass(frozen=True)
class LocalJetComparison:
    status: str
    coefficient_match: bool
    same_expansion_point: bool
    overlap_radius: Tuple[Fraction, ...]
    global_equivalence_eligible: bool
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "coefficient_match": self.coefficient_match,
            "same_expansion_point": self.same_expansion_point,
            "overlap_radius": _fraction_tuple_payload(self.overlap_radius),
            "global_equivalence_eligible": self.global_equivalence_eligible,
            "signature": self.signature,
        }


def _canonical_terms(
    *,
    input_count: int,
    output_count: int,
    order: int,
    terms: Sequence[TaylorJetTerm],
) -> Tuple[TaylorJetTerm, ...]:
    if len(terms) > MAX_JET_TERMS:
        raise EGCFError(f"Taylor jet term count exceeds bounded cap {MAX_JET_TERMS}")
    accumulator: dict[tuple[int, Tuple[int, ...]], Fraction] = {}
    for raw in terms:
        if not isinstance(raw, TaylorJetTerm):
            raise EGCFError("Taylor jet terms must be TaylorJetTerm records")
        output_index = int(raw.output_index)
        if output_index < 0 or output_index >= output_count:
            raise EGCFError("Taylor jet output index outside output dimension")
        powers = tuple(int(value) for value in raw.powers)
        if len(powers) != input_count:
            raise EGCFError("Taylor jet multi-index dimension mismatch")
        if any(value < 0 for value in powers):
            raise EGCFError("Taylor jet powers cannot be negative")
        if _degree(powers) > order:
            raise EGCFError("Taylor jet term exceeds declared truncation order")
        coefficient = _exact_fraction(raw.coefficient, label="Taylor jet coefficient")
        if coefficient == 0:
            continue
        key = (output_index, powers)
        accumulator[key] = accumulator.get(key, Fraction(0)) + coefficient
    canonical = [
        TaylorJetTerm(output_index=output, powers=powers, coefficient=coefficient)
        for (output, powers), coefficient in accumulator.items()
        if coefficient != 0
    ]
    canonical.sort(key=lambda item: (item.output_index, item.degree, item.powers))
    if len(canonical) > MAX_JET_TERMS:
        raise EGCFError(f"canonical Taylor jet term count exceeds cap {MAX_JET_TERMS}")
    return tuple(canonical)


def assess_nonlinear_coupling(
    form: CanonicalRepresentativeAlgorithmForm,
    terms: Sequence[TaylorJetTerm],
) -> NonlinearCouplingAssessment:
    _validate_parent(form)
    pairing = {item.canonical_position: item.paired_output_index for item in form.inputs}
    dependencies: list[set[int]] = [set() for _ in range(form.representative_input_count)]
    cross_terms: list[NonlinearCouplingTerm] = []
    off_pair_terms: list[NonlinearCouplingTerm] = []
    for term in terms:
        if term.degree == 0:
            continue
        support = tuple(index for index, power in enumerate(term.powers) if power)
        for input_index in support:
            dependencies[input_index].add(term.output_index)
        if len(support) > 1:
            cross_terms.append(
                NonlinearCouplingTerm(
                    output_index=term.output_index,
                    powers=term.powers,
                    coefficient=term.coefficient,
                    input_support=support,
                    reason="MULTI_INPUT_NONLINEAR_INTERACTION",
                )
            )
        for input_index in support:
            paired = pairing.get(input_index)
            if paired is not None and paired != term.output_index:
                off_pair_terms.append(
                    NonlinearCouplingTerm(
                        output_index=term.output_index,
                        powers=term.powers,
                        coefficient=term.coefficient,
                        input_support=(input_index,),
                        reason="INPUT_AFFECTS_NON_PAIRED_OUTPUT",
                    )
                )
    unique_off = {
        (item.output_index, item.powers, item.input_support, item.reason): item
        for item in off_pair_terms
    }
    off_pair_terms = list(unique_off.values())
    score = len(cross_terms) + len(off_pair_terms)
    representative = score == 0
    status = (
        "NONLINEAR_REPRESENTATIVE"
        if representative
        else "NONLINEAR_SEMANTIC_MISREPRESENTATION"
    )
    material = {
        "schema_version": 1,
        "jet_version": NONLINEAR_JET_VERSION,
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "dependency_by_input": [sorted(item) for item in dependencies],
        "cross_terms": [item.to_dict() for item in cross_terms],
        "off_pair_terms": [item.to_dict() for item in off_pair_terms],
        "coupling_score": score,
    }
    return NonlinearCouplingAssessment(
        status=status,
        dependency_by_input=tuple(tuple(sorted(item)) for item in dependencies),
        cross_terms=tuple(cross_terms),
        off_pair_terms=tuple(off_pair_terms),
        coupling_score=score,
        representative=representative,
        signature=sha256_json(material),
    )


def canonicalize_taylor_jet(
    form: CanonicalRepresentativeAlgorithmForm,
    spec: TaylorJetSpec,
) -> CanonicalTaylorJet:
    _validate_parent(form)
    if not isinstance(spec, TaylorJetSpec):
        raise EGCFError("SAA-7 requires TaylorJetSpec")
    input_count = int(spec.input_count)
    output_count = int(spec.output_count)
    order = int(spec.order)
    if input_count != form.representative_input_count:
        raise EGCFError("SAA-7 jet input count must match SAA-6 representative input count")
    if output_count != form.output_count:
        raise EGCFError("SAA-7 jet output count must match SAA-6 output count")
    if input_count < 0 or input_count > MAX_JET_INPUTS:
        raise EGCFError(f"SAA-7 input dimension exceeds cap {MAX_JET_INPUTS}")
    if output_count < 1 or output_count > MAX_JET_OUTPUTS:
        raise EGCFError(f"SAA-7 output dimension exceeds cap {MAX_JET_OUTPUTS}")
    if order < 1 or order > MAX_JET_ORDER:
        raise EGCFError(f"SAA-7 Taylor order must lie in [1,{MAX_JET_ORDER}]")
    if len(spec.center) != input_count or len(spec.validity_radius) != input_count:
        raise EGCFError("SAA-7 center/radius dimension mismatch")
    center = tuple(
        _exact_fraction(value, label=f"Taylor center {index}")
        for index, value in enumerate(spec.center)
    )
    radius = tuple(
        _exact_fraction(value, label=f"Taylor validity radius {index}")
        for index, value in enumerate(spec.validity_radius)
    )
    for index, (value, local_radius) in enumerate(zip(center, radius)):
        if value < 0 or value > 1:
            raise EGCFError("SAA-7 expansion points must lie in normalized [0,1] coordinates")
        if local_radius <= 0:
            raise EGCFError("SAA-7 requires a positive exact local validity radius")
        if value - local_radius < 0 or value + local_radius > 1:
            raise EGCFError(
                f"SAA-7 local validity box for coordinate {index} leaves normalized [0,1]"
            )
    terms = _canonical_terms(
        input_count=input_count,
        output_count=output_count,
        order=order,
        terms=spec.terms,
    )
    coefficient_payload = {
        "schema_version": 1,
        "jet_version": NONLINEAR_JET_VERSION,
        "claim_scope": "EXACT_FINITE_TAYLOR_JET_AT_FIXED_REPRESENTATIVE_POINT",
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "parent_semantic_signature": form.semantic_representative_signature,
        "input_count": input_count,
        "output_count": output_count,
        "order": order,
        "center": _fraction_tuple_payload(center),
        "terms": [item.to_dict() for item in terms],
    }
    coefficient_signature = sha256_json(coefficient_payload)
    scope_payload = {
        "schema_version": 1,
        "jet_version": NONLINEAR_JET_VERSION,
        "coefficient_signature": coefficient_signature,
        "validity_radius": _fraction_tuple_payload(radius),
        "scope": "LOCAL_BOX_ONLY",
    }
    scope_signature = sha256_json(scope_payload)
    coupling = assess_nonlinear_coupling(form, terms)
    behavior_payload = {
        "schema_version": 1,
        "jet_version": NONLINEAR_JET_VERSION,
        "coefficient_signature": coefficient_signature,
        "scope_signature": scope_signature,
        "coupling_signature": coupling.signature,
    }
    warnings = [
        "A finite Taylor jet certifies only local truncated behavior around its exact expansion point; it never proves global nonlinear equivalence."
    ]
    if not any(item.degree >= 2 for item in terms):
        warnings.append("Jet contains no nonlinear term at the declared truncation order.")
    return CanonicalTaylorJet(
        schema_version=1,
        jet_version=NONLINEAR_JET_VERSION,
        parent_representative_behavior_signature=form.representative_behavior_signature,
        parent_semantic_signature=form.semantic_representative_signature,
        input_count=input_count,
        output_count=output_count,
        order=order,
        center=center,
        validity_radius=radius,
        terms=terms,
        coefficient_signature=coefficient_signature,
        scope_signature=scope_signature,
        local_behavior_signature=sha256_json(behavior_payload),
        coupling=coupling,
        local_equivalence_scope="LOCAL_TRUNCATED_JET_ONLY",
        global_equivalence_eligible=False,
        exact=True,
        warnings=tuple(warnings),
    )


def compare_taylor_jets(
    left: CanonicalTaylorJet,
    right: CanonicalTaylorJet,
) -> LocalJetComparison:
    if not isinstance(left, CanonicalTaylorJet) or not isinstance(right, CanonicalTaylorJet):
        raise EGCFError("compare_taylor_jets requires canonical SAA-7 jets")
    same_center = left.center == right.center
    same_parent = (
        left.parent_representative_behavior_signature
        == right.parent_representative_behavior_signature
        and left.parent_semantic_signature == right.parent_semantic_signature
    )
    coefficient_match = same_parent and left.coefficient_signature == right.coefficient_signature
    overlap = (
        tuple(min(a, b) for a, b in zip(left.validity_radius, right.validity_radius))
        if same_center and left.input_count == right.input_count
        else ()
    )
    if coefficient_match and same_center and (overlap or left.input_count == 0):
        status = "EXACT_LOCAL_JET_MATCH_ON_INTERSECTION"
    elif not same_parent:
        status = "INCOMPARABLE_PARENT_REPRESENTATION"
    elif not same_center:
        status = "DIFFERENT_EXPANSION_POINT"
    else:
        status = "DIFFERENT_LOCAL_JET"
    material = {
        "schema_version": 1,
        "jet_version": NONLINEAR_JET_VERSION,
        "left": left.local_behavior_signature,
        "right": right.local_behavior_signature,
        "status": status,
        "overlap_radius": _fraction_tuple_payload(overlap),
    }
    return LocalJetComparison(
        status=status,
        coefficient_match=coefficient_match,
        same_expansion_point=same_center,
        overlap_radius=overlap,
        global_equivalence_eligible=False,
        signature=sha256_json(material),
    )
