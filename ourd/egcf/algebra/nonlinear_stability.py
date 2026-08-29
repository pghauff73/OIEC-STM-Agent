from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .nonlinear_search import (
    CanonicalNonlinearRepresentativeForm,
    NonlinearRepresentativeSearch,
)


NONLINEAR_STABILITY_VERSION = "saa-nonlinear-semantic-stability-v1"
MAX_REGIONAL_OBSERVATIONS = 64


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _box_payload(center: Sequence[Fraction], radius: Sequence[Fraction]) -> list[list[list[int]]]:
    return [
        [_fraction_payload(c - r), _fraction_payload(c + r)]
        for c, r in zip(center, radius)
    ]


def _transform_family_payload(search: NonlinearRepresentativeSearch | None) -> list[dict[str, Any]]:
    if search is None or search.best_candidate is None:
        return []
    rows: list[dict[str, Any]] = []
    for transform in search.best_candidate.transforms:
        row: dict[str, Any] = {
            "kind": transform.to_dict().get("kind", type(transform).__name__),
            "target_input_index": int(transform.target_input_index),
        }
        if hasattr(transform, "monomial_powers"):
            row["monomial_powers"] = list(transform.monomial_powers)
        elif hasattr(transform, "terms"):
            row["term_powers"] = sorted(
                [list(item.powers) for item in transform.terms]
            )
        rows.append(row)
    rows.sort(key=lambda item: sha256_json(item))
    return rows


def _boxes_overlap(
    left_center: Sequence[Fraction],
    left_radius: Sequence[Fraction],
    right_center: Sequence[Fraction],
    right_radius: Sequence[Fraction],
) -> bool:
    return all(
        max(lc - lr, rc - rr) <= min(lc + lr, rc + rr)
        for lc, lr, rc, rr in zip(left_center, left_radius, right_center, right_radius)
    )


def _connected(adjacency: Sequence[Sequence[int]]) -> bool:
    if not adjacency:
        return False
    visited = {0}
    queue = [0]
    while queue:
        current = queue.pop(0)
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return len(visited) == len(adjacency)


@dataclass(frozen=True)
class NonlinearRegionalObservation:
    local_form: CanonicalNonlinearRepresentativeForm
    transform_family_signature: str
    evidence_signature: str = ""

    @property
    def center(self) -> Tuple[Fraction, ...]:
        return self.local_form.transformed_jet.center

    @property
    def validity_radius(self) -> Tuple[Fraction, ...]:
        return self.local_form.transformed_jet.validity_radius

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_representative_behavior_signature": self.local_form.local_representative_behavior_signature,
            "semantic_signature": self.local_form.semantic_signature,
            "resolved_input_meanings": list(self.local_form.resolved_input_meanings),
            "center": [_fraction_payload(value) for value in self.center],
            "validity_radius": [_fraction_payload(value) for value in self.validity_radius],
            "transform_family_signature": self.transform_family_signature,
            "evidence_signature": self.evidence_signature,
        }


def make_regional_observation(
    local_form: CanonicalNonlinearRepresentativeForm,
    *,
    search: NonlinearRepresentativeSearch | None = None,
    evidence_signature: str = "",
) -> NonlinearRegionalObservation:
    if not isinstance(local_form, CanonicalNonlinearRepresentativeForm):
        raise EGCFError("SAA-7.3 regional observations require canonical local nonlinear forms")
    if not local_form.local_canonical_eligible or local_form.global_equivalence_eligible:
        raise EGCFError("SAA-7.3 requires qualified local-only nonlinear forms")
    if search is not None:
        if search.best_candidate is None:
            raise EGCFError("SAA-7.3 search observation has no representative candidate")
        if (
            search.best_candidate.transformed_jet.local_behavior_signature
            != local_form.transformed_jet.local_behavior_signature
        ):
            raise EGCFError("SAA-7.3 search does not correspond to supplied local form")
    family_payload = _transform_family_payload(search)
    family_signature = sha256_json(
        {
            "schema_version": 1,
            "stability_version": NONLINEAR_STABILITY_VERSION,
            "transform_family": family_payload,
        }
    )
    return NonlinearRegionalObservation(
        local_form=local_form,
        transform_family_signature=family_signature,
        evidence_signature=str(evidence_signature).strip(),
    )


@dataclass(frozen=True)
class SemanticStabilityAssessment:
    schema_version: int
    stability_version: str
    parent_representative_behavior_signature: str
    status: str
    observation_count: int
    connected_region: bool
    meanings_stable: bool
    representation_family_stable: bool
    stable_meanings: Tuple[str, ...]
    transition_coordinates: Tuple[int, ...]
    adjacency: Tuple[Tuple[int, ...], ...]
    regional_boxes: Tuple[Tuple[Tuple[Fraction, Fraction], ...], ...]
    local_behavior_signatures: Tuple[str, ...]
    transform_family_signatures: Tuple[str, ...]
    evidence_signatures: Tuple[str, ...]
    regional_semantic_eligible: bool
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stability_version": self.stability_version,
            "parent_representative_behavior_signature": self.parent_representative_behavior_signature,
            "status": self.status,
            "observation_count": self.observation_count,
            "connected_region": self.connected_region,
            "meanings_stable": self.meanings_stable,
            "representation_family_stable": self.representation_family_stable,
            "stable_meanings": list(self.stable_meanings),
            "transition_coordinates": list(self.transition_coordinates),
            "adjacency": [list(item) for item in self.adjacency],
            "regional_boxes": [
                [
                    [_fraction_payload(lower), _fraction_payload(upper)]
                    for lower, upper in box
                ]
                for box in self.regional_boxes
            ],
            "local_behavior_signatures": list(self.local_behavior_signatures),
            "transform_family_signatures": list(self.transform_family_signatures),
            "evidence_signatures": list(self.evidence_signatures),
            "regional_semantic_eligible": self.regional_semantic_eligible,
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


def assess_semantic_stability(
    observations: Sequence[NonlinearRegionalObservation],
) -> SemanticStabilityAssessment:
    if not observations:
        raise EGCFError("SAA-7.3 requires at least one local nonlinear observation")
    if len(observations) > MAX_REGIONAL_OBSERVATIONS:
        raise EGCFError(f"SAA-7.3 observation count exceeds cap {MAX_REGIONAL_OBSERVATIONS}")
    if any(not isinstance(item, NonlinearRegionalObservation) for item in observations):
        raise EGCFError("SAA-7.3 observations must be NonlinearRegionalObservation records")

    parent = observations[0].local_form.parent_representative_behavior_signature
    dimension = len(observations[0].local_form.resolved_input_meanings)
    for item in observations:
        if item.local_form.parent_representative_behavior_signature != parent:
            raise EGCFError("SAA-7.3 cannot compare local forms from different canonical parents")
        if len(item.local_form.resolved_input_meanings) != dimension:
            raise EGCFError("SAA-7.3 semantic dimensions are inconsistent")

    adjacency_lists: list[list[int]] = [[] for _ in observations]
    for left in range(len(observations)):
        for right in range(left + 1, len(observations)):
            if _boxes_overlap(
                observations[left].center,
                observations[left].validity_radius,
                observations[right].center,
                observations[right].validity_radius,
            ):
                adjacency_lists[left].append(right)
                adjacency_lists[right].append(left)
    adjacency = tuple(tuple(sorted(item)) for item in adjacency_lists)
    connected = _connected(adjacency)

    meaning_rows = [tuple(item.local_form.resolved_input_meanings) for item in observations]
    stable_meanings = meaning_rows[0]
    transition_coordinates = tuple(
        index
        for index in range(dimension)
        if len({row[index] for row in meaning_rows}) > 1
    )
    meanings_stable = not transition_coordinates
    family_signatures = tuple(item.transform_family_signature for item in observations)
    family_stable = len(set(family_signatures)) == 1

    if len(observations) == 1:
        status = "LOCALLY_STABLE_SEMANTICS"
        eligible = False
    elif not connected:
        status = "MULTI_REGION_SEMANTICS_UNRESOLVED"
        eligible = False
    elif not meanings_stable:
        status = "SEMANTIC_TRANSITION_DETECTED"
        eligible = False
    elif not family_stable:
        status = "REPRESENTATION_REGIME_CHANGE"
        eligible = False
    else:
        status = "REGIONALLY_STABLE_SEMANTICS"
        eligible = True

    boxes = tuple(
        tuple(
            (center - radius, center + radius)
            for center, radius in zip(item.center, item.validity_radius)
        )
        for item in observations
    )
    local_signatures = tuple(
        item.local_form.local_representative_behavior_signature for item in observations
    )
    evidence_signatures = tuple(
        item.evidence_signature for item in observations if item.evidence_signature
    )
    payload = {
        "schema_version": 1,
        "stability_version": NONLINEAR_STABILITY_VERSION,
        "parent_representative_behavior_signature": parent,
        "status": status,
        "observation_count": len(observations),
        "connected_region": connected,
        "meanings_stable": meanings_stable,
        "representation_family_stable": family_stable,
        "stable_meanings": list(stable_meanings if meanings_stable else ()),
        "transition_coordinates": list(transition_coordinates),
        "adjacency": [list(item) for item in adjacency],
        "regional_boxes": [
            [
                [_fraction_payload(lower), _fraction_payload(upper)]
                for lower, upper in box
            ]
            for box in boxes
        ],
        "local_behavior_signatures": list(local_signatures),
        "transform_family_signatures": list(family_signatures),
        "evidence_signatures": list(evidence_signatures),
        "regional_semantic_eligible": eligible,
    }
    warnings: list[str] = []
    if status == "LOCALLY_STABLE_SEMANTICS":
        warnings.append("One local observation cannot establish semantic stability across an operating region.")
    if status == "MULTI_REGION_SEMANTICS_UNRESOLVED":
        warnings.append("Local semantic islands are disconnected; no continuous regional semantic claim is admitted.")
    if status == "REPRESENTATION_REGIME_CHANGE":
        warnings.append("Meaning labels agree but the required representative transform family changes across the region.")
    if eligible:
        warnings.append("Regional stability is limited to the connected union of the qualified local boxes and does not prove global semantic invariance.")
    return SemanticStabilityAssessment(
        schema_version=1,
        stability_version=NONLINEAR_STABILITY_VERSION,
        parent_representative_behavior_signature=parent,
        status=status,
        observation_count=len(observations),
        connected_region=connected,
        meanings_stable=meanings_stable,
        representation_family_stable=family_stable,
        stable_meanings=tuple(stable_meanings if meanings_stable else ()),
        transition_coordinates=transition_coordinates,
        adjacency=adjacency,
        regional_boxes=boxes,
        local_behavior_signatures=local_signatures,
        transform_family_signatures=family_signatures,
        evidence_signatures=evidence_signatures,
        regional_semantic_eligible=eligible,
        assessment_signature=sha256_json(payload),
        warnings=tuple(warnings),
    )
