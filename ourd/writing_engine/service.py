from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..persistence import atomic_write_text
from ..workspace import Workspace
from .concepts import identify_concepts
from .critique import validate_references, writing_certificate
from .metadata import bibliographic_record_from_source
from .models import (
    DraftArtifact,
    ExtractedSource,
    FormalWritingRequest,
    FormalWritingResult,
    ReferenceSpan,
)
from .passage_index import PassageIndex
from .pipeline import build_qualified_document
from .pipeline_models import QualifiedDocument
from .planning import build_writing_plan
from .progress import CancellationCheck, ProgressSink, report_progress, require_not_cancelled
from .reasoning import identify_reasoning
from .signatures import content_sha256
from .source_registry import SourceRegistry


class FormalWritingService:
    def __init__(self, workspace: Workspace | Path):
        self.workspace = workspace if isinstance(workspace, Workspace) else Workspace(workspace)
        self.state_dir = self.workspace.root / self.workspace.internal_name / "writing"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.registry = SourceRegistry(self.workspace, self.workspace.root / self.workspace.internal_name)

    def register_sources(
        self,
        paths: Sequence[str],
        *,
        allow_ocr: bool = False,
        ocr_language: str = "eng",
    ) -> tuple[ExtractedSource, ...]:
        return tuple(
            self.registry.register(path, allow_ocr=allow_ocr, ocr_language=ocr_language)
            for path in paths
        )

    def _resolve_sources(
        self,
        request: FormalWritingRequest,
        *,
        allow_ocr: bool,
        ocr_language: str,
        allow_empty: bool = False,
    ) -> tuple[ExtractedSource, ...]:
        sources = list(self.register_sources(request.source_paths, allow_ocr=allow_ocr, ocr_language=ocr_language))
        for source_id in request.source_document_ids:
            if source_id not in {item.document.source_document_id for item in sources}:
                sources.append(self.registry.load(source_id))
        if not sources and not allow_empty:
            raise ValueError("formal writing requires at least one source path or source document ID")
        return tuple(sources)

    def inspect(self, request: FormalWritingRequest, *, allow_ocr: bool = False, ocr_language: str = "eng") -> FormalWritingResult:
        sources = self._resolve_sources(
            request,
            allow_ocr=allow_ocr,
            ocr_language=ocr_language,
            allow_empty=request.operation in {"BUILD_ARGUMENT_MAP", "OUTLINE"},
        )
        return FormalWritingResult(request=request, sources=tuple(item.document for item in sources))

    def locate(
        self,
        request: FormalWritingRequest,
        *,
        allow_ocr: bool = False,
        ocr_language: str = "eng",
        limit: int = 8,
    ) -> tuple[tuple[ExtractedSource, ...], tuple[Any, ...]]:
        sources = self._resolve_sources(request, allow_ocr=allow_ocr, ocr_language=ocr_language)
        matches = PassageIndex(sources).search(request.objective, limit=limit)
        return sources, matches

    def execute(
        self,
        request: FormalWritingRequest,
        *,
        allow_ocr: bool = False,
        ocr_language: str = "eng",
        persist: bool = True,
        prior_draft_text: str = "",
        progress_sink: ProgressSink | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> FormalWritingResult:
        report_progress(progress_sink, "request_compiled")
        require_not_cancelled(cancellation_check)
        sources = self._resolve_sources(
            request,
            allow_ocr=allow_ocr,
            ocr_language=ocr_language,
            allow_empty=request.operation in {"BUILD_ARGUMENT_MAP", "OUTLINE"},
        )
        documents = tuple(item.document for item in sources)
        report_progress(progress_sink, "sources_ingested")
        require_not_cancelled(cancellation_check)
        if request.operation == "INSPECT_SOURCES":
            result = FormalWritingResult(request=request, sources=documents)
            return self._complete(
                result,
                persist=persist,
                progress_sink=progress_sink,
                cancellation_check=cancellation_check,
            )
        matches = PassageIndex(sources).search(request.objective, limit=12) if sources else ()
        references = tuple(match.reference for match in matches)
        report_progress(progress_sink, "references_located")
        report_progress(progress_sink, "references_qualified")
        require_not_cancelled(cancellation_check)
        reference_source_ids = {
            match.reference.reference_span_id: match.source_document_id
            for match in matches
        }
        if request.operation == "LOCATE_REFERENCE":
            result = FormalWritingResult(request=request, sources=documents, references=references)
            return self._complete(
                result,
                persist=persist,
                progress_sink=progress_sink,
                cancellation_check=cancellation_check,
            )
        concepts = identify_concepts(references, domain=request.discipline)
        reasoning = identify_reasoning(references)
        report_progress(progress_sink, "source_annotations_built")
        require_not_cancelled(cancellation_check)
        if request.operation == "EXPLAIN_REFERENCE":
            result = FormalWritingResult(
                request=request,
                sources=documents,
                references=references,
                concepts=concepts,
                reasoning=reasoning,
            )
            return self._complete(
                result,
                persist=persist,
                progress_sink=progress_sink,
                cancellation_check=cancellation_check,
            )
        plan = build_writing_plan(request, references, concepts, reasoning)
        report_progress(progress_sink, "legacy_plan_built")
        require_not_cancelled(cancellation_check)
        bibliography = {
            source.source_document_id: bibliographic_record_from_source(source)
            for source in documents
        }
        bibliography_records = tuple(
            sorted(bibliography.values(), key=lambda item: item.bibliographic_record_id)
        )
        qualified_document, governed_draft = build_qualified_document(
            request,
            self.workspace.root,
            documents,
            references,
            concepts,
            reasoning,
            bibliography,
            reference_source_ids,
            progress_sink=progress_sink,
            cancellation_check=cancellation_check,
        )
        if request.operation in {
            "BUILD_SOURCE_MAP",
            "BUILD_ARGUMENT_MAP",
            "OUTLINE",
            "EXPORT_REFERENCES",
        }:
            result = FormalWritingResult(
                request=request,
                sources=documents,
                references=references,
                concepts=concepts,
                reasoning=reasoning,
                bibliographic_records=bibliography_records,
                plan=plan,
                qualified_document=qualified_document,
            )
            return self._complete(
                result,
                persist=persist,
                progress_sink=progress_sink,
                cancellation_check=cancellation_check,
            )
        if request.operation == "REVISE":
            if prior_draft_text:
                resolved_prior_draft = prior_draft_text
            else:
                if len(request.draft_paths) != 1:
                    raise ValueError("REVISE requires exactly one draft path or trusted persisted draft text")
                draft_path = self.workspace.resolve(self.workspace.canonical(request.draft_paths[0]))
                resolved_prior_draft = draft_path.read_text(encoding="utf-8")
            draft = DraftArtifact(
                request_id=governed_draft.request_id,
                plan_id=governed_draft.plan_id,
                text=governed_draft.text,
                citation_uses=governed_draft.citation_uses,
                source_document_ids=governed_draft.source_document_ids,
                revision_of_sha256=content_sha256(resolved_prior_draft),
                revision_notes=(
                    "The argument graph was revised before prose was regenerated.",
                    "The prior draft is bound by SHA-256 for review and rollback.",
                ),
            )
            qualified_document = QualifiedDocument(
                plan=qualified_document.plan,
                draft_sections=qualified_document.draft_sections,
                falsification_challenges=qualified_document.falsification_challenges,
                audit=qualified_document.audit,
                novelty_assessments=qualified_document.novelty_assessments,
                reasoning_algorithm_proposal=qualified_document.reasoning_algorithm_proposal,
                revision_of_sha256=draft.revision_of_sha256,
                status=qualified_document.status,
            )
        else:
            draft = governed_draft
        current_hashes = {
            source.workspace_relative_path: self.workspace.file_hash_or_none(source.workspace_relative_path) or ""
            for source in documents
        }
        report = validate_references(
            draft,
            references,
            documents,
            concepts=concepts,
            reasoning=reasoning,
            current_hashes=current_hashes,
        )
        certificate = writing_certificate(request, plan, draft, report)
        report_progress(progress_sink, "reference_integrity_validated")
        require_not_cancelled(cancellation_check)
        result = FormalWritingResult(
            request=request,
            sources=documents,
            references=references,
            concepts=concepts,
            reasoning=reasoning,
            bibliographic_records=bibliography_records,
            plan=plan,
            draft=draft,
            integrity_report=report,
            certificate=certificate,
            qualified_document=qualified_document,
            output_paths=request.output_paths,
            limitations=tuple(
                dict.fromkeys(
                    (*plan.unresolved_evidence_gaps, *qualified_document.plan.unresolved_evidence_gaps)
                )
            ),
        )
        return self._complete(
            result,
            persist=persist,
            progress_sink=progress_sink,
            cancellation_check=cancellation_check,
        )

    def _complete(
        self,
        result: FormalWritingResult,
        *,
        persist: bool,
        progress_sink: ProgressSink | None,
        cancellation_check: CancellationCheck | None,
    ) -> FormalWritingResult:
        require_not_cancelled(cancellation_check)
        completed = self._persist(result) if persist else result
        report_progress(progress_sink, "artifacts_persisted" if persist else "result_completed")
        return completed

    def _persist(self, result: FormalWritingResult) -> FormalWritingResult:
        target = self.state_dir / "results" / f"{result.request.request_id.replace(':', '-')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, json.dumps(asdict(result), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        if result.draft is not None:
            draft_target = self.state_dir / "drafts" / f"{result.draft.draft_id.replace(':', '-')}.md"
            draft_target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(draft_target, result.draft.text)
        proposal = (
            result.qualified_document.reasoning_algorithm_proposal
            if result.qualified_document is not None
            else None
        )
        if proposal is not None:
            proposal_target = self.state_dir / "algorithm-proposals" / f"{proposal.proposal_id.replace(':', '-')}.json"
            proposal_target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                proposal_target,
                json.dumps(asdict(proposal), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )
        return result


__all__ = ["FormalWritingService"]
