from __future__ import annotations

import json
import types
from collections.abc import Mapping as MappingABC
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Union, get_args, get_origin, get_type_hints

from ourd.writing_engine.models import ExtractedSource, FormalWritingRequest, FormalWritingResult, ReferenceSpan
from ourd.writing_engine.pipeline_models import WritingAudit
from ourd.workspace import Workspace

from .formal_writing_models import FormalWritingFormState
from .widgets.graph_view import GraphEdge, GraphNode


MAX_PROJECTION_FILE_BYTES = 32 * 1024 * 1024
MAX_RESULTS = 500
MAX_SOURCE_FILES = 500
MAX_SOURCE_PAGES = 5_000
MAX_DIAGNOSTIC_MESSAGE_CHARACTERS = 2_000


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProjectionDiagnostic:
    path: Path
    category: str
    message: str
    observed_at: str = field(default_factory=_observed_at)

    def __post_init__(self) -> None:
        if len(self.message) > MAX_DIAGNOSTIC_MESSAGE_CHARACTERS:
            object.__setattr__(
                self,
                "message",
                self.message[:MAX_DIAGNOSTIC_MESSAGE_CHARACTERS] + "[truncated]",
            )


@dataclass(frozen=True)
class SentenceTraceProjection:
    start: int
    end: int
    claim_id: str
    section_heading: str
    evidence_ids: tuple[str, ...]
    reasoning_edge_ids: tuple[str, ...]
    qualification_ids: tuple[str, ...]


@dataclass(frozen=True)
class WritingAuditProjection:
    audit_id: str = ""
    status: str = "EVIDENCE_INSUFFICIENT"
    claim_support_rate_bp: int = 0
    evidence_coverage_bp: int = 0
    semantic_consistency_bp: int = 0
    argument_connectivity_bp: int = 0
    unsupported_claim_rate_bp: int = 0
    counterargument_coverage_bp: int = 0
    qualification_adequacy_bp: int = 0
    citation_traceability_bp: int = 0
    unsupported_claim_ids: tuple[str, ...] = ()
    graph_issue_codes: tuple[str, ...] = ()
    performed_checks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @classmethod
    def from_audit(cls, audit: WritingAudit | None) -> "WritingAuditProjection":
        if audit is None:
            return cls()
        return cls(
            audit_id=audit.audit_id,
            status=audit.status,
            claim_support_rate_bp=audit.claim_support_rate_bp,
            evidence_coverage_bp=audit.evidence_coverage_bp,
            semantic_consistency_bp=audit.semantic_consistency_bp,
            argument_connectivity_bp=audit.argument_connectivity_bp,
            unsupported_claim_rate_bp=audit.unsupported_claim_rate_bp,
            counterargument_coverage_bp=audit.counterargument_coverage_bp,
            qualification_adequacy_bp=audit.qualification_adequacy_bp,
            citation_traceability_bp=audit.citation_traceability_bp,
            unsupported_claim_ids=audit.unsupported_claim_ids,
            graph_issue_codes=audit.graph_issue_codes,
            performed_checks=audit.performed_checks,
            limitations=audit.limitations,
        )


@dataclass(frozen=True)
class FormalWritingResultProjection:
    path: Path
    result: FormalWritingResult
    request_id: str
    request_signature: str
    operation: str
    objective: str
    profile: str
    source_count: int
    reference_count: int
    source_document_ids: tuple[str, ...]
    source_paths: tuple[str, ...]
    plan_id: str
    document_plan_id: str
    selected_path_id: str
    draft_id: str
    revision_of_sha256: str
    draft_text: str
    audit_id: str
    audit_status: str
    qualified_document_id: str
    integrity_report: Mapping[str, Any]
    certificate: Mapping[str, Any]
    argument_graph: Mapping[str, Any]
    writing_audit: Mapping[str, Any]
    audit: WritingAuditProjection
    novelty_assessments: tuple[Mapping[str, Any], ...]
    sentence_traces: tuple[SentenceTraceProjection, ...]
    graph_nodes: tuple[GraphNode, ...]
    graph_edges: tuple[GraphEdge, ...]
    limitations: tuple[str, ...]
    output_paths: tuple[str, ...]
    reasoning_algorithm_proposal: Mapping[str, Any]
    reasoning_paths: tuple[Mapping[str, Any], ...]
    selected_reasoning_path: Mapping[str, Any]

    @property
    def identifiers(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.request_id,
                self.plan_id,
                self.document_plan_id,
                self.draft_id,
                self.audit_id,
                self.qualified_document_id,
            )
            if value
        )

    def form_state(self) -> FormalWritingFormState:
        return FormalWritingFormState.from_request(
            self.result.request,
            plan_id=self.document_plan_id or self.plan_id,
            draft_id=self.draft_id,
        )

    def reference(self, identifier: str) -> ReferenceSpan | None:
        return next(
            (reference for reference in self.result.references if reference.reference_span_id == identifier),
            None,
        )


@dataclass(frozen=True)
class SourcePageProjection:
    source_path: str
    source_document_id: str
    title: str
    content_sha256: str
    media_type: str
    byte_size: int
    page_count: int
    physical_page_index: int
    physical_page_number: int
    display_page_label: str
    text_layer_kind: str
    extraction_confidence: int
    text: str
    ocr_status: str
    ingestion_adapter: str
    freshness: str


@dataclass(frozen=True)
class FormalWritingProjectionSnapshot:
    results: tuple[FormalWritingResultProjection, ...]
    source_pages: tuple[SourcePageProjection, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...]


class FormalWritingProjectionStore:
    def __init__(self, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.root = self.repository_root / ".ourd-agent" / "writing"
        self.workspace = Workspace(self.repository_root)
        self._last_diagnostics: tuple[ProjectionDiagnostic, ...] = ()
        self._result_cache: dict[
            Path,
            tuple[int, int, FormalWritingResultProjection],
        ] = {}
        self._source_cache: dict[
            Path,
            tuple[int, int, tuple[SourcePageProjection, ...]],
        ] = {}

    def snapshot(self) -> FormalWritingProjectionSnapshot:
        diagnostics: list[ProjectionDiagnostic] = []
        results = self._load_results(diagnostics)
        pages = self._load_source_pages(diagnostics)
        self._last_diagnostics = tuple(diagnostics)
        return FormalWritingProjectionSnapshot(
            results=results,
            source_pages=pages,
            diagnostics=self._last_diagnostics,
        )

    def results(self) -> tuple[FormalWritingResultProjection, ...]:
        return self.snapshot().results

    def source_pages(self) -> tuple[SourcePageProjection, ...]:
        return self.snapshot().source_pages

    def diagnostics(self) -> tuple[ProjectionDiagnostic, ...]:
        self.snapshot()
        return self._last_diagnostics

    def find_result(self, identifier: str) -> FormalWritingResultProjection | None:
        normalized = identifier.strip()
        if not normalized:
            return None
        return next((result for result in self.results() if normalized in result.identifiers), None)

    def persisted_draft_text(self, draft_id: str) -> str:
        projection = self.find_result(draft_id)
        if projection is None or projection.draft_id != draft_id:
            raise ValueError(f"unknown persisted draft ID: {draft_id}")
        path = self.root / "drafts" / f"{draft_id.replace(':', '-')}.md"
        try:
            size = path.stat().st_size
            if size > MAX_PROJECTION_FILE_BYTES:
                raise ValueError(f"persisted draft exceeds projection limit: {size} bytes")
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"persisted draft artifact is unavailable: {path}") from exc

    def _load_results(
        self,
        diagnostics: list[ProjectionDiagnostic],
    ) -> tuple[FormalWritingResultProjection, ...]:
        projections: list[FormalWritingResultProjection] = []
        paths = sorted((self.root / "results").glob("*.json"), reverse=True)
        if len(paths) > MAX_RESULTS:
            diagnostics.append(
                ProjectionDiagnostic(
                    path=self.root / "results",
                    category="RESULT_LIMIT",
                    message=f"showing newest {MAX_RESULTS} of {len(paths)} result artifacts",
                )
            )
            paths = paths[:MAX_RESULTS]
        for path in paths:
            try:
                stat = path.stat()
                cached = self._result_cache.get(path)
                if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
                    projections.append(cached[2])
                    continue
                payload = self._read_json(path)
                result = _decode_dataclass(FormalWritingResult, payload)
                projection = _result_projection(path, result)
                self._result_cache[path] = (stat.st_mtime_ns, stat.st_size, projection)
                projections.append(projection)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                diagnostics.append(
                    ProjectionDiagnostic(
                        path=path,
                        category="INVALID_RESULT_ARTIFACT",
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
        return tuple(projections)

    def _load_source_pages(
        self,
        diagnostics: list[ProjectionDiagnostic],
    ) -> tuple[SourcePageProjection, ...]:
        pages: list[SourcePageProjection] = []
        paths = [
            path
            for path in sorted((self.root / "sources").glob("*.json"))
            if path.name != "index.json"
        ]
        if len(paths) > MAX_SOURCE_FILES:
            diagnostics.append(
                ProjectionDiagnostic(
                    path=self.root / "sources",
                    category="SOURCE_LIMIT",
                    message=f"showing first {MAX_SOURCE_FILES} of {len(paths)} source artifacts",
                )
            )
            paths = paths[:MAX_SOURCE_FILES]
        for path in paths:
            try:
                stat = path.stat()
                cached = self._source_cache.get(path)
                if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
                    remaining = MAX_SOURCE_PAGES - len(pages)
                    if remaining <= 0:
                        diagnostics.append(
                            ProjectionDiagnostic(
                                path=self.root / "sources",
                                category="SOURCE_PAGE_LIMIT",
                                message=(
                                    f"showing first {MAX_SOURCE_PAGES} projected source pages"
                                ),
                            )
                        )
                        return tuple(pages)
                    refreshed = tuple(
                        replace(
                            page,
                            freshness=self._freshness(
                                page.source_path,
                                page.content_sha256,
                            ),
                        )
                        for page in cached[2]
                    )
                    pages.extend(refreshed[:remaining])
                    if len(refreshed) > remaining:
                        diagnostics.append(
                            ProjectionDiagnostic(
                                path=self.root / "sources",
                                category="SOURCE_PAGE_LIMIT",
                                message=(
                                    f"showing first {MAX_SOURCE_PAGES} projected source pages"
                                ),
                            )
                        )
                        return tuple(pages)
                    continue
                payload = self._read_json(path)
                extracted = _decode_dataclass(ExtractedSource, payload)
                document = extracted.document
                freshness = self._freshness(
                    document.workspace_relative_path,
                    document.content_sha256,
                )
                if not extracted.pages:
                    projected = (
                        SourcePageProjection(
                            source_path=document.workspace_relative_path,
                            source_document_id=document.source_document_id,
                            title=document.title,
                            content_sha256=document.content_sha256,
                            media_type=document.media_type,
                            byte_size=document.byte_size,
                            page_count=document.page_count,
                            physical_page_index=-1,
                            physical_page_number=0,
                            display_page_label="reflowable",
                            text_layer_kind="reflowable",
                            extraction_confidence=10_000,
                            text=extracted.document_text,
                            ocr_status=document.ocr_status,
                            ingestion_adapter=document.ingestion_adapter,
                            freshness=freshness,
                        ),
                    )
                    self._source_cache[path] = (stat.st_mtime_ns, stat.st_size, projected)
                    pages.extend(projected)
                    continue
                projected_pages: list[SourcePageProjection] = []
                for page in extracted.pages:
                    if len(pages) >= MAX_SOURCE_PAGES:
                        diagnostics.append(
                            ProjectionDiagnostic(
                                path=self.root / "sources",
                                category="SOURCE_PAGE_LIMIT",
                                message=(
                                    f"showing first {MAX_SOURCE_PAGES} projected source pages"
                                ),
                            )
                        )
                        return tuple(pages)
                    projection = (
                        SourcePageProjection(
                            source_path=document.workspace_relative_path,
                            source_document_id=document.source_document_id,
                            title=document.title,
                            content_sha256=document.content_sha256,
                            media_type=document.media_type,
                            byte_size=document.byte_size,
                            page_count=document.page_count,
                            physical_page_index=page.physical_page_index,
                            physical_page_number=page.physical_page_number,
                            display_page_label=page.display_page_label,
                            text_layer_kind=page.text_layer_kind,
                            extraction_confidence=page.extraction_confidence,
                            text=page.text,
                            ocr_status=document.ocr_status,
                            ingestion_adapter=document.ingestion_adapter,
                            freshness=freshness,
                        )
                    )
                    pages.append(projection)
                    projected_pages.append(projection)
                self._source_cache[path] = (
                    stat.st_mtime_ns,
                    stat.st_size,
                    tuple(projected_pages),
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                diagnostics.append(
                    ProjectionDiagnostic(
                        path=path,
                        category="INVALID_SOURCE_ARTIFACT",
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
        return tuple(pages)

    def _freshness(self, path: str, expected_sha256: str) -> str:
        current = self.workspace.file_hash_or_none(path)
        if current is None:
            return "MISSING"
        return "CURRENT" if current == expected_sha256 else "DRIFTED"

    @staticmethod
    def _read_json(path: Path) -> Mapping[str, Any]:
        size = path.stat().st_size
        if size > MAX_PROJECTION_FILE_BYTES:
            raise ValueError(f"artifact exceeds projection limit: {size} bytes")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("artifact root must be a JSON object")
        return payload


def _decode_dataclass(target: type[Any], payload: Mapping[str, Any]) -> Any:
    if not is_dataclass(target):
        raise TypeError(f"projection target is not a dataclass: {target}")
    if not isinstance(payload, Mapping):
        raise TypeError(f"{target.__name__} payload must be a mapping")
    hints, target_fields, known = _dataclass_schema(target)
    unknown = sorted(set(payload) - known)
    if unknown:
        payload = {key: value for key, value in payload.items() if key in known}
    values = {
        field.name: _decode_value(hints.get(field.name, Any), payload[field.name])
        for field in target_fields
        if field.name in payload
    }
    return target(**values)


@lru_cache(maxsize=None)
def _dataclass_schema(
    target: type[Any],
) -> tuple[dict[str, Any], tuple[Any, ...], frozenset[str]]:
    target_fields = fields(target)
    return (
        get_type_hints(target),
        target_fields,
        frozenset(field.name for field in target_fields),
    )


def _decode_value(annotation: Any, value: Any) -> Any:
    if annotation is Any:
        return value
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in arguments:
            return None
        candidates = [argument for argument in arguments if argument is not type(None)]
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                return _decode_value(candidate, value)
            except (TypeError, ValueError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return value
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise TypeError("tuple field requires a JSON array")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_decode_value(arguments[0], item) for item in value)
        if arguments and len(arguments) != len(value):
            raise ValueError("fixed tuple field has the wrong length")
        return tuple(
            _decode_value(arguments[index], item) if arguments else item
            for index, item in enumerate(value)
        )
    if origin in (dict, Mapping, MappingABC):
        if not isinstance(value, Mapping):
            raise TypeError("mapping field requires a JSON object")
        return dict(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        return _decode_dataclass(annotation, value)
    if annotation is bool:
        if not isinstance(value, bool):
            raise TypeError("boolean field requires a JSON boolean")
        return value
    if annotation in (str, int, float):
        return annotation(value)
    return value


def _result_projection(path: Path, result: FormalWritingResult) -> FormalWritingResultProjection:
    request = result.request
    qualified = result.qualified_document
    graph = qualified.plan.graph if qualified is not None else None
    audit = qualified.audit if qualified is not None else None
    draft = result.draft
    traces: list[SentenceTraceProjection] = []
    draft_text = draft.text if draft is not None else ""
    cursor = 0
    if qualified is not None:
        for section in qualified.draft_sections:
            section_start = draft_text.find(section.text, cursor)
            if section_start < 0:
                section_start = draft_text.find(section.text)
            if section_start < 0:
                continue
            cursor = section_start + len(section.text)
            for start, end, claim_id in section.sentence_claim_map:
                traces.append(
                    SentenceTraceProjection(
                        start=section_start + int(start),
                        end=section_start + int(end),
                        claim_id=claim_id,
                        section_heading=section.heading,
                        evidence_ids=section.evidence_ids,
                        reasoning_edge_ids=section.reasoning_edge_ids,
                        qualification_ids=section.qualification_ids,
                    )
                )
    graph_mapping = asdict(graph) if graph is not None else {}
    nodes, edges = argument_graph_projection(graph_mapping)
    plan = result.plan
    document_plan = qualified.plan if qualified is not None else None
    proposal = qualified.reasoning_algorithm_proposal if qualified is not None else None
    reasoning_paths = (
        tuple(asdict(item) for item in document_plan.candidate_paths)
        if document_plan is not None
        else ()
    )
    selected_reasoning_path = next(
        (
            item
            for item in reasoning_paths
            if str(item.get("path_id", "")) == document_plan.selected_path_id
        ),
        {},
    ) if document_plan is not None else {}
    return FormalWritingResultProjection(
        path=path,
        result=result,
        request_id=request.request_id,
        request_signature=request.request_signature,
        operation=request.operation,
        objective=request.objective,
        profile=request.profile,
        source_count=len(result.sources),
        reference_count=len(result.references),
        source_document_ids=tuple(source.source_document_id for source in result.sources),
        source_paths=tuple(source.workspace_relative_path for source in result.sources),
        plan_id=plan.plan_id if plan is not None else "",
        document_plan_id=document_plan.document_plan_id if document_plan is not None else "",
        selected_path_id=document_plan.selected_path_id if document_plan is not None else "",
        draft_id=draft.draft_id if draft is not None else "",
        revision_of_sha256=draft.revision_of_sha256 if draft is not None else "",
        draft_text=draft_text,
        audit_id=audit.audit_id if audit is not None else "",
        audit_status=audit.status if audit is not None else "EVIDENCE_INSUFFICIENT",
        qualified_document_id=qualified.qualified_document_id if qualified is not None else "",
        integrity_report=asdict(result.integrity_report) if result.integrity_report is not None else {},
        certificate=asdict(result.certificate) if result.certificate is not None else {},
        argument_graph=graph_mapping,
        writing_audit=asdict(audit) if audit is not None else {},
        audit=WritingAuditProjection.from_audit(audit),
        novelty_assessments=tuple(asdict(item) for item in qualified.novelty_assessments) if qualified is not None else (),
        sentence_traces=tuple(traces),
        graph_nodes=nodes,
        graph_edges=edges,
        limitations=result.limitations,
        output_paths=result.output_paths,
        reasoning_algorithm_proposal=asdict(proposal) if proposal is not None else {},
        reasoning_paths=reasoning_paths,
        selected_reasoning_path=selected_reasoning_path,
    )


def argument_graph_projection(
    graph: Mapping[str, Any],
) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
    claims = tuple(graph.get("claims", ()) or ())
    evidence_links = tuple(graph.get("evidence_links", ()) or ())
    reasoning_edges = tuple(graph.get("reasoning_edges", ()) or ())
    counterclaims = tuple(graph.get("counterclaims", ()) or ())
    qualifications = tuple(graph.get("qualifications", ()) or ())
    thesis_id = str(graph.get("thesis_claim_id", ""))
    claim_ids = {str(claim.get("claim_id", "")) for claim in claims}
    layers = {claim_id: 1 for claim_id in claim_ids if claim_id}
    for _ in range(max(1, len(claims))):
        changed = False
        for edge in reasoning_edges:
            source = str(edge.get("source_id", ""))
            target = str(edge.get("target_id", ""))
            if source in layers and target in layers:
                candidate = min(6, layers[source] + 1)
                if candidate > layers[target]:
                    layers[target] = candidate
                    changed = True
        if not changed:
            break
    if thesis_id in layers:
        layers[thesis_id] = max(layers.values(), default=1) + 1
    nodes: list[GraphNode] = []
    for order, link in enumerate(evidence_links):
        node_id = str(link.get("evidence_link_id", ""))
        if not node_id:
            continue
        artifact_id = str(link.get("evidence_artifact_id", ""))
        nodes.append(
            GraphNode(
                node_id=node_id,
                label=_short_identifier(artifact_id, "Evidence"),
                layer=0,
                order=order,
                status=_status_name(str(link.get("status", ""))),
                subtitle=f"{link.get('support_relation', '')} · {int(link.get('strength_bp', 0)) / 100:.0f}%",
                object_id=artifact_id,
                data=dict(link),
            )
        )
    for order, claim in enumerate(claims):
        node_id = str(claim.get("claim_id", ""))
        if not node_id:
            continue
        claim_type = str(claim.get("claim_type", "CLAIM"))
        status = str(claim.get("status", ""))
        label = str(claim.get("statement", "")) or _short_identifier(node_id, "Claim")
        if node_id == thesis_id:
            claim_type = f"THESIS · {claim_type}"
        nodes.append(
            GraphNode(
                node_id=node_id,
                label=label,
                layer=layers.get(node_id, 1),
                order=order,
                status=_status_name(status),
                subtitle=f"{claim_type} · {status}",
                object_id=node_id,
                data=dict(claim),
            )
        )
    base_layer = max(layers.values(), default=1)
    for order, item in enumerate(counterclaims):
        claim = item.get("claim") or {}
        node_id = str(claim.get("claim_id", ""))
        if not node_id or node_id in {node.node_id for node in nodes}:
            continue
        nodes.append(
            GraphNode(
                node_id=node_id,
                label=str(claim.get("statement", "Counterclaim")),
                layer=max(1, base_layer - 1),
                order=len(claims) + order,
                status="blocked" if item.get("status") == "UNANSWERED" else "gated",
                subtitle=f"COUNTERCLAIM · {item.get('status', '')}",
                object_id=str(item.get("counterclaim_id", "")),
                data=dict(item),
            )
        )
    for order, item in enumerate(qualifications):
        node_id = str(item.get("qualification_id", ""))
        if not node_id:
            continue
        nodes.append(
            GraphNode(
                node_id=node_id,
                label=str(item.get("statement", "Qualification")),
                layer=base_layer,
                order=len(claims) + len(counterclaims) + order,
                status="gated",
                subtitle=f"QUALIFICATION · {int(item.get('adequacy_bp', 0)) / 100:.0f}%",
                object_id=node_id,
                data=dict(item),
            )
        )
    edges: list[GraphEdge] = []
    existing: set[tuple[str, str, str]] = set()

    def append_edge(source: str, target: str, label: str) -> None:
        candidate = (source, target, label)
        if source and target and candidate not in existing:
            edges.append(GraphEdge(source=source, target=target, label=label))
            existing.add(candidate)

    for edge in reasoning_edges:
        source = str(edge.get("source_id", ""))
        target = str(edge.get("target_id", ""))
        append_edge(source, target, str(edge.get("relation", "")))
    for link in evidence_links:
        source = str(link.get("evidence_link_id", ""))
        target = str(link.get("claim_id", ""))
        append_edge(source, target, str(link.get("support_relation", "")))
    for item in counterclaims:
        claim = item.get("claim") or {}
        source = str(claim.get("claim_id", ""))
        for target in item.get("target_claim_ids", ()) or ():
            append_edge(source, str(target), "CONTRADICTS")
        for response in item.get("response_claim_ids", ()) or ():
            append_edge(str(response), source, "RESPONDS")
    for item in qualifications:
        source = str(item.get("qualification_id", ""))
        target = str(item.get("target_claim_id", ""))
        append_edge(source, target, "QUALIFIES")
    return tuple(nodes), tuple(edges)


def _short_identifier(identifier: str, fallback: str) -> str:
    if not identifier:
        return fallback
    prefix, separator, digest = identifier.partition(":")
    if separator and digest:
        return f"{prefix}:…{digest[-10:]}"
    return identifier[:40]


def _status_name(status: str) -> str:
    normalized = status.upper()
    if normalized == "SUPPORTED":
        return "qualified"
    if normalized in {"PARTIALLY_SUPPORTED", "REVIEW_REQUIRED"}:
        return "gated"
    if normalized in {"CONTRADICTED", "UNSUPPORTED", "EVIDENCE_INSUFFICIENT", "EVIDENCE_CONFLICT"}:
        return "blocked"
    return "neutral"


__all__ = [
    "FormalWritingProjectionSnapshot",
    "FormalWritingProjectionStore",
    "FormalWritingResultProjection",
    "ProjectionDiagnostic",
    "SentenceTraceProjection",
    "SourcePageProjection",
    "WritingAuditProjection",
    "argument_graph_projection",
]
