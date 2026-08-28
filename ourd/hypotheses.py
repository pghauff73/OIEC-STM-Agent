from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Mapping, Sequence

from .errors import PolicyError
from .models import (
    EvidenceArtifact,
    Hypothesis,
    HypothesisEvidenceLink,
    HypothesisSet,
    SCORE_SCALE,
)
from .oiec import stable_hash


MAX_EVIDENCE_LINKS_PER_HYPOTHESIS = 64
FALSIFIER_QUALITY_THRESHOLD_BP = 5_000
STATUS_MARGIN_BP = 1_000


def evidence_fingerprint(artifact: EvidenceArtifact) -> str:
    """Stable evidence identity independent of runtime-generated UUIDs."""

    return stable_hash(
        {
            "kind": artifact.kind,
            "description": artifact.description,
            "sha256": artifact.sha256,
            "source_snapshot_hash": artifact.source_snapshot_hash,
            "path": artifact.path,
            "command_capability": artifact.command_capability,
            "success": artifact.success,
            "requirement_ids": sorted(set(artifact.requirement_ids)),
            "quality_bp": int(artifact.quality_bp),
            "polarity": artifact.polarity,
        }
    )


def hypothesis_definition_material(
    *,
    proposition: str,
    model_prior_bp: int,
    assumptions: Sequence[str],
    predictions: Sequence[str],
    falsifiers: Sequence[str],
) -> dict[str, Any]:
    proposition = " ".join(str(proposition).split()).strip()
    if not proposition:
        raise PolicyError("hypothesis proposition must be non-empty")
    prior = int(model_prior_bp)
    if not 0 <= prior <= SCORE_SCALE:
        raise PolicyError("hypothesis model_prior_bp must be 0..10000")
    return {
        "proposition": proposition,
        "model_prior_bp": prior,
        "assumptions": tuple(sorted({str(value).strip() for value in assumptions if str(value).strip()})),
        "predictions": tuple(sorted({str(value).strip() for value in predictions if str(value).strip()})),
        "falsifiers": tuple(sorted({str(value).strip() for value in falsifiers if str(value).strip()})),
    }


def _hypothesis_signature(hypothesis: Hypothesis) -> str:
    payload = asdict(hypothesis)
    payload.pop("signature", None)
    return stable_hash(payload)


def _set_signature(max_hypotheses: int, hypotheses: Sequence[Hypothesis]) -> str:
    return stable_hash(
        {
            "max_hypotheses": int(max_hypotheses),
            "hypotheses": [
                {"hypothesis_id": item.hypothesis_id, "signature": item.signature}
                for item in sorted(hypotheses, key=lambda value: value.hypothesis_id)
            ],
        }
    )


def make_hypothesis(
    *,
    proposition: str,
    model_prior_bp: int = 5_000,
    assumptions: Sequence[str] = (),
    predictions: Sequence[str] = (),
    falsifiers: Sequence[str] = (),
) -> Hypothesis:
    material = hypothesis_definition_material(
        proposition=proposition,
        model_prior_bp=model_prior_bp,
        assumptions=assumptions,
        predictions=predictions,
        falsifiers=falsifiers,
    )
    hypothesis_id = "hypothesis:" + stable_hash(material)
    hypothesis = Hypothesis(
        hypothesis_id=hypothesis_id,
        proposition=material["proposition"],
        model_prior_bp=material["model_prior_bp"],
        assumptions=material["assumptions"],
        predictions=material["predictions"],
        falsifiers=material["falsifiers"],
        status="ACTIVE",
        verification_status="UNVERIFIED_PROPOSITION",
    )
    return replace(hypothesis, signature=_hypothesis_signature(hypothesis))


def bounded_hypothesis_set(
    current: HypothesisSet | None,
    proposals: Sequence[Mapping[str, Any]],
    *,
    max_hypotheses: int,
) -> tuple[HypothesisSet, tuple[str, ...]]:
    bound = max(1, int(max_hypotheses))
    existing = {
        item.hypothesis_id: item
        for item in (current.hypotheses if current is not None else ())
    }
    if len(existing) > bound:
        raise PolicyError(
            f"existing hypothesis state ({len(existing)}) exceeds current active bound ({bound})"
        )
    added: list[str] = []
    for proposal in proposals:
        hypothesis = make_hypothesis(
            proposition=str(proposal.get("proposition", "")),
            model_prior_bp=int(proposal.get("model_prior_bp", 5_000)),
            assumptions=tuple(proposal.get("assumptions", ()) or ()),
            predictions=tuple(proposal.get("predictions", ()) or ()),
            falsifiers=tuple(proposal.get("falsifiers", ()) or ()),
        )
        if hypothesis.hypothesis_id in existing:
            continue
        if len(existing) >= bound:
            raise PolicyError(f"hypothesis set exceeds active bound ({bound})")
        existing[hypothesis.hypothesis_id] = hypothesis
        added.append(hypothesis.hypothesis_id)
    hypotheses = tuple(sorted(existing.values(), key=lambda item: item.hypothesis_id))
    result = HypothesisSet(
        max_hypotheses=bound,
        hypotheses=hypotheses,
        signature=_set_signature(bound, hypotheses),
    )
    return result, tuple(added)


def _derive_scores(links: Sequence[HypothesisEvidenceLink]) -> tuple[int, int, int, str]:
    support = min(
        SCORE_SCALE,
        sum(link.quality_bp for link in links if link.relation == "supports"),
    )
    conflict = min(
        SCORE_SCALE,
        sum(link.quality_bp for link in links if link.relation in {"conflicts", "falsifies"}),
    )
    balance = max(-SCORE_SCALE, min(SCORE_SCALE, support - conflict))
    has_material_falsifier = any(
        link.relation == "falsifies" and link.quality_bp >= FALSIFIER_QUALITY_THRESHOLD_BP
        for link in links
    )
    if has_material_falsifier:
        status = "FALSIFIED_BY_LINKED_EVIDENCE"
    elif balance >= STATUS_MARGIN_BP:
        status = "SUPPORTED_BY_LINKED_EVIDENCE"
    elif balance <= -STATUS_MARGIN_BP:
        status = "WEAKENED_BY_LINKED_EVIDENCE"
    else:
        status = "UNRESOLVED"
    return support, conflict, balance, status


def link_hypothesis_evidence(
    current: HypothesisSet,
    evidence_registry: Mapping[str, EvidenceArtifact],
    *,
    hypothesis_id: str,
    evidence_id: str,
    relation: str,
) -> tuple[HypothesisSet, bool]:
    if relation not in {"supports", "conflicts", "falsifies"}:
        raise PolicyError("hypothesis evidence relation must be supports, conflicts, or falsifies")
    artifact = evidence_registry.get(evidence_id)
    if artifact is None:
        raise PolicyError("hypothesis evidence link references unknown grounded evidence")
    if int(artifact.quality_bp) <= 0:
        raise PolicyError("zero-quality evidence cannot create hypothesis-resolution progress")
    hypotheses = {item.hypothesis_id: item for item in current.hypotheses}
    hypothesis = hypotheses.get(hypothesis_id)
    if hypothesis is None:
        raise PolicyError("unknown hypothesis_id")

    fingerprint = evidence_fingerprint(artifact)
    if any(item.evidence_fingerprint == fingerprint for item in hypothesis.evidence_links):
        return current, False
    if len(hypothesis.evidence_links) >= MAX_EVIDENCE_LINKS_PER_HYPOTHESIS:
        raise PolicyError("hypothesis evidence-link bound exceeded")

    link_material = {
        "hypothesis_id": hypothesis_id,
        "evidence_fingerprint": fingerprint,
        "relation": relation,
        "quality_bp": int(artifact.quality_bp),
        "source_snapshot_hash": artifact.source_snapshot_hash,
        "relation_epistemic_status": "MODEL_PROPOSED_RELATION_TO_VERIFIED_EVIDENCE",
    }
    link = HypothesisEvidenceLink(
        evidence_id=evidence_id,
        evidence_fingerprint=fingerprint,
        relation=relation,
        quality_bp=int(artifact.quality_bp),
        source_snapshot_hash=artifact.source_snapshot_hash,
        signature=stable_hash(link_material),
    )
    links = tuple((*hypothesis.evidence_links, link))
    support, conflict, balance, status = _derive_scores(links)
    updated = replace(
        hypothesis,
        evidence_links=links,
        evidence_support_bp=support,
        evidence_conflict_bp=conflict,
        evidence_balance_bp=balance,
        status=status,
        verification_status="UNVERIFIED_PROPOSITION",
        signature="",
    )
    updated = replace(updated, signature=_hypothesis_signature(updated))
    hypotheses[hypothesis_id] = updated
    ordered = tuple(sorted(hypotheses.values(), key=lambda item: item.hypothesis_id))
    result = HypothesisSet(
        max_hypotheses=current.max_hypotheses,
        hypotheses=ordered,
        signature=_set_signature(current.max_hypotheses, ordered),
    )
    return result, True


def public_hypothesis_projection(state: HypothesisSet | None) -> dict[str, Any]:
    if state is None:
        return {"max_hypotheses": 0, "hypotheses": [], "signature": ""}
    return {
        "max_hypotheses": state.max_hypotheses,
        "signature": state.signature,
        "hypotheses": [
            {
                "hypothesis_id": item.hypothesis_id,
                "proposition": item.proposition,
                "model_prior_bp": item.model_prior_bp,
                "assumptions": list(item.assumptions),
                "predictions": list(item.predictions),
                "falsifiers": list(item.falsifiers),
                "evidence_support_bp": item.evidence_support_bp,
                "evidence_conflict_bp": item.evidence_conflict_bp,
                "evidence_balance_bp": item.evidence_balance_bp,
                "status": item.status,
                "verification_status": item.verification_status,
                "evidence_links": [
                    {
                        "evidence_id": link.evidence_id,
                        "relation": link.relation,
                        "quality_bp": link.quality_bp,
                        "relation_epistemic_status": link.relation_epistemic_status,
                    }
                    for link in item.evidence_links
                ],
            }
            for item in state.hypotheses
        ],
    }
