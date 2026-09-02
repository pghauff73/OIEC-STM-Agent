from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence, Tuple

from .pipeline_models import QualifiedDocument
from .signatures import content_sha256, signature


REFERENCE_KINDS = {
    "quotation",
    "paraphrase_support",
    "summary_support",
    "synthesis_support",
    "definition",
    "data",
    "method",
    "counterevidence",
    "background",
}
SUPPORT_RELATIONS = {
    "entailed",
    "supported",
    "partially_supported",
    "contradicted",
    "unresolved",
    "writer_inference",
}
REASONING_COMPONENT_ROLES = {
    "thesis",
    "claim",
    "premise",
    "evidence",
    "warrant",
    "counterclaim",
    "rebuttal",
    "qualifier",
    "limitation",
    "implication",
}
FORMAL_WRITING_OPERATIONS = {
    "INSPECT_SOURCES",
    "LOCATE_REFERENCE",
    "EXPLAIN_REFERENCE",
    "BUILD_SOURCE_MAP",
    "BUILD_ARGUMENT_MAP",
    "OUTLINE",
    "DRAFT",
    "REVISE",
    "VALIDATE",
    "WRITE",
    "EXPORT_REFERENCES",
}


def _strings(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _pairs(values: Mapping[str, Any] | Sequence[tuple[str, Any]]) -> Tuple[Tuple[str, Any], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    return tuple(sorted((str(key), value) for key, value in items))


def _score(value: int, name: str) -> int:
    score = int(value)
    if not 0 <= score <= 10_000:
        raise ValueError(f"{name} must be 0..10000")
    return score


@dataclass(frozen=True)
class SourceDocument:
    schema_version: int = 1
    source_document_id: str = ""
    source_uri_or_path: str = ""
    workspace_relative_path: str = ""
    media_type: str = "application/octet-stream"
    content_sha256: str = ""
    byte_size: int = 0
    title: str = ""
    authors: Tuple[str, ...] = ()
    issued_date: str = ""
    publisher: str = ""
    edition: str = ""
    doi: str = ""
    isbn: str = ""
    language: str = "und"
    page_count: int = 0
    page_label_map: Tuple[Tuple[int, str], ...] = ()
    ingestion_adapter: str = ""
    ingestion_adapter_version: str = ""
    extraction_created_at: str = ""
    ocr_status: str = "not_requested"
    ocr_engine: str = ""
    ocr_engine_version: str = ""
    license_or_access_note: str = ""
    metadata_provenance: Tuple[Tuple[str, Any], ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("source document schema_version must be 1")
        if len(self.content_sha256) != 64:
            raise ValueError("source document requires an exact SHA-256")
        if int(self.byte_size) < 0 or int(self.page_count) < 0:
            raise ValueError("source document sizes cannot be negative")
        expected_id = f"source:{self.content_sha256}"
        if self.source_document_id and self.source_document_id != expected_id:
            raise ValueError("source document ID must be content-addressed")
        object.__setattr__(self, "source_document_id", expected_id)
        object.__setattr__(self, "authors", _strings(self.authors))
        object.__setattr__(self, "page_label_map", tuple(sorted(self.page_label_map)))
        object.__setattr__(self, "metadata_provenance", _pairs(self.metadata_provenance))
        material = {
            key: value
            for key, value in asdict(self).items()
            if key not in {"signature", "extraction_created_at"}
        }
        expected = signature(material)
        if self.signature and self.signature != expected:
            raise ValueError("source document signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class TextWord:
    index: int
    text: str
    bbox: Tuple[float, float, float, float] = ()
    block_index: int = 0
    line_index: int = 0


@dataclass(frozen=True)
class TextLine:
    index: int
    text: str
    bbox: Tuple[float, float, float, float] = ()
    block_index: int = 0


@dataclass(frozen=True)
class TextBlock:
    index: int
    text: str
    bbox: Tuple[float, float, float, float] = ()


@dataclass(frozen=True)
class PageRecord:
    source_document_id: str
    physical_page_index: int
    physical_page_number: int
    display_page_label: str
    width: float
    height: float
    coordinate_space: str
    rotation: int
    text_layer_kind: str
    extraction_confidence: int
    page_text_sha256: str
    text: str = ""
    blocks: Tuple[TextBlock, ...] = ()
    lines: Tuple[TextLine, ...] = ()
    words: Tuple[TextWord, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.physical_page_index < 0 or self.physical_page_number < 1:
            raise ValueError("invalid physical page index or number")
        object.__setattr__(self, "extraction_confidence", _score(self.extraction_confidence, "extraction confidence"))
        if self.page_text_sha256 != content_sha256(self.text):
            raise ValueError("page text hash mismatch")
        material = {key: value for key, value in asdict(self).items() if key != "signature"}
        expected = signature(material)
        if self.signature and self.signature != expected:
            raise ValueError("page record signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class PageSpan:
    physical_page_index: int
    display_page_label: str
    page_start_offset: int
    page_end_offset: int
    word_start_index: int = -1
    word_end_index: int = -1
    line_indexes: Tuple[int, ...] = ()
    block_indexes: Tuple[int, ...] = ()
    bounding_quads: Tuple[Tuple[float, ...], ...] = ()


@dataclass(frozen=True)
class TextAnchor:
    anchor_id: str = ""
    source_document_id: str = ""
    source_content_sha256: str = ""
    exact_text: str = ""
    prefix_text: str = ""
    suffix_text: str = ""
    normalized_exact_text: str = ""
    normalization_profile: str = "unicode-whitespace-v1"
    document_start_offset: int = 0
    document_end_offset: int = 0
    page_spans: Tuple[PageSpan, ...] = ()
    section_path: Tuple[str, ...] = ()
    paragraph_index: int = -1
    sentence_indexes: Tuple[int, ...] = ()
    selector_signature: str = ""

    def __post_init__(self) -> None:
        if not self.exact_text:
            raise ValueError("text anchor exact text must be non-empty")
        if self.document_end_offset <= self.document_start_offset:
            raise ValueError("text anchor offsets are invalid")
        material = {key: value for key, value in asdict(self).items() if key not in {"anchor_id", "selector_signature"}}
        expected_id = f"anchor:{signature(material)}"
        if self.anchor_id and self.anchor_id != expected_id:
            raise ValueError("text anchor ID mismatch")
        expected_signature = signature({**material, "anchor_id": expected_id})
        if self.selector_signature and self.selector_signature != expected_signature:
            raise ValueError("text anchor selector signature mismatch")
        object.__setattr__(self, "anchor_id", expected_id)
        object.__setattr__(self, "selector_signature", expected_signature)


@dataclass(frozen=True)
class ReferenceSpan:
    reference_span_id: str = ""
    anchor_id: str = ""
    reference_kind: str = "background"
    verbatim_text: str = ""
    bounded_context: str = ""
    locator_display: str = ""
    extraction_confidence: int = 10_000
    verification_status: str = "VERIFIED"
    verification_failures: Tuple[str, ...] = ()
    created_by: str = "system"
    created_at: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if self.reference_kind not in REFERENCE_KINDS:
            raise ValueError(f"invalid reference kind: {self.reference_kind}")
        object.__setattr__(self, "extraction_confidence", _score(self.extraction_confidence, "extraction confidence"))
        object.__setattr__(self, "verification_failures", _strings(self.verification_failures))
        material = {
            key: value
            for key, value in asdict(self).items()
            if key not in {"reference_span_id", "signature", "created_at"}
        }
        expected_id = f"reference:{signature(material)}"
        if self.reference_span_id and self.reference_span_id != expected_id:
            raise ValueError("reference span ID mismatch")
        expected_signature = signature({**material, "reference_span_id": expected_id})
        if self.signature and self.signature != expected_signature:
            raise ValueError("reference span signature mismatch")
        object.__setattr__(self, "reference_span_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)


@dataclass(frozen=True)
class ParaphraseLink:
    paraphrase_link_id: str = ""
    draft_text: str = ""
    source_span_ids: Tuple[str, ...] = ()
    paraphrase_kind: str = "single_source"
    lexical_overlap: int = 0
    semantic_similarity: int = 0
    support_relation: str = "unresolved"
    qualifier_preservation: bool = False
    polarity_preservation: bool = False
    scope_preservation: bool = False
    causal_strength_preservation: bool = False
    patchwriting_risk: int = 0
    unsupported_additions: Tuple[str, ...] = ()
    advisory_model: str = "deterministic-v1"
    review_status: str = "REVIEW_REQUIRED"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.support_relation not in SUPPORT_RELATIONS:
            raise ValueError("invalid paraphrase support relation")
        for name in ("lexical_overlap", "semantic_similarity", "patchwriting_risk"):
            object.__setattr__(self, name, _score(getattr(self, name), name))
        object.__setattr__(self, "source_span_ids", _strings(self.source_span_ids))
        object.__setattr__(self, "unsupported_additions", _strings(self.unsupported_additions))
        material = {key: value for key, value in asdict(self).items() if key not in {"paraphrase_link_id", "signature"}}
        expected_id = f"paraphrase:{signature(material)}"
        if self.paraphrase_link_id and self.paraphrase_link_id != expected_id:
            raise ValueError("paraphrase link ID mismatch")
        object.__setattr__(self, "paraphrase_link_id", expected_id)
        expected = signature({**material, "paraphrase_link_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("paraphrase link signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ConceptAnnotation:
    concept_annotation_id: str = ""
    concept_id: str = ""
    preferred_label: str = ""
    definition: str = ""
    aliases: Tuple[str, ...] = ()
    source_span_ids: Tuple[str, ...] = ()
    broader_concept_ids: Tuple[str, ...] = ()
    narrower_concept_ids: Tuple[str, ...] = ()
    related_concept_ids: Tuple[str, ...] = ()
    domain: str = "general"
    explicit_or_inferred: str = "inferred"
    confidence: int = 0
    proposed_by: str = "deterministic-v1"
    review_status: str = "REVIEW_REQUIRED"
    signature: str = ""

    def __post_init__(self) -> None:
        label = self.preferred_label.strip()
        if not label:
            raise ValueError("concept label must be non-empty")
        concept_id = self.concept_id or f"concept:{signature(label.casefold())}"
        object.__setattr__(self, "concept_id", concept_id)
        object.__setattr__(self, "confidence", _score(self.confidence, "concept confidence"))
        for name in ("aliases", "source_span_ids", "broader_concept_ids", "narrower_concept_ids", "related_concept_ids"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key not in {"concept_annotation_id", "signature"}}
        expected_id = f"concept-annotation:{signature(material)}"
        if self.concept_annotation_id and self.concept_annotation_id != expected_id:
            raise ValueError("concept annotation ID mismatch")
        object.__setattr__(self, "concept_annotation_id", expected_id)
        expected = signature({**material, "concept_annotation_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("concept annotation signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ReasoningAnnotation:
    reasoning_annotation_id: str = ""
    source_span_ids: Tuple[str, ...] = ()
    component_role: str = "claim"
    relation_type: str = "supports"
    inference_mode: str = "unspecified"
    source_claim: str = ""
    target_claim: str = ""
    implicit_premises: Tuple[str, ...] = ()
    qualifiers: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()
    alternative_explanations: Tuple[str, ...] = ()
    confidence: int = 0
    proposed_by: str = "deterministic-v1"
    review_status: str = "REVIEW_REQUIRED"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.component_role not in REASONING_COMPONENT_ROLES:
            raise ValueError("invalid reasoning component role")
        object.__setattr__(self, "confidence", _score(self.confidence, "reasoning confidence"))
        for name in ("source_span_ids", "implicit_premises", "qualifiers", "limitations", "alternative_explanations"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key not in {"reasoning_annotation_id", "signature"}}
        expected_id = f"reasoning:{signature(material)}"
        if self.reasoning_annotation_id and self.reasoning_annotation_id != expected_id:
            raise ValueError("reasoning annotation ID mismatch")
        object.__setattr__(self, "reasoning_annotation_id", expected_id)
        expected = signature({**material, "reasoning_annotation_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("reasoning annotation signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class BibliographicRecord:
    bibliographic_record_id: str = ""
    csl_item: Tuple[Tuple[str, Any], ...] = ()
    source_document_ids: Tuple[str, ...] = ()
    metadata_sources: Tuple[str, ...] = ()
    field_provenance: Tuple[Tuple[str, Any], ...] = ()
    conflicts: Tuple[str, ...] = ()
    unresolved_fields: Tuple[str, ...] = ()
    verified_doi: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "csl_item", _pairs(self.csl_item))
        object.__setattr__(self, "field_provenance", _pairs(self.field_provenance))
        for name in ("source_document_ids", "metadata_sources", "conflicts", "unresolved_fields"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key not in {"bibliographic_record_id", "signature"}}
        expected_id = f"bibliography:{signature(material)}"
        if self.bibliographic_record_id and self.bibliographic_record_id != expected_id:
            raise ValueError("bibliographic record ID mismatch")
        object.__setattr__(self, "bibliographic_record_id", expected_id)
        expected = signature({**material, "bibliographic_record_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("bibliographic record signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class FormalWritingRequest:
    schema_version: int = 1
    request_id: str = ""
    operation: str = "INSPECT_SOURCES"
    objective: str = ""
    profile: str = "general"
    genre: str = "essay"
    audience: str = "general"
    discipline: str = "general"
    word_target: int = 0
    source_document_ids: Tuple[str, ...] = ()
    source_paths: Tuple[str, ...] = ()
    rubric_paths: Tuple[str, ...] = ()
    draft_paths: Tuple[str, ...] = ()
    output_paths: Tuple[str, ...] = ()
    citation_style: str = "author-date"
    locale: str = "en"
    quotation_policy: str = "verify-exact"
    paraphrase_policy: str = "verify-support"
    reference_policy: str = "require-locators"
    network_policy: str = "offline"
    constraints: Tuple[str, ...] = ()
    requested_outputs: Tuple[str, ...] = ()
    authority_binding: str = ""
    context_envelope_signature: str = ""
    request_signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("formal writing request schema_version must be 1")
        operation = self.operation.strip().upper()
        if operation not in FORMAL_WRITING_OPERATIONS:
            raise ValueError(f"unsupported formal writing operation: {self.operation}")
        if not self.objective.strip():
            raise ValueError("formal writing objective must be non-empty")
        if int(self.word_target) < 0:
            raise ValueError("word target cannot be negative")
        object.__setattr__(self, "operation", operation)
        for name in (
            "source_document_ids",
            "source_paths",
            "rubric_paths",
            "draft_paths",
            "output_paths",
            "constraints",
            "requested_outputs",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key not in {"request_id", "request_signature"}}
        expected_id = f"writing-request:{signature(material)}"
        if self.request_id and self.request_id != expected_id:
            raise ValueError("formal writing request ID mismatch")
        object.__setattr__(self, "request_id", expected_id)
        expected = signature({**material, "request_id": expected_id})
        if self.request_signature and self.request_signature != expected:
            raise ValueError("formal writing request signature mismatch")
        object.__setattr__(self, "request_signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FormalWritingRequest":
        values = dict(payload)
        for name in (
            "source_document_ids",
            "source_paths",
            "rubric_paths",
            "draft_paths",
            "output_paths",
            "constraints",
            "requested_outputs",
        ):
            values[name] = tuple(values.get(name, ()))
        return cls(**values)


@dataclass(frozen=True)
class FormalWritingPlan:
    plan_id: str = ""
    request_id: str = ""
    task_interpretation: str = ""
    thesis_or_purpose: str = ""
    section_structure: Tuple[str, ...] = ()
    claim_inventory: Tuple[str, ...] = ()
    source_allocations: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    concept_coverage: Tuple[str, ...] = ()
    argument_topology_signature: str = ""
    counterargument_plan: Tuple[str, ...] = ()
    citation_style: str = "author-date"
    quotation_policy: str = "verify-exact"
    paraphrase_policy: str = "verify-support"
    unresolved_evidence_gaps: Tuple[str, ...] = ()
    planned_output_paths: Tuple[str, ...] = ()
    validation_requirements: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        for name in (
            "section_structure",
            "claim_inventory",
            "concept_coverage",
            "counterargument_plan",
            "unresolved_evidence_gaps",
            "planned_output_paths",
            "validation_requirements",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        allocations = tuple(sorted((claim, tuple(sorted(source_ids))) for claim, source_ids in self.source_allocations))
        object.__setattr__(self, "source_allocations", allocations)
        material = {key: value for key, value in asdict(self).items() if key not in {"plan_id", "signature"}}
        expected_id = f"writing-plan:{signature(material)}"
        if self.plan_id and self.plan_id != expected_id:
            raise ValueError("formal writing plan ID mismatch")
        object.__setattr__(self, "plan_id", expected_id)
        expected = signature({**material, "plan_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("formal writing plan signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class CitationUse:
    citation_use_id: str = ""
    draft_span: Tuple[int, int] = (0, 0)
    claim_id: str = ""
    bibliographic_record_ids: Tuple[str, ...] = ()
    reference_span_ids: Tuple[str, ...] = ()
    locator: str = ""
    use_kind: str = "paraphrase"
    quotation_transformations: Tuple[str, ...] = ()
    paraphrase_link_id: str = ""
    concept_annotation_ids: Tuple[str, ...] = ()
    reasoning_annotation_ids: Tuple[str, ...] = ()
    verification_status: str = "UNVERIFIED"

    def __post_init__(self) -> None:
        material = {key: value for key, value in asdict(self).items() if key != "citation_use_id"}
        expected_id = f"citation-use:{signature(material)}"
        if self.citation_use_id and self.citation_use_id != expected_id:
            raise ValueError("citation use ID mismatch")
        object.__setattr__(self, "citation_use_id", expected_id)


@dataclass(frozen=True)
class ReferenceIntegrityReport:
    report_id: str = ""
    draft_sha256: str = ""
    verified_quotations: Tuple[str, ...] = ()
    verified_paraphrases: Tuple[str, ...] = ()
    partially_supported_claims: Tuple[str, ...] = ()
    unsupported_claims: Tuple[str, ...] = ()
    contradicted_claims: Tuple[str, ...] = ()
    missing_locators: Tuple[str, ...] = ()
    stale_source_hashes: Tuple[str, ...] = ()
    metadata_conflicts: Tuple[str, ...] = ()
    unresolved_citation_fields: Tuple[str, ...] = ()
    page_label_uncertainty: Tuple[str, ...] = ()
    ocr_uncertainty: Tuple[str, ...] = ()
    patchwriting_risks: Tuple[str, ...] = ()
    concept_review_requirements: Tuple[str, ...] = ()
    reasoning_review_requirements: Tuple[str, ...] = ()
    passed: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        for name in (
            "verified_quotations",
            "verified_paraphrases",
            "partially_supported_claims",
            "unsupported_claims",
            "contradicted_claims",
            "missing_locators",
            "stale_source_hashes",
            "metadata_conflicts",
            "unresolved_citation_fields",
            "page_label_uncertainty",
            "ocr_uncertainty",
            "patchwriting_risks",
            "concept_review_requirements",
            "reasoning_review_requirements",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key not in {"report_id", "signature"}}
        expected_id = f"integrity-report:{signature(material)}"
        if self.report_id and self.report_id != expected_id:
            raise ValueError("reference integrity report ID mismatch")
        object.__setattr__(self, "report_id", expected_id)
        expected = signature({**material, "report_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("reference integrity report signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class WritingCertificate:
    certificate_id: str = ""
    draft_sha256: str = ""
    request_signature: str = ""
    plan_signature: str = ""
    integrity_report_signature: str = ""
    performed_checks: Tuple[str, ...] = ()
    passed_checks: Tuple[str, ...] = ()
    failed_checks: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        for name in ("performed_checks", "passed_checks", "failed_checks", "evidence_ids", "limitations"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = {key: value for key, value in asdict(self).items() if key not in {"certificate_id", "signature"}}
        expected_id = f"writing-certificate:{signature(material)}"
        if self.certificate_id and self.certificate_id != expected_id:
            raise ValueError("writing certificate ID mismatch")
        object.__setattr__(self, "certificate_id", expected_id)
        expected = signature({**material, "certificate_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("writing certificate signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ExtractedSource:
    document: SourceDocument
    document_text: str
    pages: Tuple[PageRecord, ...] = ()
    section_offsets: Tuple[Tuple[str, int], ...] = ()
    paragraph_offsets: Tuple[Tuple[int, int], ...] = ()
    extraction_signature: str = ""

    def __post_init__(self) -> None:
        material = {
            "document_signature": self.document.signature,
            "document_text_sha256": content_sha256(self.document_text),
            "page_signatures": tuple(page.signature for page in self.pages),
            "section_offsets": self.section_offsets,
            "paragraph_offsets": self.paragraph_offsets,
        }
        expected = signature(material)
        if self.extraction_signature and self.extraction_signature != expected:
            raise ValueError("extracted source signature mismatch")
        object.__setattr__(self, "extraction_signature", expected)


@dataclass(frozen=True)
class PassageMatch:
    source_document_id: str
    score: int
    text: str
    anchor: TextAnchor
    reference: ReferenceSpan


@dataclass(frozen=True)
class DraftArtifact:
    draft_id: str = ""
    request_id: str = ""
    plan_id: str = ""
    text: str = ""
    citation_uses: Tuple[CitationUse, ...] = ()
    source_document_ids: Tuple[str, ...] = ()
    revision_of_sha256: str = ""
    revision_notes: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("draft text must be non-empty")
        object.__setattr__(self, "source_document_ids", _strings(self.source_document_ids))
        object.__setattr__(self, "revision_notes", _strings(self.revision_notes))
        material = {
            "request_id": self.request_id,
            "plan_id": self.plan_id,
            "text_sha256": content_sha256(self.text),
            "citation_uses": tuple(asdict(item) for item in self.citation_uses),
            "source_document_ids": self.source_document_ids,
            "revision_of_sha256": self.revision_of_sha256,
            "revision_notes": self.revision_notes,
        }
        expected_id = f"draft:{signature(material)}"
        if self.draft_id and self.draft_id != expected_id:
            raise ValueError("draft ID mismatch")
        object.__setattr__(self, "draft_id", expected_id)
        expected = signature({**material, "draft_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("draft signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class FormalWritingResult:
    request: FormalWritingRequest
    sources: Tuple[SourceDocument, ...] = ()
    references: Tuple[ReferenceSpan, ...] = ()
    concepts: Tuple[ConceptAnnotation, ...] = ()
    reasoning: Tuple[ReasoningAnnotation, ...] = ()
    bibliographic_records: Tuple[BibliographicRecord, ...] = ()
    plan: FormalWritingPlan | None = None
    draft: DraftArtifact | None = None
    integrity_report: ReferenceIntegrityReport | None = None
    certificate: WritingCertificate | None = None
    qualified_document: QualifiedDocument | None = None
    output_paths: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()


__all__ = [
    "BibliographicRecord",
    "CitationUse",
    "ConceptAnnotation",
    "DraftArtifact",
    "ExtractedSource",
    "FORMAL_WRITING_OPERATIONS",
    "FormalWritingPlan",
    "FormalWritingRequest",
    "FormalWritingResult",
    "PageRecord",
    "PageSpan",
    "ParaphraseLink",
    "PassageMatch",
    "REASONING_COMPONENT_ROLES",
    "REFERENCE_KINDS",
    "ReasoningAnnotation",
    "ReferenceIntegrityReport",
    "ReferenceSpan",
    "SUPPORT_RELATIONS",
    "SourceDocument",
    "TextAnchor",
    "TextBlock",
    "TextLine",
    "TextWord",
    "WritingCertificate",
]
