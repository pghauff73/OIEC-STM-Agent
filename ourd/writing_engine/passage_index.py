from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from .anchors import build_text_anchor
from .models import ExtractedSource, PassageMatch
from .references import reference_from_anchor


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")


def tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).casefold() for match in TOKEN_PATTERN.finditer(text))


@dataclass(frozen=True)
class IndexedPassage:
    source: ExtractedSource
    start_offset: int
    end_offset: int
    text: str
    terms: Counter[str]


class PassageIndex:
    def __init__(self, sources: Sequence[ExtractedSource]):
        self.passages = self._build_passages(sources)
        document_frequency = Counter()
        for passage in self.passages:
            document_frequency.update(set(passage.terms))
        self.document_frequency = document_frequency

    @staticmethod
    def _build_passages(sources: Sequence[ExtractedSource]) -> tuple[IndexedPassage, ...]:
        passages = []
        for source in sources:
            offsets = source.paragraph_offsets or ((0, len(source.document_text)),)
            for start, end in offsets:
                text = source.document_text[start:end].strip()
                if not text:
                    continue
                actual_start = source.document_text.find(text, start, end)
                actual_end = actual_start + len(text)
                passages.append(
                    IndexedPassage(
                        source=source,
                        start_offset=actual_start,
                        end_offset=actual_end,
                        text=text,
                        terms=Counter(tokens(text)),
                    )
                )
        return tuple(passages)

    def search(self, query: str, *, limit: int = 10) -> tuple[PassageMatch, ...]:
        query_terms = Counter(tokens(query))
        if not query_terms:
            raise ValueError("passage query must contain searchable terms")
        total = max(1, len(self.passages))
        ranked = []
        for passage in self.passages:
            score = 0.0
            for term, frequency in query_terms.items():
                if term not in passage.terms:
                    continue
                inverse_frequency = math.log((total + 1) / (1 + self.document_frequency[term])) + 1
                score += min(frequency, passage.terms[term]) * inverse_frequency
            if query.casefold() in passage.text.casefold():
                score += 10.0
            if score <= 0:
                continue
            anchor = build_text_anchor(passage.source, passage.start_offset, passage.end_offset)
            reference = reference_from_anchor(passage.source, anchor, reference_kind="background")
            ranked.append(
                PassageMatch(
                    source_document_id=passage.source.document.source_document_id,
                    score=min(10_000, int(score * 1_000)),
                    text=passage.text,
                    anchor=anchor,
                    reference=reference,
                )
            )
        return tuple(sorted(ranked, key=lambda item: (-item.score, item.reference.reference_span_id))[: max(1, int(limit))])


__all__ = ["IndexedPassage", "PassageIndex", "tokens"]
