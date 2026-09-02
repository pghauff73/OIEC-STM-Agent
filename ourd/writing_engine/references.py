from __future__ import annotations

from datetime import datetime, timezone

from .anchors import verify_anchor
from .models import ExtractedSource, ReferenceSpan, TextAnchor


def locator_for_anchor(source: ExtractedSource, anchor: TextAnchor) -> str:
    if anchor.page_spans:
        labels = []
        for span in anchor.page_spans:
            if span.display_page_label not in labels:
                labels.append(span.display_page_label)
        prefix = "p." if len(labels) == 1 else "pp."
        return f"{prefix} {'–'.join(labels)}"
    before = source.document_text[:anchor.document_start_offset]
    start_line = before.count("\n") + 1
    end_line = start_line + anchor.exact_text.count("\n")
    section = f", § {anchor.section_path[-1]}" if anchor.section_path else ""
    return f"lines {start_line}–{end_line}{section}"


def reference_from_anchor(
    source: ExtractedSource,
    anchor: TextAnchor,
    *,
    reference_kind: str,
    created_by: str = "system",
) -> ReferenceSpan:
    verified, failures = verify_anchor(source, anchor)
    context = f"{anchor.prefix_text}[{anchor.exact_text}]{anchor.suffix_text}"
    return ReferenceSpan(
        anchor_id=anchor.anchor_id,
        reference_kind=reference_kind,
        verbatim_text=anchor.exact_text,
        bounded_context=context,
        locator_display=locator_for_anchor(source, anchor),
        extraction_confidence=min(
            (page.extraction_confidence for page in source.pages if any(span.physical_page_index == page.physical_page_index for span in anchor.page_spans)),
            default=10_000,
        ),
        verification_status="VERIFIED" if verified else "FAILED",
        verification_failures=failures,
        created_by=created_by,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


__all__ = ["locator_for_anchor", "reference_from_anchor"]
