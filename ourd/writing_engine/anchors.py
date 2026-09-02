from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from .models import ExtractedSource, PageSpan, TextAnchor


def normalize_text(text: str, profile: str = "unicode-whitespace-v1") -> str:
    if profile != "unicode-whitespace-v1":
        raise ValueError(f"unsupported normalization profile: {profile}")
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip()


def _page_offsets(source: ExtractedSource) -> tuple[tuple[int, int], ...]:
    if not source.pages:
        return ()
    offsets = []
    cursor = 0
    separator_length = len("\n\f\n")
    for page in source.pages:
        start = cursor
        end = start + len(page.text)
        offsets.append((start, end))
        cursor = end + separator_length
    return tuple(offsets)


def _section_path(source: ExtractedSource, start_offset: int) -> tuple[str, ...]:
    active = [label for label, offset in source.section_offsets if offset <= start_offset]
    return (active[-1],) if active else ()


def _paragraph_index(source: ExtractedSource, start_offset: int) -> int:
    for index, (start, end) in enumerate(source.paragraph_offsets):
        if start <= start_offset < end:
            return index
    return -1


def _page_spans(source: ExtractedSource, start: int, end: int) -> tuple[PageSpan, ...]:
    spans = []
    for page, (page_start, page_end) in zip(source.pages, _page_offsets(source)):
        overlap_start = max(start, page_start)
        overlap_end = min(end, page_end)
        if overlap_start >= overlap_end:
            continue
        local_start = overlap_start - page_start
        local_end = overlap_end - page_start
        selected_words = tuple(
            word for word in page.words if word.text and word.text in source.document_text[overlap_start:overlap_end]
        )
        spans.append(
            PageSpan(
                physical_page_index=page.physical_page_index,
                display_page_label=page.display_page_label,
                page_start_offset=local_start,
                page_end_offset=local_end,
                word_start_index=selected_words[0].index if selected_words else -1,
                word_end_index=selected_words[-1].index if selected_words else -1,
                line_indexes=tuple(sorted({word.line_index for word in selected_words})),
                block_indexes=tuple(sorted({word.block_index for word in selected_words})),
                bounding_quads=tuple(tuple(word.bbox) for word in selected_words if word.bbox),
            )
        )
    return tuple(spans)


def build_text_anchor(
    source: ExtractedSource,
    start_offset: int,
    end_offset: int,
    *,
    normalization_profile: str = "unicode-whitespace-v1",
    context_characters: int = 80,
) -> TextAnchor:
    start = int(start_offset)
    end = int(end_offset)
    if start < 0 or end > len(source.document_text) or end <= start:
        raise ValueError("anchor offsets are outside the extracted document")
    exact = source.document_text[start:end]
    prefix = source.document_text[max(0, start - context_characters):start]
    suffix = source.document_text[end:min(len(source.document_text), end + context_characters)]
    sentence_indexes = tuple(
        index
        for index, match in enumerate(re.finditer(r"[^.!?]+[.!?]?", source.document_text))
        if match.start() < end and match.end() > start
    )
    return TextAnchor(
        source_document_id=source.document.source_document_id,
        source_content_sha256=source.document.content_sha256,
        exact_text=exact,
        prefix_text=prefix,
        suffix_text=suffix,
        normalized_exact_text=normalize_text(exact, normalization_profile),
        normalization_profile=normalization_profile,
        document_start_offset=start,
        document_end_offset=end,
        page_spans=_page_spans(source, start, end),
        section_path=_section_path(source, start),
        paragraph_index=_paragraph_index(source, start),
        sentence_indexes=sentence_indexes,
    )


def locate_exact_text(source: ExtractedSource, exact_text: str) -> tuple[TextAnchor, ...]:
    query = exact_text.strip()
    if not query:
        raise ValueError("exact text query must be non-empty")
    matches = []
    lowered_document = source.document_text.casefold()
    lowered_query = query.casefold()
    cursor = 0
    while True:
        start = lowered_document.find(lowered_query, cursor)
        if start < 0:
            break
        matches.append(build_text_anchor(source, start, start + len(query)))
        cursor = start + max(1, len(query))
    return tuple(matches)


def verify_anchor(source: ExtractedSource, anchor: TextAnchor) -> tuple[bool, tuple[str, ...]]:
    failures = []
    if source.document.source_document_id != anchor.source_document_id:
        failures.append("source document identity mismatch")
    if source.document.content_sha256 != anchor.source_content_sha256:
        failures.append("source content hash mismatch")
    actual = source.document_text[anchor.document_start_offset:anchor.document_end_offset]
    if actual != anchor.exact_text:
        failures.append("exact text selector mismatch")
    if normalize_text(actual, anchor.normalization_profile) != anchor.normalized_exact_text:
        failures.append("normalized text selector mismatch")
    return not failures, tuple(failures)


__all__ = ["build_text_anchor", "locate_exact_text", "normalize_text", "verify_anchor"]
