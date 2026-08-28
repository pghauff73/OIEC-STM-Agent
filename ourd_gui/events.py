from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Mapping

from ourd.egcf.ids import utc_now


GUI_EVENT_SCHEMA_VERSION = 1


class AgentEventType(str, Enum):
    SESSION_OPENED = "SESSION_OPENED"
    SESSION_CLOSED = "SESSION_CLOSED"
    TASK_STARTED = "TASK_STARTED"
    TASK_FINISHED = "TASK_FINISHED"
    TASK_SELECTED = "TASK_SELECTED"
    TASK_OBJECTS_ATTACHED = "TASK_OBJECTS_ATTACHED"
    AGENT_STEP = "AGENT_STEP"
    TOOL_REQUESTED = "TOOL_REQUESTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    GOVERNANCE_UPDATED = "GOVERNANCE_UPDATED"
    SELECTION_UPDATED = "SELECTION_UPDATED"
    EON_CREATED = "EON_CREATED"
    EVIDENCE_UPDATED = "EVIDENCE_UPDATED"
    GATE_DECIDED = "GATE_DECIDED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_RECORDED = "APPROVAL_RECORDED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_FINISHED = "ACTION_FINISHED"
    FAILURE_DETECTED = "FAILURE_DETECTED"
    CFEL_UPDATED = "CFEL_UPDATED"
    FILE_CHANGED = "FILE_CHANGED"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    WORKFLOW_UPDATED = "WORKFLOW_UPDATED"
    ASSURANCE_UPDATED = "ASSURANCE_UPDATED"
    REPLAY_POSITION_CHANGED = "REPLAY_POSITION_CHANGED"
    OBJECT_SELECTED = "OBJECT_SELECTED"
    NAVIGATE_BACK = "NAVIGATE_BACK"
    NAVIGATE_FORWARD = "NAVIGATE_FORWARD"
    WORKER_STATUS = "WORKER_STATUS"
    UI_ERROR = "UI_ERROR"
    CHAT_MESSAGE_ADDED = "CHAT_MESSAGE_ADDED"
    CHAT_TURN_STARTED = "CHAT_TURN_STARTED"
    CHAT_TURN_STOP_REQUESTED = "CHAT_TURN_STOP_REQUESTED"
    CHAT_TURN_FINISHED = "CHAT_TURN_FINISHED"
    CHAT_CONTEXT_CLEARED = "CHAT_CONTEXT_CLEARED"
    CHAT_ACTIVITY = "CHAT_ACTIVITY"


@dataclass(frozen=True)
class AgentEvent:
    event_id: str
    sequence: int
    event_type: AgentEventType
    timestamp: str
    schema_version: int = GUI_EVENT_SCHEMA_VERSION
    session_id: str = ""
    task_id: str = ""
    action_id: str = ""
    source: str = "ui"
    authoritative: bool = False
    core_event_hash: str = ""
    object_ids: tuple[str, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != GUI_EVENT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported GUI event schema version: {self.schema_version}"
            )
        if self.authoritative and not (self.core_event_hash or self.object_ids):
            raise ValueError(
                "authoritative GUI events require a core event hash or canonical object ID"
            )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type.value
        payload["object_ids"] = list(self.object_ids)
        payload["payload"] = dict(self.payload)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentEvent":
        schema_version = int(payload.get("schema_version", GUI_EVENT_SCHEMA_VERSION))
        if schema_version != GUI_EVENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported GUI event schema version: {schema_version}")
        raw_event_type = str(payload["event_type"])
        event_payload = dict(payload.get("payload", {}))
        try:
            event_type = AgentEventType(raw_event_type)
        except ValueError:
            event_type = AgentEventType.AGENT_STEP
            event_payload = {
                **event_payload,
                "unknown_gui_event_type": raw_event_type,
            }
        return cls(
            event_id=str(payload["event_id"]),
            sequence=int(payload["sequence"]),
            event_type=event_type,
            timestamp=str(payload["timestamp"]),
            schema_version=schema_version,
            session_id=str(payload.get("session_id", "")),
            task_id=str(payload.get("task_id", "")),
            action_id=str(payload.get("action_id", "")),
            source=str(payload.get("source", "ui")),
            authoritative=bool(payload.get("authoritative", False)),
            core_event_hash=str(payload.get("core_event_hash", "")),
            object_ids=tuple(str(item) for item in payload.get("object_ids", [])),
            payload=event_payload,
        )


Subscriber = Callable[[AgentEvent], None]


class AgentEventBus:
    """Thread-safe queued event delivery for a Tk main-loop consumer."""

    def __init__(self) -> None:
        self._queue: queue.SimpleQueue[AgentEvent] = queue.SimpleQueue()
        self._subscriptions: Dict[str, tuple[AgentEventType | None, Subscriber]] = {}
        self._lock = threading.Lock()
        self._sequence = 0

    def subscribe(
        self,
        handler: Subscriber,
        event_type: AgentEventType | None = None,
    ) -> str:
        token = str(uuid.uuid4())
        with self._lock:
            self._subscriptions[token] = (event_type, handler)
        return token

    def set_sequence_floor(self, value: int) -> None:
        with self._lock:
            self._sequence = max(self._sequence, int(value))

    def unsubscribe(self, token: str) -> None:
        with self._lock:
            self._subscriptions.pop(token, None)

    def make_event(
        self,
        event_type: AgentEventType,
        *,
        session_id: str = "",
        task_id: str = "",
        action_id: str = "",
        source: str = "ui",
        authoritative: bool = False,
        core_event_hash: str = "",
        object_ids: Iterable[str] = (),
        payload: Mapping[str, Any] | None = None,
        timestamp: str = "",
    ) -> AgentEvent:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        return AgentEvent(
            event_id=str(uuid.uuid4()),
            sequence=sequence,
            event_type=event_type,
            timestamp=timestamp or utc_now(),
            session_id=session_id,
            task_id=task_id,
            action_id=action_id,
            source=source,
            authoritative=authoritative,
            core_event_hash=core_event_hash,
            object_ids=tuple(dict.fromkeys(str(item) for item in object_ids if item)),
            payload=dict(payload or {}),
        )

    def publish(self, event: AgentEvent) -> None:
        self._queue.put(event)

    def emit(self, event_type: AgentEventType, **kwargs: Any) -> AgentEvent:
        event = self.make_event(event_type, **kwargs)
        self.publish(event)
        return event

    def drain(self, limit: int = 500) -> tuple[list[AgentEvent], list[Exception]]:
        delivered: list[AgentEvent] = []
        failures: list[Exception] = []
        for _ in range(max(0, limit)):
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            with self._lock:
                subscriptions = list(self._subscriptions.values())
            for expected_type, handler in subscriptions:
                if expected_type is not None and expected_type != event.event_type:
                    continue
                try:
                    handler(event)
                except Exception as exc:
                    failures.append(exc)
            delivered.append(event)
        return delivered, failures
