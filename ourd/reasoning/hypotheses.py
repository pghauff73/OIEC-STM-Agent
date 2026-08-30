from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Mapping, Sequence

from ..errors import PolicyError
from .models import (
    HYPOTHESIS_STATUSES,
    Hypothesis,
    HypothesisSet,
    HypothesisUpdateRecord,
    SCORE_SCALE,
    bounded_score,
    canonical_strings,
    stable_hash,
)


def _canonical_hypothesis(hypothesis: Hypothesis) -> Hypothesis:
    material = asdict(hypothesis)
    material.pop("signature", None)
    return Hypothesis(**material, signature=stable_hash(material))


def _normalize_values(values: Mapping[str, int], ordered_ids: Sequence[str]) -> dict[str, int]:
    if not ordered_ids:
        raise PolicyError("mutually exclusive hypothesis state has no surviving hypothesis")
    scores = {hypothesis_id: max(0, int(values[hypothesis_id])) for hypothesis_id in ordered_ids}
    total = sum(scores.values())
    if total <= 0:
        quotient, remainder = divmod(SCORE_SCALE, len(ordered_ids))
        normalized = {hypothesis_id: quotient for hypothesis_id in ordered_ids}
        for hypothesis_id in ordered_ids[:remainder]:
            normalized[hypothesis_id] += 1
    else:
        floors: dict[str, int] = {}
        remainders: list[tuple[int, str]] = []
        for hypothesis_id in ordered_ids:
            numerator = scores[hypothesis_id] * SCORE_SCALE
            floors[hypothesis_id] = numerator // total
            remainders.append((numerator % total, hypothesis_id))
        missing = SCORE_SCALE - sum(floors.values())
        for _, hypothesis_id in sorted(remainders, key=lambda item: (-item[0], item[1]))[:missing]:
            floors[hypothesis_id] += 1
        normalized = floors
    return normalized


def _normalize_scores(
    hypotheses: Sequence[Hypothesis],
    *,
    field: str,
) -> dict[str, int]:
    eligible = [
        hypothesis
        for hypothesis in hypotheses
        if field == "prior_bp" or hypothesis.status != "FALSIFIED"
    ]
    if not eligible and field == "posterior_bp":
        return {hypothesis.hypothesis_id: 0 for hypothesis in hypotheses}
    normalized = _normalize_values(
        {hypothesis.hypothesis_id: int(getattr(hypothesis, field)) for hypothesis in eligible},
        tuple(hypothesis.hypothesis_id for hypothesis in eligible),
    )
    return {
        hypothesis.hypothesis_id: normalized.get(hypothesis.hypothesis_id, 0)
        for hypothesis in hypotheses
    }


def _hypothesis_uncertainty_bp(
    hypotheses: Sequence[Hypothesis],
    *,
    mutually_exclusive: bool,
) -> int:
    if mutually_exclusive:
        return SCORE_SCALE - max(hypothesis.posterior_bp for hypothesis in hypotheses)
    return sum(
        SCORE_SCALE - abs((2 * hypothesis.posterior_bp) - SCORE_SCALE)
        for hypothesis in hypotheses
    ) // len(hypotheses)


def build_hypothesis_set(
    proposals: Sequence[Mapping[str, Any] | Hypothesis],
    *,
    problem_id: str,
    max_hypotheses: int,
    mutually_exclusive: bool = False,
    update_ids: Iterable[str] = (),
) -> HypothesisSet:
    if not proposals:
        raise PolicyError("super reasoning requires at least one hypothesis")
    maximum = int(max_hypotheses)
    if maximum < 1:
        raise PolicyError("hypothesis budget must be positive")
    if len(proposals) > maximum:
        raise PolicyError("hypothesis pool exceeds the reasoning budget")
    hypotheses = []
    for proposal in proposals:
        if isinstance(proposal, Hypothesis):
            hypothesis = _canonical_hypothesis(proposal)
        else:
            values = dict(proposal)
            proposition = str(values.get("proposition", "")).strip()
            hypothesis_id = str(values.get("hypothesis_id", "")).strip()
            if not hypothesis_id:
                hypothesis_id = f"hypothesis:{stable_hash({'proposition': proposition})}"
            material = {
                "hypothesis_id": hypothesis_id,
                "proposition": proposition,
                "prior_bp": int(values.get("prior_bp", 0)),
                "posterior_bp": int(values.get("posterior_bp", values.get("prior_bp", 0))),
                "supporting_evidence": tuple(values.get("supporting_evidence", ())),
                "conflicting_evidence": tuple(values.get("conflicting_evidence", ())),
                "assumptions": tuple(values.get("assumptions", ())),
                "predictions": tuple(values.get("predictions", ())),
                "falsifiers": tuple(values.get("falsifiers", ())),
                "status": str(values.get("status", "ACTIVE")),
            }
            hypothesis = Hypothesis(**material, signature=stable_hash(material))
        hypotheses.append(hypothesis)
    ordered = tuple(sorted(hypotheses, key=lambda item: item.hypothesis_id))
    if len({hypothesis.hypothesis_id for hypothesis in ordered}) != len(ordered):
        raise PolicyError("hypothesis IDs must be unique")
    if mutually_exclusive:
        normalized_priors = _normalize_scores(ordered, field="prior_bp")
        normalized_posteriors = _normalize_scores(ordered, field="posterior_bp")
        normalized = []
        for hypothesis in ordered:
            material = asdict(hypothesis)
            material.pop("signature", None)
            material["prior_bp"] = normalized_priors[hypothesis.hypothesis_id]
            material["posterior_bp"] = normalized_posteriors[hypothesis.hypothesis_id]
            normalized.append(Hypothesis(**material, signature=stable_hash(material)))
        ordered = tuple(normalized)
    evidence_ids = canonical_strings(
        evidence_id
        for hypothesis in ordered
        for evidence_id in (*hypothesis.supporting_evidence, *hypothesis.conflicting_evidence)
    )
    return HypothesisSet(
        problem_id=str(problem_id),
        hypotheses=ordered,
        max_hypotheses=maximum,
        mutually_exclusive=bool(mutually_exclusive),
        uncertainty_bp=_hypothesis_uncertainty_bp(
            ordered,
            mutually_exclusive=bool(mutually_exclusive),
        ),
        evidence_ids=evidence_ids,
        update_ids=canonical_strings(update_ids),
    )


def compatibility_hypothesis_pool(state: HypothesisSet | None) -> dict[str, Hypothesis]:
    if state is None:
        return {}
    return {hypothesis.hypothesis_id: hypothesis for hypothesis in state.hypotheses}


def require_hypothesis_set_integrity(state: HypothesisSet) -> None:
    HypothesisSet.from_dict(asdict(state))


def _independent_posterior(
    posterior_bp: int,
    likelihood_if_true_bp: int,
    likelihood_if_false_bp: int,
) -> int:
    if likelihood_if_true_bp == likelihood_if_false_bp:
        return posterior_bp
    effective_prior = min(SCORE_SCALE - 1, max(1, posterior_bp))
    true_mass = effective_prior * likelihood_if_true_bp
    false_mass = (SCORE_SCALE - effective_prior) * likelihood_if_false_bp
    denominator = true_mass + false_mass
    if denominator <= 0:
        return posterior_bp
    return min(SCORE_SCALE, max(0, (true_mass * SCORE_SCALE + denominator // 2) // denominator))


def _status_after_update(
    hypothesis: Hypothesis,
    *,
    updated_posterior_bp: int,
    polarity: str,
    new_provenance: bool,
) -> str:
    if updated_posterior_bp <= 0:
        return "FALSIFIED"
    if hypothesis.status == "FALSIFIED" and updated_posterior_bp > hypothesis.posterior_bp:
        if not new_provenance:
            raise PolicyError("falsified hypothesis recovery requires new evidence")
        return "WEAKENED"
    if polarity in {"counterexample", "conflict"} and updated_posterior_bp <= hypothesis.posterior_bp:
        return "WEAKENED"
    if updated_posterior_bp > hypothesis.posterior_bp:
        if hypothesis.assumptions:
            return "UNRESOLVED"
        if updated_posterior_bp >= 7_500:
            return "SUPPORTED"
        return "ACTIVE"
    return hypothesis.status


def update_hypothesis_state(
    state: HypothesisSet,
    *,
    likelihoods: Mapping[str, tuple[int, int]],
    evidence_ids: Iterable[str] = (),
    collision_ids: Iterable[str] = (),
    evidence_polarity: str = "support",
    operation: str = "BAYES_EVIDENCE_UPDATE",
    reason: str = "",
) -> tuple[HypothesisSet, tuple[HypothesisUpdateRecord, ...]]:
    require_hypothesis_set_integrity(state)
    if evidence_polarity not in {"support", "counterexample", "conflict"}:
        raise PolicyError("evidence polarity is invalid")
    declared = {hypothesis.hypothesis_id for hypothesis in state.hypotheses}
    supplied = {str(hypothesis_id) for hypothesis_id in likelihoods}
    if supplied - declared:
        raise PolicyError("likelihood update references an unknown hypothesis")
    if state.mutually_exclusive and supplied != declared:
        raise PolicyError("mutually exclusive updates require one likelihood per hypothesis")
    evidence = canonical_strings(evidence_ids)
    collisions = canonical_strings(collision_ids)
    if not evidence and not collisions:
        raise PolicyError("hypothesis update requires evidence or collision provenance")
    score_pairs: dict[str, tuple[int, int]] = {}
    for hypothesis_id, pair in likelihoods.items():
        if len(pair) != 2:
            raise PolicyError("hypothesis likelihood must contain true and false scores")
        score_pairs[str(hypothesis_id)] = (
            bounded_score(pair[0], "likelihood if true"),
            bounded_score(pair[1], "likelihood if false"),
        )
    if state.mutually_exclusive:
        weighted = {}
        for hypothesis in state.hypotheses:
            likelihood_if_true_bp, _ = score_pairs[hypothesis.hypothesis_id]
            effective_prior = min(SCORE_SCALE - 1, max(1, hypothesis.posterior_bp))
            weighted[hypothesis.hypothesis_id] = effective_prior * likelihood_if_true_bp
        surviving_ids = tuple(
            hypothesis.hypothesis_id
            for hypothesis in state.hypotheses
            if hypothesis.status != "FALSIFIED"
            and score_pairs[hypothesis.hypothesis_id][0] > 0
        )
        normalized = _normalize_values(weighted, surviving_ids) if surviving_ids else {}
        updated_scores = {
            hypothesis.hypothesis_id: normalized.get(hypothesis.hypothesis_id, 0)
            for hypothesis in state.hypotheses
        }
    else:
        updated_scores = {
            hypothesis.hypothesis_id: _independent_posterior(
                hypothesis.posterior_bp,
                *score_pairs[hypothesis.hypothesis_id],
            )
            for hypothesis in state.hypotheses
            if hypothesis.hypothesis_id in score_pairs
        }
    updated_hypotheses = []
    records = []
    for hypothesis in state.hypotheses:
        if hypothesis.hypothesis_id not in score_pairs:
            updated_hypotheses.append(hypothesis)
            continue
        likelihood_if_true_bp, likelihood_if_false_bp = score_pairs[hypothesis.hypothesis_id]
        if evidence_polarity == "conflict":
            polarity = "conflict"
        elif likelihood_if_true_bp > likelihood_if_false_bp:
            polarity = "support"
        elif likelihood_if_true_bp < likelihood_if_false_bp:
            polarity = "counterexample"
        else:
            updated_hypotheses.append(hypothesis)
            continue
        existing_evidence = set(hypothesis.supporting_evidence) | set(
            hypothesis.conflicting_evidence
        )
        new_provenance = bool(set(evidence) - existing_evidence or collisions)
        if not new_provenance:
            updated_hypotheses.append(hypothesis)
            continue
        updated_posterior = updated_scores[hypothesis.hypothesis_id]
        updated_status = _status_after_update(
            hypothesis,
            updated_posterior_bp=updated_posterior,
            polarity=polarity,
            new_provenance=new_provenance,
        )
        supporting = set(hypothesis.supporting_evidence)
        conflicting = set(hypothesis.conflicting_evidence)
        if polarity in {"support", "conflict"}:
            supporting.update(evidence)
        if polarity in {"counterexample", "conflict"}:
            conflicting.update(evidence)
        material = asdict(hypothesis)
        material.pop("signature", None)
        material.update(
            {
                "posterior_bp": updated_posterior,
                "supporting_evidence": tuple(sorted(supporting)),
                "conflicting_evidence": tuple(sorted(conflicting)),
                "status": updated_status,
            }
        )
        updated = Hypothesis(**material, signature=stable_hash(material))
        record = HypothesisUpdateRecord(
            problem_id=state.problem_id,
            hypothesis_id=hypothesis.hypothesis_id,
            operation=str(operation),
            evidence_ids=evidence,
            collision_ids=collisions,
            polarity=polarity,
            likelihood_if_true_bp=likelihood_if_true_bp,
            likelihood_if_false_bp=likelihood_if_false_bp,
            previous_posterior_bp=hypothesis.posterior_bp,
            updated_posterior_bp=updated.posterior_bp,
            previous_status=hypothesis.status,
            updated_status=updated.status,
            previous_hypothesis_signature=hypothesis.signature,
            updated_hypothesis_signature=updated.signature,
            reason=str(reason),
        )
        updated_hypotheses.append(updated)
        records.append(record)
    if not records:
        return state, ()
    updated_state = build_hypothesis_set(
        updated_hypotheses,
        problem_id=state.problem_id,
        max_hypotheses=state.max_hypotheses,
        mutually_exclusive=state.mutually_exclusive,
        update_ids=(*state.update_ids, *(record.update_id for record in records)),
    )
    return updated_state, tuple(sorted(records, key=lambda item: item.update_id))


def apply_collision_update(
    state: HypothesisSet,
    *,
    objects: Iterable[str],
    falsifier: str,
    evidence_ids: Iterable[str],
    collision_id: str,
    severity_bp: int,
) -> tuple[HypothesisSet, tuple[HypothesisUpdateRecord, ...]]:
    severity = bounded_score(severity_bp, "collision severity")
    object_set = {str(value).casefold() for value in objects if str(value)}
    falsifier_key = str(falsifier).strip().casefold()
    targeted: dict[str, tuple[int, int]] = {}
    for hypothesis in state.hypotheses:
        named = hypothesis.hypothesis_id.casefold() in object_set
        matched_falsifier = bool(
            falsifier_key
            and any(
                falsifier_key == item.casefold()
                or falsifier_key in item.casefold()
                or item.casefold() in falsifier_key
                for item in hypothesis.falsifiers
            )
        )
        if named or matched_falsifier:
            targeted[hypothesis.hypothesis_id] = (
                0 if matched_falsifier and severity >= 5_000 else max(1, SCORE_SCALE - severity),
                SCORE_SCALE,
            )
        elif state.mutually_exclusive:
            targeted[hypothesis.hypothesis_id] = (SCORE_SCALE, SCORE_SCALE)
    if not targeted:
        return state, ()
    return update_hypothesis_state(
        state,
        likelihoods=targeted,
        evidence_ids=evidence_ids,
        collision_ids=(collision_id,),
        evidence_polarity="counterexample",
        operation="CFEL_COLLISION_UPDATE",
        reason="CFEL collision contradicted a hypothesis prediction or falsifier",
    )


__all__ = [
    "apply_collision_update",
    "build_hypothesis_set",
    "compatibility_hypothesis_pool",
    "require_hypothesis_set_integrity",
    "update_hypothesis_state",
]
