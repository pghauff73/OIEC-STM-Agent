from __future__ import annotations

import re
from collections import Counter
from typing import Sequence

from .models import ConceptAnnotation, ReferenceSpan
from .passage_index import tokens


STOPWORDS = {
    "about", "after", "also", "because", "before", "between", "could", "from", "have",
    "into", "more", "most", "other", "over", "such", "than", "that", "their", "there",
    "these", "this", "those", "through", "under", "using", "were", "which", "with", "would",
}


def identify_concepts(
    source_spans: Sequence[ReferenceSpan],
    *,
    domain: str = "general",
    limit: int = 8,
) -> tuple[ConceptAnnotation, ...]:
    term_counts = Counter(
        term
        for span in source_spans
        for term in tokens(span.verbatim_text)
        if len(term) >= 5 and term not in STOPWORDS
    )
    annotations = []
    source_ids = tuple(span.reference_span_id for span in source_spans)
    for term, count in term_counts.most_common(max(1, int(limit))):
        definition = next(
            (
                sentence.strip()
                for span in source_spans
                for sentence in re.split(r"(?<=[.!?])\s+", span.verbatim_text)
                if re.search(rf"\b{re.escape(term)}\b", sentence, flags=re.IGNORECASE)
            ),
            f"Concept proposed from repeated source usage of {term!r}.",
        )
        annotations.append(
            ConceptAnnotation(
                preferred_label=term,
                definition=definition,
                source_span_ids=source_ids,
                domain=domain,
                explicit_or_inferred="explicit" if count > 1 else "inferred",
                confidence=min(9_000, 4_000 + count * 1_000),
            )
        )
    return tuple(annotations)


__all__ = ["identify_concepts"]
