from __future__ import annotations

import re
from typing import Sequence

from .models import ParaphraseLink, ReferenceSpan
from .passage_index import tokens


QUALIFIERS = {"may", "might", "could", "often", "sometimes", "likely", "approximately", "suggests"}
NEGATIONS = {"not", "no", "never", "without", "unlikely"}
CAUSAL = {"cause", "causes", "caused", "because", "therefore", "leads", "produces"}


def _ratio(left: set[str], right: set[str]) -> int:
    if not left and not right:
        return 10_000
    union = left | right
    return int(10_000 * len(left & right) / max(1, len(union)))


def analyse_paraphrase(
    draft_text: str,
    source_spans: Sequence[ReferenceSpan],
    *,
    advisory_model: str = "deterministic-v1",
) -> ParaphraseLink:
    source_text = " ".join(span.verbatim_text for span in source_spans)
    source_terms = set(tokens(source_text))
    draft_terms = set(tokens(draft_text))
    lexical_overlap = _ratio(source_terms, draft_terms)
    source_qualifiers = source_terms & QUALIFIERS
    draft_qualifiers = draft_terms & QUALIFIERS
    qualifier_preservation = not source_qualifiers or bool(source_qualifiers & draft_qualifiers)
    polarity_preservation = bool(source_terms & NEGATIONS) == bool(draft_terms & NEGATIONS)
    source_causal = bool(source_terms & CAUSAL)
    draft_causal = bool(draft_terms & CAUSAL)
    causal_preservation = not draft_causal or source_causal
    unsupported = tuple(sorted(draft_terms - source_terms - {
        "the", "a", "an", "and", "or", "of", "to", "in", "that", "this", "is", "are", "was", "were"
    }))
    unsupported_ratio = int(10_000 * len(unsupported) / max(1, len(draft_terms)))
    if not polarity_preservation or not causal_preservation:
        relation = "contradicted"
    elif unsupported_ratio > 4_000 or not qualifier_preservation:
        relation = "partially_supported"
    elif lexical_overlap >= 2_000:
        relation = "supported"
    else:
        relation = "unresolved"
    patchwriting_risk = max(0, lexical_overlap - 6_000)
    review_status = "VERIFIED" if relation == "supported" and patchwriting_risk < 2_000 else "REVIEW_REQUIRED"
    return ParaphraseLink(
        draft_text=draft_text,
        source_span_ids=tuple(span.reference_span_id for span in source_spans),
        paraphrase_kind="synthesis" if len(source_spans) > 1 else "single_source",
        lexical_overlap=lexical_overlap,
        semantic_similarity=lexical_overlap,
        support_relation=relation,
        qualifier_preservation=qualifier_preservation,
        polarity_preservation=polarity_preservation,
        scope_preservation=unsupported_ratio <= 4_000,
        causal_strength_preservation=causal_preservation,
        patchwriting_risk=patchwriting_risk,
        unsupported_additions=unsupported,
        advisory_model=advisory_model,
        review_status=review_status,
    )


__all__ = ["analyse_paraphrase"]
