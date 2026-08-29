from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .jet import CanonicalTaylorJet, TaylorJetSpec, TaylorJetTerm, canonicalize_taylor_jet
from .nonlinear_search import CanonicalNonlinearRepresentativeForm
from .representative_form import CanonicalRepresentativeAlgorithmForm
from .semantic import SemanticCandidateMeaning, SemanticResolution


NONLINEAR_TRANSFORM_VERSION = "saa-exact-polynomial-automorphism-v1"
MAX_POLYNOMIAL_SHEAR_TERMS = 32
MAX_POLYNOMIAL_AUTOMORPHISM_DEPTH = 4
MAX_POLYNOMIAL_AUTOMORPHISM_CANDIDATES = 128
MAX_POLYNOMIAL_TRANSFORM_COEFFICIENT_BITS = 48


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must be exact and cannot be float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _degree(powers: Sequence[int]) -> int:
    return sum(int(value) for value in powers)


def _zero_powers(input_count: int) -> Tuple[int, ...]:
    return tuple(0 for _ in range(input_count))


def _unit_powers(input_count: int, index: int) -> Tuple[int, ...]:
    return tuple(1 if value == index else 0 for value in range(input_count))


def _powers_add(left: Sequence[int], right: Sequence[int]) -> Tuple[int, ...]:
    return tuple(int(a) + int(b) for a, b in zip(left, right))


def _coefficient_bits(value: Fraction) -> int:
    return max(abs(value.numerator).bit_length(), abs(value.denominator).bit_length())


def _canonical_text(value: str) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _poly_add(
    left: Mapping[Tuple[int, ...], Fraction],
    right: Mapping[Tuple[int, ...], Fraction],
) -> dict[Tuple[int, ...], Fraction]:
    result = dict(left)
    for powers, coefficient in right.items():
        result[powers] = result.get(powers, Fraction(0)) + coefficient
        if result[powers] == 0:
            del result[powers]
    return result


def _poly_mul(
    left: Mapping[Tuple[int, ...], Fraction],
    right: Mapping[Tuple[int, ...], Fraction],
    *,
    order: int,
) -> dict[Tuple[int, ...], Fraction]:
    result: dict[Tuple[int, ...], Fraction] = {}
    for left_powers, left_coefficient in left.items():
        for right_powers, right_coefficient in right.items():
            powers = _powers_add(left_powers, right_powers)
            if _degree(powers) > order:
                continue
            result[powers] = result.get(powers, Fraction(0)) + left_coefficient * right_coefficient
    return {powers: coefficient for powers, coefficient in result.items() if coefficient}


def _poly_pow(
    base: Mapping[Tuple[int, ...], Fraction],
    exponent: int,
    *,
    input_count: int,
    order: int,
) -> dict[Tuple[int, ...], Fraction]:
    result: dict[Tuple[int, ...], Fraction] = {_zero_powers(input_count): Fraction(1)}
    factor = dict(base)
    remaining = int(exponent)
    while remaining:
        if remaining & 1:
            result = _poly_mul(result, factor, order=order)
        remaining >>= 1
        if remaining:
            factor = _poly_mul(factor, factor, order=order)
    return result


@dataclass(frozen=True)
class PolynomialShearTerm:
    powers: Tuple[int, ...]
    coefficient: Fraction

    def to_dict(self) -> dict[str, Any]:
        return {
            "powers": list(self.powers),
            "coefficient": _fraction_payload(self.coefficient),
        }


@dataclass(frozen=True)
class ExactPolynomialShear:
    input_count: int
    target_input_index: int
    terms: Tuple[PolynomialShearTerm, ...]
    transform_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "EXACT_MULTI_TERM_POLYNOMIAL_SHEAR",
            "input_count": self.input_count,
            "target_input_index": self.target_input_index,
            "terms": [item.to_dict() for item in self.terms],
            "transform_signature": self.transform_signature,
        }


def make_polynomial_shear(
    *,
    input_count: int,
    target_input_index: int,
    terms: Sequence[PolynomialShearTerm],
) -> ExactPolynomialShear:
    count = int(input_count)
    target = int(target_input_index)
    if count < 1 or count > 8:
        raise EGCFError("SAA-7.5 polynomial shear input count outside bounded range")
    if target < 0 or target >= count:
        raise EGCFError("SAA-7.5 polynomial shear target outside input dimension")
    if not terms or len(terms) > MAX_POLYNOMIAL_SHEAR_TERMS:
        raise EGCFError("SAA-7.5 polynomial shear term count outside bounded range")
    accumulator: dict[Tuple[int, ...], Fraction] = {}
    for raw in terms:
        if not isinstance(raw, PolynomialShearTerm):
            raise EGCFError("SAA-7.5 shear terms must be PolynomialShearTerm")
        powers = tuple(int(value) for value in raw.powers)
        coefficient = _exact_fraction(raw.coefficient, label="polynomial shear coefficient")
        if len(powers) != count or any(value < 0 for value in powers):
            raise EGCFError("SAA-7.5 polynomial shear powers are invalid")
        if powers[target] != 0:
            raise EGCFError("exact polynomial shear cannot depend on its target coordinate")
        if _degree(powers) < 2 or _degree(powers) > 4:
            raise EGCFError("SAA-7.5 shear terms must be nonlinear and within Taylor order cap")
        if _coefficient_bits(coefficient) > MAX_POLYNOMIAL_TRANSFORM_COEFFICIENT_BITS:
            raise EGCFError("SAA-7.5 shear coefficient exceeds exact complexity budget")
        if coefficient:
            accumulator[powers] = accumulator.get(powers, Fraction(0)) + coefficient
    canonical = tuple(
        PolynomialShearTerm(powers, coefficient)
        for powers, coefficient in sorted(accumulator.items(), key=lambda item: (_degree(item[0]), item[0]))
        if coefficient
    )
    if not canonical:
        raise EGCFError("SAA-7.5 polynomial shear collapses to identity")
    payload = {
        "schema_version": 1,
        "transform_version": NONLINEAR_TRANSFORM_VERSION,
        "kind": "EXACT_MULTI_TERM_POLYNOMIAL_SHEAR",
        "input_count": count,
        "target_input_index": target,
        "terms": [item.to_dict() for item in canonical],
    }
    return ExactPolynomialShear(
        input_count=count,
        target_input_index=target,
        terms=canonical,
        transform_signature=sha256_json(payload),
    )


def _inverse_variables(transform: ExactPolynomialShear) -> Tuple[dict[Tuple[int, ...], Fraction], ...]:
    variables: list[dict[Tuple[int, ...], Fraction]] = [
        {_unit_powers(transform.input_count, index): Fraction(1)}
        for index in range(transform.input_count)
    ]
    target_poly = dict(variables[transform.target_input_index])
    for term in transform.terms:
        target_poly[term.powers] = target_poly.get(term.powers, Fraction(0)) - term.coefficient
        if target_poly[term.powers] == 0:
            del target_poly[term.powers]
    variables[transform.target_input_index] = target_poly
    return tuple(variables)


def _substitute(
    jet: CanonicalTaylorJet,
    variables: Sequence[Mapping[Tuple[int, ...], Fraction]],
) -> Tuple[TaylorJetTerm, ...]:
    output_polynomials: list[dict[Tuple[int, ...], Fraction]] = [
        {} for _ in range(jet.output_count)
    ]
    for term in jet.terms:
        term_poly: dict[Tuple[int, ...], Fraction] = {_zero_powers(jet.input_count): term.coefficient}
        for input_index, exponent in enumerate(term.powers):
            if exponent:
                term_poly = _poly_mul(
                    term_poly,
                    _poly_pow(
                        variables[input_index],
                        exponent,
                        input_count=jet.input_count,
                        order=jet.order,
                    ),
                    order=jet.order,
                )
        output_polynomials[term.output_index] = _poly_add(
            output_polynomials[term.output_index], term_poly
        )
    terms: list[TaylorJetTerm] = []
    for output_index, polynomial in enumerate(output_polynomials):
        for powers, coefficient in polynomial.items():
            if coefficient:
                terms.append(TaylorJetTerm(output_index, powers, coefficient))
    return tuple(terms)


def _transformed_radius(
    jet: CanonicalTaylorJet,
    transform: ExactPolynomialShear,
) -> Tuple[Fraction, ...]:
    excursion = Fraction(0)
    for term in transform.terms:
        bound = abs(term.coefficient)
        for radius, power in zip(jet.validity_radius, term.powers):
            if power:
                bound *= radius ** power
        excursion += bound
    radius = list(jet.validity_radius)
    target = transform.target_input_index
    radius[target] -= excursion
    if radius[target] <= 0:
        raise EGCFError("SAA-7.5 polynomial shear consumes complete certified target radius")
    center = jet.center[target]
    if center - radius[target] < 0 or center + radius[target] > 1:
        raise EGCFError("SAA-7.5 transformed local box leaves normalized [0,1]")
    return tuple(radius)


def apply_polynomial_shear(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    transform: ExactPolynomialShear,
) -> CanonicalTaylorJet:
    if transform.input_count != jet.input_count:
        raise EGCFError("SAA-7.5 polynomial shear dimension mismatches jet")
    if jet.parent_representative_behavior_signature != form.representative_behavior_signature:
        raise EGCFError("SAA-7.5 jet does not belong to supplied SAA-6 form")
    return canonicalize_taylor_jet(
        form,
        TaylorJetSpec(
            input_count=jet.input_count,
            output_count=jet.output_count,
            order=jet.order,
            center=jet.center,
            validity_radius=_transformed_radius(jet, transform),
            terms=_substitute(jet, _inverse_variables(transform)),
        ),
    )


@dataclass(frozen=True)
class ExactPolynomialAutomorphism:
    input_count: int
    transforms: Tuple[ExactPolynomialShear, ...]
    automorphism_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "EXACT_POLYNOMIAL_AUTOMORPHISM",
            "input_count": self.input_count,
            "transforms": [item.to_dict() for item in self.transforms],
            "inverse_order": [item.transform_signature for item in reversed(self.transforms)],
            "automorphism_signature": self.automorphism_signature,
        }


def make_polynomial_automorphism(
    transforms: Sequence[ExactPolynomialShear],
) -> ExactPolynomialAutomorphism:
    if not transforms or len(transforms) > MAX_POLYNOMIAL_AUTOMORPHISM_DEPTH:
        raise EGCFError("SAA-7.5 automorphism depth outside bounded range")
    if any(not isinstance(item, ExactPolynomialShear) for item in transforms):
        raise EGCFError("SAA-7.5 automorphism requires exact polynomial shears")
    count = transforms[0].input_count
    if any(item.input_count != count for item in transforms):
        raise EGCFError("SAA-7.5 automorphism transform dimensions differ")
    payload = {
        "schema_version": 1,
        "transform_version": NONLINEAR_TRANSFORM_VERSION,
        "kind": "EXACT_POLYNOMIAL_AUTOMORPHISM",
        "input_count": count,
        "transform_signatures": [item.transform_signature for item in transforms],
    }
    return ExactPolynomialAutomorphism(
        input_count=count,
        transforms=tuple(transforms),
        automorphism_signature=sha256_json(payload),
    )


def apply_polynomial_automorphism(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    automorphism: ExactPolynomialAutomorphism,
) -> CanonicalTaylorJet:
    current = jet
    for transform in automorphism.transforms:
        current = apply_polynomial_shear(form, current, transform)
    return current


def _linear_coefficient(jet: CanonicalTaylorJet, output: int, input_index: int) -> Fraction:
    powers = _unit_powers(jet.input_count, input_index)
    for term in jet.terms:
        if term.output_index == output and term.powers == powers:
            return term.coefficient
    return Fraction(0)


def _generated_grouped_shears(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
) -> Tuple[ExactPolynomialShear, ...]:
    output_to_input = {
        item.paired_output_index: item.canonical_position for item in form.inputs
    }
    problematic = {
        (item.output_index, item.powers, item.coefficient)
        for item in (*jet.coupling.cross_terms, *jet.coupling.off_pair_terms)
    }
    grouped: dict[int, list[PolynomialShearTerm]] = {}
    singles: list[tuple[int, PolynomialShearTerm]] = []
    for output, powers, coefficient in sorted(problematic, key=lambda item: (item[0], _degree(item[1]), item[1])):
        target = output_to_input.get(output)
        if target is None or powers[target] != 0 or _degree(powers) < 2:
            continue
        linear = _linear_coefficient(jet, output, target)
        if linear == 0:
            continue
        term = PolynomialShearTerm(tuple(powers), coefficient / linear)
        grouped.setdefault(target, []).append(term)
        singles.append((target, term))
    candidates: dict[str, ExactPolynomialShear] = {}
    for target, terms in grouped.items():
        try:
            transform = make_polynomial_shear(
                input_count=jet.input_count,
                target_input_index=target,
                terms=terms,
            )
            candidates[transform.transform_signature] = transform
        except EGCFError:
            pass
    for target, term in singles:
        try:
            transform = make_polynomial_shear(
                input_count=jet.input_count,
                target_input_index=target,
                terms=(term,),
            )
            candidates[transform.transform_signature] = transform
        except EGCFError:
            pass
    return tuple(candidates[key] for key in sorted(candidates))


@dataclass(frozen=True)
class PolynomialSemanticIssue:
    issue_id: str
    coordinate_index: int
    affected_output_indices: Tuple[int, ...]
    source_input_indices: Tuple[int, ...]
    previous_meaning: str
    transform_signatures: Tuple[str, ...]
    status: str
    signature: str
    questions: Tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_kind": "POLYNOMIAL_AUTOMORPHISM_COORDINATE",
            "coordinate_kind": "NONLINEAR_REPRESENTATIVE_INPUT",
            "coordinate_index": self.coordinate_index,
            "affected_output_indices": list(self.affected_output_indices),
            "source_input_indices": list(self.source_input_indices),
            "previous_meaning": self.previous_meaning,
            "transform_signatures": list(self.transform_signatures),
            "status": self.status,
            "resolution_required": True,
            "signature": self.signature,
            "questions": list(self.questions),
        }


def _issues_for_automorphism(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    transforms: Sequence[ExactPolynomialShear],
) -> Tuple[PolynomialSemanticIssue, ...]:
    by_target: dict[int, list[ExactPolynomialShear]] = {}
    for transform in transforms:
        by_target.setdefault(transform.target_input_index, []).append(transform)
    meanings = {item.canonical_position: item.canonical_meaning for item in form.inputs}
    issues: list[PolynomialSemanticIssue] = []
    for target in sorted(by_target):
        sources = {target}
        for transform in by_target[target]:
            for term in transform.terms:
                sources.update(index for index, power in enumerate(term.powers) if power)
        affected = jet.coupling.dependency_by_input[target]
        previous = meanings.get(target, f"r{target}")
        payload = {
            "schema_version": 1,
            "transform_version": NONLINEAR_TRANSFORM_VERSION,
            "coordinate_index": target,
            "affected_output_indices": list(affected),
            "source_input_indices": sorted(sources),
            "previous_meaning": previous,
            "transform_signatures": [item.transform_signature for item in by_target[target]],
        }
        signature = sha256_json(payload)
        issues.append(
            PolynomialSemanticIssue(
                issue_id=f"polynomial-semantic:{signature[:24]}",
                coordinate_index=target,
                affected_output_indices=tuple(affected),
                source_input_indices=tuple(sorted(sources)),
                previous_meaning=previous,
                transform_signatures=tuple(item.transform_signature for item in by_target[target]),
                status="UNRESOLVED_NONLINEAR_SEMANTICS",
                signature=signature,
                questions=(
                    f"What independent quantity does polynomial representative coordinate v{target} mean?",
                    f"Does the previous meaning '{previous}' survive the multi-term nonlinear transformation?",
                    f"Why do source coordinates {tuple(sorted(sources))} combine into v{target}?",
                    "What evidence falsifies this proposed polynomial coordinate meaning?",
                    "Is this meaning stable across multiple operating regions?",
                ),
            )
        )
    return tuple(issues)


@dataclass(frozen=True)
class PolynomialAutomorphismCandidate:
    transformed_jet: CanonicalTaylorJet
    transforms: Tuple[ExactPolynomialShear, ...]
    source_coupling_score: int
    coupling_score: int
    exact_invertible: bool
    mathematical_eligible: bool
    semantic_issues: Tuple[PolynomialSemanticIssue, ...]
    candidate_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformed_jet": self.transformed_jet.to_dict(),
            "transforms": [item.to_dict() for item in self.transforms],
            "source_coupling_score": self.source_coupling_score,
            "coupling_score": self.coupling_score,
            "exact_invertible": self.exact_invertible,
            "mathematical_eligible": self.mathematical_eligible,
            "semantic_issues": [item.to_dict() for item in self.semantic_issues],
            "candidate_signature": self.candidate_signature,
        }


@dataclass(frozen=True)
class PolynomialAutomorphismSearch:
    schema_version: int
    transform_version: str
    source_jet_signature: str
    status: str
    representative_found: bool
    best_candidate: PolynomialAutomorphismCandidate
    candidates_evaluated: int
    search_depth: int
    budget_exhausted: bool
    audit_hash: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transform_version": self.transform_version,
            "source_jet_signature": self.source_jet_signature,
            "status": self.status,
            "representative_found": self.representative_found,
            "best_candidate": self.best_candidate.to_dict(),
            "candidates_evaluated": self.candidates_evaluated,
            "search_depth": self.search_depth,
            "budget_exhausted": self.budget_exhausted,
            "audit_hash": self.audit_hash,
            "warnings": list(self.warnings),
        }


def _candidate(
    form: CanonicalRepresentativeAlgorithmForm,
    source: CanonicalTaylorJet,
    transformed: CanonicalTaylorJet,
    transforms: Sequence[ExactPolynomialShear],
) -> PolynomialAutomorphismCandidate:
    issues = _issues_for_automorphism(form, transformed, transforms)
    payload = {
        "schema_version": 1,
        "transform_version": NONLINEAR_TRANSFORM_VERSION,
        "source_jet_signature": source.local_behavior_signature,
        "transformed_jet_signature": transformed.local_behavior_signature,
        "transform_signatures": [item.transform_signature for item in transforms],
        "coupling_score": transformed.coupling.coupling_score,
        "semantic_issue_signatures": [item.signature for item in issues],
    }
    return PolynomialAutomorphismCandidate(
        transformed_jet=transformed,
        transforms=tuple(transforms),
        source_coupling_score=source.coupling.coupling_score,
        coupling_score=transformed.coupling.coupling_score,
        exact_invertible=True,
        mathematical_eligible=transformed.coupling.representative,
        semantic_issues=issues,
        candidate_signature=sha256_json(payload),
    )


def search_polynomial_automorphisms(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    *,
    max_candidates: int = MAX_POLYNOMIAL_AUTOMORPHISM_CANDIDATES,
    max_depth: int = MAX_POLYNOMIAL_AUTOMORPHISM_DEPTH,
) -> PolynomialAutomorphismSearch:
    if jet.parent_representative_behavior_signature != form.representative_behavior_signature:
        raise EGCFError("SAA-7.5 source jet belongs to a different representative form")
    if max_candidates < 1 or max_candidates > MAX_POLYNOMIAL_AUTOMORPHISM_CANDIDATES:
        raise EGCFError("SAA-7.5 search budget outside bounded range")
    if max_depth < 0 or max_depth > MAX_POLYNOMIAL_AUTOMORPHISM_DEPTH:
        raise EGCFError("SAA-7.5 search depth outside bounded range")
    identity = _candidate(form, jet, jet, ())
    if identity.mathematical_eligible:
        payload = {
            "source": jet.local_behavior_signature,
            "status": "POLYNOMIAL_REPRESENTATIVE_ALREADY_FOUND",
            "candidate": identity.candidate_signature,
        }
        return PolynomialAutomorphismSearch(
            1,
            NONLINEAR_TRANSFORM_VERSION,
            jet.local_behavior_signature,
            "POLYNOMIAL_REPRESENTATIVE_ALREADY_FOUND",
            True,
            identity,
            0,
            0,
            False,
            sha256_json(payload),
            ("No broader nonlinear transform was required.",),
        )

    queue: list[tuple[CanonicalTaylorJet, Tuple[ExactPolynomialShear, ...]]] = [(jet, ())]
    visited = {jet.local_behavior_signature}
    best = identity
    evaluated = 0
    reached_depth = 0
    exhausted = False
    while queue:
        current, history = queue.pop(0)
        if len(history) >= max_depth:
            continue
        for transform in _generated_grouped_shears(form, current):
            if evaluated >= max_candidates:
                exhausted = True
                queue.clear()
                break
            evaluated += 1
            try:
                transformed = apply_polynomial_shear(form, current, transform)
            except EGCFError:
                continue
            if transformed.local_behavior_signature in visited:
                continue
            visited.add(transformed.local_behavior_signature)
            next_history = (*history, transform)
            reached_depth = max(reached_depth, len(next_history))
            candidate = _candidate(form, jet, transformed, next_history)
            if (
                candidate.coupling_score < best.coupling_score
                or (
                    candidate.coupling_score == best.coupling_score
                    and len(candidate.transforms) < len(best.transforms)
                )
                or (
                    candidate.coupling_score == best.coupling_score
                    and len(candidate.transforms) == len(best.transforms)
                    and candidate.candidate_signature < best.candidate_signature
                )
            ):
                best = candidate
            if candidate.mathematical_eligible:
                queue.clear()
                break
            queue.append((transformed, next_history))
        if best.mathematical_eligible:
            break
    if best.mathematical_eligible:
        status = "POLYNOMIAL_REPRESENTATIVE_FORM_FOUND"
        found = True
    elif exhausted:
        status = "POLYNOMIAL_AUTOMORPHISM_BUDGET_EXHAUSTED"
        found = False
    else:
        status = "POLYNOMIAL_REPRESENTATION_UNRESOLVED"
        found = False
    payload = {
        "schema_version": 1,
        "transform_version": NONLINEAR_TRANSFORM_VERSION,
        "source": jet.local_behavior_signature,
        "status": status,
        "best": best.candidate_signature,
        "evaluated": evaluated,
        "depth": reached_depth,
        "budget_exhausted": exhausted,
    }
    return PolynomialAutomorphismSearch(
        schema_version=1,
        transform_version=NONLINEAR_TRANSFORM_VERSION,
        source_jet_signature=jet.local_behavior_signature,
        status=status,
        representative_found=found,
        best_candidate=best,
        candidates_evaluated=evaluated,
        search_depth=reached_depth,
        budget_exhausted=exhausted,
        audit_hash=sha256_json(payload),
        warnings=(
            "SAA-7.5 searches bounded exact polynomial automorphisms generated by multi-term target-independent shears; unresolved does not prove no better nonlinear representation exists.",
        ),
    )


def canonicalize_polynomial_representative(
    form: CanonicalRepresentativeAlgorithmForm,
    search: PolynomialAutomorphismSearch,
    *,
    semantic_candidates: Sequence[SemanticCandidateMeaning] = (),
    semantic_resolutions: Sequence[SemanticResolution] = (),
) -> CanonicalNonlinearRepresentativeForm:
    if not search.representative_found or not search.best_candidate.mathematical_eligible:
        raise EGCFError("SAA-7.5 has no mathematically representative polynomial candidate")
    candidate = search.best_candidate
    meanings = [
        item.canonical_meaning
        for item in sorted(form.inputs, key=lambda value: value.canonical_position)
    ]
    candidate_by_issue = {item.issue_id: item for item in semantic_candidates}
    resolution_by_issue = {item.issue_id: item for item in semantic_resolutions}
    issues = {item.issue_id: item for item in candidate.semantic_issues}
    if set(candidate_by_issue) != set(issues) or set(resolution_by_issue) != set(issues):
        if issues:
            raise EGCFError("SAA-7.5 transformed coordinates require exact semantic coverage")
        if candidate_by_issue or resolution_by_issue:
            raise EGCFError("SAA-7.5 received semantic records for unchanged coordinates")
    for issue_id, issue in issues.items():
        semantic_candidate = candidate_by_issue[issue_id]
        resolution = resolution_by_issue[issue_id]
        if resolution.candidate_id != semantic_candidate.candidate_id:
            raise EGCFError("SAA-7.5 semantic resolution references different candidate")
        if (
            resolution.status != "SEMANTICALLY_RESOLVED"
            or not resolution.canonical_semantic_eligible
            or resolution.semantic_fit_bp != 10000
        ):
            raise EGCFError("SAA-7.5 polynomial coordinate semantics remain unresolved")
        meanings[issue.coordinate_index] = _canonical_text(semantic_candidate.meaning)
    semantic_payload = {
        "schema_version": 1,
        "representation_version": NONLINEAR_TRANSFORM_VERSION,
        "parent_semantic_signature": form.semantic_representative_signature,
        "resolved_input_meanings": meanings,
        "semantic_resolution_signatures": [
            resolution_by_issue[item.issue_id].resolution_signature for item in candidate.semantic_issues
        ],
    }
    semantic_signature = sha256_json(semantic_payload)
    behavior_payload = {
        "schema_version": 1,
        "representation_version": NONLINEAR_TRANSFORM_VERSION,
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "transformed_jet_coefficient_signature": candidate.transformed_jet.coefficient_signature,
        "transformed_jet_scope_signature": candidate.transformed_jet.scope_signature,
        "semantic_signature": semantic_signature,
    }
    behavior_signature = sha256_json(behavior_payload)
    audit_payload = {
        "search_audit_hash": search.audit_hash,
        "candidate_signature": candidate.candidate_signature,
        "transform_signatures": [item.transform_signature for item in candidate.transforms],
        "local_representative_behavior_signature": behavior_signature,
    }
    return CanonicalNonlinearRepresentativeForm(
        schema_version=1,
        representation_version=NONLINEAR_TRANSFORM_VERSION,
        parent_representative_behavior_signature=form.representative_behavior_signature,
        source_jet_signature=search.source_jet_signature,
        transformed_jet=candidate.transformed_jet,
        transform_signatures=tuple(item.transform_signature for item in candidate.transforms),
        resolved_input_meanings=tuple(meanings),
        semantic_signature=semantic_signature,
        local_representative_behavior_signature=behavior_signature,
        local_canonical_eligible=True,
        global_equivalence_eligible=False,
        store_status="ELIGIBLE_LOCAL_NONLINEAR_REPRESENTATIVE_FORM",
        audit_hash=sha256_json(audit_payload),
        warnings=(
            "SAA-7.5 polynomial automorphism identity remains local to the qualified Taylor scope.",
            "Exact invertibility of the coordinate map does not convert a finite jet into global nonlinear equivalence.",
        ),
    )
