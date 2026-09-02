from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .citations import render_bibliography, render_citation
from .metadata import bibliographic_record_from_source
from .models import (
    BibliographicRecord,
    CitationUse,
    ConceptAnnotation,
    DraftArtifact,
    FormalWritingRequest,
    ReasoningAnnotation,
    ReferenceSpan,
    SourceDocument,
)
from .passage_index import tokens
from .pipeline_models import (
    ArgumentGraph,
    Claim,
    ConceptDefinition,
    CounterClaim,
    DocumentPlan,
    DraftSection,
    EvidenceLink,
    FalsificationChallenge,
    GraphIssue,
    NoveltyAssessment,
    ParagraphPlan,
    QualifiedDocument,
    ReasoningAlgorithmProposal,
    ReasoningEdge,
    ReasoningPathCandidate,
    Qualification,
    WritingAudit,
    WritingTask,
)
from .progress import CancellationCheck, ProgressSink, report_progress, require_not_cancelled


PROFILE_SPECS: dict[str, dict[str, Any]] = {
    "general": {
        "sections": ("Introduction", "Analysis", "Conclusion"),
        "claim_types": tuple(sorted({"FACTUAL", "INTERPRETIVE", "DEFINITIONAL", "HYPOTHESIS"})),
        "counterargument": False,
        "qualification": True,
        "patterns": ("evidence-synthesis argument", "problem-solution argument"),
    },
    "scientific-essay": {
        "sections": ("Question", "Current Evidence", "Competing Explanation", "Limitations", "Conclusion"),
        "claim_types": tuple(sorted({"FACTUAL", "CAUSAL", "COMPARATIVE", "INTERPRETIVE", "HYPOTHESIS"})),
        "counterargument": True,
        "qualification": True,
        "patterns": ("falsification-first argument", "causal argument", "evidence-synthesis argument"),
    },
    "argumentative-essay": {
        "sections": ("Position", "Support", "Counterargument", "Rebuttal", "Qualified Conclusion"),
        "claim_types": tuple(sorted({"FACTUAL", "CAUSAL", "COMPARATIVE", "NORMATIVE", "INTERPRETIVE"})),
        "counterargument": True,
        "qualification": True,
        "patterns": ("comparison argument", "falsification-first argument", "problem-solution argument"),
    },
    "engineering-report": {
        "sections": ("Objective", "Evidence and Constraints", "Options", "Recommendation", "Limitations"),
        "claim_types": tuple(sorted({"FACTUAL", "CAUSAL", "COMPARATIVE", "NORMATIVE", "HYPOTHESIS"})),
        "counterargument": True,
        "qualification": True,
        "patterns": ("problem-solution argument", "comparison argument", "causal argument"),
    },
    "literature-review": {
        "sections": ("Review Question", "Evidence Themes", "Disagreement", "Synthesis", "Gaps"),
        "claim_types": tuple(sorted({"FACTUAL", "COMPARATIVE", "INTERPRETIVE", "DEFINITIONAL", "HYPOTHESIS"})),
        "counterargument": True,
        "qualification": True,
        "patterns": ("evidence-synthesis argument", "comparison argument", "falsification-first argument"),
    },
    "business-analysis": {
        "sections": ("Decision", "Benefits", "Costs and Risks", "Alternatives", "Qualified Recommendation"),
        "claim_types": tuple(sorted({"FACTUAL", "CAUSAL", "COMPARATIVE", "NORMATIVE", "HYPOTHESIS"})),
        "counterargument": True,
        "qualification": True,
        "patterns": ("comparison argument", "problem-solution argument", "evidence-synthesis argument"),
    },
    "research-proposal": {
        "sections": ("Problem", "Existing Knowledge", "Research Gap", "Method Rationale", "Expected Contribution"),
        "claim_types": tuple(sorted({"FACTUAL", "CAUSAL", "INTERPRETIVE", "NORMATIVE", "HYPOTHESIS"})),
        "counterargument": True,
        "qualification": True,
        "patterns": ("problem-solution argument", "falsification-first argument", "causal argument"),
    },
    "lab-report": {
        "sections": ("Question", "Method", "Results", "Interpretation", "Limitations"),
        "claim_types": tuple(sorted({"FACTUAL", "CAUSAL", "COMPARATIVE", "INTERPRETIVE", "HYPOTHESIS"})),
        "counterargument": False,
        "qualification": True,
        "patterns": ("causal argument", "falsification-first argument", "evidence-synthesis argument"),
    },
}


EVIDENCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "FACTUAL": ("verified source artifact", "scope-compatible observation"),
    "CAUSAL": ("verified source artifact", "causal design or mechanism", "alternative explanation analysis"),
    "COMPARATIVE": ("verified evidence for each comparison side", "common comparison scope"),
    "NORMATIVE": ("supported factual premises", "explicit value or decision criterion"),
    "INTERPRETIVE": ("verified source artifact", "explicit inference and alternatives"),
    "DEFINITIONAL": ("authoritative definition or stable source usage", "scope and exclusions"),
    "HYPOTHESIS": ("supporting observation", "falsifier or test condition", "uncertainty qualification"),
}


POSITIVE_RELATIONS = {
    "SUPPORTS",
    "CAUSES",
    "GENERALIZES",
    "SPECIALIZES",
    "EXPLAINS",
    "COMPARES_WITH",
    "DEPENDS_ON",
}
NEGATION_TERMS = {"not", "no", "never", "cannot", "without", "fails", "false"}


@dataclass(frozen=True)
class _KnownPattern:
    name: str
    source_algorithm_ids: tuple[str, ...] = ()


def _profile(profile: str) -> dict[str, Any]:
    try:
        return PROFILE_SPECS[profile]
    except KeyError as exc:
        raise ValueError(f"unsupported formal writing profile: {profile}") from exc


def build_writing_task(
    request: FormalWritingRequest,
    sources: Sequence[SourceDocument],
) -> WritingTask:
    profile = _profile(request.profile)
    return WritingTask(
        question=request.objective,
        profile=request.profile,
        genre=request.genre,
        audience=request.audience,
        discipline=request.discipline,
        word_target=request.word_target,
        citation_style=request.citation_style,
        source_document_ids=tuple(source.source_document_id for source in sources),
        constraints=request.constraints,
        required_counterargument=bool(profile["counterargument"]),
    )


def resolve_meaning(
    task: WritingTask,
    annotations: Sequence[ConceptAnnotation],
) -> tuple[ConceptDefinition, ...]:
    definitions = []
    for annotation in annotations:
        scope = tuple(
            item
            for item in (task.discipline, annotation.domain)
            if item and item != "general"
        ) or ("task-bound usage",)
        exclusions = (
            "unstated broader meanings",
            "uses outside the registered source scope",
        )
        definitions.append(
            ConceptDefinition(
                concept_id=annotation.concept_id,
                preferred_label=annotation.preferred_label,
                definition=annotation.definition,
                scope=scope,
                aliases=annotation.aliases,
                exclusions=exclusions,
                evidence_ids=annotation.source_span_ids,
                source_annotation_ids=(annotation.concept_annotation_id,),
                status=annotation.review_status,
            )
        )
    return tuple(sorted(definitions, key=lambda item: item.preferred_label.casefold()))


def classify_claim(statement: str) -> str:
    lowered = statement.casefold()
    if any(cue in lowered for cue in ("causes", "caused", "leads to", "results in", "because")):
        return "CAUSAL"
    if any(cue in lowered for cue in ("compared with", "compared to", "more than", "less than", "whereas")):
        return "COMPARATIVE"
    if re.search(r"\b(should|ought|must be adopted|recommend)\b", lowered):
        return "NORMATIVE"
    if any(cue in lowered for cue in ("is defined as", "means that", "refers to", "definition")):
        return "DEFINITIONAL"
    if any(cue in lowered for cue in ("hypothesis", "may", "might", "could")):
        return "HYPOTHESIS"
    if any(cue in lowered for cue in ("suggests", "implies", "indicates", "interpreted")):
        return "INTERPRETIVE"
    return "FACTUAL"


def _semantic_terms(statement: str, concepts: Sequence[ConceptDefinition]) -> tuple[str, ...]:
    lowered = statement.casefold()
    return tuple(
        concept.preferred_label
        for concept in concepts
        if concept.preferred_label.casefold() in lowered
        or any(alias.casefold() in lowered for alias in concept.aliases)
    )


def _claim_status(reference_ids: Sequence[str], reference_map: Mapping[str, ReferenceSpan]) -> str:
    if not reference_ids:
        return "EVIDENCE_INSUFFICIENT"
    statuses = [
        reference_map[reference_id].verification_status
        for reference_id in reference_ids
        if reference_id in reference_map
    ]
    if not statuses:
        return "UNSUPPORTED"
    if all(status == "VERIFIED" for status in statuses):
        return "SUPPORTED"
    if any(status == "VERIFIED" for status in statuses):
        return "PARTIALLY_SUPPORTED"
    return "UNSUPPORTED"


def generate_claims(
    task: WritingTask,
    concepts: Sequence[ConceptDefinition],
    annotations: Sequence[ReasoningAnnotation],
    references: Sequence[ReferenceSpan],
) -> tuple[Claim, ...]:
    reference_map = {reference.reference_span_id: reference for reference in references}
    claims = []
    seen_statements: set[str] = set()
    for annotation in annotations:
        statement = (annotation.source_claim or annotation.target_claim).strip()
        statement_key = " ".join(statement.casefold().split())
        if not statement or statement_key in seen_statements:
            continue
        seen_statements.add(statement_key)
        claim_type = classify_claim(statement)
        limitations = tuple(annotation.limitations) + tuple(annotation.alternative_explanations)
        status = _claim_status(annotation.source_span_ids, reference_map)
        confidence = annotation.confidence
        if claim_type == "CAUSAL" and len(annotation.source_span_ids) < 2 and status == "SUPPORTED":
            status = "PARTIALLY_SUPPORTED"
            limitations += ("A single source passage does not independently establish causation.",)
            confidence = min(confidence, 6_500)
        claims.append(
            Claim(
                statement=statement,
                claim_type=claim_type,
                semantic_terms=_semantic_terms(statement, concepts),
                evidence_requirements=EVIDENCE_REQUIREMENTS[claim_type],
                supporting_evidence=annotation.source_span_ids,
                confidence_bp=confidence,
                status=status,
                scope=(task.discipline, task.audience),
                limitations=limitations,
            )
        )
    supported_claims = [claim for claim in claims if claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}]
    thesis_status = "SUPPORTED" if supported_claims and all(claim.status == "SUPPORTED" for claim in supported_claims) else "PARTIALLY_SUPPORTED" if supported_claims else "EVIDENCE_INSUFFICIENT"
    thesis = Claim(
        statement=task.question,
        claim_type="NORMATIVE" if re.search(r"\b(should|recommend|beneficial|adopt)\b", task.question, re.I) else "INTERPRETIVE",
        semantic_terms=_semantic_terms(task.question, concepts),
        evidence_requirements=("supported subordinate claims", "valid reasoning path"),
        supporting_evidence=tuple(
            evidence_id
            for claim in supported_claims
            for evidence_id in claim.supporting_evidence
        ),
        confidence_bp=min((claim.confidence_bp for claim in supported_claims), default=0),
        status=thesis_status,
        scope=(task.discipline, task.audience),
        limitations=("The thesis is bounded to the registered evidence and selected reasoning path.",),
    )
    return (thesis, *claims)


def qualify_evidence(
    claims: Sequence[Claim],
    references: Sequence[ReferenceSpan],
    sources: Sequence[SourceDocument],
    reference_source_ids: Mapping[str, str] | None = None,
) -> tuple[EvidenceLink, ...]:
    reference_map = {reference.reference_span_id: reference for reference in references}
    source_map = {source.source_document_id: source for source in sources}
    source_by_reference: dict[str, SourceDocument] = {}
    explicit_source_ids = dict(reference_source_ids or {})
    for reference in references:
        explicit_source = source_map.get(explicit_source_ids.get(reference.reference_span_id, ""))
        if explicit_source is not None:
            source_by_reference[reference.reference_span_id] = explicit_source
            continue
        for source in sources:
            if reference.anchor_id.startswith("anchor:") and source.source_document_id in reference.anchor_id:
                source_by_reference[reference.reference_span_id] = source
                break
        if reference.reference_span_id not in source_by_reference and len(sources) == 1:
            source_by_reference[reference.reference_span_id] = sources[0]
    links = []
    for claim in claims:
        for reference_id in claim.supporting_evidence:
            reference = reference_map.get(reference_id)
            if reference is None:
                continue
            source = source_by_reference.get(reference_id)
            verified = reference.verification_status == "VERIFIED"
            relation = claim.status if verified else "UNSUPPORTED"
            status = relation if relation in {"SUPPORTED", "PARTIALLY_SUPPORTED"} else "UNSUPPORTED"
            provenance = {
                "reference_span_id": reference.reference_span_id,
                "anchor_id": reference.anchor_id,
                "verification_status": reference.verification_status,
                "locator": reference.locator_display,
            }
            if source is not None:
                provenance.update(
                    {
                        "source_content_sha256": source.content_sha256,
                        "source_path": source.workspace_relative_path,
                    }
                )
            links.append(
                EvidenceLink(
                    claim_id=claim.claim_id,
                    evidence_artifact_id=reference.reference_span_id,
                    source_document_id=source.source_document_id if source is not None else "",
                    source_provenance=provenance,
                    support_relation=relation,
                    scope_compatible=verified,
                    strength_bp=reference.extraction_confidence if verified else 0,
                    status=status,
                    limitations=() if verified else ("Evidence locator is not verified.",),
                )
            )
    return tuple(sorted(links, key=lambda item: item.evidence_link_id))


def _role_claims(
    claims: Sequence[Claim],
    annotations: Sequence[ReasoningAnnotation],
) -> dict[str, list[Claim]]:
    by_statement = {" ".join(claim.statement.casefold().split()): claim for claim in claims}
    roles: dict[str, list[Claim]] = {}
    for annotation in annotations:
        statement = " ".join((annotation.source_claim or annotation.target_claim).casefold().split())
        claim = by_statement.get(statement)
        if claim is not None:
            roles.setdefault(annotation.component_role, []).append(claim)
    return roles


def _semantic_drift_issues(
    concepts: Sequence[ConceptDefinition],
    claims: Sequence[Claim],
) -> list[GraphIssue]:
    issues = []
    for concept in concepts:
        label = re.escape(concept.preferred_label)
        defining = re.compile(rf"\b{label}\b\s+(?:means|is defined as|refers to)\s+(.+)", re.I)
        expected_terms = set(tokens(concept.definition))
        for claim in claims:
            match = defining.search(claim.statement)
            if not match:
                continue
            observed_terms = set(tokens(match.group(1)))
            union = expected_terms | observed_terms
            similarity = len(expected_terms & observed_terms) / len(union) if union else 1.0
            if similarity < 0.25:
                issues.append(
                    GraphIssue(
                        code="SEMANTIC_DRIFT",
                        severity="ERROR",
                        subject_ids=(concept.concept_id, claim.claim_id),
                        message=f"{concept.preferred_label!r} is redefined inconsistently with the resolved meaning.",
                    )
                )
    return issues


def _has_positive_cycle(claim_ids: set[str], edges: Sequence[ReasoningEdge]) -> bool:
    graph = {claim_id: set() for claim_id in claim_ids}
    for edge in edges:
        if edge.relation in POSITIVE_RELATIONS and edge.source_id in claim_ids and edge.target_id in claim_ids:
            graph[edge.source_id].add(edge.target_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(target_id) for target_id in graph[node_id]):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in graph)


def _reaches(
    source_id: str,
    target_id: str,
    edges: Sequence[ReasoningEdge],
) -> bool:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if edge.relation in POSITIVE_RELATIONS | {"QUALIFIES", "CONTRADICTS", "FALSIFIES"}:
            adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
    pending = [source_id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, ()))
    return False


def _contradictory_claim_pairs(claims: Sequence[Claim]) -> tuple[tuple[Claim, Claim], ...]:
    contradictions = []
    for index, first in enumerate(claims):
        first_tokens = set(tokens(first.statement))
        first_negated = bool(first_tokens & NEGATION_TERMS)
        for second in claims[index + 1 :]:
            second_tokens = set(tokens(second.statement))
            second_negated = bool(second_tokens & NEGATION_TERMS)
            shared = (first_tokens - NEGATION_TERMS) & (second_tokens - NEGATION_TERMS)
            minimum = max(1, min(len(first_tokens), len(second_tokens)) - 1)
            if first_negated != second_negated and len(shared) >= max(2, minimum // 2):
                contradictions.append((first, second))
    return tuple(contradictions)


def _graph_issues(
    task: WritingTask,
    claims: Sequence[Claim],
    evidence_links: Sequence[EvidenceLink],
    edges: Sequence[ReasoningEdge],
    counterclaims: Sequence[CounterClaim],
    concepts: Sequence[ConceptDefinition],
    thesis_claim_id: str,
) -> tuple[GraphIssue, ...]:
    issues: list[GraphIssue] = []
    claim_ids = {claim.claim_id for claim in claims}
    linked_evidence_ids = {
        edge.source_id
        for edge in edges
        if edge.source_id.startswith("evidence-link:")
    }
    for link in evidence_links:
        if link.evidence_link_id not in linked_evidence_ids:
            issues.append(
                GraphIssue(
                    code="ORPHAN_EVIDENCE",
                    severity="ERROR",
                    subject_ids=(link.evidence_link_id,),
                    message="Verified evidence is not connected to a claim.",
                )
            )
    if _has_positive_cycle(claim_ids, edges):
        issues.append(
            GraphIssue(
                code="CIRCULAR_SUPPORT",
                severity="ERROR",
                message="The positive support graph contains a cycle.",
            )
        )
    for claim in claims:
        if claim.claim_id == thesis_claim_id:
            continue
        if not _reaches(claim.claim_id, thesis_claim_id, edges):
            issues.append(
                GraphIssue(
                    code="UNSUPPORTED_TERMINAL_CLAIM",
                    severity="ERROR",
                    subject_ids=(claim.claim_id,),
                    message="A material claim does not connect to the thesis.",
                )
            )
        if claim.status in {"UNSUPPORTED", "EVIDENCE_INSUFFICIENT", "CONTRADICTED", "EVIDENCE_CONFLICT"}:
            issues.append(
                GraphIssue(
                    code="UNSUPPORTED_TERMINAL_CLAIM",
                    severity="ERROR",
                    subject_ids=(claim.claim_id,),
                    message="A material claim lacks sufficient qualified evidence.",
                )
            )
        if claim.claim_type == "CAUSAL" and claim.status != "SUPPORTED":
            issues.append(
                GraphIssue(
                    code="CLAIM_STRONGER_THAN_EVIDENCE",
                    severity="WARNING",
                    subject_ids=(claim.claim_id,),
                    message="A causal claim is stronger than its current evidence qualification.",
                )
            )
        if claim.claim_type == "COMPARATIVE" and len(claim.supporting_evidence) < 2:
            issues.append(
                GraphIssue(
                    code="CLAIM_STRONGER_THAN_EVIDENCE",
                    severity="WARNING",
                    subject_ids=(claim.claim_id,),
                    message="A comparative claim lacks evidence for both comparison sides.",
                )
            )
    for first, second in _contradictory_claim_pairs(claims):
        issues.append(
            GraphIssue(
                code="CONTRADICTORY_PREMISES",
                severity="ERROR",
                subject_ids=(first.claim_id, second.claim_id),
                message="Two premises appear to assert incompatible polarities.",
            )
        )
    if task.required_counterargument and not counterclaims:
        issues.append(
            GraphIssue(
                code="MISSING_COUNTERARGUMENT",
                severity="ERROR",
                subject_ids=(thesis_claim_id,),
                message="The selected writing profile requires a material counterargument.",
            )
        )
    for counterclaim in counterclaims:
        if not counterclaim.response_claim_ids:
            issues.append(
                GraphIssue(
                    code="MISSING_COUNTERARGUMENT_RESPONSE",
                    severity="ERROR",
                    subject_ids=(counterclaim.counterclaim_id,),
                    message="A counterclaim has no explicit response or qualification.",
                )
            )
    issues.extend(_semantic_drift_issues(concepts, claims))
    unique = {
        (issue.code, issue.severity, issue.subject_ids, issue.message): issue
        for issue in issues
    }
    return tuple(sorted(unique.values(), key=lambda item: (item.code, item.subject_ids, item.message)))


def build_argument_graph(
    task: WritingTask,
    concepts: Sequence[ConceptDefinition],
    claims: Sequence[Claim],
    evidence_links: Sequence[EvidenceLink],
    annotations: Sequence[ReasoningAnnotation],
) -> ArgumentGraph:
    if not claims:
        raise ValueError("argument graph requires at least one claim")
    thesis = claims[0]
    roles = _role_claims(claims, annotations)
    rebuttal_ids = tuple(claim.claim_id for claim in roles.get("rebuttal", ()))
    counterclaims = tuple(
        CounterClaim(
            claim=claim,
            target_claim_ids=(thesis.claim_id,),
            counterevidence_ids=claim.supporting_evidence,
            response_claim_ids=rebuttal_ids,
            status="ANSWERED" if rebuttal_ids else "UNANSWERED",
        )
        for claim in roles.get("counterclaim", ())
    )
    qualifications = []
    for claim in claims:
        triggers = list(claim.limitations)
        if claim.status != "SUPPORTED":
            triggers.append(f"evidence status is {claim.status}")
        if claim.claim_type in {"CAUSAL", "NORMATIVE", "HYPOTHESIS"} or triggers:
            qualifications.append(
                Qualification(
                    target_claim_id=claim.claim_id,
                    statement=(
                        f"This claim is limited to {', '.join(claim.scope)} and remains conditional on "
                        f"the registered evidence status ({claim.status})."
                    ),
                    triggers=tuple(triggers) or ("claim type requires calibrated language",),
                    evidence_ids=claim.supporting_evidence,
                    adequacy_bp=10_000 if claim.limitations or claim.status == "SUPPORTED" else 7_500,
                )
            )
    edges = []
    claim_by_id = {claim.claim_id: claim for claim in claims}
    for link in evidence_links:
        relation = "CONTRADICTS" if link.status in {"CONTRADICTED", "EVIDENCE_CONFLICT"} else "SUPPORTS"
        edges.append(
            ReasoningEdge(
                source_id=link.evidence_link_id,
                target_id=link.claim_id,
                relation=relation,
                rationale="The verified source artifact is scope-checked before supporting the claim.",
                evidence_ids=(link.evidence_artifact_id,),
                inference_mode="inductive",
                confidence_bp=link.strength_bp,
            )
        )
    counterclaim_claim_ids = {item.claim.claim_id for item in counterclaims if item.claim is not None}
    rebuttal_claim_ids = set(rebuttal_ids)
    for claim in claims[1:]:
        if claim.claim_id in counterclaim_claim_ids:
            relation = "CONTRADICTS"
        elif claim.claim_id in rebuttal_claim_ids:
            relation = "QUALIFIES"
        elif claim.claim_type == "CAUSAL":
            relation = "EXPLAINS"
        elif claim.claim_type == "COMPARATIVE":
            relation = "COMPARES_WITH"
        else:
            relation = "SUPPORTS"
        edges.append(
            ReasoningEdge(
                source_id=claim.claim_id,
                target_id=thesis.claim_id,
                relation=relation,
                rationale="This proposition contributes explicitly to the document thesis.",
                evidence_ids=claim.supporting_evidence,
                inference_mode="defeasible",
                confidence_bp=claim.confidence_bp,
            )
        )
    for qualification in qualifications:
        edges.append(
            ReasoningEdge(
                source_id=qualification.qualification_id,
                target_id=qualification.target_claim_id,
                relation="QUALIFIES",
                rationale="The qualification prevents the prose from exceeding evidence scope.",
                evidence_ids=qualification.evidence_ids,
                inference_mode="constraint",
                confidence_bp=qualification.adequacy_bp,
            )
        )
    for counterclaim in counterclaims:
        for response_claim_id in counterclaim.response_claim_ids:
            if response_claim_id in claim_by_id:
                edges.append(
                    ReasoningEdge(
                        source_id=response_claim_id,
                        target_id=counterclaim.claim.claim_id,
                        relation="FALSIFIES",
                        rationale="The response challenges the objection before the thesis is retained.",
                        evidence_ids=claim_by_id[response_claim_id].supporting_evidence,
                        inference_mode="defeasible",
                        confidence_bp=claim_by_id[response_claim_id].confidence_bp,
                    )
                )
    issues = _graph_issues(
        task,
        claims,
        evidence_links,
        edges,
        counterclaims,
        concepts,
        thesis.claim_id,
    )
    return ArgumentGraph(
        thesis_claim_id=thesis.claim_id,
        claims=tuple(claims),
        evidence_links=tuple(evidence_links),
        reasoning_edges=tuple(edges),
        counterclaims=counterclaims,
        qualifications=tuple(qualifications),
        concepts=tuple(concepts),
        issues=issues,
    )


def retrieve_known_reasoning_patterns(
    workspace_root: Path,
    profile: str,
) -> tuple[_KnownPattern, ...]:
    patterns: dict[str, set[str]] = {
        name: set() for name in _profile(profile)["patterns"]
    }
    object_root = workspace_root / ".ourd-agent" / "egcf" / "objects" / "sha256"
    if object_root.exists():
        from ..egcf.errors import EGCFError
        from ..egcf.store import ObjectStore

        try:
            envelopes = tuple(ObjectStore(object_root).iter_envelopes())
        except EGCFError as exc:
            raise ValueError("the SAA/EGCF reasoning store failed identity validation") from exc
        for envelope in envelopes:
            if envelope.get("object_type") != "algorithm-definition":
                continue
            payload = envelope.get("payload") or {}
            if str(payload.get("status", "")).upper() != "QUALIFIED":
                continue
            applicability = payload.get("applicability") or {}
            name = str(payload.get("name", ""))
            algorithm_id = f"{name}@{payload.get('version', 1)}" if name else ""
            declared_pattern = str(applicability.get("formal_writing_pattern", "")).strip()
            if declared_pattern:
                patterns.setdefault(declared_pattern, set()).add(algorithm_id)
                continue
            lowered = name.casefold().replace("_", "-")
            for pattern_name in tuple(patterns):
                key = pattern_name.split()[0]
                if key in lowered:
                    patterns[pattern_name].add(algorithm_id)
    return tuple(
        _KnownPattern(name=name, source_algorithm_ids=tuple(sorted(algorithm_ids)))
        for name, algorithm_ids in sorted(patterns.items())
    )


def _path_order(pattern_name: str, graph: ArgumentGraph) -> tuple[Claim, ...]:
    thesis = next(claim for claim in graph.claims if claim.claim_id == graph.thesis_claim_id)
    others = [claim for claim in graph.claims if claim.claim_id != graph.thesis_claim_id]
    priorities = {
        "causal argument": {"CAUSAL": 0, "FACTUAL": 1, "HYPOTHESIS": 2},
        "comparison argument": {"COMPARATIVE": 0, "FACTUAL": 1, "NORMATIVE": 2},
        "falsification-first argument": {"HYPOTHESIS": 0, "INTERPRETIVE": 1, "FACTUAL": 2},
        "problem-solution argument": {"NORMATIVE": 0, "CAUSAL": 1, "COMPARATIVE": 2},
        "evidence-synthesis argument": {"FACTUAL": 0, "INTERPRETIVE": 1, "COMPARATIVE": 2},
    }.get(pattern_name, {})
    ordered = sorted(
        others,
        key=lambda claim: (
            priorities.get(claim.claim_type, 9),
            -claim.confidence_bp,
            claim.claim_id,
        ),
    )
    return (thesis, *ordered)


def search_reasoning_paths(
    task: WritingTask,
    graph: ArgumentGraph,
    workspace_root: Path,
) -> tuple[ReasoningPathCandidate, ...]:
    known_patterns = retrieve_known_reasoning_patterns(workspace_root, task.profile)
    supported_claims = [claim for claim in graph.claims if claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}]
    evidence_strength = sum(claim.confidence_bp for claim in supported_claims) // max(1, len(supported_claims))
    semantic_clarity = max(0, 10_000 - 2_000 * sum(issue.code == "SEMANTIC_DRIFT" for issue in graph.issues))
    connectivity = sum(
        _reaches(claim.claim_id, graph.thesis_claim_id, graph.reasoning_edges)
        for claim in graph.claims
    ) * 10_000 // max(1, len(graph.claims))
    counter_resistance = 10_000
    if task.required_counterargument:
        counter_resistance = (
            sum(bool(item.response_claim_ids) for item in graph.counterclaims)
            * 10_000
            // max(1, len(graph.counterclaims))
        ) if graph.counterclaims else 0
    task_terms = set(tokens(task.question))
    candidates = []
    for pattern in known_patterns:
        ordered_claims = _path_order(pattern.name, graph)
        claim_terms = set(tokens(" ".join(claim.statement for claim in ordered_claims)))
        relevance = len(task_terms & claim_terms) * 10_000 // max(1, len(task_terms))
        novelty = 5_000 if pattern.source_algorithm_ids else 6_000
        coherence = min(connectivity, 10_000 - 1_000 * sum(issue.severity == "ERROR" for issue in graph.issues))
        components = (
            ("EvidenceStrength", max(0, evidence_strength)),
            ("Novelty", novelty),
            ("Coherence", max(0, coherence)),
            ("Relevance", relevance),
            ("CounterargumentResistance", counter_resistance),
            ("SemanticClarity", semantic_clarity),
        )
        total = sum(score for _, score in components) // len(components)
        selected_claim_ids = tuple(claim.claim_id for claim in ordered_claims)
        selected_edge_ids = tuple(
            edge.edge_id
            for edge in graph.reasoning_edges
            if edge.source_id in selected_claim_ids or edge.target_id in selected_claim_ids
        )
        candidates.append(
            ReasoningPathCandidate(
                pattern_name=pattern.name,
                claim_ids=selected_claim_ids,
                edge_ids=selected_edge_ids,
                score_components=components,
                total_score_bp=total,
                source_algorithm_ids=pattern.source_algorithm_ids,
                adaptation_notes=(
                    "Retrieved from the SAA/EGCF algorithm store before local adaptation."
                    if pattern.source_algorithm_ids
                    else "Used the built-in qualified topology template because no matching SAA algorithm was registered.",
                ),
            )
        )
    return tuple(sorted(candidates, key=lambda item: (-item.total_score_bp, item.path_id)))


def compile_paragraph_plans(
    task: WritingTask,
    graph: ArgumentGraph,
    selected_path: ReasoningPathCandidate,
) -> tuple[ParagraphPlan, ...]:
    profile = _profile(task.profile)
    claim_map = {claim.claim_id: claim for claim in graph.claims}
    counterclaim_ids = {
        counterclaim.claim.claim_id
        for counterclaim in graph.counterclaims
        if counterclaim.claim is not None
    }
    qualification_map: dict[str, list[str]] = {}
    for qualification in graph.qualifications:
        qualification_map.setdefault(qualification.target_claim_id, []).append(qualification.qualification_id)
    plans = []
    sections = profile["sections"]
    ordered_claim_ids = selected_path.claim_ids
    for order, claim_id in enumerate(ordered_claim_ids):
        claim = claim_map[claim_id]
        if claim_id == graph.thesis_claim_id:
            section_title = sections[0]
            purpose = "Define the question, scope, and qualified thesis before presenting evidence."
        elif claim_id in counterclaim_ids:
            section_title = next((item for item in sections if "counter" in item.casefold() or "disagreement" in item.casefold()), sections[-2])
            purpose = "Present a material objection and its evidential basis fairly."
        elif order == len(ordered_claim_ids) - 1:
            section_title = sections[-1]
            purpose = "State the bounded conclusion without exceeding the qualified graph."
        else:
            section_title = sections[min(order, max(1, len(sections) - 2))]
            purpose = f"Develop the {claim.claim_type.casefold()} proposition with evidence and explicit reasoning."
        evidence_ids = claim.supporting_evidence
        reasoning_edge_ids = tuple(
            edge.edge_id
            for edge in graph.reasoning_edges
            if edge.source_id == claim_id
            or edge.target_id == claim_id
            or edge.evidence_ids and set(edge.evidence_ids) & set(evidence_ids)
        )
        plans.append(
            ParagraphPlan(
                section_title=section_title,
                order=order,
                purpose=purpose,
                claim_ids=(claim_id,),
                evidence_ids=evidence_ids,
                reasoning_edge_ids=reasoning_edge_ids,
                qualification_ids=tuple(qualification_map.get(claim_id, ())),
                link=(
                    "This proposition contributes to the selected reasoning path while retaining its evidence boundary."
                ),
            )
        )
    return tuple(plans)


def build_document_plan(
    task: WritingTask,
    graph: ArgumentGraph,
    workspace_root: Path,
) -> DocumentPlan:
    paths = search_reasoning_paths(task, graph, workspace_root)
    if not paths:
        raise ValueError("no reasoning path could be generated")
    selected = paths[0]
    paragraph_plans = compile_paragraph_plans(task, graph, selected)
    gaps = tuple(
        issue.message
        for issue in graph.issues
        if issue.code in {
            "UNSUPPORTED_TERMINAL_CLAIM",
            "MISSING_COUNTERARGUMENT",
            "MISSING_COUNTERARGUMENT_RESPONSE",
            "CLAIM_STRONGER_THAN_EVIDENCE",
        }
    )
    return DocumentPlan(
        task=task,
        graph=graph,
        candidate_paths=paths,
        selected_path_id=selected.path_id,
        paragraph_plans=paragraph_plans,
        no_new_material_claims=True,
        unresolved_evidence_gaps=gaps,
    )


def falsification_pass(plan: DocumentPlan) -> tuple[FalsificationChallenge, ...]:
    graph = plan.graph
    claim_map = {claim.claim_id: claim for claim in graph.claims}
    qualification_by_claim = {
        qualification.target_claim_id: qualification
        for qualification in graph.qualifications
    }
    challenges = []
    for claim in graph.claims:
        if claim.claim_id == graph.thesis_claim_id:
            continue
        alternatives = tuple(claim.limitations) or (
            "An unobserved scope, measurement, or selection factor may explain the same evidence.",
        )
        qualification = qualification_by_claim.get(claim.claim_id)
        response = (
            "Retain the claim only within its verified evidence scope and explicit qualification."
            if claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
            else "Do not render this proposition as a supported material claim."
        )
        challenges.append(
            FalsificationChallenge(
                claim_id=claim.claim_id,
                challenge=f"What evidence or alternative explanation would defeat: {claim.statement}",
                counterevidence_ids=claim.counterevidence,
                alternative_explanations=alternatives,
                response=response,
                qualification_id=qualification.qualification_id if qualification else "",
                status="QUALIFIED" if qualification and claim.status != "UNSUPPORTED" else "OPEN",
            )
        )
    return tuple(challenges)


def revise_plan_after_falsification(
    plan: DocumentPlan,
    challenges: Sequence[FalsificationChallenge],
    workspace_root: Path,
) -> tuple[DocumentPlan, tuple[FalsificationChallenge, ...]]:
    graph = plan.graph
    claim_map = {claim.claim_id: claim for claim in graph.claims}
    qualifications = list(graph.qualifications)
    edges = list(graph.reasoning_edges)
    revised_challenges = []
    for challenge in challenges:
        claim = claim_map[challenge.claim_id]
        qualification_id = challenge.qualification_id
        if not qualification_id:
            qualification = Qualification(
                target_claim_id=claim.claim_id,
                statement=(
                    "This proposition remains defeasible: retain it only while the registered evidence "
                    "survives the stated counterexample and alternative-explanation checks."
                ),
                triggers=(challenge.challenge, *challenge.alternative_explanations),
                evidence_ids=claim.supporting_evidence,
                adequacy_bp=8_000 if claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"} else 5_000,
            )
            qualifications.append(qualification)
            edges.append(
                ReasoningEdge(
                    source_id=qualification.qualification_id,
                    target_id=claim.claim_id,
                    relation="QUALIFIES",
                    rationale="The falsification pass revised the graph before prose rendering.",
                    evidence_ids=claim.supporting_evidence,
                    inference_mode="defeasible",
                    confidence_bp=qualification.adequacy_bp,
                )
            )
            qualification_id = qualification.qualification_id
        revised_challenges.append(
            FalsificationChallenge(
                claim_id=challenge.claim_id,
                challenge=challenge.challenge,
                counterevidence_ids=challenge.counterevidence_ids,
                alternative_explanations=challenge.alternative_explanations,
                response=challenge.response,
                qualification_id=qualification_id,
                status=(
                    "QUALIFIED"
                    if claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
                    else challenge.status
                ),
            )
        )
    issues = _graph_issues(
        plan.task,
        graph.claims,
        graph.evidence_links,
        edges,
        graph.counterclaims,
        graph.concepts,
        graph.thesis_claim_id,
    )
    revised_graph = ArgumentGraph(
        thesis_claim_id=graph.thesis_claim_id,
        claims=graph.claims,
        evidence_links=graph.evidence_links,
        reasoning_edges=tuple(edges),
        counterclaims=graph.counterclaims,
        qualifications=tuple(qualifications),
        concepts=graph.concepts,
        issues=issues,
    )
    paths = search_reasoning_paths(plan.task, revised_graph, workspace_root)
    selected = paths[0]
    gaps = tuple(
        issue.message
        for issue in revised_graph.issues
        if issue.code in {
            "UNSUPPORTED_TERMINAL_CLAIM",
            "MISSING_COUNTERARGUMENT",
            "MISSING_COUNTERARGUMENT_RESPONSE",
            "CLAIM_STRONGER_THAN_EVIDENCE",
        }
    )
    revised_plan = DocumentPlan(
        task=plan.task,
        graph=revised_graph,
        candidate_paths=paths,
        selected_path_id=selected.path_id,
        paragraph_plans=compile_paragraph_plans(plan.task, revised_graph, selected),
        no_new_material_claims=plan.no_new_material_claims,
        unresolved_evidence_gaps=gaps,
    )
    return revised_plan, tuple(revised_challenges)


def render_document(
    request: FormalWritingRequest,
    plan: DocumentPlan,
    sources: Sequence[SourceDocument],
    references: Sequence[ReferenceSpan],
    bibliographic_records: Mapping[str, BibliographicRecord] | None = None,
    reference_source_ids: Mapping[str, str] | None = None,
) -> tuple[DraftArtifact, tuple[DraftSection, ...]]:
    graph = plan.graph
    claim_map = {claim.claim_id: claim for claim in graph.claims}
    edge_map = {edge.edge_id: edge for edge in graph.reasoning_edges}
    qualification_map = {
        qualification.qualification_id: qualification
        for qualification in graph.qualifications
    }
    reference_map = {reference.reference_span_id: reference for reference in references}
    records = dict(bibliographic_records or {})
    for source in sources:
        records.setdefault(source.source_document_id, bibliographic_record_from_source(source))
    reference_sources = dict(reference_source_ids or {})
    sections = []
    for paragraph_plan in plan.paragraph_plans:
        claim = claim_map[paragraph_plan.claim_ids[0]]
        sentences = [claim.statement.rstrip(". ") + "."]
        claim_end = len(sentences[0])
        for reference_id in paragraph_plan.evidence_ids:
            reference = reference_map.get(reference_id)
            if reference is None or reference.verification_status != "VERIFIED":
                continue
            source_id = reference_sources.get(reference_id, "")
            record = records.get(source_id)
            citation = (
                render_citation((record,), reference.locator_display, style=request.citation_style)
                if record is not None
                else f"({reference.locator_display})"
            )
            sentences.append(f"Verified evidence states: “{reference.verbatim_text}” {citation}")
        rationales = tuple(
            edge_map[edge_id].rationale
            for edge_id in paragraph_plan.reasoning_edge_ids
            if edge_id in edge_map and edge_map[edge_id].rationale
        )
        if rationales:
            sentences.append(rationales[0].rstrip(". ") + ".")
        for qualification_id in paragraph_plan.qualification_ids:
            qualification = qualification_map.get(qualification_id)
            if qualification is not None:
                sentences.append(qualification.statement.rstrip(". ") + ".")
        sentences.append(paragraph_plan.link.rstrip(". ") + ".")
        text = " ".join(sentences)
        sections.append(
            DraftSection(
                paragraph_plan_id=paragraph_plan.paragraph_plan_id,
                heading=paragraph_plan.section_title,
                text=text,
                claim_ids=paragraph_plan.claim_ids,
                evidence_ids=paragraph_plan.evidence_ids,
                reasoning_edge_ids=paragraph_plan.reasoning_edge_ids,
                qualification_ids=paragraph_plan.qualification_ids,
                sentence_claim_map=((0, claim_end, claim.claim_id),),
            )
        )
    lines = [f"# {request.genre.title()}: {request.objective}", ""]
    citation_uses = []
    for section in sections:
        lines.extend((f"## {section.heading}", ""))
        paragraph_start = sum(len(line) + 1 for line in lines)
        lines.extend((section.text, ""))
        for reference_id in section.evidence_ids:
            reference = reference_map.get(reference_id)
            if reference is None or reference.verification_status != "VERIFIED":
                continue
            source_id = reference_sources.get(reference_id, "")
            record = records.get(source_id)
            citation_uses.append(
                CitationUse(
                    draft_span=(paragraph_start, paragraph_start + len(section.text)),
                    claim_id=section.claim_ids[0],
                    bibliographic_record_ids=(record.bibliographic_record_id,) if record else (),
                    reference_span_ids=(reference.reference_span_id,),
                    locator=reference.locator_display,
                    use_kind="quotation",
                    verification_status=reference.verification_status,
                )
            )
    if records:
        lines.extend(("## References", "", render_bibliography(tuple(records.values()), style=request.citation_style), ""))
    draft = DraftArtifact(
        request_id=request.request_id,
        plan_id=plan.document_plan_id,
        text="\n".join(lines).strip() + "\n",
        citation_uses=tuple(citation_uses),
        source_document_ids=tuple(source.source_document_id for source in sources),
    )
    return draft, tuple(sections)


def detect_novelty(
    plan: DocumentPlan,
    references: Sequence[ReferenceSpan],
) -> tuple[NoveltyAssessment, ...]:
    source_texts = {
        reference.reference_span_id: " ".join(reference.verbatim_text.casefold().split())
        for reference in references
    }
    selected = next(path for path in plan.candidate_paths if path.path_id == plan.selected_path_id)
    assessments = []
    for claim in plan.graph.claims:
        normalized = " ".join(claim.statement.casefold().split())
        exact_matches = tuple(
            reference_id
            for reference_id, source_text in source_texts.items()
            if normalized == source_text or normalized in source_text or source_text in normalized
        )
        if exact_matches:
            status = "KNOWN"
            rationale = "The claim is directly represented in a registered source passage."
            requires_review = False
        elif claim.supporting_evidence:
            status = "KNOWN_COMBINATION"
            rationale = "The claim combines registered evidence but is not an exact source proposition."
            requires_review = False
        elif claim.claim_id == plan.graph.thesis_claim_id and len(selected.claim_ids) > 1:
            status = "NEW_APPLICATION"
            rationale = "The selected known reasoning pattern is applied to this task-specific thesis."
            requires_review = False
        else:
            status = "POTENTIAL_NOVELTY_REQUIRES_REVIEW"
            rationale = "No registered source or known reasoning artifact establishes the claim; literature review is required."
            requires_review = True
        assessments.append(
            NoveltyAssessment(
                claim_id=claim.claim_id,
                status=status,
                matching_claim_ids=exact_matches,
                matching_algorithm_ids=selected.source_algorithm_ids,
                rationale=rationale,
                requires_review=requires_review,
            )
        )
    return tuple(assessments)


def audit_writing(
    plan: DocumentPlan,
    draft_sections: Sequence[DraftSection],
) -> WritingAudit:
    graph = plan.graph
    material_claims = [claim for claim in graph.claims if claim.material]
    fully_supported = [claim for claim in material_claims if claim.status == "SUPPORTED"]
    partially_supported = [claim for claim in material_claims if claim.status == "PARTIALLY_SUPPORTED"]
    unsupported = [
        claim
        for claim in material_claims
        if claim.status in {"UNSUPPORTED", "CONTRADICTED", "EVIDENCE_CONFLICT", "EVIDENCE_INSUFFICIENT"}
    ]
    total = max(1, len(material_claims))
    claims_with_evidence = {
        link.claim_id
        for link in graph.evidence_links
        if link.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
    }
    incoming_supported_claims = {
        edge.target_id
        for edge in graph.reasoning_edges
        if edge.relation in POSITIVE_RELATIONS
        and any(claim.claim_id == edge.source_id and claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"} for claim in material_claims)
    }
    claims_with_evidence |= incoming_supported_claims
    if any(claim.claim_id in claims_with_evidence for claim in material_claims if claim.claim_id != graph.thesis_claim_id):
        claims_with_evidence.add(graph.thesis_claim_id)
    claim_support_rate = (len(fully_supported) + len(partially_supported)) * 10_000 // total
    evidence_coverage = len({claim.claim_id for claim in material_claims} & claims_with_evidence) * 10_000 // total
    semantic_consistency = max(0, 10_000 - 2_500 * sum(issue.code == "SEMANTIC_DRIFT" for issue in graph.issues))
    connected = sum(
        claim.claim_id == graph.thesis_claim_id
        or _reaches(claim.claim_id, graph.thesis_claim_id, graph.reasoning_edges)
        for claim in material_claims
    )
    connectivity = connected * 10_000 // total
    unsupported_rate = len(unsupported) * 10_000 // total
    if plan.task.required_counterargument:
        counter_coverage = (
            sum(bool(counterclaim.response_claim_ids) for counterclaim in graph.counterclaims)
            * 10_000
            // max(1, len(graph.counterclaims))
        ) if graph.counterclaims else 0
    else:
        counter_coverage = 10_000
    claims_requiring_qualification = [
        claim
        for claim in material_claims
        if claim.claim_type in {"CAUSAL", "NORMATIVE", "HYPOTHESIS"}
        or claim.status != "SUPPORTED"
    ]
    qualified_claim_ids = {qualification.target_claim_id for qualification in graph.qualifications}
    qualification_adequacy = (
        sum(claim.claim_id in qualified_claim_ids for claim in claims_requiring_qualification)
        * 10_000
        // max(1, len(claims_requiring_qualification))
    ) if claims_requiring_qualification else 10_000
    traceable_links = [
        link
        for link in graph.evidence_links
        if link.source_provenance and link.evidence_artifact_id and link.source_document_id
    ]
    citation_traceability = len(traceable_links) * 10_000 // max(1, len(graph.evidence_links)) if graph.evidence_links else 0
    mapped_claim_ids = {
        claim_id
        for section in draft_sections
        for _, _, claim_id in section.sentence_claim_map
    }
    unmapped_material_claims = {
        claim.claim_id
        for claim in material_claims
        if claim.claim_id not in mapped_claim_ids
    }
    graph_issue_codes = {issue.code for issue in graph.issues}
    if unmapped_material_claims:
        graph_issue_codes.add("UNMAPPED_MATERIAL_CLAIM")
    hard_failures = graph_issue_codes & {
        "UNSUPPORTED_TERMINAL_CLAIM",
        "CIRCULAR_SUPPORT",
        "CONTRADICTORY_PREMISES",
        "ORPHAN_EVIDENCE",
        "MISSING_COUNTERARGUMENT",
        "MISSING_COUNTERARGUMENT_RESPONSE",
        "SEMANTIC_DRIFT",
        "UNMAPPED_MATERIAL_CLAIM",
    }
    if unsupported or evidence_coverage == 0:
        status = "EVIDENCE_INSUFFICIENT"
    elif hard_failures or min(
        claim_support_rate,
        evidence_coverage,
        semantic_consistency,
        connectivity,
        counter_coverage,
        qualification_adequacy,
        citation_traceability,
    ) < 8_000:
        status = "REVISION_REQUIRED"
    else:
        status = "QUALIFIED_FORMAL_DOCUMENT"
    return WritingAudit(
        document_plan_id=plan.document_plan_id,
        material_claims=len(material_claims),
        fully_supported_claims=len(fully_supported),
        partially_supported_claims=len(partially_supported),
        unsupported_claims=len(unsupported),
        claim_support_rate_bp=claim_support_rate,
        evidence_coverage_bp=evidence_coverage,
        semantic_consistency_bp=semantic_consistency,
        argument_connectivity_bp=connectivity,
        unsupported_claim_rate_bp=unsupported_rate,
        counterargument_coverage_bp=counter_coverage,
        qualification_adequacy_bp=qualification_adequacy,
        citation_traceability_bp=citation_traceability,
        unsupported_claim_ids=tuple(claim.claim_id for claim in unsupported) + tuple(unmapped_material_claims),
        graph_issue_codes=tuple(graph_issue_codes),
        performed_checks=(
            "claim support classification",
            "evidence coverage",
            "semantic drift gate",
            "argument connectivity",
            "unsupported material claim gate",
            "counterargument coverage",
            "qualification adequacy",
            "citation traceability",
            "NoNewMaterialClaims sentence mapping",
        ),
        limitations=(
            "The audit is deterministic and does not certify truth or institutional acceptance.",
            "Potential novelty remains review-only until a literature search is supplied.",
        ),
        status=status,
    )


def reasoning_algorithm_proposal(
    plan: DocumentPlan,
    audit: WritingAudit,
) -> ReasoningAlgorithmProposal | None:
    if audit.status != "QUALIFIED_FORMAL_DOCUMENT":
        return None
    selected = next(path for path in plan.candidate_paths if path.path_id == plan.selected_path_id)
    safe_name = re.sub(r"[^a-z0-9]+", "-", selected.pattern_name.casefold()).strip("-")
    return ReasoningAlgorithmProposal(
        name=f"formal-writing.{safe_name}",
        pattern_name=selected.pattern_name,
        source_document_plan_id=plan.document_plan_id,
        source_audit_id=audit.audit_id,
        applicability={
            "formal_writing_pattern": selected.pattern_name,
            "profile": plan.task.profile,
            "discipline": plan.task.discipline,
        },
        invariants=(
            "NoNewMaterialClaims",
            "all material claims are evidence-qualified",
            "semantic definitions remain stable",
            "human review is required before SAA admission",
        ),
    )


def admit_reasoning_algorithm_proposal(
    workspace_root: Path,
    qualified_document: QualifiedDocument,
    *,
    approved_by: str,
    human_approval_id: str,
) -> str:
    proposal = qualified_document.reasoning_algorithm_proposal
    if qualified_document.audit.status != "QUALIFIED_FORMAL_DOCUMENT" or proposal is None:
        raise ValueError("only a qualified formal document can propose an SAA reasoning algorithm")
    if not approved_by.strip() or not human_approval_id.strip():
        raise ValueError("SAA admission requires exact human reviewer and approval identifiers")
    from ..egcf.models import AlgorithmDefinition
    from ..egcf.store import EGCFStore

    algorithm = AlgorithmDefinition(
        name=proposal.name,
        version=1,
        implementation_kind="semantic",
        implementation_ref=f"formal-writing:{proposal.proposal_id}",
        implementation_digest=proposal.signature,
        command_ids=["hrt.interpret@1"],
        input_schema={
            "type": "object",
            "required": ["writing_task", "argument_graph"],
        },
        output_schema={
            "type": "object",
            "required": ["document_plan", "writing_audit"],
        },
        applicability=dict(proposal.applicability),
        capability_requirements=["analysis.reason", "evidence.analyse"],
        capability_level="C1",
        risk_floor="L0",
        rollback_class="none",
        invariants=list(proposal.invariants),
        evidence_requirements=[
            qualified_document.audit.audit_id,
            qualified_document.plan.document_plan_id,
            human_approval_id,
        ],
        qualification_policy={
            "tests_required": True,
            "benchmarks_required": True,
            "human_review_required": True,
        },
        owner=approved_by,
        provenance={
            "proposal_id": proposal.proposal_id,
            "qualified_document_id": qualified_document.qualified_document_id,
            "human_approval_id": human_approval_id,
        },
        status="PROPOSED",
        known_failures=[
            "Not reusable until SAA qualification evidence promotes this exact digest."
        ],
    )
    with EGCFStore(workspace_root) as store:
        return store.register(algorithm)


def build_qualified_document(
    request: FormalWritingRequest,
    workspace_root: Path,
    sources: Sequence[SourceDocument],
    references: Sequence[ReferenceSpan],
    concept_annotations: Sequence[ConceptAnnotation],
    reasoning_annotations: Sequence[ReasoningAnnotation],
    bibliographic_records: Mapping[str, BibliographicRecord] | None = None,
    reference_source_ids: Mapping[str, str] | None = None,
    *,
    progress_sink: ProgressSink | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> tuple[QualifiedDocument, DraftArtifact]:
    require_not_cancelled(cancellation_check)
    task = build_writing_task(request, sources)
    concepts = resolve_meaning(task, concept_annotations)
    report_progress(progress_sink, "meaning_resolved")
    require_not_cancelled(cancellation_check)
    claims = generate_claims(task, concepts, reasoning_annotations, references)
    report_progress(progress_sink, "claims_generated")
    require_not_cancelled(cancellation_check)
    evidence_links = qualify_evidence(
        claims,
        references,
        sources,
        reference_source_ids,
    )
    report_progress(progress_sink, "evidence_qualified")
    require_not_cancelled(cancellation_check)
    graph = build_argument_graph(task, concepts, claims, evidence_links, reasoning_annotations)
    report_progress(progress_sink, "argument_graph_built")
    require_not_cancelled(cancellation_check)
    plan = build_document_plan(task, graph, workspace_root)
    report_progress(progress_sink, "reasoning_path_selected")
    require_not_cancelled(cancellation_check)
    challenges = falsification_pass(plan)
    plan, challenges = revise_plan_after_falsification(plan, challenges, workspace_root)
    report_progress(progress_sink, "falsification_completed")
    require_not_cancelled(cancellation_check)
    draft, sections = render_document(
        request,
        plan,
        sources,
        references,
        bibliographic_records,
        reference_source_ids,
    )
    report_progress(progress_sink, "draft_rendered")
    require_not_cancelled(cancellation_check)
    audit = audit_writing(plan, sections)
    report_progress(progress_sink, "audit_completed")
    require_not_cancelled(cancellation_check)
    novelty = detect_novelty(plan, references)
    proposal = reasoning_algorithm_proposal(plan, audit)
    return (
        QualifiedDocument(
            plan=plan,
            draft_sections=sections,
            falsification_challenges=challenges,
            audit=audit,
            novelty_assessments=novelty,
            reasoning_algorithm_proposal=proposal,
            status=audit.status,
        ),
        draft,
    )


__all__ = [
    "EVIDENCE_REQUIREMENTS",
    "PROFILE_SPECS",
    "admit_reasoning_algorithm_proposal",
    "audit_writing",
    "build_argument_graph",
    "build_document_plan",
    "build_qualified_document",
    "build_writing_task",
    "classify_claim",
    "compile_paragraph_plans",
    "detect_novelty",
    "falsification_pass",
    "generate_claims",
    "qualify_evidence",
    "reasoning_algorithm_proposal",
    "render_document",
    "revise_plan_after_falsification",
    "resolve_meaning",
    "retrieve_known_reasoning_patterns",
    "search_reasoning_paths",
]
