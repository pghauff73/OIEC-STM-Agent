from __future__ import annotations

import re
from typing import Sequence

from .models import ReasoningAnnotation, ReferenceSpan


ROLE_CUES = (
    ("counterclaim", ("however", "although", "critics", "contrary")),
    ("limitation", ("limitation", "limited", "uncertain", "cannot", "caution")),
    ("rebuttal", ("nevertheless", "despite", "yet this", "respond")),
    ("evidence", ("data", "study", "observed", "results", "evidence")),
    ("warrant", ("because", "therefore", "thus", "implies")),
    ("qualifier", ("may", "might", "likely", "often", "sometimes")),
)


def _role(text: str) -> str:
    lowered = text.casefold()
    for role, cues in ROLE_CUES:
        if any(cue in lowered for cue in cues):
            return role
    return "claim"


def _inference_mode(text: str) -> str:
    lowered = text.casefold()
    if any(term in lowered for term in ("causes", "because", "leads to", "produces")):
        return "causal"
    if any(term in lowered for term in ("probably", "likely", "suggests", "observed")):
        return "inductive"
    if any(term in lowered for term in ("best explanation", "explains", "hypothesis")):
        return "abductive"
    if any(term in lowered for term in ("therefore", "must", "entails")):
        return "deductive"
    return "unspecified"


def identify_reasoning(source_spans: Sequence[ReferenceSpan]) -> tuple[ReasoningAnnotation, ...]:
    annotations = []
    for span in source_spans:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", span.verbatim_text) if item.strip()]
        for sentence in sentences or [span.verbatim_text]:
            role = _role(sentence)
            qualifiers = tuple(term for term in ("may", "might", "likely", "often", "sometimes") if re.search(rf"\b{term}\b", sentence, re.I))
            limitations = (sentence,) if role == "limitation" else ()
            annotations.append(
                ReasoningAnnotation(
                    source_span_ids=(span.reference_span_id,),
                    component_role=role,
                    relation_type="grounds" if role in {"evidence", "warrant"} else "supports",
                    inference_mode=_inference_mode(sentence),
                    source_claim=sentence,
                    target_claim="",
                    qualifiers=qualifiers,
                    limitations=limitations,
                    confidence=7_000 if role != "claim" else 5_500,
                )
            )
    return tuple(annotations)


__all__ = ["identify_reasoning"]
