from __future__ import annotations

from typing import Mapping, Sequence

from .models import (
    ConceptAnnotation,
    DraftArtifact,
    FormalWritingPlan,
    FormalWritingRequest,
    ParaphraseLink,
    ReasoningAnnotation,
    ReferenceIntegrityReport,
    ReferenceSpan,
    SourceDocument,
    WritingCertificate,
)
from .signatures import content_sha256


def validate_references(
    draft: DraftArtifact,
    references: Sequence[ReferenceSpan],
    sources: Sequence[SourceDocument],
    *,
    paraphrases: Sequence[ParaphraseLink] = (),
    concepts: Sequence[ConceptAnnotation] = (),
    reasoning: Sequence[ReasoningAnnotation] = (),
    current_hashes: Mapping[str, str] | None = None,
) -> ReferenceIntegrityReport:
    reference_map = {item.reference_span_id: item for item in references}
    verified_quotations = []
    missing_locators = []
    unsupported = []
    for use in draft.citation_uses:
        if not use.reference_span_ids:
            unsupported.append(use.claim_id)
            continue
        for reference_id in use.reference_span_ids:
            reference = reference_map.get(reference_id)
            if reference is None or reference.verification_status != "VERIFIED":
                unsupported.append(use.claim_id)
                continue
            if use.use_kind == "quotation":
                verified_quotations.append(reference_id)
            if not reference.locator_display:
                missing_locators.append(reference_id)
    stale = []
    if current_hashes is not None:
        for source in sources:
            current = current_hashes.get(source.workspace_relative_path)
            if current is not None and current != source.content_sha256:
                stale.append(source.source_document_id)
    verified_paraphrases = tuple(
        item.paraphrase_link_id for item in paraphrases if item.support_relation in {"entailed", "supported"}
    )
    partial = tuple(
        item.paraphrase_link_id for item in paraphrases if item.support_relation == "partially_supported"
    )
    contradicted = tuple(
        item.paraphrase_link_id for item in paraphrases if item.support_relation == "contradicted"
    )
    patchwriting = tuple(
        item.paraphrase_link_id for item in paraphrases if item.patchwriting_risk >= 2_000
    )
    passed = not (unsupported or missing_locators or stale or contradicted)
    return ReferenceIntegrityReport(
        draft_sha256=content_sha256(draft.text),
        verified_quotations=tuple(verified_quotations),
        verified_paraphrases=verified_paraphrases,
        partially_supported_claims=partial,
        unsupported_claims=tuple(unsupported),
        contradicted_claims=contradicted,
        missing_locators=tuple(missing_locators),
        stale_source_hashes=tuple(stale),
        unresolved_citation_fields=tuple(
            source.source_document_id for source in sources if not source.title
        ),
        page_label_uncertainty=tuple(
            source.source_document_id for source in sources if source.page_count and not source.page_label_map
        ),
        ocr_uncertainty=tuple(
            source.source_document_id for source in sources if source.ocr_status == "performed"
        ),
        patchwriting_risks=patchwriting,
        concept_review_requirements=tuple(
            item.concept_annotation_id for item in concepts if item.review_status != "VERIFIED"
        ),
        reasoning_review_requirements=tuple(
            item.reasoning_annotation_id for item in reasoning if item.review_status != "VERIFIED"
        ),
        passed=passed,
    )


def writing_certificate(
    request: FormalWritingRequest,
    plan: FormalWritingPlan,
    draft: DraftArtifact,
    report: ReferenceIntegrityReport,
) -> WritingCertificate:
    performed = (
        "draft hash bound",
        "source hash freshness",
        "quotation/reference linkage",
        "locator presence",
        "paraphrase support classification",
    )
    passed = performed if report.passed else ("draft hash bound",)
    failed = tuple(item for item in performed if item not in passed)
    return WritingCertificate(
        draft_sha256=content_sha256(draft.text),
        request_signature=request.request_signature,
        plan_signature=plan.signature,
        integrity_report_signature=report.signature,
        performed_checks=performed,
        passed_checks=passed,
        failed_checks=failed,
        limitations=(
            "This certificate records deterministic checks only.",
            "It does not certify truth, academic acceptability, originality, or institutional compliance.",
        ),
    )


__all__ = ["validate_references", "writing_certificate"]
