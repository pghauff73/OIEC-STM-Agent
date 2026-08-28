from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, Mapping

from ourd.egcf.ids import sha256_json

from .events import AgentEvent, AgentEventType


GUI_READ_MODEL_SCHEMA_VERSION = 2
MAX_PROJECTED_CHAT_MESSAGES = 500


OBJECT_BUCKETS = {
    "intent": "intent_ids",
    "command-invocation": "invocation_ids",
    "selection-decision": "selection_ids",
    "compiled-workflow": "compiled_workflow_ids",
    "execution-plan": "execution_plan_ids",
    "execution": "execution_ids",
    "egcf-evidence": "evidence_ids",
    "failure": "failure_ids",
    "artifact": "artifact_ids",
    "assurance-case": "assurance_case_ids",
    "approval": "approval_ids",
}


@dataclass(frozen=True)
class GuiSession:
    session_id: str
    repository_root: str
    opened_at: str
    source_snapshot_at_open: str
    task_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuiTask:
    task_id: str
    session_id: str
    title: str
    status: str = "PENDING"
    intent_ids: tuple[str, ...] = ()
    invocation_ids: tuple[str, ...] = ()
    selection_ids: tuple[str, ...] = ()
    compiled_workflow_ids: tuple[str, ...] = ()
    execution_plan_ids: tuple[str, ...] = ()
    execution_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    failure_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    assurance_case_ids: tuple[str, ...] = ()
    approval_ids: tuple[str, ...] = ()
    last_message: str = ""
    last_result: Any = None


@dataclass(frozen=True)
class GuiChatMessage:
    message_id: str
    turn_id: str
    role: str
    content: str
    timestamp: str
    status: str = "complete"


@dataclass(frozen=True)
class GuiState:
    schema_version: int = GUI_READ_MODEL_SCHEMA_VERSION
    repository_root: str = ""
    source_snapshot: str = ""
    event_head: str = ""
    sessions: Mapping[str, GuiSession] = field(default_factory=dict)
    tasks: Mapping[str, GuiTask] = field(default_factory=dict)
    selected_session_id: str = ""
    selected_task_id: str = ""
    selected_object_id: str = ""
    navigation_back: tuple[str, ...] = ()
    navigation_forward: tuple[str, ...] = ()
    worker_status: str = "idle"
    last_error: str = ""
    replay_cursor: int = -1
    chat_messages: tuple[GuiChatMessage, ...] = ()
    chat_status: str = "idle"
    active_chat_turn_id: str = ""
    chat_context_start: int = 0

    @property
    def digest(self) -> str:
        return sha256_json(asdict(self))


def _append_unique(values: tuple[str, ...], additions: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*values, *[item for item in additions if item]]))


def _replace_task(state: GuiState, task: GuiTask) -> GuiState:
    tasks = dict(state.tasks)
    tasks[task.task_id] = task
    return replace(state, tasks=tasks)


def reduce_event(state: GuiState, event: AgentEvent) -> GuiState:
    payload = dict(event.payload)
    if event.event_type == AgentEventType.SESSION_OPENED:
        session = GuiSession(
            session_id=event.session_id,
            repository_root=str(payload.get("repository_root", "")),
            opened_at=event.timestamp,
            source_snapshot_at_open=str(payload.get("source_snapshot", "")),
        )
        sessions = dict(state.sessions)
        sessions[session.session_id] = session
        return replace(
            state,
            repository_root=session.repository_root,
            source_snapshot=session.source_snapshot_at_open,
            sessions=sessions,
            selected_session_id=session.session_id,
            event_head=event.core_event_hash or state.event_head,
            last_error="",
        )
    if event.event_type == AgentEventType.TASK_STARTED:
        task = GuiTask(
            task_id=event.task_id,
            session_id=event.session_id,
            title=str(payload.get("title", "Untitled task")),
            status=str(payload.get("status", "RUNNING")),
            last_message=str(payload.get("message", "")),
        )
        sessions = dict(state.sessions)
        session = sessions.get(event.session_id)
        if session is not None:
            sessions[event.session_id] = replace(
                session,
                task_ids=_append_unique(session.task_ids, [task.task_id]),
            )
        tasks = dict(state.tasks)
        tasks[task.task_id] = task
        return replace(
            state,
            sessions=sessions,
            tasks=tasks,
            selected_session_id=event.session_id or state.selected_session_id,
            selected_task_id=task.task_id,
        )
    if event.event_type == AgentEventType.TASK_SELECTED:
        return replace(state, selected_task_id=event.task_id)
    if event.event_type == AgentEventType.TASK_OBJECTS_ATTACHED:
        task = state.tasks.get(event.task_id)
        if task is None:
            return state
        updates: Dict[str, Any] = {}
        typed_ids = payload.get("typed_ids", {})
        if isinstance(typed_ids, Mapping):
            for object_type, identifiers in typed_ids.items():
                bucket = OBJECT_BUCKETS.get(str(object_type))
                if bucket is None or not isinstance(identifiers, list):
                    continue
                updates[bucket] = _append_unique(
                    getattr(task, bucket),
                    [str(item) for item in identifiers],
                )
        if payload.get("status"):
            updates["status"] = str(payload["status"])
        if payload.get("message"):
            updates["last_message"] = str(payload["message"])
        if "result" in payload:
            updates["last_result"] = payload["result"]
        updated = _replace_task(state, replace(task, **updates))
        if payload.get("source_snapshot"):
            updated = replace(updated, source_snapshot=str(payload["source_snapshot"]))
        return updated
    if event.event_type == AgentEventType.TASK_FINISHED:
        task = state.tasks.get(event.task_id)
        if task is None:
            return state
        return _replace_task(
            state,
            replace(
                task,
                status=str(payload.get("status", "COMPLETED")),
                last_message=str(payload.get("message", task.last_message)),
                last_result=payload.get("result", task.last_result),
            ),
        )
    if event.event_type == AgentEventType.CHAT_MESSAGE_ADDED:
        message = GuiChatMessage(
            message_id=str(payload.get("message_id", event.event_id)),
            turn_id=str(payload.get("turn_id", event.task_id)),
            role=str(payload.get("role", "system")),
            content=str(payload.get("content", "")),
            timestamp=str(payload.get("timestamp", event.timestamp)),
            status=str(payload.get("status", "complete")),
        )
        messages = (*state.chat_messages, message)[-MAX_PROJECTED_CHAT_MESSAGES:]
        dropped = max(0, len(state.chat_messages) + 1 - len(messages))
        return replace(
            state,
            chat_messages=messages,
            chat_context_start=max(0, state.chat_context_start - dropped),
        )
    if event.event_type == AgentEventType.CHAT_TURN_STARTED:
        return replace(
            state,
            chat_status="running",
            active_chat_turn_id=str(payload.get("turn_id", event.task_id)),
        )
    if event.event_type == AgentEventType.CHAT_TURN_STOP_REQUESTED:
        return replace(state, chat_status="stopping")
    if event.event_type == AgentEventType.CHAT_TURN_FINISHED:
        return replace(state, chat_status="idle", active_chat_turn_id="")
    if event.event_type == AgentEventType.CHAT_CONTEXT_CLEARED:
        return replace(state, chat_context_start=len(state.chat_messages))
    if event.event_type == AgentEventType.OBJECT_SELECTED:
        selected = str(payload.get("object_id", ""))
        if not selected or selected == state.selected_object_id:
            return state
        back = state.navigation_back
        if state.selected_object_id:
            back = (*back, state.selected_object_id)
        return replace(
            state,
            selected_object_id=selected,
            navigation_back=back,
            navigation_forward=(),
        )
    if event.event_type == AgentEventType.NAVIGATE_BACK:
        if not state.navigation_back:
            return state
        selected = state.navigation_back[-1]
        forward = state.navigation_forward
        if state.selected_object_id:
            forward = (state.selected_object_id, *forward)
        return replace(
            state,
            selected_object_id=selected,
            navigation_back=state.navigation_back[:-1],
            navigation_forward=forward,
        )
    if event.event_type == AgentEventType.NAVIGATE_FORWARD:
        if not state.navigation_forward:
            return state
        selected = state.navigation_forward[0]
        back = state.navigation_back
        if state.selected_object_id:
            back = (*back, state.selected_object_id)
        return replace(
            state,
            selected_object_id=selected,
            navigation_back=back,
            navigation_forward=state.navigation_forward[1:],
        )
    if event.event_type == AgentEventType.WORKER_STATUS:
        return replace(state, worker_status=str(payload.get("status", "idle")))
    if event.event_type == AgentEventType.REPLAY_POSITION_CHANGED:
        return replace(state, replay_cursor=int(payload.get("cursor", -1)))
    if event.event_type == AgentEventType.UI_ERROR:
        return replace(state, last_error=str(payload.get("message", "Unknown GUI error")))
    if event.authoritative and event.core_event_hash:
        return replace(state, event_head=event.core_event_hash)
    return state
