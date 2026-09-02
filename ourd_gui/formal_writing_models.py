from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from ourd.writing_engine import FormalWritingRequest, compile_formal_writing_request
from ourd.writing_engine.compiler import WRITING_PROFILES


NETWORK_POLICIES = ("offline", "metadata-only", "explicit-retrieval")
MAX_FORMAL_WRITING_INPUTS = 500
MAX_FORMAL_WRITING_INPUT_BYTES = 32 * 1024 * 1024
MAX_FORMAL_WRITING_TOTAL_INPUT_BYTES = 256 * 1024 * 1024
FORMAL_WRITING_ACTIONS = (
    "inspect",
    "locate",
    "research",
    "argue",
    "plan",
    "draft",
    "audit",
    "revise",
    "explain",
    "export",
)


def _strings(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


@dataclass(frozen=True)
class FormalWritingFormState:
    objective: str = ""
    profile: str = "general"
    genre: str = "essay"
    audience: str = "general"
    discipline: str = "general"
    word_target: int = 0
    source_paths: tuple[str, ...] = ()
    rubric_paths: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    citation_style: str = "author-date"
    locale: str = "en"
    network_policy: str = "offline"
    plan_id: str = ""
    draft_id: str = ""
    output_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.profile not in WRITING_PROFILES:
            raise ValueError(f"unsupported writing profile: {self.profile}")
        if self.network_policy not in NETWORK_POLICIES:
            raise ValueError(f"unsupported network policy: {self.network_policy}")
        if int(self.word_target) < 0:
            raise ValueError("word target cannot be negative")
        for name in ("source_paths", "rubric_paths", "constraints", "output_paths"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        object.__setattr__(self, "objective", self.objective.strip())
        object.__setattr__(self, "genre", self.genre.strip() or "essay")
        object.__setattr__(self, "audience", self.audience.strip() or "general")
        object.__setattr__(self, "discipline", self.discipline.strip() or "general")
        object.__setattr__(self, "citation_style", self.citation_style.strip() or "author-date")
        object.__setattr__(self, "locale", self.locale.strip() or "en")
        object.__setattr__(self, "plan_id", self.plan_id.strip())
        object.__setattr__(self, "draft_id", self.draft_id.strip())

    @classmethod
    def from_request(
        cls,
        request: FormalWritingRequest,
        *,
        plan_id: str = "",
        draft_id: str = "",
    ) -> "FormalWritingFormState":
        return cls(
            objective=request.objective,
            profile=request.profile,
            genre=request.genre,
            audience=request.audience,
            discipline=request.discipline,
            word_target=request.word_target,
            source_paths=request.source_paths,
            rubric_paths=request.rubric_paths,
            constraints=request.constraints,
            citation_style=request.citation_style,
            locale=request.locale,
            network_policy=request.network_policy,
            plan_id=plan_id,
            draft_id=draft_id,
            output_paths=request.output_paths,
        )

    def with_paths_relative_to(self, workspace: Path) -> "FormalWritingFormState":
        root = workspace.resolve()

        def relative(value: str, *, require_input_file: bool = False) -> str:
            candidate = Path(value).expanduser()
            workspace_candidate = candidate if candidate.is_absolute() else root / candidate
            if require_input_file and workspace_candidate.is_symlink():
                raise ValueError(f"formal-writing input symlinks are not supported: {value}")
            try:
                resolved = workspace_candidate.resolve()
                normalized = resolved.relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError(f"formal-writing path is outside the workspace: {value}") from exc
            if require_input_file and (not resolved.exists() or not resolved.is_file()):
                raise ValueError(f"formal-writing input is unavailable: {value}")
            return normalized

        inputs = (*self.source_paths, *self.rubric_paths)
        if len(inputs) > MAX_FORMAL_WRITING_INPUTS:
            raise ValueError(
                f"formal-writing input count exceeds {MAX_FORMAL_WRITING_INPUTS}: {len(inputs)}"
            )
        normalized_sources = tuple(
            relative(path, require_input_file=True) for path in self.source_paths
        )
        normalized_rubrics = tuple(
            relative(path, require_input_file=True) for path in self.rubric_paths
        )
        total_bytes = 0
        for path in (*normalized_sources, *normalized_rubrics):
            size = (root / path).stat().st_size
            if size > MAX_FORMAL_WRITING_INPUT_BYTES:
                raise ValueError(
                    "formal-writing input exceeds the individual size limit: "
                    f"{path} ({size} bytes)"
                )
            total_bytes += size
        if total_bytes > MAX_FORMAL_WRITING_TOTAL_INPUT_BYTES:
            raise ValueError(
                "formal-writing inputs exceed the total size limit: "
                f"{total_bytes} bytes"
            )

        return replace(
            self,
            source_paths=normalized_sources,
            rubric_paths=normalized_rubrics,
            output_paths=tuple(relative(path) for path in self.output_paths),
        )

    def compile_request(
        self,
        operation: str,
        *,
        source_document_ids: tuple[str, ...] = (),
        authority_binding: str = "",
    ) -> FormalWritingRequest:
        normalized = operation.casefold().strip()
        if normalized not in FORMAL_WRITING_ACTIONS and normalized != "write":
            raise ValueError(f"unsupported formal-writing GUI action: {operation}")
        if not self.objective:
            raise ValueError("formal writing requires a task or research question")
        return compile_formal_writing_request(
            operation=normalized,
            objective=self.objective,
            profile=self.profile,
            genre=self.genre,
            audience=self.audience,
            discipline=self.discipline,
            word_target=self.word_target,
            source_document_ids=source_document_ids,
            source_paths=self.source_paths,
            rubric_paths=self.rubric_paths,
            output_paths=self.output_paths,
            citation_style=self.citation_style,
            locale=self.locale,
            network_policy=self.network_policy,
            constraints=self.constraints,
            requested_outputs=(normalized,),
            authority_binding=authority_binding,
        )


@dataclass(frozen=True)
class FormalWritingExecutionOptions:
    allow_ocr: bool = False
    ocr_language: str = "eng"
    require_page_accuracy: bool = False
    require_qualified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "ocr_language", self.ocr_language.strip() or "eng")


@dataclass(frozen=True)
class GovernedWritePreview:
    request: FormalWritingRequest
    draft_id: str
    draft_sha256: str
    audit_id: str
    audit_status: str
    qualified_document_id: str
    source_bindings: tuple[tuple[str, str, str], ...]
    output_paths: tuple[str, ...]
    authority_path: str
    authority_sha256: str
    limitations: tuple[str, ...]

    @property
    def request_signature(self) -> str:
        return self.request.request_signature


class FormalWritingJobStatus(str, Enum):
    IDLE = "IDLE"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FormalWritingGuiEventType(str, Enum):
    JOB_QUEUED = "JOB_QUEUED"
    JOB_STARTED = "JOB_STARTED"
    JOB_PROGRESS = "JOB_PROGRESS"
    JOB_CANCEL_REQUESTED = "JOB_CANCEL_REQUESTED"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"
    JOB_CANCELLED = "JOB_CANCELLED"


@dataclass(frozen=True)
class FormalWritingGuiEvent:
    sequence: int
    event_type: FormalWritingGuiEventType
    job_id: str
    operation: str
    request_id: str = ""
    phase: str = ""
    message: str = ""
    result_request_id: str = ""
    result_path: str = ""
    audit_status: str = ""
    error_type: str = ""
    details: tuple[tuple[str, Any], ...] = ()
    authoritative: bool = False

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        event_type: FormalWritingGuiEventType,
        job_id: str,
        operation: str,
        request_id: str = "",
        phase: str = "",
        message: str = "",
        result_request_id: str = "",
        result_path: str = "",
        audit_status: str = "",
        error_type: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> "FormalWritingGuiEvent":
        return cls(
            sequence=sequence,
            event_type=event_type,
            job_id=job_id,
            operation=operation,
            request_id=request_id,
            phase=phase,
            message=message,
            result_request_id=result_request_id,
            result_path=result_path,
            audit_status=audit_status,
            error_type=error_type,
            details=tuple(sorted((str(key), value) for key, value in (details or {}).items())),
            authoritative=False,
        )


__all__ = [
    "FORMAL_WRITING_ACTIONS",
    "MAX_FORMAL_WRITING_INPUTS",
    "MAX_FORMAL_WRITING_INPUT_BYTES",
    "MAX_FORMAL_WRITING_TOTAL_INPUT_BYTES",
    "NETWORK_POLICIES",
    "FormalWritingExecutionOptions",
    "FormalWritingFormState",
    "FormalWritingGuiEvent",
    "FormalWritingGuiEventType",
    "FormalWritingJobStatus",
    "GovernedWritePreview",
]
