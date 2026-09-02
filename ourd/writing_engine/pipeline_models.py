from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence, Tuple

from .signatures import signature as stable_signature


CLAIM_TYPES = {
    "FACTUAL",
    "CAUSAL",
    "COMPARATIVE",
    "NORMATIVE",
    "INTERPRETIVE",
    "DEFINITIONAL",
    "HYPOTHESIS",
}
EVIDENCE_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNSUPPORTED",
    "EVIDENCE_CONFLICT",
    "EVIDENCE_INSUFFICIENT",
}
REASONING_RELATIONS = {
    "SUPPORTS",
    "CONTRADICTS",
    "QUALIFIES",
    "CAUSES",
    "GENERALIZES",
    "SPECIALIZES",
    "EXPLAINS",
    "COMPARES_WITH",
    "FALSIFIES",
    "DEPENDS_ON",
}
NOVELTY_STATUSES = {
    "KNOWN",
    "KNOWN_COMBINATION",
    "NEW_APPLICATION",
    "NEW_RELATION",
    "POTENTIAL_NOVELTY_REQUIRES_REVIEW",
}
WRITING_AUDIT_STATUSES = {
    "QUALIFIED_FORMAL_DOCUMENT",
    "REVISION_REQUIRED",
    "EVIDENCE_INSUFFICIENT",
}


def _strings(values: Iterable[Any], *, preserve_order: bool = False) -> Tuple[str, ...]:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if preserve_order:
        return tuple(dict.fromkeys(cleaned))
    return tuple(sorted(set(cleaned)))


def _pairs(
    values: Mapping[str, Any] | Sequence[tuple[str, Any]],
) -> Tuple[Tuple[str, Any], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    return tuple(sorted((str(key), value) for key, value in items))


def _score(value: int, name: str) -> int:
    normalized = int(value)
    if not 0 <= normalized <= 10_000:
        raise ValueError(f"{name} must be 0..10000")
    return normalized


def _signed_material(instance: Any, *, omit: Sequence[str]) -> dict[str, Any]:
    omitted = set(omit)
    return {
        key: value
        for key, value in asdict(instance).items()
        if key not in omitted
    }


@dataclass(frozen=True)
class WritingTask:
    task_id: str = ""
    question: str = ""
    profile: str = "general"
    genre: str = "essay"
    audience: str = "general"
    discipline: str = "general"
    word_target: int = 0
    citation_style: str = "author-date"
    source_document_ids: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    required_counterargument: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("writing task question must be non-empty")
        if int(self.word_target) < 0:
            raise ValueError("writing task word target cannot be negative")
        object.__setattr__(self, "source_document_ids", _strings(self.source_document_ids))
        object.__setattr__(self, "constraints", _strings(self.constraints))
        material = _signed_material(self, omit=("task_id", "signature"))
        expected_id = f"writing-task:{stable_signature(material)}"
        if self.task_id and self.task_id != expected_id:
            raise ValueError("writing task ID mismatch")
        object.__setattr__(self, "task_id", expected_id)
        expected = stable_signature({**material, "task_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("writing task signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ConceptDefinition:
    concept_id: str = ""
    preferred_label: str = ""
    definition: str = ""
    scope: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()
    exclusions: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    source_annotation_ids: Tuple[str, ...] = ()
    status: str = "REVIEW_REQUIRED"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.preferred_label.strip() or not self.definition.strip():
            raise ValueError("concept definition requires a label and definition")
        for name in (
            "scope",
            "aliases",
            "exclusions",
            "evidence_ids",
            "source_annotation_ids",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = _signed_material(self, omit=("concept_id", "signature"))
        expected_id = self.concept_id or f"writing-concept:{stable_signature(material)}"
        object.__setattr__(self, "concept_id", expected_id)
        expected = stable_signature({**material, "concept_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("concept definition signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class Claim:
    claim_id: str = ""
    statement: str = ""
    claim_type: str = "FACTUAL"
    semantic_terms: Tuple[str, ...] = ()
    evidence_requirements: Tuple[str, ...] = ()
    supporting_evidence: Tuple[str, ...] = ()
    counterevidence: Tuple[str, ...] = ()
    confidence_bp: int = 0
    status: str = "EVIDENCE_INSUFFICIENT"
    scope: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()
    material: bool = True
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("claim statement must be non-empty")
        normalized_type = self.claim_type.strip().upper()
        if normalized_type not in CLAIM_TYPES:
            raise ValueError(f"unsupported claim type: {self.claim_type}")
        normalized_status = self.status.strip().upper()
        if normalized_status not in EVIDENCE_STATUSES:
            raise ValueError(f"unsupported claim status: {self.status}")
        object.__setattr__(self, "claim_type", normalized_type)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "confidence_bp", _score(self.confidence_bp, "claim confidence"))
        for name in (
            "semantic_terms",
            "evidence_requirements",
            "supporting_evidence",
            "counterevidence",
            "scope",
            "limitations",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = _signed_material(self, omit=("claim_id", "signature"))
        expected_id = f"writing-claim:{stable_signature(material)}"
        if self.claim_id and self.claim_id != expected_id:
            raise ValueError("claim ID mismatch")
        object.__setattr__(self, "claim_id", expected_id)
        expected = stable_signature({**material, "claim_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("claim signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class EvidenceLink:
    evidence_link_id: str = ""
    claim_id: str = ""
    evidence_artifact_id: str = ""
    source_document_id: str = ""
    source_provenance: Tuple[Tuple[str, Any], ...] = ()
    support_relation: str = "UNSUPPORTED"
    scope_compatible: bool = False
    strength_bp: int = 0
    status: str = "EVIDENCE_INSUFFICIENT"
    limitations: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.claim_id or not self.evidence_artifact_id:
            raise ValueError("evidence link requires claim and evidence IDs")
        relation = self.support_relation.strip().upper()
        status = self.status.strip().upper()
        if relation not in EVIDENCE_STATUSES or status not in EVIDENCE_STATUSES:
            raise ValueError("invalid evidence support relation or status")
        object.__setattr__(self, "support_relation", relation)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source_provenance", _pairs(self.source_provenance))
        object.__setattr__(self, "limitations", _strings(self.limitations))
        object.__setattr__(self, "strength_bp", _score(self.strength_bp, "evidence strength"))
        material = _signed_material(self, omit=("evidence_link_id", "signature"))
        expected_id = f"evidence-link:{stable_signature(material)}"
        if self.evidence_link_id and self.evidence_link_id != expected_id:
            raise ValueError("evidence link ID mismatch")
        object.__setattr__(self, "evidence_link_id", expected_id)
        expected = stable_signature({**material, "evidence_link_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("evidence link signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ReasoningEdge:
    edge_id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation: str = "SUPPORTS"
    rationale: str = ""
    evidence_ids: Tuple[str, ...] = ()
    inference_mode: str = "unspecified"
    confidence_bp: int = 0
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.source_id or not self.target_id or self.source_id == self.target_id:
            raise ValueError("reasoning edge requires distinct endpoints")
        relation = self.relation.strip().upper()
        if relation not in REASONING_RELATIONS:
            raise ValueError(f"unsupported reasoning relation: {self.relation}")
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids))
        object.__setattr__(self, "confidence_bp", _score(self.confidence_bp, "reasoning confidence"))
        material = _signed_material(self, omit=("edge_id", "signature"))
        expected_id = f"writing-edge:{stable_signature(material)}"
        if self.edge_id and self.edge_id != expected_id:
            raise ValueError("reasoning edge ID mismatch")
        object.__setattr__(self, "edge_id", expected_id)
        expected = stable_signature({**material, "edge_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("reasoning edge signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class CounterClaim:
    counterclaim_id: str = ""
    claim: Claim | None = None
    target_claim_ids: Tuple[str, ...] = ()
    counterevidence_ids: Tuple[str, ...] = ()
    response_claim_ids: Tuple[str, ...] = ()
    status: str = "UNANSWERED"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.claim is None:
            raise ValueError("counterclaim requires a claim")
        for name in ("target_claim_ids", "counterevidence_ids", "response_claim_ids"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = _signed_material(self, omit=("counterclaim_id", "signature"))
        expected_id = f"counterclaim:{stable_signature(material)}"
        if self.counterclaim_id and self.counterclaim_id != expected_id:
            raise ValueError("counterclaim ID mismatch")
        object.__setattr__(self, "counterclaim_id", expected_id)
        expected = stable_signature({**material, "counterclaim_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("counterclaim signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class Qualification:
    qualification_id: str = ""
    target_claim_id: str = ""
    statement: str = ""
    triggers: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    adequacy_bp: int = 0
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.target_claim_id or not self.statement.strip():
            raise ValueError("qualification requires a target claim and statement")
        object.__setattr__(self, "triggers", _strings(self.triggers))
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids))
        object.__setattr__(self, "adequacy_bp", _score(self.adequacy_bp, "qualification adequacy"))
        material = _signed_material(self, omit=("qualification_id", "signature"))
        expected_id = f"qualification:{stable_signature(material)}"
        if self.qualification_id and self.qualification_id != expected_id:
            raise ValueError("qualification ID mismatch")
        object.__setattr__(self, "qualification_id", expected_id)
        expected = stable_signature({**material, "qualification_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("qualification signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class GraphIssue:
    code: str
    severity: str
    subject_ids: Tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        if not self.code or not self.message.strip():
            raise ValueError("graph issue requires a code and message")
        object.__setattr__(self, "subject_ids", _strings(self.subject_ids))


@dataclass(frozen=True)
class ArgumentGraph:
    graph_id: str = ""
    thesis_claim_id: str = ""
    claims: Tuple[Claim, ...] = ()
    evidence_links: Tuple[EvidenceLink, ...] = ()
    reasoning_edges: Tuple[ReasoningEdge, ...] = ()
    counterclaims: Tuple[CounterClaim, ...] = ()
    qualifications: Tuple[Qualification, ...] = ()
    concepts: Tuple[ConceptDefinition, ...] = ()
    issues: Tuple[GraphIssue, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        claim_ids = {claim.claim_id for claim in self.claims}
        if not self.thesis_claim_id or self.thesis_claim_id not in claim_ids:
            raise ValueError("argument graph requires a known thesis claim")
        if len(claim_ids) != len(self.claims):
            raise ValueError("argument graph claim IDs must be unique")
        known_ids = claim_ids | {
            link.evidence_link_id for link in self.evidence_links
        } | {qualification.qualification_id for qualification in self.qualifications}
        if any(
            edge.source_id not in known_ids or edge.target_id not in known_ids
            for edge in self.reasoning_edges
        ):
            raise ValueError("argument graph edge references an unknown node")
        material = _signed_material(self, omit=("graph_id", "signature"))
        expected_id = f"argument-graph:{stable_signature(material)}"
        if self.graph_id and self.graph_id != expected_id:
            raise ValueError("argument graph ID mismatch")
        object.__setattr__(self, "graph_id", expected_id)
        expected = stable_signature({**material, "graph_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("argument graph signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ReasoningPathCandidate:
    path_id: str = ""
    pattern_name: str = ""
    claim_ids: Tuple[str, ...] = ()
    edge_ids: Tuple[str, ...] = ()
    score_components: Tuple[Tuple[str, int], ...] = ()
    total_score_bp: int = 0
    source_algorithm_ids: Tuple[str, ...] = ()
    adaptation_notes: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.pattern_name.strip() or not self.claim_ids:
            raise ValueError("reasoning path requires a pattern and claims")
        object.__setattr__(self, "claim_ids", _strings(self.claim_ids, preserve_order=True))
        object.__setattr__(self, "edge_ids", _strings(self.edge_ids, preserve_order=True))
        object.__setattr__(self, "source_algorithm_ids", _strings(self.source_algorithm_ids))
        object.__setattr__(self, "adaptation_notes", _strings(self.adaptation_notes))
        normalized_scores = tuple(
            sorted((str(name), _score(score, f"path score {name}")) for name, score in self.score_components)
        )
        object.__setattr__(self, "score_components", normalized_scores)
        object.__setattr__(self, "total_score_bp", _score(self.total_score_bp, "path total score"))
        material = _signed_material(self, omit=("path_id", "signature"))
        expected_id = f"writing-path:{stable_signature(material)}"
        if self.path_id and self.path_id != expected_id:
            raise ValueError("reasoning path ID mismatch")
        object.__setattr__(self, "path_id", expected_id)
        expected = stable_signature({**material, "path_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("reasoning path signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ParagraphPlan:
    paragraph_plan_id: str = ""
    section_title: str = ""
    order: int = 0
    purpose: str = ""
    claim_ids: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    reasoning_edge_ids: Tuple[str, ...] = ()
    qualification_ids: Tuple[str, ...] = ()
    link: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.section_title.strip() or not self.purpose.strip() or not self.claim_ids:
            raise ValueError("paragraph plan requires section, purpose, and claim")
        if int(self.order) < 0:
            raise ValueError("paragraph plan order cannot be negative")
        for name in ("claim_ids", "evidence_ids", "reasoning_edge_ids", "qualification_ids"):
            object.__setattr__(self, name, _strings(getattr(self, name), preserve_order=True))
        material = _signed_material(self, omit=("paragraph_plan_id", "signature"))
        expected_id = f"paragraph-plan:{stable_signature(material)}"
        if self.paragraph_plan_id and self.paragraph_plan_id != expected_id:
            raise ValueError("paragraph plan ID mismatch")
        object.__setattr__(self, "paragraph_plan_id", expected_id)
        expected = stable_signature({**material, "paragraph_plan_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("paragraph plan signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class DocumentPlan:
    document_plan_id: str = ""
    task: WritingTask | None = None
    graph: ArgumentGraph | None = None
    candidate_paths: Tuple[ReasoningPathCandidate, ...] = ()
    selected_path_id: str = ""
    paragraph_plans: Tuple[ParagraphPlan, ...] = ()
    no_new_material_claims: bool = True
    unresolved_evidence_gaps: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.task is None or self.graph is None:
            raise ValueError("document plan requires a task and argument graph")
        path_ids = {path.path_id for path in self.candidate_paths}
        if self.selected_path_id and self.selected_path_id not in path_ids:
            raise ValueError("document plan selected path is unknown")
        object.__setattr__(self, "unresolved_evidence_gaps", _strings(self.unresolved_evidence_gaps))
        material = _signed_material(self, omit=("document_plan_id", "signature"))
        expected_id = f"document-plan:{stable_signature(material)}"
        if self.document_plan_id and self.document_plan_id != expected_id:
            raise ValueError("document plan ID mismatch")
        object.__setattr__(self, "document_plan_id", expected_id)
        expected = stable_signature({**material, "document_plan_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("document plan signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class DraftSection:
    draft_section_id: str = ""
    paragraph_plan_id: str = ""
    heading: str = ""
    text: str = ""
    claim_ids: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    reasoning_edge_ids: Tuple[str, ...] = ()
    qualification_ids: Tuple[str, ...] = ()
    sentence_claim_map: Tuple[Tuple[int, int, str], ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.heading.strip() or not self.text.strip() or not self.claim_ids:
            raise ValueError("draft section requires heading, text, and claims")
        for name in ("claim_ids", "evidence_ids", "reasoning_edge_ids", "qualification_ids"):
            object.__setattr__(self, name, _strings(getattr(self, name), preserve_order=True))
        for start, end, claim_id in self.sentence_claim_map:
            if start < 0 or end <= start or end > len(self.text) or not claim_id:
                raise ValueError("invalid sentence-to-claim mapping")
        material = _signed_material(self, omit=("draft_section_id", "signature"))
        expected_id = f"draft-section:{stable_signature(material)}"
        if self.draft_section_id and self.draft_section_id != expected_id:
            raise ValueError("draft section ID mismatch")
        object.__setattr__(self, "draft_section_id", expected_id)
        expected = stable_signature({**material, "draft_section_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("draft section signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class FalsificationChallenge:
    challenge_id: str = ""
    claim_id: str = ""
    challenge: str = ""
    counterevidence_ids: Tuple[str, ...] = ()
    alternative_explanations: Tuple[str, ...] = ()
    response: str = ""
    qualification_id: str = ""
    status: str = "OPEN"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.claim_id or not self.challenge.strip():
            raise ValueError("falsification challenge requires a claim and challenge")
        object.__setattr__(self, "counterevidence_ids", _strings(self.counterevidence_ids))
        object.__setattr__(self, "alternative_explanations", _strings(self.alternative_explanations))
        material = _signed_material(self, omit=("challenge_id", "signature"))
        expected_id = f"writing-challenge:{stable_signature(material)}"
        if self.challenge_id and self.challenge_id != expected_id:
            raise ValueError("falsification challenge ID mismatch")
        object.__setattr__(self, "challenge_id", expected_id)
        expected = stable_signature({**material, "challenge_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("falsification challenge signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class NoveltyAssessment:
    assessment_id: str = ""
    claim_id: str = ""
    status: str = "KNOWN"
    matching_claim_ids: Tuple[str, ...] = ()
    matching_algorithm_ids: Tuple[str, ...] = ()
    rationale: str = ""
    requires_review: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        normalized = self.status.strip().upper()
        if normalized not in NOVELTY_STATUSES:
            raise ValueError(f"unsupported novelty status: {self.status}")
        if not self.claim_id or not self.rationale.strip():
            raise ValueError("novelty assessment requires claim and rationale")
        if normalized == "POTENTIAL_NOVELTY_REQUIRES_REVIEW" and not self.requires_review:
            raise ValueError("potential novelty must require review")
        object.__setattr__(self, "status", normalized)
        object.__setattr__(self, "matching_claim_ids", _strings(self.matching_claim_ids))
        object.__setattr__(self, "matching_algorithm_ids", _strings(self.matching_algorithm_ids))
        material = _signed_material(self, omit=("assessment_id", "signature"))
        expected_id = f"novelty-assessment:{stable_signature(material)}"
        if self.assessment_id and self.assessment_id != expected_id:
            raise ValueError("novelty assessment ID mismatch")
        object.__setattr__(self, "assessment_id", expected_id)
        expected = stable_signature({**material, "assessment_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("novelty assessment signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class WritingAudit:
    audit_id: str = ""
    document_plan_id: str = ""
    material_claims: int = 0
    fully_supported_claims: int = 0
    partially_supported_claims: int = 0
    unsupported_claims: int = 0
    claim_support_rate_bp: int = 0
    evidence_coverage_bp: int = 0
    semantic_consistency_bp: int = 0
    argument_connectivity_bp: int = 0
    unsupported_claim_rate_bp: int = 0
    counterargument_coverage_bp: int = 0
    qualification_adequacy_bp: int = 0
    citation_traceability_bp: int = 0
    unsupported_claim_ids: Tuple[str, ...] = ()
    graph_issue_codes: Tuple[str, ...] = ()
    performed_checks: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()
    status: str = "REVISION_REQUIRED"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.document_plan_id:
            raise ValueError("writing audit requires a document plan ID")
        for name in (
            "material_claims",
            "fully_supported_claims",
            "partially_supported_claims",
            "unsupported_claims",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in (
            "claim_support_rate_bp",
            "evidence_coverage_bp",
            "semantic_consistency_bp",
            "argument_connectivity_bp",
            "unsupported_claim_rate_bp",
            "counterargument_coverage_bp",
            "qualification_adequacy_bp",
            "citation_traceability_bp",
        ):
            object.__setattr__(self, name, _score(getattr(self, name), name))
        normalized_status = self.status.strip().upper()
        if normalized_status not in WRITING_AUDIT_STATUSES:
            raise ValueError(f"unsupported writing audit status: {self.status}")
        object.__setattr__(self, "status", normalized_status)
        for name in (
            "unsupported_claim_ids",
            "graph_issue_codes",
            "performed_checks",
            "limitations",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        material = _signed_material(self, omit=("audit_id", "signature"))
        expected_id = f"writing-audit:{stable_signature(material)}"
        if self.audit_id and self.audit_id != expected_id:
            raise ValueError("writing audit ID mismatch")
        object.__setattr__(self, "audit_id", expected_id)
        expected = stable_signature({**material, "audit_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("writing audit signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ReasoningAlgorithmProposal:
    proposal_id: str = ""
    name: str = ""
    pattern_name: str = ""
    source_document_plan_id: str = ""
    source_audit_id: str = ""
    applicability: Tuple[Tuple[str, Any], ...] = ()
    invariants: Tuple[str, ...] = ()
    status: str = "PROPOSED_PENDING_HUMAN_REVIEW"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.pattern_name.strip():
            raise ValueError("reasoning algorithm proposal requires a name and pattern")
        if not self.source_document_plan_id or not self.source_audit_id:
            raise ValueError("reasoning algorithm proposal requires plan and audit provenance")
        object.__setattr__(self, "applicability", _pairs(self.applicability))
        object.__setattr__(self, "invariants", _strings(self.invariants))
        material = _signed_material(self, omit=("proposal_id", "signature"))
        expected_id = f"writing-algorithm-proposal:{stable_signature(material)}"
        if self.proposal_id and self.proposal_id != expected_id:
            raise ValueError("reasoning algorithm proposal ID mismatch")
        object.__setattr__(self, "proposal_id", expected_id)
        expected = stable_signature({**material, "proposal_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("reasoning algorithm proposal signature mismatch")
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class QualifiedDocument:
    qualified_document_id: str = ""
    plan: DocumentPlan | None = None
    draft_sections: Tuple[DraftSection, ...] = ()
    falsification_challenges: Tuple[FalsificationChallenge, ...] = ()
    audit: WritingAudit | None = None
    novelty_assessments: Tuple[NoveltyAssessment, ...] = ()
    reasoning_algorithm_proposal: ReasoningAlgorithmProposal | None = None
    revision_of_sha256: str = ""
    status: str = "REVISION_REQUIRED"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.plan is None or self.audit is None:
            raise ValueError("qualified document requires a plan and audit")
        if self.status != self.audit.status:
            raise ValueError("qualified document status must match its audit")
        material = _signed_material(self, omit=("qualified_document_id", "signature"))
        expected_id = f"qualified-document:{stable_signature(material)}"
        if self.qualified_document_id and self.qualified_document_id != expected_id:
            raise ValueError("qualified document ID mismatch")
        object.__setattr__(self, "qualified_document_id", expected_id)
        expected = stable_signature({**material, "qualified_document_id": expected_id})
        if self.signature and self.signature != expected:
            raise ValueError("qualified document signature mismatch")
        object.__setattr__(self, "signature", expected)


__all__ = [
    "ArgumentGraph",
    "CLAIM_TYPES",
    "Claim",
    "ConceptDefinition",
    "CounterClaim",
    "DocumentPlan",
    "DraftSection",
    "EVIDENCE_STATUSES",
    "EvidenceLink",
    "FalsificationChallenge",
    "GraphIssue",
    "NOVELTY_STATUSES",
    "NoveltyAssessment",
    "ParagraphPlan",
    "QualifiedDocument",
    "REASONING_RELATIONS",
    "ReasoningAlgorithmProposal",
    "ReasoningEdge",
    "ReasoningPathCandidate",
    "Qualification",
    "WRITING_AUDIT_STATUSES",
    "WritingAudit",
    "WritingTask",
]
