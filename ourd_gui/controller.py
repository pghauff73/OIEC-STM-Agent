from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping

from ourd.egcf.models import AssuranceCase
from ourd.errors import AgentCancelledError
from ourd.providers import ProviderConfig

from .assurance_exports import assurance_html, assurance_json, assurance_markdown
from .commands import (
    ApprovalRequest,
    CommandRequest,
    ExecutionRequest,
    ObjectiveRequest,
    ReplayRequest,
)
from .core_gateway import CoreGateway
from .events import AgentEvent, AgentEventBus, AgentEventType
from .evidence_exports import evidence_json, evidence_markdown
from .persistence import CoreEventTailer, GuiEventJournal, GuiExportStore, GuiProjectionStore
from .performance import PerformanceMonitor
from .read_models import ReadOnlyEGCFRepository
from .redaction import safe_projection
from .selection_trace import SelectionTraceAssembler
from .state import GuiState, reduce_event


CORE_EVENT_MAP: Dict[str, AgentEventType] = {
    "egcf_execution_plan_created": AgentEventType.EON_CREATED,
    "egcf_human_approval": AgentEventType.APPROVAL_RECORDED,
    "egcf_node_executed": AgentEventType.ACTION_FINISHED,
    "egcf_workflow_completed": AgentEventType.TASK_FINISHED,
    "egcf_evidence_collected": AgentEventType.EVIDENCE_UPDATED,
    "egcf_object_superseded": AgentEventType.GOVERNANCE_UPDATED,
    "egcf_artifact_registered": AgentEventType.ARTIFACT_CREATED,
    "egcf_candidate_certified": AgentEventType.ASSURANCE_UPDATED,
}

OBJECT_EVENT_MAP: Dict[str, AgentEventType] = {
    "selection-decision": AgentEventType.SELECTION_UPDATED,
    "compiled-workflow": AgentEventType.WORKFLOW_UPDATED,
    "execution-plan": AgentEventType.EON_CREATED,
    "egcf-evidence": AgentEventType.EVIDENCE_UPDATED,
    "approval": AgentEventType.APPROVAL_RECORDED,
    "failure": AgentEventType.FAILURE_DETECTED,
    "artifact": AgentEventType.ARTIFACT_CREATED,
    "assurance-case": AgentEventType.ASSURANCE_UPDATED,
    "invariant": AgentEventType.GOVERNANCE_UPDATED,
    "decision": AgentEventType.GOVERNANCE_UPDATED,
}

CHAT_TRACE_EVENT_MAP: Dict[str, AgentEventType] = {
    "tool_call": AgentEventType.TOOL_REQUESTED,
    "tool_result": AgentEventType.TOOL_COMPLETED,
    "model_request": AgentEventType.AGENT_STEP,
    "provider_preflight": AgentEventType.CHAT_ACTIVITY,
    "run_started": AgentEventType.CHAT_ACTIVITY,
    "final": AgentEventType.CHAT_ACTIVITY,
}


@dataclass(frozen=True)
class PendingOperation:
    task_id: str
    label: str
    future: Future[Any]
    started_at: float


class GuiController:
    def __init__(
        self,
        repository_root: Path,
        *,
        authority_path: Path | None = None,
        actor: str = "user",
        provider_config: ProviderConfig | None = None,
        max_agent_steps: int = 80,
    ) -> None:
        initialization_started = time.perf_counter()
        self.repository_root = repository_root.resolve()
        self.performance = PerformanceMonitor()
        self.gateway = CoreGateway(
            self.repository_root,
            authority_path=authority_path,
            actor=actor,
            provider_config=provider_config,
            max_agent_steps=max_agent_steps,
        )
        self.repository = ReadOnlyEGCFRepository(self.repository_root)
        self.selection_assembler = SelectionTraceAssembler(self.repository)
        self.bus = AgentEventBus()
        self.journal = GuiEventJournal(self.repository_root)
        self.projection = GuiProjectionStore(self.repository_root)
        self.exports = GuiExportStore(self.repository_root)
        self.tailer = CoreEventTailer(self.repository_root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ourd-gui-core")
        self.session_id = str(uuid.uuid4())
        prior_events = self.journal.events()
        self._journal_event_count = len(prior_events)
        self.state = self.projection.load(expected_event_count=len(prior_events)) or self.projection.rebuild(prior_events)
        if prior_events:
            self.bus.set_sequence_floor(max(event.sequence for event in prior_events))
        self._state_lock = threading.Lock()
        self._journal_lock = threading.Lock()
        self._closed = False
        self._pending: Dict[str, PendingOperation] = {}
        self._active_chat_operation_id = ""
        self._active_chat_turn_id = ""
        self._chat_cancel_event: threading.Event | None = None
        self.bus.subscribe(self._reduce)
        self.tailer.reset_to_end()
        self._publish(
            self.bus.make_event(
                AgentEventType.SESSION_OPENED,
                session_id=self.session_id,
                source="controller",
                payload={
                    "repository_root": str(self.repository_root),
                    "source_snapshot": self.gateway.snapshot(),
                },
            )
        )
        self.performance.record_ms(
            "controller.initialize",
            (time.perf_counter() - initialization_started) * 1_000,
        )

    def _reduce(self, event: AgentEvent) -> None:
        with self._state_lock:
            self.state = reduce_event(self.state, event)

    def _publish(self, event: AgentEvent, *, persist: bool = True) -> None:
        if persist:
            with self._journal_lock:
                self.journal.append(event)
                self._journal_event_count += 1
        self.bus.publish(event)

    def _emit(
        self,
        event_type: AgentEventType,
        *,
        task_id: str = "",
        action_id: str = "",
        source: str = "controller",
        authoritative: bool = False,
        core_event_hash: str = "",
        object_ids: Iterable[str] = (),
        payload: Mapping[str, Any] | None = None,
        persist: bool = True,
    ) -> AgentEvent:
        event = self.bus.make_event(
            event_type,
            session_id=self.session_id,
            task_id=task_id,
            action_id=action_id,
            source=source,
            authoritative=authoritative,
            core_event_hash=core_event_hash,
            object_ids=object_ids,
            payload=payload,
        )
        self._publish(event, persist=persist)
        return event

    def _core_event_to_agent_event(self, event: Mapping[str, Any], task_id: str) -> AgentEvent:
        payload = dict(event.get("payload", {}))
        object_id = str(payload.get("object_id", ""))
        object_type = str(payload.get("object_type", ""))
        event_type = CORE_EVENT_MAP.get(str(event.get("event_type", "")))
        if event_type is None:
            event_type = OBJECT_EVENT_MAP.get(object_type, AgentEventType.AGENT_STEP)
        return self.bus.make_event(
            event_type,
            session_id=self.session_id,
            task_id=task_id,
            action_id=str(event.get("action_id", "")),
            source="egcf",
            authoritative=True,
            core_event_hash=str(event.get("event_hash", "")),
            object_ids=[object_id] if object_id else (),
            payload={
                "core_event_type": str(event.get("event_type", "")),
                "object_id": object_id,
                "object_type": object_type,
                "payload": payload,
            },
        )

    def _collect_core_events(self, task_id: str) -> Dict[str, list[str]]:
        typed_ids: Dict[str, list[str]] = {}
        for core_event in self.tailer.poll():
            event = self._core_event_to_agent_event(core_event, task_id)
            object_id = next(iter(event.object_ids), "")
            object_type = str(event.payload.get("object_type", ""))
            if object_id and object_type:
                typed_ids.setdefault(object_type, []).append(object_id)
            self._publish(event)
        return typed_ids

    def _operation_done(
        self,
        operation_id: str,
        task_id: str,
        label: str,
        future: Future[Any],
    ) -> None:
        pending = self._pending.pop(operation_id, None)
        duration_ms = (
            (time.perf_counter() - pending.started_at) * 1_000
            if pending is not None
            else 0.0
        )
        self.performance.record_ms(
            f"operation.{label}",
            duration_ms,
            {"task_id": task_id, "operation_id": operation_id},
        )
        try:
            result = future.result()
            typed_ids = self._collect_core_events(task_id)
            status = str(result.get("status", "COMPLETED")) if isinstance(result, dict) else "COMPLETED"
            self._emit(
                AgentEventType.TASK_OBJECTS_ATTACHED,
                task_id=task_id,
                payload={
                    "typed_ids": typed_ids,
                    "status": status,
                    "message": f"{label} completed",
                    "result": result,
                    "duration_ms": duration_ms,
                    "source_snapshot": self.gateway.snapshot(),
                },
            )
            self._emit(
                AgentEventType.TASK_FINISHED,
                task_id=task_id,
                payload={
                    "status": status,
                    "message": f"{label} completed",
                    "result": result,
                    "duration_ms": duration_ms,
                },
            )
        except Exception as exc:
            try:
                typed_ids = self._collect_core_events(task_id)
            except Exception:
                typed_ids = {}
            self._emit(
                AgentEventType.TASK_OBJECTS_ATTACHED,
                task_id=task_id,
                payload={"typed_ids": typed_ids, "status": "FAILED"},
            )
            self._emit(
                AgentEventType.UI_ERROR,
                task_id=task_id,
                payload={"message": f"{type(exc).__name__}: {exc}", "operation": label},
            )
            self._emit(
                AgentEventType.TASK_FINISHED,
                task_id=task_id,
                payload={
                    "status": "FAILED",
                    "message": f"{label} failed",
                    "duration_ms": duration_ms,
                },
            )
        finally:
            self._emit(
                AgentEventType.WORKER_STATUS,
                task_id=task_id,
                payload={"status": "idle"},
            )

    def _submit(
        self,
        task_id: str,
        label: str,
        function: Callable[[], Any],
    ) -> str:
        if self._closed:
            raise RuntimeError("GUI controller is closed")
        operation_id = str(uuid.uuid4())
        self._emit(
            AgentEventType.WORKER_STATUS,
            task_id=task_id,
            payload={"status": f"running: {label}"},
        )
        started_at = time.perf_counter()
        future = self.executor.submit(function)
        self._pending[operation_id] = PendingOperation(task_id, label, future, started_at)
        future.add_done_callback(
            lambda completed: self._operation_done(operation_id, task_id, label, completed)
        )
        return operation_id

    def submit_objective(self, request: ObjectiveRequest) -> str:
        task_id = str(uuid.uuid4())
        self._emit(
            AgentEventType.TASK_STARTED,
            task_id=task_id,
            payload={"title": request.objective, "status": "RUNNING"},
        )
        self._submit(task_id, "objective", lambda: self.gateway.run_objective(request))
        return task_id

    def submit_command(self, request: CommandRequest) -> str:
        task_id = str(uuid.uuid4())
        self._emit(
            AgentEventType.TASK_STARTED,
            task_id=task_id,
            payload={"title": request.command_id, "status": "RUNNING"},
        )
        self._submit(task_id, "command", lambda: self.gateway.invoke(request))
        return task_id

    def _chat_history(self) -> list[Dict[str, str]]:
        return [
            {"role": message.role, "content": message.content}
            for message in self.state.chat_messages[self.state.chat_context_start :]
            if message.role in {"user", "assistant"}
            and message.status == "complete"
            and message.content
        ]

    def _publish_chat_trace(
        self,
        task_id: str,
        turn_id: str,
        envelope: Mapping[str, Any],
    ) -> None:
        trace_type = str(envelope.get("event_type", "agent_trace"))
        payload = safe_projection(
            envelope.get("payload", {}),
            max_depth=8,
            max_items=200,
            max_string_characters=20_000,
        )
        self._emit(
            CHAT_TRACE_EVENT_MAP.get(trace_type, AgentEventType.CHAT_ACTIVITY),
            task_id=task_id,
            source="ourd-agent",
            authoritative=True,
            core_event_hash=str(envelope.get("event_hash", "")),
            payload={
                "turn_id": turn_id,
                "trace_type": trace_type,
                "trace_payload": payload,
                "run_id": str(envelope.get("run_id", "")),
            },
        )

    def submit_chat_message(self, content: str) -> str:
        message = content.strip()
        if not message:
            raise ValueError("chat message is empty")
        if len(message) > 32_000:
            raise ValueError("chat message exceeds the 32,000 character limit")
        if self._active_chat_operation_id:
            raise RuntimeError("an agent chat turn is already running")
        task_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        history = self._chat_history()
        cancel_event = threading.Event()
        self._chat_cancel_event = cancel_event
        self._active_chat_operation_id = operation_id
        self._active_chat_turn_id = turn_id
        self._emit(
            AgentEventType.TASK_STARTED,
            task_id=task_id,
            payload={
                "title": message[:120],
                "status": "RUNNING",
                "message": "agent chat turn",
            },
        )
        self._emit(
            AgentEventType.CHAT_MESSAGE_ADDED,
            task_id=task_id,
            payload={
                "message_id": str(uuid.uuid4()),
                "turn_id": turn_id,
                "role": "user",
                "content": message,
                "status": "complete",
            },
        )
        self._emit(
            AgentEventType.CHAT_TURN_STARTED,
            task_id=task_id,
            payload={
                "turn_id": turn_id,
                "history_message_count": len(history),
            },
        )
        self._emit(
            AgentEventType.WORKER_STATUS,
            task_id=task_id,
            payload={"status": "running: agent chat"},
        )
        started_at = time.perf_counter()
        future = self.executor.submit(
            lambda: self.gateway.chat_turn(
                message,
                history,
                event_callback=lambda envelope: self._publish_chat_trace(
                    task_id,
                    turn_id,
                    envelope,
                ),
                cancel_check=cancel_event.is_set,
            )
        )
        self._pending[operation_id] = PendingOperation(
            task_id,
            "agent chat",
            future,
            started_at,
        )
        future.add_done_callback(
            lambda completed: self._chat_done(
                operation_id,
                task_id,
                turn_id,
                completed,
            )
        )
        return turn_id

    def _chat_done(
        self,
        operation_id: str,
        task_id: str,
        turn_id: str,
        future: Future[Any],
    ) -> None:
        pending = self._pending.pop(operation_id, None)
        duration_ms = (
            (time.perf_counter() - pending.started_at) * 1_000
            if pending is not None
            else 0.0
        )
        self.performance.record_ms(
            "operation.agent_chat",
            duration_ms,
            {"task_id": task_id, "turn_id": turn_id},
        )
        status = "COMPLETED"
        message = "agent chat completed"
        result: Any = None
        try:
            result = future.result()
            self._emit(
                AgentEventType.CHAT_MESSAGE_ADDED,
                task_id=task_id,
                payload={
                    "message_id": str(uuid.uuid4()),
                    "turn_id": turn_id,
                    "role": "assistant",
                    "content": str(result),
                    "status": "complete",
                },
            )
        except (AgentCancelledError, CancelledError):
            status = "CANCELLED"
            message = "agent chat stopped"
            self._emit(
                AgentEventType.CHAT_MESSAGE_ADDED,
                task_id=task_id,
                payload={
                    "message_id": str(uuid.uuid4()),
                    "turn_id": turn_id,
                    "role": "system",
                    "content": "Turn stopped. No further tool calls were dispatched.",
                    "status": "cancelled",
                },
            )
        except Exception as exc:
            status = "FAILED"
            message = "agent chat failed"
            error = f"{type(exc).__name__}: {exc}"
            self._emit(
                AgentEventType.CHAT_MESSAGE_ADDED,
                task_id=task_id,
                payload={
                    "message_id": str(uuid.uuid4()),
                    "turn_id": turn_id,
                    "role": "error",
                    "content": error,
                    "status": "failed",
                },
            )
            self._emit(
                AgentEventType.UI_ERROR,
                task_id=task_id,
                payload={"message": error, "operation": "agent chat"},
            )
        finally:
            self._emit(
                AgentEventType.CHAT_TURN_FINISHED,
                task_id=task_id,
                payload={
                    "turn_id": turn_id,
                    "status": status,
                    "duration_ms": duration_ms,
                },
            )
            self._emit(
                AgentEventType.TASK_OBJECTS_ATTACHED,
                task_id=task_id,
                payload={
                    "typed_ids": {},
                    "status": status,
                    "message": message,
                    "result": result,
                    "duration_ms": duration_ms,
                    "source_snapshot": self.gateway.snapshot(),
                },
            )
            self._emit(
                AgentEventType.TASK_FINISHED,
                task_id=task_id,
                payload={
                    "status": status,
                    "message": message,
                    "result": result,
                    "duration_ms": duration_ms,
                },
            )
            self._emit(
                AgentEventType.WORKER_STATUS,
                task_id=task_id,
                payload={"status": "idle"},
            )
            if self._active_chat_operation_id == operation_id:
                self._active_chat_operation_id = ""
                self._active_chat_turn_id = ""
                self._chat_cancel_event = None

    def stop_chat(self) -> bool:
        if not self._active_chat_operation_id or self._chat_cancel_event is None:
            return False
        self._chat_cancel_event.set()
        pending = self._pending.get(self._active_chat_operation_id)
        if pending is not None:
            pending.future.cancel()
        self._emit(
            AgentEventType.CHAT_TURN_STOP_REQUESTED,
            task_id=pending.task_id if pending is not None else "",
            payload={"turn_id": self._active_chat_turn_id},
        )
        return True

    def new_chat_context(self) -> None:
        if self._active_chat_operation_id:
            raise RuntimeError("cannot start a new chat while a turn is running")
        self._emit(
            AgentEventType.CHAT_MESSAGE_ADDED,
            payload={
                "message_id": str(uuid.uuid4()),
                "turn_id": "",
                "role": "system",
                "content": "New chat context started. Earlier messages remain in the audit log but are no longer sent to the model.",
                "status": "complete",
            },
        )
        self._emit(AgentEventType.CHAT_CONTEXT_CLEARED)

    def authorize(self, task_id: str, request: ApprovalRequest) -> str:
        self._emit(
            AgentEventType.APPROVAL_REQUIRED,
            task_id=task_id,
            object_ids=[request.plan_id],
            payload={"plan_id": request.plan_id, "approver": request.approver},
        )
        return self._submit(task_id, "approval", lambda: self.gateway.authorize(request))

    def reject_approval(self, task_id: str, plan_id: str, reason: str = "") -> None:
        self._emit(
            AgentEventType.APPROVAL_REJECTED,
            task_id=task_id,
            object_ids=[plan_id],
            payload={"plan_id": plan_id, "reason": reason or "rejected by user"},
        )

    def execute(self, task_id: str, request: ExecutionRequest) -> str:
        self._emit(
            AgentEventType.ACTION_STARTED,
            task_id=task_id,
            object_ids=[request.plan_id, request.approval_id],
            payload={"plan_id": request.plan_id, "approval_id": request.approval_id},
        )
        return self._submit(task_id, "execution", lambda: self.gateway.execute(request))

    def replay(self, task_id: str, request: ReplayRequest) -> str:
        return self._submit(task_id, "replay", lambda: self.gateway.replay(request))

    def select_task(self, task_id: str) -> None:
        self._emit(AgentEventType.TASK_SELECTED, task_id=task_id, persist=False)

    def select_object(self, object_id: str, task_id: str = "") -> None:
        self._emit(
            AgentEventType.OBJECT_SELECTED,
            task_id=task_id,
            object_ids=[object_id],
            payload={"object_id": object_id},
            persist=False,
        )

    def navigate_back(self) -> None:
        self._emit(AgentEventType.NAVIGATE_BACK, persist=False)

    def navigate_forward(self) -> None:
        self._emit(AgentEventType.NAVIGATE_FORWARD, persist=False)

    def set_replay_cursor(self, cursor: int) -> None:
        self._emit(
            AgentEventType.REPLAY_POSITION_CHANGED,
            payload={"cursor": int(cursor)},
            persist=False,
        )

    def export_assurance(self, assurance_id: str, format_name: str) -> Path:
        record = self.repository.get(assurance_id)
        if not isinstance(record, AssuranceCase):
            raise TypeError(f"not an assurance case: {assurance_id}")
        renderers = {
            "json": assurance_json,
            "markdown": assurance_markdown,
            "html": assurance_html,
        }
        try:
            content = renderers[format_name](record)
        except KeyError as exc:
            raise ValueError(f"unsupported assurance export format: {format_name}") from exc
        path = self.exports.save_assurance(assurance_id, format_name, content)
        self._emit(
            AgentEventType.ASSURANCE_UPDATED,
            object_ids=[assurance_id],
            payload={
                "assurance_id": assurance_id,
                "export_format": format_name,
                "export_path": str(path.relative_to(self.repository_root)),
                "authoritative": False,
            },
        )
        return path

    def export_evidence(self, identifiers: Iterable[str], format_name: str) -> Path:
        evidence_ids = tuple(dict.fromkeys(str(item) for item in identifiers if item))
        if not evidence_ids:
            raise ValueError("evidence export requires at least one object ID")
        renderers = {
            "json": evidence_json,
            "markdown": evidence_markdown,
        }
        try:
            content = renderers[format_name](self.repository, evidence_ids)
        except KeyError as exc:
            raise ValueError(f"unsupported evidence export format: {format_name}") from exc
        path = self.exports.save_evidence(evidence_ids, format_name, content)
        self._emit(
            AgentEventType.EVIDENCE_UPDATED,
            object_ids=evidence_ids,
            payload={
                "evidence_ids": list(evidence_ids),
                "export_format": format_name,
                "export_path": str(path.relative_to(self.repository_root)),
                "authoritative": False,
            },
        )
        return path

    def load_selection_trace(
        self,
        selection_id: str,
        *,
        task_id: str = "",
        invocation_id: str = "",
        compiled_workflow_id: str = "",
    ) -> str:
        def assemble() -> Any:
            return self.selection_assembler.assemble(
                selection_id,
                invocation_id=invocation_id,
                compiled_workflow_id=compiled_workflow_id,
            )

        operation_id = str(uuid.uuid4())
        started_at = time.perf_counter()
        future = self.executor.submit(assemble)
        self._pending[operation_id] = PendingOperation(
            task_id,
            "selection trace",
            future,
            started_at,
        )

        def done(completed: Future[Any]) -> None:
            pending = self._pending.pop(operation_id, None)
            duration_ms = (
                (time.perf_counter() - pending.started_at) * 1_000
                if pending is not None
                else 0.0
            )
            self.performance.record_ms(
                "operation.selection_trace",
                duration_ms,
                {"task_id": task_id, "operation_id": operation_id},
            )
            try:
                trace = completed.result()
                self._emit(
                    AgentEventType.SELECTION_UPDATED,
                    task_id=task_id,
                    object_ids=[selection_id],
                    payload={"trace": trace},
                    persist=False,
                )
            except Exception as exc:
                self._emit(
                    AgentEventType.UI_ERROR,
                    task_id=task_id,
                    payload={"message": f"{type(exc).__name__}: {exc}"},
                )

        future.add_done_callback(done)
        return operation_id

    def drain_events(self, limit: int = 500) -> tuple[list[AgentEvent], list[Exception]]:
        with self.performance.measure("controller.drain_events", {"limit": limit}):
            delivered, failures = self.bus.drain(limit)
            if delivered:
                with self.performance.measure(
                    "projection.save",
                    {"event_count": self._journal_event_count},
                ):
                    self.projection.save(
                        self.state,
                        event_count=self._journal_event_count,
                    )
        return delivered, failures

    def performance_snapshot(self) -> Mapping[str, Any]:
        return {
            **self.performance.snapshot(),
            "read_model_cache": dict(self.repository.cache_stats()),
            "pending_operations": len(self._pending),
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._chat_cancel_event is not None:
            self._chat_cancel_event.set()
        for operation in list(self._pending.values()):
            operation.future.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self._publish(
            self.bus.make_event(
                AgentEventType.SESSION_CLOSED,
                session_id=self.session_id,
                source="controller",
            )
        )
