from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .jet import (
    MAX_JET_ORDER,
    CanonicalTaylorJet,
    TaylorJetSpec,
    TaylorJetTerm,
    canonicalize_taylor_jet,
)
from .representative_form import CanonicalRepresentativeAlgorithmForm
from .semantic import SemanticCandidateMeaning, SemanticResolution


NONLINEAR_REPRESENTATION_VERSION = "saa-nonlinear-representation-v1"
MAX_NONLINEAR_SEARCH_CANDIDATES = 128
MAX_NONLINEAR_SEARCH_DEPTH = 2
MAX_NONLINEAR_TRANSFORM_COEFFICIENT_BITS = 32


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _fraction_tuple_payload(values: Sequence[Fraction]) -> list[list[int]]:
    return [_fraction_payload(value) for value in values]


def _canonical_text(value: str) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _exact_fraction(value: Any, *, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise EGCFError(f"{label} must use an exact integer/Fraction/rational string, not float")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EGCFError(f"invalid exact rational {label}: {value!r}") from exc


def _degree(powers: Sequence[int]) -> int:
    return sum(int(value) for value in powers)


def _zero_powers(input_count: int) -> Tuple[int, ...]:
    return tuple(0 for _ in range(input_count))


def _unit_powers(input_count: int, index: int) -> Tuple[int, ...]:
    return tuple(1 if item == index else 0 for item in range(input_count))


def _powers_add(left: Sequence[int], right: Sequence[int]) -> Tuple[int, ...]:
    return tuple(int(a) + int(b) for a, b in zip(left, right))


def _coefficient_bits(value: Fraction) -> int:
    return max(abs(value.numerator).bit_length(), abs(value.denominator).bit_length())


def _validate_parent(form: CanonicalRepresentativeAlgorithmForm) -> None:
    if not isinstance(form, CanonicalRepresentativeAlgorithmForm):
        raise EGCFError("SAA-7.1 requires a SAA-6 CanonicalRepresentativeAlgorithmForm")
    if not form.canonical_admission_eligible:
        raise EGCFError("SAA-7.1 parent SAA-6 form is not canonical-admission eligible")


@dataclass(frozen=True)
class NonlinearShearTransform:
    target_input_index: int
    monomial_powers: Tuple[int, ...]
    coefficient: Fraction
    transform_signature: str

    @property
    def degree(self) -> int:
        return _degree(self.monomial_powers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "EXACT_TRIANGULAR_POLYNOMIAL_SHEAR",
            "target_input_index": self.target_input_index,
            "monomial_powers": list(self.monomial_powers),
            "degree": self.degree,
            "coefficient": _fraction_payload(self.coefficient),
            "transform_signature": self.transform_signature,
        }


def make_nonlinear_shear(
    *,
    target_input_index: int,
    monomial_powers: Sequence[int],
    coefficient: Any,
) -> NonlinearShearTransform:
    powers = tuple(int(value) for value in monomial_powers)
    target = int(target_input_index)
    if target < 0 or target >= len(powers):
        raise EGCFError("nonlinear shear target outside coordinate dimension")
    if any(value < 0 for value in powers):
        raise EGCFError("nonlinear shear powers cannot be negative")
    if powers[target] != 0:
        raise EGCFError("exact triangular shear monomial cannot depend on its target coordinate")
    degree = _degree(powers)
    if degree < 2 or degree > MAX_JET_ORDER:
        raise EGCFError("SAA-7.1 shear monomial degree must be nonlinear and within jet cap")
    exact_coefficient = _exact_fraction(coefficient, label="nonlinear shear coefficient")
    if exact_coefficient == 0:
        raise EGCFError("nonlinear shear coefficient cannot be zero")
    if _coefficient_bits(exact_coefficient) > MAX_NONLINEAR_TRANSFORM_COEFFICIENT_BITS:
        raise EGCFError("nonlinear shear coefficient exceeds bounded exact complexity")
    material = {
        "schema_version": 1,
        "representation_version": NONLINEAR_REPRESENTATION_VERSION,
        "kind": "EXACT_TRIANGULAR_POLYNOMIAL_SHEAR",
        "target_input_index": target,
        "monomial_powers": list(powers),
        "coefficient": _fraction_payload(exact_coefficient),
    }
    return NonlinearShearTransform(
        target_input_index=target,
        monomial_powers=powers,
        coefficient=exact_coefficient,
        transform_signature=sha256_json(material),
    )


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
            result[powers] = result.get(powers, Fraction(0)) + (
                left_coefficient * right_coefficient
            )
    return {powers: value for powers, value in result.items() if value != 0}


def _poly_pow(
    base: Mapping[Tuple[int, ...], Fraction],
    exponent: int,
    *,
    input_count: int,
    order: int,
) -> dict[Tuple[int, ...], Fraction]:
    if exponent < 0:
        raise EGCFError("polynomial exponent cannot be negative")
    result: dict[Tuple[int, ...], Fraction] = {_zero_powers(input_count): Fraction(1)}
    factor = dict(base)
    remaining = exponent
    while remaining:
        if remaining & 1:
            result = _poly_mul(result, factor, order=order)
        remaining >>= 1
        if remaining:
            factor = _poly_mul(factor, factor, order=order)
    return result


def _jet_polynomials(jet: CanonicalTaylorJet) -> list[dict[Tuple[int, ...], Fraction]]:
    result: list[dict[Tuple[int, ...], Fraction]] = [
        {} for _ in range(jet.output_count)
    ]
    for term in jet.terms:
        result[term.output_index][term.powers] = term.coefficient
    return result


def _inverse_shear_variables(
    transform: NonlinearShearTransform,
    *,
    input_count: int,
) -> Tuple[dict[Tuple[int, ...], Fraction], ...]:
    variables: list[dict[Tuple[int, ...], Fraction]] = []
    for index in range(input_count):
        variables.append({_unit_powers(input_count, index): Fraction(1)})
    target = transform.target_input_index
    target_poly = dict(variables[target])
    target_poly[transform.monomial_powers] = (
        target_poly.get(transform.monomial_powers, Fraction(0)) - transform.coefficient
    )
    variables[target] = target_poly
    return tuple(variables)


def _substitute_inverse_shear(
    jet: CanonicalTaylorJet,
    transform: NonlinearShearTransform,
) -> Tuple[TaylorJetTerm, ...]:
    variables = _inverse_shear_variables(transform, input_count=jet.input_count)
    result_terms: list[TaylorJetTerm] = []
    for output_index, polynomial in enumerate(_jet_polynomials(jet)):
        transformed: dict[Tuple[int, ...], Fraction] = {}
        for powers, coefficient in polynomial.items():
            term_poly: dict[Tuple[int, ...], Fraction] = {
                _zero_powers(jet.input_count): coefficient
            }
            for input_index, exponent in enumerate(powers):
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
            transformed = _poly_add(transformed, term_poly)
        for powers, coefficient in transformed.items():
            if coefficient:
                result_terms.append(
                    TaylorJetTerm(
                        output_index=output_index,
                        powers=powers,
                        coefficient=coefficient,
                    )
                )
    return tuple(result_terms)


def _transformed_radius(
    jet: CanonicalTaylorJet,
    transform: NonlinearShearTransform,
) -> Tuple[Fraction, ...]:
    monomial_bound = Fraction(1)
    for radius, power in zip(jet.validity_radius, transform.monomial_powers):
        if power:
            monomial_bound *= radius ** power
    excursion = abs(transform.coefficient) * monomial_bound
    radius = list(jet.validity_radius)
    target = transform.target_input_index
    radius[target] = radius[target] - excursion
    if radius[target] <= 0:
        raise EGCFError("nonlinear shear consumes the complete certified local target radius")
    center = jet.center[target]
    if center - radius[target] < 0 or center + radius[target] > 1:
        raise EGCFError("nonlinear shear transformed local domain leaves normalized [0,1]")
    return tuple(radius)


def apply_nonlinear_shear(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    transform: NonlinearShearTransform,
) -> CanonicalTaylorJet:
    _validate_parent(form)
    if jet.parent_representative_behavior_signature != form.representative_behavior_signature:
        raise EGCFError("nonlinear shear jet does not belong to supplied SAA-6 form")
    if len(transform.monomial_powers) != jet.input_count:
        raise EGCFError("nonlinear shear dimension mismatches Taylor jet")
    return canonicalize_taylor_jet(
        form,
        TaylorJetSpec(
            input_count=jet.input_count,
            output_count=jet.output_count,
            order=jet.order,
            center=jet.center,
            validity_radius=_transformed_radius(jet, transform),
            terms=_substitute_inverse_shear(jet, transform),
        ),
    )


@dataclass(frozen=True)
class NonlinearSemanticRepresentationIssue:
    issue_id: str
    issue_kind: str
    coordinate_kind: str
    coordinate_index: int
    coordinate_label: str
    previous_meaning: str
    transform_signatures: Tuple[str, ...]
    source_input_indices: Tuple[int, ...]
    affected_output_indices: Tuple[int, ...]
    status: str
    resolution_required: bool
    questions: Tuple[str, ...]
    source_representation_signature: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_kind": self.issue_kind,
            "coordinate_kind": self.coordinate_kind,
            "coordinate_index": self.coordinate_index,
            "coordinate_label": self.coordinate_label,
            "previous_meaning": self.previous_meaning,
            "transform_signatures": list(self.transform_signatures),
            "source_input_indices": list(self.source_input_indices),
            "affected_output_indices": list(self.affected_output_indices),
            "status": self.status,
            "resolution_required": self.resolution_required,
            "questions": list(self.questions),
            "source_representation_signature": self.source_representation_signature,
            "signature": self.signature,
        }


def _semantic_issues_for_history(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    transforms: Sequence[NonlinearShearTransform],
) -> Tuple[NonlinearSemanticRepresentationIssue, ...]:
    if not transforms:
        return ()
    by_target: dict[int, list[NonlinearShearTransform]] = {}
    for transform in transforms:
        by_target.setdefault(transform.target_input_index, []).append(transform)
    input_meanings = {
        item.canonical_position: item.canonical_meaning for item in form.inputs
    }
    issues: list[NonlinearSemanticRepresentationIssue] = []
    for target in sorted(by_target):
        target_transforms = by_target[target]
        sources: set[int] = {target}
        for transform in target_transforms:
            sources.update(
                index for index, power in enumerate(transform.monomial_powers) if power
            )
        affected = jet.coupling.dependency_by_input[target]
        previous = input_meanings.get(target, f"r{target}")
        material = {
            "schema_version": 1,
            "representation_version": NONLINEAR_REPRESENTATION_VERSION,
            "issue_kind": "NONLINEAR_REPRESENTATIVE_COORDINATE",
            "coordinate_index": target,
            "previous_meaning": previous,
            "source_input_indices": sorted(sources),
            "transform_signatures": [item.transform_signature for item in target_transforms],
            "affected_output_indices": list(affected),
            "source_representation_signature": jet.local_behavior_signature,
        }
        signature = sha256_json(material)
        questions = (
            f"What independent domain quantity does nonlinear coordinate v{target} actually represent?",
            f"Does the previous meaning '{previous}' remain valid after the nonlinear coordinate change?",
            f"Which mechanism explains why v{target} requires the discovered nonlinear combination of source coordinates?",
            f"Which outputs should vary when only v{target} changes inside the qualified local domain?",
            f"What observation would falsify the proposed meaning of v{target}?",
            "Is the proposed meaning stable across more than one expansion point, or only a local interpretation?",
        )
        issues.append(
            NonlinearSemanticRepresentationIssue(
                issue_id=f"nonlinear-semantic:{signature[:24]}",
                issue_kind="NONLINEAR_REPRESENTATIVE_COORDINATE",
                coordinate_kind="NONLINEAR_REPRESENTATIVE_INPUT",
                coordinate_index=target,
                coordinate_label=f"v{target}",
                previous_meaning=previous,
                transform_signatures=tuple(
                    item.transform_signature for item in target_transforms
                ),
                source_input_indices=tuple(sorted(sources)),
                affected_output_indices=tuple(affected),
                status="UNRESOLVED_NONLINEAR_SEMANTICS",
                resolution_required=True,
                questions=questions,
                source_representation_signature=jet.local_behavior_signature,
                signature=signature,
            )
        )
    return tuple(issues)


@dataclass(frozen=True)
class NonlinearRepresentativeCandidate:
    source_jet_signature: str
    transformed_jet: CanonicalTaylorJet
    transforms: Tuple[NonlinearShearTransform, ...]
    source_coupling_score: int
    coupling_score: int
    exact_invertible: bool
    mathematical_eligible: bool
    semantic_issues: Tuple[NonlinearSemanticRepresentationIssue, ...]
    local_canonical_eligible: bool
    candidate_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_jet_signature": self.source_jet_signature,
            "transformed_jet": self.transformed_jet.to_dict(),
            "transforms": [item.to_dict() for item in self.transforms],
            "source_coupling_score": self.source_coupling_score,
            "coupling_score": self.coupling_score,
            "exact_invertible": self.exact_invertible,
            "mathematical_eligible": self.mathematical_eligible,
            "semantic_issues": [item.to_dict() for item in self.semantic_issues],
            "local_canonical_eligible": self.local_canonical_eligible,
            "candidate_signature": self.candidate_signature,
        }


@dataclass(frozen=True)
class NonlinearRepresentativeSearch:
    schema_version: int
    representation_version: str
    source_jet_signature: str
    status: str
    representative_found: bool
    best_candidate: NonlinearRepresentativeCandidate | None
    candidates_evaluated: int
    search_depth: int
    search_budget: int
    budget_exhausted: bool
    explored_signatures: Tuple[str, ...]
    audit_hash: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "representation_version": self.representation_version,
            "source_jet_signature": self.source_jet_signature,
            "status": self.status,
            "representative_found": self.representative_found,
            "best_candidate": (
                self.best_candidate.to_dict() if self.best_candidate is not None else None
            ),
            "candidates_evaluated": self.candidates_evaluated,
            "search_depth": self.search_depth,
            "search_budget": self.search_budget,
            "budget_exhausted": self.budget_exhausted,
            "explored_signatures": list(self.explored_signatures),
            "audit_hash": self.audit_hash,
            "warnings": list(self.warnings),
        }


def _linear_coefficient(
    jet: CanonicalTaylorJet,
    *,
    output_index: int,
    input_index: int,
) -> Fraction:
    target_powers = _unit_powers(jet.input_count, input_index)
    for term in jet.terms:
        if term.output_index == output_index and term.powers == target_powers:
            return term.coefficient
    return Fraction(0)


def _generated_shears(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
) -> Tuple[NonlinearShearTransform, ...]:
    output_to_input = {
        item.paired_output_index: item.canonical_position for item in form.inputs
    }
    problematic = {
        (item.output_index, item.powers, item.coefficient)
        for item in (*jet.coupling.cross_terms, *jet.coupling.off_pair_terms)
    }
    candidates: dict[str, NonlinearShearTransform] = {}
    for output_index, powers, coefficient in sorted(
        problematic,
        key=lambda item: (item[0], _degree(item[1]), item[1], item[2]),
    ):
        if _degree(powers) < 2:
            continue
        target = output_to_input.get(output_index)
        if target is None or powers[target] != 0:
            continue
        linear = _linear_coefficient(
            jet,
            output_index=output_index,
            input_index=target,
        )
        if linear == 0:
            continue
        try:
            transform = make_nonlinear_shear(
                target_input_index=target,
                monomial_powers=powers,
                coefficient=coefficient / linear,
            )
        except EGCFError:
            continue
        candidates[transform.transform_signature] = transform
    return tuple(candidates[key] for key in sorted(candidates))


def _candidate_for(
    form: CanonicalRepresentativeAlgorithmForm,
    source: CanonicalTaylorJet,
    transformed: CanonicalTaylorJet,
    transforms: Sequence[NonlinearShearTransform],
) -> NonlinearRepresentativeCandidate:
    issues = _semantic_issues_for_history(form, transformed, transforms)
    mathematical_eligible = transformed.coupling.representative
    material = {
        "schema_version": 1,
        "representation_version": NONLINEAR_REPRESENTATION_VERSION,
        "source_jet_signature": source.local_behavior_signature,
        "transformed_jet_signature": transformed.local_behavior_signature,
        "transform_signatures": [item.transform_signature for item in transforms],
        "source_coupling_score": source.coupling.coupling_score,
        "coupling_score": transformed.coupling.coupling_score,
        "semantic_issue_signatures": [item.signature for item in issues],
    }
    return NonlinearRepresentativeCandidate(
        source_jet_signature=source.local_behavior_signature,
        transformed_jet=transformed,
        transforms=tuple(transforms),
        source_coupling_score=source.coupling.coupling_score,
        coupling_score=transformed.coupling.coupling_score,
        exact_invertible=True,
        mathematical_eligible=mathematical_eligible,
        semantic_issues=issues,
        local_canonical_eligible=mathematical_eligible and not issues,
        candidate_signature=sha256_json(material),
    )


def search_nonlinear_representative_coordinates(
    form: CanonicalRepresentativeAlgorithmForm,
    jet: CanonicalTaylorJet,
    *,
    max_candidates: int = MAX_NONLINEAR_SEARCH_CANDIDATES,
    max_depth: int = MAX_NONLINEAR_SEARCH_DEPTH,
) -> NonlinearRepresentativeSearch:
    _validate_parent(form)
    if not isinstance(jet, CanonicalTaylorJet):
        raise EGCFError("SAA-7.1 requires a canonical SAA-7 Taylor jet")
    if jet.parent_representative_behavior_signature != form.representative_behavior_signature:
        raise EGCFError("SAA-7.1 Taylor jet does not belong to supplied SAA-6 form")
    if max_candidates < 1 or max_candidates > MAX_NONLINEAR_SEARCH_CANDIDATES:
        raise EGCFError("SAA-7.1 candidate budget outside bounded range")
    if max_depth < 0 or max_depth > MAX_NONLINEAR_SEARCH_DEPTH:
        raise EGCFError("SAA-7.1 search depth outside bounded range")

    identity = _candidate_for(form, jet, jet, ())
    if jet.coupling.representative:
        material = {
            "schema_version": 1,
            "representation_version": NONLINEAR_REPRESENTATION_VERSION,
            "source_jet_signature": jet.local_behavior_signature,
            "status": "NONLINEAR_REPRESENTATIVE_ALREADY_FOUND",
            "best_candidate": identity.candidate_signature,
        }
        return NonlinearRepresentativeSearch(
            schema_version=1,
            representation_version=NONLINEAR_REPRESENTATION_VERSION,
            source_jet_signature=jet.local_behavior_signature,
            status="NONLINEAR_REPRESENTATIVE_ALREADY_FOUND",
            representative_found=True,
            best_candidate=identity,
            candidates_evaluated=0,
            search_depth=0,
            search_budget=max_candidates,
            budget_exhausted=False,
            explored_signatures=(jet.local_behavior_signature,),
            audit_hash=sha256_json(material),
            warnings=(
                "SAA-7.1 found no nonlinear representational defect; existing SAA-6 semantics remain inherited.",
            ),
        )

    queue: list[tuple[CanonicalTaylorJet, Tuple[NonlinearShearTransform, ...]]] = [
        (jet, ())
    ]
    visited = {jet.local_behavior_signature}
    explored = [jet.local_behavior_signature]
    evaluated = 0
    best = identity
    budget_exhausted = False
    reached_depth = 0

    while queue:
        current, history = queue.pop(0)
        if len(history) >= max_depth:
            continue
        transforms = _generated_shears(form, current)
        for transform in transforms:
            if evaluated >= max_candidates:
                budget_exhausted = True
                queue.clear()
                break
            evaluated += 1
            try:
                transformed = apply_nonlinear_shear(form, current, transform)
            except EGCFError:
                continue
            if transformed.local_behavior_signature in visited:
                continue
            visited.add(transformed.local_behavior_signature)
            explored.append(transformed.local_behavior_signature)
            next_history = (*history, transform)
            reached_depth = max(reached_depth, len(next_history))
            candidate = _candidate_for(form, jet, transformed, next_history)
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
        status = "NONLINEAR_REPRESENTATIVE_FORM_FOUND"
        found = True
    elif budget_exhausted:
        status = "NONLINEAR_SEARCH_BUDGET_EXHAUSTED"
        found = False
    else:
        status = "NONLINEAR_REPRESENTATION_UNRESOLVED"
        found = False

    material = {
        "schema_version": 1,
        "representation_version": NONLINEAR_REPRESENTATION_VERSION,
        "source_jet_signature": jet.local_behavior_signature,
        "status": status,
        "best_candidate": best.candidate_signature,
        "candidates_evaluated": evaluated,
        "search_depth": reached_depth,
        "search_budget": max_candidates,
        "budget_exhausted": budget_exhausted,
        "explored_signatures": explored,
    }
    return NonlinearRepresentativeSearch(
        schema_version=1,
        representation_version=NONLINEAR_REPRESENTATION_VERSION,
        source_jet_signature=jet.local_behavior_signature,
        status=status,
        representative_found=found,
        best_candidate=best,
        candidates_evaluated=evaluated,
        search_depth=reached_depth,
        search_budget=max_candidates,
        budget_exhausted=budget_exhausted,
        explored_signatures=tuple(explored),
        audit_hash=sha256_json(material),
        warnings=(
            "SAA-7.1 searches only bounded exact triangular polynomial shears; unresolved does not prove that no representative nonlinear coordinates exist.",
            "Any transformed coordinate receives unresolved semantics and cannot become locally canonical until its new meaning is independently evidenced and falsifier-tested.",
        ),
    )


@dataclass(frozen=True)
class CanonicalNonlinearRepresentativeForm:
    schema_version: int
    representation_version: str
    parent_representative_behavior_signature: str
    source_jet_signature: str
    transformed_jet: CanonicalTaylorJet
    transform_signatures: Tuple[str, ...]
    resolved_input_meanings: Tuple[str, ...]
    semantic_signature: str
    local_representative_behavior_signature: str
    local_canonical_eligible: bool
    global_equivalence_eligible: bool
    store_status: str
    audit_hash: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "representation_version": self.representation_version,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "source_jet_signature": self.source_jet_signature,
            "transformed_jet": self.transformed_jet.to_dict(),
            "transform_signatures": list(self.transform_signatures),
            "resolved_input_meanings": list(self.resolved_input_meanings),
            "semantic_signature": self.semantic_signature,
            "local_representative_behavior_signature": self.local_representative_behavior_signature,
            "local_canonical_eligible": self.local_canonical_eligible,
            "global_equivalence_eligible": self.global_equivalence_eligible,
            "store_status": self.store_status,
            "audit_hash": self.audit_hash,
            "warnings": list(self.warnings),
        }


def canonicalize_nonlinear_representative(
    form: CanonicalRepresentativeAlgorithmForm,
    search: NonlinearRepresentativeSearch,
    *,
    semantic_candidates: Sequence[SemanticCandidateMeaning] = (),
    semantic_resolutions: Sequence[SemanticResolution] = (),
) -> CanonicalNonlinearRepresentativeForm:
    _validate_parent(form)
    if not isinstance(search, NonlinearRepresentativeSearch):
        raise EGCFError("SAA-7.1 requires NonlinearRepresentativeSearch")
    if not search.representative_found or search.best_candidate is None:
        raise EGCFError("SAA-7.1 has not found a mathematically representative local form")
    candidate = search.best_candidate
    if not candidate.mathematical_eligible or not candidate.exact_invertible:
        raise EGCFError("SAA-7.1 candidate is not exact and mathematically representative")

    base_meanings = {
        item.canonical_position: item.canonical_meaning for item in form.inputs
    }
    meanings = [
        base_meanings.get(index, f"r{index}")
        for index in range(form.representative_input_count)
    ]
    issue_by_id = {item.issue_id: item for item in candidate.semantic_issues}
    candidate_by_issue = {item.issue_id: item for item in semantic_candidates}
    resolution_by_issue = {item.issue_id: item for item in semantic_resolutions}
    if len(candidate_by_issue) != len(semantic_candidates):
        raise EGCFError("duplicate SAA-7.1 semantic candidate for one nonlinear issue")
    if len(resolution_by_issue) != len(semantic_resolutions):
        raise EGCFError("duplicate SAA-7.1 semantic resolution for one nonlinear issue")

    for issue_id, issue in issue_by_id.items():
        semantic_candidate = candidate_by_issue.get(issue_id)
        resolution = resolution_by_issue.get(issue_id)
        if semantic_candidate is None or resolution is None:
            raise EGCFError(
                "SAA-7.1 transformed coordinates require explicit semantic candidate and resolution"
            )
        if semantic_candidate.candidate_id != resolution.candidate_id:
            raise EGCFError("SAA-7.1 semantic resolution references a different candidate")
        if (
            resolution.status != "SEMANTICALLY_RESOLVED"
            or not resolution.canonical_semantic_eligible
            or resolution.semantic_fit_bp != 10000
        ):
            raise EGCFError("SAA-7.1 nonlinear coordinate meaning is not semantically resolved")
        meanings[issue.coordinate_index] = _canonical_text(semantic_candidate.meaning)

    if set(candidate_by_issue) != set(issue_by_id):
        raise EGCFError("SAA-7.1 semantic candidates must exactly cover transformed coordinates")
    if set(resolution_by_issue) != set(issue_by_id):
        raise EGCFError("SAA-7.1 semantic resolutions must exactly cover transformed coordinates")

    semantic_payload = {
        "schema_version": 1,
        "representation_version": NONLINEAR_REPRESENTATION_VERSION,
        "parent_semantic_signature": form.semantic_representative_signature,
        "resolved_input_meanings": meanings,
        "semantic_resolution_signatures": [
            resolution_by_issue[issue.issue_id].resolution_signature
            for issue in candidate.semantic_issues
        ],
    }
    semantic_signature = sha256_json(semantic_payload)
    behavior_payload = {
        "schema_version": 1,
        "representation_version": NONLINEAR_REPRESENTATION_VERSION,
        "parent_representative_behavior_signature": form.representative_behavior_signature,
        "transformed_jet_coefficient_signature": candidate.transformed_jet.coefficient_signature,
        "transformed_jet_scope_signature": candidate.transformed_jet.scope_signature,
        "semantic_signature": semantic_signature,
    }
    behavior_signature = sha256_json(behavior_payload)
    audit_payload = {
        "schema_version": 1,
        "representation_version": NONLINEAR_REPRESENTATION_VERSION,
        "search_audit_hash": search.audit_hash,
        "candidate_signature": candidate.candidate_signature,
        "transform_signatures": [
            item.transform_signature for item in candidate.transforms
        ],
        "semantic_signature": semantic_signature,
        "local_representative_behavior_signature": behavior_signature,
    }
    return CanonicalNonlinearRepresentativeForm(
        schema_version=1,
        representation_version=NONLINEAR_REPRESENTATION_VERSION,
        parent_representative_behavior_signature=form.representative_behavior_signature,
        source_jet_signature=search.source_jet_signature,
        transformed_jet=candidate.transformed_jet,
        transform_signatures=tuple(
            item.transform_signature for item in candidate.transforms
        ),
        resolved_input_meanings=tuple(meanings),
        semantic_signature=semantic_signature,
        local_representative_behavior_signature=behavior_signature,
        local_canonical_eligible=True,
        global_equivalence_eligible=False,
        store_status="ELIGIBLE_LOCAL_NONLINEAR_REPRESENTATIVE_FORM",
        audit_hash=sha256_json(audit_payload),
        warnings=(
            "SAA-7.1 canonicality is local to the exact Taylor expansion point, truncation order, and certified validity box.",
            "Global nonlinear equivalence remains unproved and is explicitly ineligible.",
        ),
    )
