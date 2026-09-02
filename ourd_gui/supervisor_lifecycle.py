from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ourd.persistence import atomic_write_text


APP_LIFECYCLE_SCHEMA_VERSION = 1
SUPERVISOR_SESSION_ENV = "OURD_SUPERVISOR_SESSION_ID"
SUPERVISOR_REPOSITORY_ENV = "OURD_SUPERVISOR_REPOSITORY_ROOT"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AppLifecycleRecorder:
    def __init__(
        self,
        repository_root: Path,
        *,
        supervisor_session_id: str = "",
    ) -> None:
        self.repository_root = repository_root.expanduser().resolve()
        self.supervisor_session_id = supervisor_session_id.strip()
        self.root = self.repository_root / ".ourd-agent" / "supervisor"
        self.events_path = self.root / "app-events.jsonl"
        self.current_path = self.root / "app-current.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.gui_session_id = ""

    @classmethod
    def from_environment(cls, repository_root: Path) -> "AppLifecycleRecorder":
        configured_root = os.getenv(SUPERVISOR_REPOSITORY_ENV, "").strip()
        resolved_root = Path(configured_root) if configured_root else repository_root
        return cls(
            resolved_root,
            supervisor_session_id=os.getenv(SUPERVISOR_SESSION_ENV, ""),
        )

    def event(
        self,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        state: str | None = None,
        durable: bool = True,
    ) -> None:
        timestamp = utc_now()
        record = {
            "schema_version": APP_LIFECYCLE_SCHEMA_VERSION,
            "timestamp": timestamp,
            "supervisor_session_id": self.supervisor_session_id,
            "gui_session_id": self.gui_session_id,
            "pid": os.getpid(),
            "event_type": event_type,
            "payload": dict(payload or {}),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            if durable:
                os.fsync(handle.fileno())
        current = {
            "schema_version": APP_LIFECYCLE_SCHEMA_VERSION,
            "updated_at": timestamp,
            "heartbeat_at": timestamp,
            "supervisor_session_id": self.supervisor_session_id,
            "gui_session_id": self.gui_session_id,
            "pid": os.getpid(),
            "state": state or event_type,
            "last_event_type": event_type,
            "events_path": str(self.events_path),
        }
        atomic_write_text(
            self.current_path,
            json.dumps(current, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            durable=durable,
        )

    def startup_begin(self) -> None:
        self.event(
            "STARTUP_BEGIN",
            {"repository_root": str(self.repository_root)},
            state="STARTING",
        )

    def startup_ready(
        self,
        *,
        gui_session_id: str,
        source_snapshot: str,
        event_head: str,
    ) -> None:
        self.gui_session_id = gui_session_id
        self.event(
            "STARTUP_READY",
            {
                "source_snapshot": source_snapshot,
                "event_head": event_head,
            },
            state="READY",
        )

    def heartbeat(self, *, chat_status: str, pending_operations: int) -> None:
        self.event(
            "HEARTBEAT",
            {
                "chat_status": chat_status,
                "pending_operations": int(pending_operations),
            },
            state="READY",
            durable=False,
        )

    def shutdown_requested(self, *, chat_status: str) -> None:
        self.event(
            "SHUTDOWN_REQUESTED",
            {"chat_status": chat_status},
            state="STOPPING",
        )

    def checkpoint(self, *, state_digest: str, event_head: str) -> None:
        self.event(
            "CHECKPOINT_SAVED",
            {"state_digest": state_digest, "event_head": event_head},
            state="STOPPING",
        )

    def shutdown_complete(self) -> None:
        self.event("SHUTDOWN_COMPLETE", state="STOPPED")

    def failure(self, event_type: str, exc: BaseException) -> None:
        self.event(
            event_type,
            {"error_type": type(exc).__name__, "message": str(exc)},
            state="FAILED",
        )


__all__ = [
    "APP_LIFECYCLE_SCHEMA_VERSION",
    "SUPERVISOR_REPOSITORY_ENV",
    "SUPERVISOR_SESSION_ENV",
    "AppLifecycleRecorder",
    "utc_now",
]
