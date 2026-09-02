from __future__ import annotations

from typing import Mapping, Sequence

from .citations import render_bibliography, render_citation
from .metadata import bibliographic_record_from_source
from .models import (
    BibliographicRecord,
    CitationUse,
    DraftArtifact,
    FormalWritingPlan,
    FormalWritingRequest,
    ReferenceSpan,
    SourceDocument,
)
from .signatures import content_sha256


def draft_grounded_document(
    request: FormalWritingRequest,
    plan: FormalWritingPlan,
    sources: Sequence[SourceDocument],
    references: Sequence[ReferenceSpan],
    bibliographic_records: Mapping[str, BibliographicRecord] | None = None,
    reference_source_ids: Mapping[str, str] | None = None,
) -> DraftArtifact:
    records = dict(bibliographic_records or {})
    for source in sources:
        records.setdefault(source.source_document_id, bibliographic_record_from_source(source))
    lines = [f"# {request.genre.title()}: {request.objective}", "", plan.thesis_or_purpose, ""]
    citation_uses = []
    reference_by_section = list(references)
    reference_sources = dict(reference_source_ids or {})
    for section_index, section in enumerate(plan.section_structure):
        lines.extend((f"## {section}", ""))
        if section_index == 0:
            paragraph = (
                f"This {request.genre} addresses {request.objective}. The analysis is bounded to "
                f"{len(sources)} registered source artifact(s) and distinguishes verified passages from writer inference."
            )
            lines.extend((paragraph, ""))
            continue
        if section.casefold() == "conclusion":
            lines.extend((
                "The available source passages support only the calibrated conclusions stated above. "
                "Unresolved evidence gaps and source limitations remain material to interpretation.",
                "",
            ))
            continue
        if not reference_by_section:
            lines.extend(("[Evidence gap: no verified passage is allocated to this section.]", ""))
            continue
        reference = reference_by_section[(section_index - 1) % len(reference_by_section)]
        source_id = reference_sources.get(reference.reference_span_id, "")
        if not source_id and sources:
            source_id = sources[(section_index - 1) % len(sources)].source_document_id
        record = records.get(source_id) or (next(iter(records.values())) if records else None)
        citation = render_citation((record,), reference.locator_display, style=request.citation_style) if record else f"({reference.locator_display})"
        paragraph = f"The source states: “{reference.verbatim_text}” {citation}"
        start = sum(len(line) + 1 for line in lines)
        lines.extend((paragraph, ""))
        end = start + len(paragraph)
        citation_uses.append(
            CitationUse(
                draft_span=(start, end),
                claim_id=f"section-{section_index}",
                bibliographic_record_ids=(record.bibliographic_record_id,) if record else (),
                reference_span_ids=(reference.reference_span_id,),
                locator=reference.locator_display,
                use_kind="quotation",
                verification_status=reference.verification_status,
            )
        )
    if records:
        lines.extend(("## References", "", render_bibliography(tuple(records.values()), style=request.citation_style), ""))
    return DraftArtifact(
        request_id=request.request_id,
        plan_id=plan.plan_id,
        text="\n".join(lines).strip() + "\n",
        citation_uses=tuple(citation_uses),
        source_document_ids=tuple(source.source_document_id for source in sources),
    )


def revise_grounded_document(
    request: FormalWritingRequest,
    plan: FormalWritingPlan,
    sources: Sequence[SourceDocument],
    references: Sequence[ReferenceSpan],
    prior_draft_text: str,
    bibliographic_records: Mapping[str, BibliographicRecord] | None = None,
    reference_source_ids: Mapping[str, str] | None = None,
) -> DraftArtifact:
    if not prior_draft_text.strip():
        raise ValueError("revision requires a non-empty prior draft")
    candidate = draft_grounded_document(
        request,
        plan,
        sources,
        references,
        bibliographic_records,
        reference_source_ids,
    )
    return DraftArtifact(
        request_id=candidate.request_id,
        plan_id=candidate.plan_id,
        text=candidate.text,
        citation_uses=candidate.citation_uses,
        source_document_ids=candidate.source_document_ids,
        revision_of_sha256=content_sha256(prior_draft_text),
        revision_notes=(
            "Regenerated from verified source passages rather than silently editing unsupported prose.",
            "The prior draft is bound by SHA-256 for review and rollback.",
        ),
    )


__all__ = ["draft_grounded_document", "revise_grounded_document"]
