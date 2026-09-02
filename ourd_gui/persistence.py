from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable

from ourd.egcf.ids import canonical_json, sha256_bytes
from ourd.persistence import EventStore, atomic_write_text, sha256_text

from .events import AgentEvent
from .state import (
    GUI_READ_MODEL_SCHEMA_VERSION,
    GuiChatMessage,
    GuiSession,
    GuiState,
    GuiTask,
    reduce_event,
)
from .visual_text import DEFAULT_VISUAL_TEXT_THEME


@dataclass(frozen=True)
class GuiPreferences:
    schema_version: int = 4
    window_geometry: str = "1280x800"
    selected_tab: str = "selection"
    selected_left_tab: int = 0
    selected_center_tab: int = 0
    selected_right_tab: int = 0
    pane_positions: tuple[int, ...] = ()
    open_file: str = ""
    filter_values: tuple[tuple[str, str], ...] = ()
    recent_repositories: tuple[str, ...] = ()
    show_internal_state: bool = False
    font_scale: float = 1.0
    reduced_motion: bool = False
    chat_visual_formatting: bool = True
    chat_visual_theme: str = DEFAULT_VISUAL_TEXT_THEME
    formal_window_geometry: str = "1500x920"
    formal_selected_control_tab: int = 0
    formal_selected_result_id: str = ""
    formal_font_scale: float = 1.0


class GuiPreferencesStore:
    def __init__(self, repository_root: Path) -> None:
        self.path = repository_root.resolve() / ".ourd-agent" / "gui" / "preferences.json"

    def load(self) -> GuiPreferences:
        if not self.path.exists():
            return GuiPreferences()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return GuiPreferences(
                schema_version=max(4, int(payload.get("schema_version", 1))),
                window_geometry=str(payload.get("window_geometry", "1280x800")),
                selected_tab=str(payload.get("selected_tab", "selection")),
                selected_left_tab=int(payload.get("selected_left_tab", 0)),
                selected_center_tab=int(payload.get("selected_center_tab", 0)),
                selected_right_tab=int(payload.get("selected_right_tab", 0)),
                pane_positions=tuple(int(item) for item in payload.get("pane_positions", [])),
                open_file=str(payload.get("open_file", "")),
                filter_values=tuple(
                    (str(item[0]), str(item[1]))
                    for item in payload.get("filter_values", [])
                    if isinstance(item, list) and len(item) == 2
                ),
                recent_repositories=tuple(
                    str(item) for item in payload.get("recent_repositories", [])
                ),
                show_internal_state=bool(payload.get("show_internal_state", False)),
                font_scale=float(payload.get("font_scale", 1.0)),
                reduced_motion=bool(payload.get("reduced_motion", False)),
                chat_visual_formatting=bool(payload.get("chat_visual_formatting", True)),
                chat_visual_theme=str(
                    payload.get("chat_visual_theme", DEFAULT_VISUAL_TEXT_THEME)
                ),
                formal_window_geometry=str(
                    payload.get("formal_window_geometry", "1500x920")
                ),
                formal_selected_control_tab=int(
                    payload.get("formal_selected_control_tab", 0)
                ),
                formal_selected_result_id=str(
                    payload.get("formal_selected_result_id", "")
                ),
                formal_font_scale=float(payload.get("formal_font_scale", 1.0)),
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return GuiPreferences()

    def save(self, preferences: GuiPreferences) -> None:
        payload = asdict(preferences)
        payload["recent_repositories"] = list(preferences.recent_repositories)
        payload["pane_positions"] = list(preferences.pane_positions)
        payload["filter_values"] = [list(item) for item in preferences.filter_values]
        atomic_write_text(
            self.path,
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )


class GuiExportStore:
    EXTENSIONS = {"json": ".json", "markdown": ".md", "html": ".html"}

    def __init__(self, repository_root: Path) -> None:
        self.root = repository_root.resolve() / ".ourd-agent" / "gui" / "exports"

    def save_assurance(self, object_id: str, format_name: str, content: str) -> Path:
        try:
            extension = self.EXTENSIONS[format_name]
        except KeyError as exc:
            raise ValueError(f"unsupported assurance export format: {format_name}") from exc
        digest = object_id.partition(":sha256:")[2]
        if len(digest) != 64:
            raise ValueError("assurance export requires a typed content-addressed ID")
        destination = self.root / f"assurance-{digest}{extension}"
        atomic_write_text(destination, content)
        return destination

    def save_evidence(
        self,
        identifiers: Iterable[str],
        format_name: str,
        content: str,
    ) -> Path:
        if format_name not in {"json", "markdown"}:
            raise ValueError(f"unsupported evidence export format: {format_name}")
        digest = sha256_bytes(canonical_json(list(identifiers)).encode("utf-8"))
        destination = self.root / f"evidence-{digest}{self.EXTENSIONS[format_name]}"
        atomic_write_text(destination, content)
        return destination


class GuiEventJournal:
    def __init__(self, repository_root: Path) -> None:
        self.path = repository_root.resolve() / ".ourd-agent" / "gui" / "events.jsonl"

    def append(self, event: AgentEvent) -> str:
        store = EventStore(self.path)
        envelope = store.append("gui_agent_event", event.to_dict())
        return str(envelope["event_hash"])

    def events(self) -> list[AgentEvent]:
        store = EventStore(self.path)
        events: list[AgentEvent] = []
        for envelope in store.events():
            if envelope.get("event_type") != "gui_agent_event":
                continue
            events.append(AgentEvent.from_dict(envelope.get("payload", {})))
        return events


class GuiProjectionStore:
    def __init__(self, repository_root: Path) -> None:
        self.path = repository_root.resolve() / ".ourd-agent" / "gui" / "projection.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _ensure(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    """
                )

    @staticmethod
    def _state_payload(state: GuiState) -> Dict[str, Any]:
        payload = asdict(state)
        payload["sessions"] = {
            key: asdict(value) for key, value in state.sessions.items()
        }
        payload["tasks"] = {key: asdict(value) for key, value in state.tasks.items()}
        return payload

    @staticmethod
    def _construct_state(payload: Dict[str, Any]) -> GuiState:
        sessions = {
            key: GuiSession(
                **{
                    **value,
                    "task_ids": tuple(value.get("task_ids", [])),
                }
            )
            for key, value in dict(payload.get("sessions", {})).items()
        }
        task_tuple_fields = {
            "intent_ids",
            "invocation_ids",
            "selection_ids",
            "compiled_workflow_ids",
            "execution_plan_ids",
            "execution_ids",
            "evidence_ids",
            "failure_ids",
            "artifact_ids",
            "assurance_case_ids",
            "approval_ids",
        }
        tasks: Dict[str, GuiTask] = {}
        for key, value in dict(payload.get("tasks", {})).items():
            normalized = dict(value)
            for field_name in task_tuple_fields:
                normalized[field_name] = tuple(normalized.get(field_name, []))
            tasks[key] = GuiTask(**normalized)
        chat_messages = tuple(
            GuiChatMessage(**dict(value))
            for value in payload.get("chat_messages", [])
            if isinstance(value, dict)
        )
        return GuiState(
            schema_version=int(
                payload.get("schema_version", GUI_READ_MODEL_SCHEMA_VERSION)
            ),
            repository_root=str(payload.get("repository_root", "")),
            source_snapshot=str(payload.get("source_snapshot", "")),
            event_head=str(payload.get("event_head", "")),
            sessions=sessions,
            tasks=tasks,
            selected_session_id=str(payload.get("selected_session_id", "")),
            selected_task_id=str(payload.get("selected_task_id", "")),
            selected_object_id=str(payload.get("selected_object_id", "")),
            navigation_back=tuple(payload.get("navigation_back", [])),
            navigation_forward=tuple(payload.get("navigation_forward", [])),
            worker_status=str(payload.get("worker_status", "idle")),
            last_error=str(payload.get("last_error", "")),
            replay_cursor=int(payload.get("replay_cursor", -1)),
            chat_messages=chat_messages,
            chat_status=str(payload.get("chat_status", "idle")),
            active_chat_turn_id=str(payload.get("active_chat_turn_id", "")),
            chat_context_start=int(payload.get("chat_context_start", 0)),
        )

    def save(self, state: GuiState, *, event_count: int) -> None:
        payload = self._state_payload(state)
        serialized = canonical_json(payload)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("DELETE FROM sessions")
                connection.execute("DELETE FROM tasks")
                connection.executemany(
                    "INSERT INTO sessions(session_id, payload_json) VALUES (?, ?)",
                    [
                        (session_id, canonical_json(asdict(session)))
                        for session_id, session in state.sessions.items()
                    ],
                )
                connection.executemany(
                    "INSERT INTO tasks(task_id, session_id, status, payload_json) VALUES (?, ?, ?, ?)",
                    [
                        (task_id, task.session_id, task.status, canonical_json(asdict(task)))
                        for task_id, task in state.tasks.items()
                    ],
                )
                connection.executemany(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                    [
                        ("schema_version", str(GUI_READ_MODEL_SCHEMA_VERSION)),
                        ("event_count", str(event_count)),
                        ("state_digest", state.digest),
                        ("state_json", serialized),
                    ],
                )

    def load(self, *, expected_event_count: int | None = None) -> GuiState | None:
        try:
            with closing(self._connect()) as connection:
                rows = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
        except sqlite3.DatabaseError:
            return None
        if (
            rows.get("schema_version") != str(GUI_READ_MODEL_SCHEMA_VERSION)
            or "state_json" not in rows
        ):
            return None
        if expected_event_count is not None and int(rows.get("event_count", "-1")) != expected_event_count:
            return None
        try:
            state = self._construct_state(json.loads(rows["state_json"]))
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None
        if rows.get("state_digest") != state.digest:
            return None
        return state

    def rebuild(self, events: Iterable[AgentEvent]) -> GuiState:
        event_list = list(events)
        state = GuiState()
        for event in event_list:
            state = reduce_event(state, event)
        self.save(state, event_count=len(event_list))
        return state


def read_complete_json_lines(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        content = content.rsplit(b"\n", 1)[0] + (b"\n" if b"\n" in content else b"")
    parsed: list[Dict[str, Any]] = []
    for line_number, raw in enumerate(content.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid complete event JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"event at {path}:{line_number} is not an object")
        parsed.append(value)
    return parsed


def validate_event_chain(events: Iterable[Dict[str, Any]]) -> str:
    previous = ""
    for event in events:
        payload_hash = sha256_text(canonical_json(event.get("payload")))
        if payload_hash != event.get("payload_hash"):
            raise ValueError(f"event payload hash mismatch: {event.get('event_id')}")
        material = {
            "event_id": event.get("event_id"),
            "timestamp": event.get("timestamp"),
            "previous_hash": event.get("previous_hash"),
            "event_type": event.get("event_type"),
            "payload_hash": payload_hash,
        }
        if any(key in event for key in ("run_id", "action_id", "transaction_id")):
            material.update(
                {
                    "run_id": event.get("run_id", ""),
                    "action_id": event.get("action_id", ""),
                    "transaction_id": event.get("transaction_id", ""),
                }
            )
        expected = sha256_text(canonical_json(material))
        if event.get("previous_hash") != previous:
            raise ValueError(f"event previous hash mismatch: {event.get('event_id')}")
        if event.get("event_hash") != expected:
            raise ValueError(f"event hash mismatch: {event.get('event_id')}")
        previous = expected
    return previous


class CoreEventTailer:
    def __init__(self, repository_root: Path) -> None:
        self.path = repository_root.resolve() / ".ourd-agent" / "egcf" / "events.jsonl"
        self.cursor = 0
        self.head = ""

    def poll(self) -> list[Dict[str, Any]]:
        events = read_complete_json_lines(self.path)
        head = validate_event_chain(events)
        if self.cursor > len(events):
            self.cursor = 0
        new_events = events[self.cursor :]
        self.cursor = len(events)
        self.head = head
        return new_events

    def reset_to_end(self) -> None:
        events = read_complete_json_lines(self.path)
        self.head = validate_event_chain(events)
        self.cursor = len(events)


def stable_payload_digest(payload: Any) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))
