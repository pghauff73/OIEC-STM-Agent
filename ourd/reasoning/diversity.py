from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

from .models import DiversityConfiguration, ReasoningPath, SCORE_SCALE, stable_hash


DEFAULT_DIVERSITY_CONFIGURATION = DiversityConfiguration()
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_claim(value: str) -> str:
    return " ".join(sorted(_TOKEN.findall(str(value).casefold())))


def _normalized_strings(values: Iterable[str]) -> tuple[str, ...]:
    normalized = {normalize_claim(value) for value in values}
    return tuple(sorted(value for value in normalized if value))


def structure_material_from_parts(
    *,
    perspective: str,
    hypothesis_ids: Iterable[str],
    steps: Sequence[Mapping[str, Any]],
    conclusion: str,
) -> Mapping[str, Any]:
    return {
        "strategy": str(perspective),
        "hypothesis_ids": tuple(sorted({str(value) for value in hypothesis_ids if str(value)})),
        "evidence_ids": tuple(
            sorted(
                {
                    str(evidence_id)
                    for step in steps
                    for evidence_id in step.get("evidence_ids", ())
                    if str(evidence_id)
                }
            )
        ),
        "inference_modes": tuple(str(step.get("inference", "")) for step in steps),
        "assumptions": _normalized_strings(
            str(assumption)
            for step in steps
            for assumption in step.get("assumptions", ())
        ),
        "falsifiers": _normalized_strings(
            str(step.get("falsifier", "")) for step in steps if str(step.get("falsifier", ""))
        ),
        "conclusion": normalize_claim(conclusion),
    }


def path_structure_material(path: ReasoningPath) -> Mapping[str, Any]:
    return structure_material_from_parts(
        perspective=path.perspective,
        hypothesis_ids=path.hypothesis_ids,
        steps=tuple(
            {
                "evidence_ids": step.evidence_ids,
                "inference": step.inference,
                "assumptions": step.assumptions,
                "falsifier": step.falsifier,
            }
            for step in path.steps
        ),
        conclusion=path.conclusion,
    )


def path_structure_signature(path: ReasoningPath) -> str:
    return stable_hash(path_structure_material(path))


def _jaccard_bp(left: Iterable[str], right: Iterable[str]) -> int:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return SCORE_SCALE
    union = left_set | right_set
    return len(left_set & right_set) * SCORE_SCALE // len(union)


def structural_similarity_bp(
    left: ReasoningPath,
    right: ReasoningPath,
    *,
    config: DiversityConfiguration = DEFAULT_DIVERSITY_CONFIGURATION,
) -> int:
    left_material = path_structure_material(left)
    right_material = path_structure_material(right)
    inference_similarity = (
        SCORE_SCALE
        if left_material["inference_modes"] == right_material["inference_modes"]
        else _jaccard_bp(left_material["inference_modes"], right_material["inference_modes"])
    )
    value = (
        config.hypothesis_weight
        * _jaccard_bp(left_material["hypothesis_ids"], right_material["hypothesis_ids"])
        + config.evidence_weight
        * _jaccard_bp(left_material["evidence_ids"], right_material["evidence_ids"])
        + config.inference_weight * inference_similarity
        + config.assumption_weight
        * _jaccard_bp(left_material["assumptions"], right_material["assumptions"])
        + config.falsifier_weight
        * _jaccard_bp(left_material["falsifiers"], right_material["falsifiers"])
        + config.conclusion_weight
        * _jaccard_bp(
            str(left_material["conclusion"]).split(),
            str(right_material["conclusion"]).split(),
        )
    ) // 100
    return max(0, min(SCORE_SCALE, value))


def is_structural_duplicate(
    candidate: ReasoningPath,
    accepted: Sequence[ReasoningPath],
    *,
    config: DiversityConfiguration = DEFAULT_DIVERSITY_CONFIGURATION,
) -> bool:
    return any(
        structural_similarity_bp(candidate, other, config=config)
        >= config.duplicate_threshold_bp
        for other in accepted
    )


def bind_diversity_scores(
    paths: Sequence[ReasoningPath],
    *,
    config: DiversityConfiguration = DEFAULT_DIVERSITY_CONFIGURATION,
) -> tuple[ReasoningPath, ...]:
    if len(paths) < 2:
        return tuple(replace(path, diversity_bp=0) for path in paths)
    values = []
    for path in paths:
        maximum_similarity = max(
            structural_similarity_bp(path, other, config=config)
            for other in paths
            if other.path_id != path.path_id
        )
        values.append(replace(path, diversity_bp=SCORE_SCALE - maximum_similarity))
    return tuple(values)


__all__ = [
    "DEFAULT_DIVERSITY_CONFIGURATION",
    "bind_diversity_scores",
    "is_structural_duplicate",
    "normalize_claim",
    "path_structure_material",
    "path_structure_signature",
    "structural_similarity_bp",
    "structure_material_from_parts",
]
