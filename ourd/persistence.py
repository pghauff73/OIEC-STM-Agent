from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .errors import StateError
from .models import RuntimeState


RUNTIME_SCHEMA_VERSION = 3


SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|token|secret|password|authorization)", re.I)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization))"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def migrate_v1_to_v2(payload: Dict[str, Any]) -> Dict[str, Any]:
    migrated = deepcopy(payload)
    if int(migrated.get("schema_version", 1)) != 1:
        raise StateError("runtime migration requires schema version 1")
    migrated["schema_version"] = 2
    migrated.setdefault("boundary_state", None)
    migrated.setdefault("dimension_budget", None)
    migrated.setdefault("finite_evidence", None)
    migrated.setdefault("last_progress", None)
    migrated.setdefault("transition_index", 0)
    action = migrated.get("pending_action")
    if isinstance(action, dict):
        action.setdefault("varied_dimensions", [])
    for artifact in migrated.get("evidence_registry", {}).values():
        if not isinstance(artifact, dict):
            continue
        artifact.setdefault("requirement_ids", [])
        artifact.setdefault("quality_bp", 10_000)
        artifact.setdefault("polarity", "support")
    for collision in migrated.get("collisions", []):
        if not isinstance(collision, dict):
            continue
        collision.setdefault("severity_bp", 0)
        collision.setdefault("attempt_key", "")
        collision.setdefault("boundary_signature", "")
        collision.setdefault("dimension_signature", "")
    return migrated


def migrate_v2_to_v3(payload: Dict[str, Any]) -> Dict[str, Any]:
    migrated = deepcopy(payload)
    if int(migrated.get("schema_version", 2)) != 2:
        raise StateError("runtime migration requires schema version 2")
    migrated["schema_version"] = 3
    migrated.setdefault("hypothesis_state", None)
    migrated.setdefault("control_only_progress_streak", 0)
    progress = migrated.get("last_progress")
    if isinstance(progress, dict):
        progress.setdefault("hypothesis_resolution_bp", 0)
    return migrated


def redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): "<redacted>" if SENSITIVE_KEY.search(str(key)) else redact(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact(value) for value in payload]
    if isinstance(payload, tuple):
        return [redact(value) for value in payload]
    if isinstance(payload, str):
        value = SENSITIVE_ASSIGNMENT.sub(r"\1\2<redacted>", payload)
        value = BEARER_TOKEN.sub("Bearer <redacted>", value)
        for configured in os.getenv("OURD_SECRET_PATTERNS", "").split(","):
            configured = configured.strip()
            if not configured:
                continue
            try:
                value = re.sub(configured, "<redacted>", value)
            except re.error:
                value = value.replace(configured, "<redacted>")
        for key, secret in os.environ.items():
            if secret and SENSITIVE_KEY.search(key) and len(secret) >= 6:
                value = value.replace(secret, "<redacted>")
        return value
    return payload


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class WorkspaceLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: Optional[Any] = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise StateError("another OURD agent process owns this workspace") from exc

    def close(self) -> None:
        if self.handle is None:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None


class EventStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.head = self.validate_chain()

    def events(self) -> Iterable[Dict[str, Any]]:
        if not self.path.exists():
            return []
        parsed = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    parsed.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    raise StateError(
                        f"invalid event JSON at {self.path}:{line_number}: {exc}"
                    ) from exc
        return parsed

    def validate_chain(self) -> str:
        previous = ""
        for event in self.events():
            payload_hash = sha256_text(canonical_json(event.get("payload")))
            if payload_hash != event.get("payload_hash"):
                raise StateError(f"event payload hash mismatch: {event.get('event_id')}")
            material = {
                "event_id": event.get("event_id"),
                "timestamp": event.get("timestamp"),
                "previous_hash": event.get("previous_hash"),
                "event_type": event.get("event_type"),
                "payload_hash": payload_hash,
            }
            if any(
                key in event for key in ("run_id", "action_id", "transaction_id")
            ):
                material.update(
                    {
                        "run_id": event.get("run_id", ""),
                        "action_id": event.get("action_id", ""),
                        "transaction_id": event.get("transaction_id", ""),
                    }
                )
            expected_hash = sha256_text(canonical_json(material))
            if event.get("previous_hash") != previous:
                raise StateError(f"event previous hash mismatch: {event.get('event_id')}")
            if event.get("event_hash") != expected_hash:
                raise StateError(f"event hash mismatch: {event.get('event_id')}")
            previous = expected_hash
        return previous

    def append(
        self,
        event_type: str,
        payload: Any,
        *,
        run_id: str = "",
        action_id: str = "",
        transaction_id: str = "",
    ) -> Dict[str, Any]:
        safe_payload = redact(payload)
        event_id = str(uuid.uuid4())
        timestamp = utc_now()
        payload_hash = sha256_text(canonical_json(safe_payload))
        material = {
            "event_id": event_id,
            "timestamp": timestamp,
            "previous_hash": self.head,
            "event_type": event_type,
            "payload_hash": payload_hash,
            "run_id": run_id,
            "action_id": action_id,
            "transaction_id": transaction_id,
        }
        event_hash = sha256_text(canonical_json(material))
        event = {
            **material,
            "payload": safe_payload,
            "event_hash": event_hash,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.head = event_hash
        return event

    def last_state_snapshot(self) -> Optional[Dict[str, Any]]:
        last = None
        for event in self.events():
            if event.get("event_type") == "state_snapshot":
                last = event
        return last


class StateStore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = WorkspaceLock(self.state_dir / "lock")
        self.lock.acquire()
        try:
            self.events = EventStore(self.state_dir / "events.jsonl")
        except Exception:
            self.lock.close()
            raise
        self.state_path = self.state_dir / "state.json"

    def close(self) -> None:
        self.lock.close()

    def load(self) -> RuntimeState:
        payload = None
        if self.state_path.exists():
            try:
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
        event = self.events.last_state_snapshot()
        event_payload = None
        if event is not None:
            event_payload = event.get("payload", {}).get("state")
            if isinstance(event_payload, dict):
                event_payload = dict(event_payload)
                event_payload["event_head"] = event.get("event_hash", "")
        if payload is None:
            payload = event_payload
        elif event_payload is not None and canonical_json(payload) != canonical_json(event_payload):
            payload = event_payload
        if payload is None:
            return RuntimeState(event_head=self.events.head)
        try:
            schema_version = int(payload.get("schema_version", 1))
        except (TypeError, ValueError) as exc:
            raise StateError("invalid runtime state schema version") from exc
        migrated_from = None
        if schema_version == 1:
            payload = migrate_v1_to_v2(payload)
            payload = migrate_v2_to_v3(payload)
            migrated_from = 1
        elif schema_version == 2:
            payload = migrate_v2_to_v3(payload)
            migrated_from = 2
        elif schema_version != RUNTIME_SCHEMA_VERSION:
            raise StateError(f"unsupported runtime state schema: {schema_version}")
        try:
            state = RuntimeState.from_dict(payload)
        except (TypeError, ValueError, KeyError) as exc:
            raise StateError(f"invalid runtime state: {exc}") from exc
        if state.schema_version != RUNTIME_SCHEMA_VERSION:
            raise StateError(f"unsupported runtime state schema: {state.schema_version}")
        if migrated_from is not None:
            migration_payload = state.to_dict()
            migration_payload["event_head"] = self.events.head
            event = self.events.append(
                "state_snapshot",
                {
                    "state": migration_payload,
                    "migration": {
                        "from_schema": migrated_from,
                        "to_schema": RUNTIME_SCHEMA_VERSION,
                    },
                },
            )
            state.event_head = event["event_hash"]
            migration_payload["event_head"] = state.event_head
            atomic_write_text(
                self.state_path,
                json.dumps(migration_payload, indent=2) + "\n",
            )
        state.event_head = self.events.head
        return state

    def save(
        self,
        state: RuntimeState,
        *,
        run_id: str = "",
        action_id: str = "",
        transaction_id: str = "",
    ) -> None:
        if state.schema_version != RUNTIME_SCHEMA_VERSION:
            raise StateError(f"unsupported runtime state schema: {state.schema_version}")
        payload = state.to_dict()
        payload["event_head"] = self.events.head
        event = self.events.append(
            "state_snapshot",
            {"state": payload},
            run_id=run_id,
            action_id=action_id,
            transaction_id=transaction_id,
        )
        state.event_head = event["event_hash"]
        payload["event_head"] = state.event_head
        atomic_write_text(self.state_path, json.dumps(payload, indent=2) + "\n")

    def trace(
        self,
        event_type: str,
        payload: Any,
        *,
        run_id: str = "",
        action_id: str = "",
        transaction_id: str = "",
    ) -> Dict[str, Any]:
        return self.events.append(
            event_type,
            payload,
            run_id=run_id,
            action_id=action_id,
            transaction_id=transaction_id,
        )