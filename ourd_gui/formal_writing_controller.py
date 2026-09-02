from __future__ import annotations

import queue
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from hashlib import sha256
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ourd.writing_engine import (
    FormalWritingCancelledError,
    FormalWritingRequest,
    FormalWritingResult,
    FormalWritingService,
)
from ourd.writing_engine.signatures import content_sha256
from ourd.formal_writing_governance import prepare_governed_formal_write

from .formal_writing_models import (
    FormalWritingExecutionOptions,
    FormalWritingFormState,
    FormalWritingGuiEvent,
    FormalWritingGuiEventType,
    FormalWritingJobStatus,
    GovernedWritePreview,
)
from .formal_writing_projection import FormalWritingProjectionStore, FormalWritingResultProjection


MAX_EVENT_QUEUE = 1_000


class FormalWritingBusyError(RuntimeError):
    pass


class FormalWritingQualificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class FormalWritingJobSnapshot:
    job_id: str = ""
    operation: str = ""
    status: FormalWritingJobStatus = FormalWritingJobStatus.IDLE
    request_id: str = ""
    phase: str = ""
    message: str = ""


class FormalWritingController:
    def __init__(
        self,
        repository_root: Path,
        *,
        authority_path: Path | None = None,
        service_factory: Callable[[Path], FormalWritingService] = FormalWritingService,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.authority_path = authority_path.resolve() if authority_path is not None else None
        self.service_factory = service_factory
        self.projections = FormalWritingProjectionStore(self.repository_root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="formal-writing-gui")
        self._events: queue.Queue[FormalWritingGuiEvent] = queue.Queue(maxsize=MAX_EVENT_QUEUE)
        self._lock = threading.Lock()
        self._sequence = 0
        self._job_sequence = 0
        self._active_job_id = ""
        self._active_operation = ""
        self._active_request_id = ""
        self._active_phase = ""
        self._active_message = ""
        self._active_status = FormalWritingJobStatus.IDLE
        self._active_cancel: threading.Event | None = None
        self._active_future: Future[None] | None = None
        self._closed = False

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return bool(self._active_job_id)

    @property
    def job_snapshot(self) -> FormalWritingJobSnapshot:
        with self._lock:
            return FormalWritingJobSnapshot(
                job_id=self._active_job_id,
                operation=self._active_operation,
                status=self._active_status,
                request_id=self._active_request_id,
                phase=self._active_phase,
                message=self._active_message,
            )

    def submit(
        self,
        operation: str,
        form: FormalWritingFormState,
        options: FormalWritingExecutionOptions | None = None,
    ) -> str:
        normalized_operation = operation.casefold().strip()
        execution_options = options or FormalWritingExecutionOptions()
        with self._lock:
            if self._closed:
                raise RuntimeError("formal-writing controller is closed")
            if self._active_job_id:
                raise FormalWritingBusyError(
                    f"formal-writing job already active: {self._active_job_id}"
                )
            self._job_sequence += 1
            job_id = f"formal-writing-job:{self._job_sequence:08d}"
            cancel_event = threading.Event()
            self._active_job_id = job_id
            self._active_operation = normalized_operation
            self._active_request_id = ""
            self._active_phase = "queued"
            self._active_message = "Queued"
            self._active_status = FormalWritingJobStatus.QUEUED
            self._active_cancel = cancel_event
        self._emit(
            FormalWritingGuiEventType.JOB_QUEUED,
            job_id,
            normalized_operation,
            phase="queued",
            message="Formal-writing job queued",
        )
        future = self.executor.submit(
            self._run_job,
            job_id,
            normalized_operation,
            form,
            execution_options,
            cancel_event,
        )
        with self._lock:
            if self._active_job_id == job_id:
                self._active_future = future
        return job_id

    def preview_governed_write(
        self,
        form: FormalWritingFormState,
        *,
        authority_path: Path | None = None,
    ) -> GovernedWritePreview:
        resolved_form, prior, source_document_ids = self._resolve_form(form)
        if prior is None or not resolved_form.draft_id or prior.draft_id != resolved_form.draft_id:
            raise ValueError("governed write requires an exact persisted draft ID")
        if not resolved_form.output_paths:
            raise ValueError("governed write requires at least one output path")
        selected_authority = (authority_path or self.authority_path)
        if selected_authority is None:
            raise ValueError("governed write requires an exact-snapshot authority manifest")
        selected_authority = selected_authority.resolve()
        try:
            authority_sha256 = sha256(selected_authority.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError(f"authority manifest is unavailable: {selected_authority}") from exc
        draft_text = self.projections.persisted_draft_text(prior.draft_id)
        request = resolved_form.compile_request(
            "write",
            source_document_ids=source_document_ids,
            authority_binding=str(selected_authority),
        )
        return GovernedWritePreview(
            request=request,
            draft_id=prior.draft_id,
            draft_sha256=content_sha256(draft_text),
            audit_id=prior.audit_id,
            audit_status=prior.audit_status,
            qualified_document_id=prior.qualified_document_id,
            source_bindings=tuple(
                (
                    source.source_document_id,
                    source.workspace_relative_path,
                    source.content_sha256,
                )
                for source in prior.result.sources
            ),
            output_paths=resolved_form.output_paths,
            authority_path=str(selected_authority),
            authority_sha256=authority_sha256,
            limitations=prior.limitations,
        )

    def submit_governed_write(
        self,
        preview: GovernedWritePreview,
        *,
        confirmed_request_signature: str,
    ) -> str:
        with self._lock:
            if self._closed:
                raise RuntimeError("formal-writing controller is closed")
            if self._active_job_id:
                raise FormalWritingBusyError(
                    f"formal-writing job already active: {self._active_job_id}"
                )
            self._job_sequence += 1
            job_id = f"formal-writing-job:{self._job_sequence:08d}"
            cancel_event = threading.Event()
            self._active_job_id = job_id
            self._active_operation = "write"
            self._active_request_id = preview.request.request_id
            self._active_phase = "queued"
            self._active_message = "Governed write preparation queued"
            self._active_status = FormalWritingJobStatus.QUEUED
            self._active_cancel = cancel_event
        self._emit(
            FormalWritingGuiEventType.JOB_QUEUED,
            job_id,
            "write",
            request_id=preview.request.request_id,
            phase="queued",
            message="Governed write preparation queued",
        )
        future = self.executor.submit(
            self._run_governed_write,
            job_id,
            preview,
            confirmed_request_signature,
            cancel_event,
        )
        with self._lock:
            if self._active_job_id == job_id:
                self._active_future = future
        return job_id

    def request_cancel(self, job_id: str | None = None) -> bool:
        with self._lock:
            if not self._active_job_id:
                return False
            if job_id is not None and job_id != self._active_job_id:
                return False
            active_job_id = self._active_job_id
            operation = self._active_operation
            request_id = self._active_request_id
            cancel_event = self._active_cancel
            self._active_status = FormalWritingJobStatus.CANCEL_REQUESTED
            self._active_message = "Cancellation requested; waiting for a safe phase boundary"
        if cancel_event is not None:
            cancel_event.set()
        self._emit(
            FormalWritingGuiEventType.JOB_CANCEL_REQUESTED,
            active_job_id,
            operation,
            request_id=request_id,
            phase="cancel_requested",
            message="Cancellation requested; the current phase may need to finish",
        )
        return True

    def poll_events(self, *, limit: int = MAX_EVENT_QUEUE) -> tuple[FormalWritingGuiEvent, ...]:
        events: list[FormalWritingGuiEvent] = []
        for _ in range(max(0, limit)):
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return tuple(events)

    def wait_for_idle(self, timeout: float | None = None) -> None:
        with self._lock:
            future = self._active_future
        if future is not None:
            future.result(timeout=timeout)

    def shutdown(
        self,
        *,
        wait: bool = False,
        timeout_seconds: float | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            cancel_event = self._active_cancel
            future = self._active_future
        if cancel_event is not None:
            cancel_event.set()
        if future is not None and timeout_seconds is not None:
            try:
                future.result(timeout=max(0.0, timeout_seconds))
            except (FutureTimeoutError, FormalWritingCancelledError):
                pass
            except Exception:
                pass
        self.executor.shutdown(
            wait=wait or (future is not None and future.done()),
            cancel_futures=True,
        )

    def _run_job(
        self,
        job_id: str,
        operation: str,
        form: FormalWritingFormState,
        options: FormalWritingExecutionOptions,
        cancel_event: threading.Event,
    ) -> None:
        request: FormalWritingRequest | None = None
        try:
            resolved_form, prior, source_document_ids = self._resolve_form(form)
            if operation == "audit" and prior is not None and form.draft_id:
                self._set_active(
                    job_id,
                    status=FormalWritingJobStatus.RUNNING,
                    request_id=prior.request_id,
                    phase="audit_loaded",
                    message="Loaded the exact persisted audit",
                )
                self._emit(
                    FormalWritingGuiEventType.JOB_STARTED,
                    job_id,
                    operation,
                    request_id=prior.request_id,
                    phase="audit_loaded",
                    message="Loading persisted audit without regenerating the draft",
                )
                self._enforce_result_policy(prior.result, options)
                self._emit_completed(job_id, operation, prior)
                return
            prior_draft_text = ""
            if operation == "revise":
                if prior is None or not form.draft_id:
                    raise ValueError("revision requires an exact persisted draft ID")
                prior_draft_text = self.projections.persisted_draft_text(form.draft_id)
            request = resolved_form.compile_request(
                operation,
                source_document_ids=source_document_ids,
                authority_binding=str(self.authority_path or ""),
            )
            self._set_active(
                job_id,
                status=FormalWritingJobStatus.RUNNING,
                request_id=request.request_id,
                phase="request_compiled",
                message="Formal-writing request compiled",
            )
            self._emit(
                FormalWritingGuiEventType.JOB_STARTED,
                job_id,
                operation,
                request_id=request.request_id,
                phase="request_compiled",
                message="Formal-writing job started",
            )
            service = self.service_factory(self.repository_root)
            result = service.execute(
                request,
                allow_ocr=options.allow_ocr,
                ocr_language=options.ocr_language,
                prior_draft_text=prior_draft_text,
                progress_sink=lambda phase: self._progress(job_id, operation, request.request_id, phase),
                cancellation_check=cancel_event.is_set,
            )
            self._enforce_result_policy(result, options)
            projection = self.projections.find_result(result.request.request_id)
            if projection is None:
                raise RuntimeError("formal-writing result persisted but could not be projected")
            self._emit_completed(job_id, operation, projection)
        except FormalWritingCancelledError as exc:
            self._set_active(
                job_id,
                status=FormalWritingJobStatus.CANCELLED,
                phase="cancelled",
                message=str(exc),
            )
            self._emit(
                FormalWritingGuiEventType.JOB_CANCELLED,
                job_id,
                operation,
                request_id=request.request_id if request is not None else "",
                phase="cancelled",
                message=str(exc),
            )
        except Exception as exc:
            self._set_active(
                job_id,
                status=FormalWritingJobStatus.FAILED,
                phase="failed",
                message=f"{type(exc).__name__}: {exc}",
            )
            self._emit(
                FormalWritingGuiEventType.JOB_FAILED,
                job_id,
                operation,
                request_id=request.request_id if request is not None else "",
                phase="failed",
                message=str(exc)[:4_000],
                error_type=type(exc).__name__,
            )
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = ""
                    self._active_operation = ""
                    self._active_request_id = ""
                    self._active_phase = ""
                    self._active_message = ""
                    self._active_status = FormalWritingJobStatus.IDLE
                    self._active_cancel = None
                    self._active_future = None

    def _run_governed_write(
        self,
        job_id: str,
        preview: GovernedWritePreview,
        confirmed_request_signature: str,
        cancel_event: threading.Event,
    ) -> None:
        try:
            self._set_active(
                job_id,
                status=FormalWritingJobStatus.RUNNING,
                request_id=preview.request.request_id,
                phase="verifying_snapshot",
                message="Verifying the exact draft, sources, authority, and request",
            )
            self._emit(
                FormalWritingGuiEventType.JOB_STARTED,
                job_id,
                "write",
                request_id=preview.request.request_id,
                phase="verifying_snapshot",
                message="Verifying governed write bindings",
            )
            if confirmed_request_signature != preview.request_signature:
                raise ValueError("confirmed request signature does not match the preview")
            if cancel_event.is_set():
                raise FormalWritingCancelledError("formal-writing operation cancelled")
            draft_text = self.projections.persisted_draft_text(preview.draft_id)
            if content_sha256(draft_text) != preview.draft_sha256:
                raise ValueError("persisted draft changed after governed write preview")
            authority = Path(preview.authority_path)
            try:
                current_authority_sha256 = sha256(authority.read_bytes()).hexdigest()
            except OSError as exc:
                raise ValueError(f"authority manifest is unavailable: {authority}") from exc
            if current_authority_sha256 != preview.authority_sha256:
                raise ValueError("authority manifest changed after governed write preview")
            for source_id, source_path, expected_sha256 in preview.source_bindings:
                current = self.projections.workspace.file_hash_or_none(source_path)
                if current != expected_sha256:
                    raise ValueError(
                        f"source changed after governed write preview: {source_path} ({source_id})"
                    )
            if cancel_event.is_set():
                raise FormalWritingCancelledError("formal-writing operation cancelled")
            prepared = prepare_governed_formal_write(
                self.repository_root,
                authority,
                preview.request_signature,
                confirmed_request_signature,
                preview.request.objective,
                preview.output_paths,
                draft_text,
            )
            transaction = prepared.get("transaction") or {}
            action = prepared.get("eon_action") or {}
            self._set_active(
                job_id,
                status=FormalWritingJobStatus.COMPLETED,
                request_id=preview.request.request_id,
                phase="governed_write_prepared",
                message=str(prepared.get("status", "")),
            )
            self._emit(
                FormalWritingGuiEventType.JOB_COMPLETED,
                job_id,
                "write",
                request_id=preview.request.request_id,
                phase="governed_write_prepared",
                message=str(prepared.get("status", "")),
                result_request_id=preview.request.request_id,
                audit_status=preview.audit_status,
                details={
                    "transaction_id": str(transaction.get("transaction_id", "")),
                    "eon_action_id": str(action.get("action_id", action.get("eon_action_id", ""))),
                    "status": str(prepared.get("status", "")),
                },
            )
        except FormalWritingCancelledError as exc:
            self._emit(
                FormalWritingGuiEventType.JOB_CANCELLED,
                job_id,
                "write",
                request_id=preview.request.request_id,
                phase="cancelled",
                message=str(exc),
            )
        except Exception as exc:
            self._emit(
                FormalWritingGuiEventType.JOB_FAILED,
                job_id,
                "write",
                request_id=preview.request.request_id,
                phase="failed",
                message=str(exc)[:4_000],
                error_type=type(exc).__name__,
            )
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = ""
                    self._active_operation = ""
                    self._active_request_id = ""
                    self._active_phase = ""
                    self._active_message = ""
                    self._active_status = FormalWritingJobStatus.IDLE
                    self._active_cancel = None
                    self._active_future = None

    def _resolve_form(
        self,
        form: FormalWritingFormState,
    ) -> tuple[FormalWritingFormState, FormalWritingResultProjection | None, tuple[str, ...]]:
        normalized = form.with_paths_relative_to(self.repository_root)
        identifier = normalized.draft_id or normalized.plan_id
        prior = self.projections.find_result(identifier) if identifier else None
        if identifier and prior is None:
            raise ValueError(f"unknown persisted formal-writing ID: {identifier}")
        if prior is None:
            return normalized, None, ()
        inherited = prior.form_state()
        resolved = FormalWritingFormState(
            objective=normalized.objective or inherited.objective,
            profile=inherited.profile,
            genre=inherited.genre,
            audience=inherited.audience,
            discipline=inherited.discipline,
            word_target=normalized.word_target or inherited.word_target,
            source_paths=normalized.source_paths,
            rubric_paths=normalized.rubric_paths or inherited.rubric_paths,
            constraints=tuple(dict.fromkeys((*inherited.constraints, *normalized.constraints))),
            citation_style=inherited.citation_style,
            locale=inherited.locale,
            network_policy=inherited.network_policy,
            plan_id=normalized.plan_id,
            draft_id=normalized.draft_id,
            output_paths=normalized.output_paths,
        )
        return resolved, prior, prior.source_document_ids

    def _enforce_result_policy(
        self,
        result: FormalWritingResult,
        options: FormalWritingExecutionOptions,
    ) -> None:
        if options.require_page_accuracy:
            reflowable = [source.workspace_relative_path for source in result.sources if source.page_count == 0]
            if reflowable:
                raise ValueError(
                    "page accuracy was required, but these sources have no stable pages: "
                    + ", ".join(reflowable)
                )
        if options.require_qualified:
            audit = result.qualified_document.audit if result.qualified_document is not None else None
            if audit is None or audit.status != "QUALIFIED_FORMAL_DOCUMENT":
                status = audit.status if audit is not None else "EVIDENCE_INSUFFICIENT"
                raise FormalWritingQualificationError(
                    f"formal-writing qualification gate failed: {status}"
                )

    def _progress(self, job_id: str, operation: str, request_id: str, phase: str) -> None:
        self._set_active(
            job_id,
            status=FormalWritingJobStatus.RUNNING,
            request_id=request_id,
            phase=phase,
            message=phase.replace("_", " ").capitalize(),
        )
        self._emit(
            FormalWritingGuiEventType.JOB_PROGRESS,
            job_id,
            operation,
            request_id=request_id,
            phase=phase,
            message=phase.replace("_", " ").capitalize(),
        )

    def _emit_completed(
        self,
        job_id: str,
        operation: str,
        projection: FormalWritingResultProjection,
    ) -> None:
        self._set_active(
            job_id,
            status=FormalWritingJobStatus.COMPLETED,
            request_id=projection.request_id,
            phase="completed",
            message="Formal-writing job completed",
        )
        self._emit(
            FormalWritingGuiEventType.JOB_COMPLETED,
            job_id,
            operation,
            request_id=projection.request_id,
            phase="completed",
            message="Formal-writing job completed",
            result_request_id=projection.request_id,
            result_path=str(projection.path),
            audit_status=projection.audit_status,
            details={
                "plan_id": projection.document_plan_id or projection.plan_id,
                "draft_id": projection.draft_id,
                "audit_id": projection.audit_id,
                "qualified_document_id": projection.qualified_document_id,
            },
        )

    def _set_active(
        self,
        job_id: str,
        *,
        status: FormalWritingJobStatus,
        phase: str,
        message: str,
        request_id: str = "",
    ) -> None:
        with self._lock:
            if self._active_job_id != job_id:
                return
            self._active_status = status
            self._active_phase = phase
            self._active_message = message
            if request_id:
                self._active_request_id = request_id

    def _emit(
        self,
        event_type: FormalWritingGuiEventType,
        job_id: str,
        operation: str,
        **kwargs: object,
    ) -> None:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        event = FormalWritingGuiEvent.create(
            sequence=sequence,
            event_type=event_type,
            job_id=job_id,
            operation=operation,
            **kwargs,
        )
        try:
            self._events.put_nowait(event)
        except queue.Full:
            try:
                self._events.get_nowait()
            except queue.Empty:
                pass
            self._events.put_nowait(event)


__all__ = [
    "FormalWritingBusyError",
    "FormalWritingController",
    "FormalWritingJobSnapshot",
    "FormalWritingQualificationError",
]
