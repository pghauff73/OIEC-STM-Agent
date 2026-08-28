from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

from ..persistence import EventStore, WorkspaceLock, atomic_write_text
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, sha256_bytes, typed_id, utc_now
from .models import ArtifactRecord, RecordMixin, SupersedenceRecord
from .schemas import construct_record, validate_record_payload


class ObjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, object_id: str) -> Path:
        _, digest = parse_typed_id(object_id)
        return self.root / digest[:2] / f"{digest}.json"

    def put(self, object_type: str, payload: Dict[str, Any]) -> str:
        validate_record_payload(object_type, payload)
        object_id = typed_id(object_type, payload)
        envelope = {
            "schema_version": 1,
            "object_type": object_type,
            "object_id": object_id,
            "payload": payload,
        }
        path = self.path_for(object_id)
        serialized = json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if canonical_json(existing) != canonical_json(envelope):
                raise EGCFError(f"immutable object collision: {object_id}")
            return object_id
        atomic_write_text(path, serialized)
        return object_id

    def get_envelope(self, object_id: str) -> Dict[str, Any]:
        path = self.path_for(object_id)
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read object {object_id}: {exc}") from exc
        if envelope.get("object_id") != object_id:
            raise EGCFError(f"object identity mismatch: {object_id}")
        object_type = str(envelope.get("object_type", ""))
        payload = envelope.get("payload")
        validate_record_payload(object_type, payload)
        if typed_id(object_type, payload) != object_id:
            raise EGCFError(f"object hash mismatch: {object_id}")
        return envelope

    def get(self, object_id: str) -> RecordMixin:
        envelope = self.get_envelope(object_id)
        return construct_record(envelope["object_type"], envelope["payload"])

    def iter_envelopes(self) -> Iterable[Dict[str, Any]]:
        for path in sorted(self.root.glob("*/*.json")):
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
                self.get_envelope(str(envelope["object_id"]))
            except (KeyError, OSError, json.JSONDecodeError, EGCFError) as exc:
                raise EGCFError(f"invalid object store entry {path}: {exc}") from exc
            yield envelope


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes) -> tuple[str, Path]:
        digest = sha256_bytes(content)
        artifact_id = f"artifact-bytes:sha256:{digest}"
        path = self.root / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise EGCFError(f"immutable artifact collision: {artifact_id}")
            return artifact_id, path
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return artifact_id, path


class EGCFStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.state_root = self.workspace_root / ".ourd-agent" / "egcf"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.lock = WorkspaceLock(self.state_root / "lock")
        self.lock.acquire()
        try:
            self.objects = ObjectStore(self.state_root / "objects" / "sha256")
            self.artifacts = ArtifactStore(self.state_root / "artifacts" / "sha256")
            root_events_path = self.workspace_root / ".ourd-agent" / "events.jsonl"
            self.parent_event_head = EventStore(root_events_path).head if root_events_path.exists() else ""
            self.events = EventStore(self.state_root / "events.jsonl")
            self.projection_path = self.state_root / "projection.sqlite3"
            self._ensure_projection()
        except Exception:
            self.lock.close()
            raise

    def close(self) -> None:
        self.lock.close()

    def __enter__(self) -> "EGCFStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.projection_path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS objects (
                    object_id TEXT PRIMARY KEY,
                    object_type TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS objects_type_idx ON objects(object_type);
                CREATE TABLE IF NOT EXISTS supersedence (
                    old_id TEXT NOT NULL,
                    new_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(old_id, new_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_type_idx ON events(event_type);
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def _index_event(self, event: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO events(event_id, timestamp, previous_hash, event_hash, "
                "event_type, payload_hash, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event["event_id"],
                    event["timestamp"],
                    event["previous_hash"],
                    event["event_hash"],
                    event["event_type"],
                    event["payload_hash"],
                    canonical_json(event["payload"]),
                ),
            )

    def register(self, record: RecordMixin, *, event_type: str = "egcf_object_registered") -> str:
        if not is_dataclass(record):
            raise EGCFError("registered object must be a typed dataclass record")
        payload = asdict(record)
        predicted_id = typed_id(record.object_type, payload)
        existed = self.objects.path_for(predicted_id).exists()
        object_id = self.objects.put(record.object_type, payload)
        _, digest = parse_typed_id(object_id)
        path = self.objects.path_for(object_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO objects(object_id, object_type, digest, payload_json, path) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    object_id,
                    record.object_type,
                    digest,
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                ),
            )
        if not existed:
            event = self.events.append(
                event_type,
                {
                    "object_id": object_id,
                    "object_type": record.object_type,
                    "parent_event_head": self.parent_event_head,
                },
            )
            self._index_event(event)
        return object_id

    def register_artifact(
        self,
        content: bytes,
        *,
        media_type: str,
        source_ids: Iterable[str] = (),
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        artifact_bytes_id, path = self.artifacts.put(content)
        _, _, digest = artifact_bytes_id.partition("artifact-bytes:sha256:")
        record = ArtifactRecord(
            media_type=media_type,
            sha256=digest,
            size=len(content),
            source_ids=list(dict.fromkeys(source_ids)),
            provenance=dict(provenance or {}),
            created_at=utc_now(),
            path=str(path.relative_to(self.state_root)),
        )
        return self.register(record, event_type="egcf_artifact_registered")

    def get(self, object_id: str) -> RecordMixin:
        return self.objects.get(object_id)

    def list(self, object_type: Optional[str] = None) -> list[Dict[str, Any]]:
        query = "SELECT object_id, object_type, digest, payload_json, path FROM objects"
        parameters: tuple[Any, ...] = ()
        if object_type:
            query += " WHERE object_type = ?"
            parameters = (object_type,)
        query += " ORDER BY object_type, object_id"
        try:
            with self._connect() as connection:
                rows = connection.execute(query, parameters).fetchall()
        except sqlite3.DatabaseError:
            self.rebuild_projection()
            with self._connect() as connection:
                rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "object_id": row[0],
                "object_type": row[1],
                "digest": row[2],
                "payload": json.loads(row[3]),
                "path": row[4],
            }
            for row in rows
        ]

    def find(self, object_type: str, predicate: Optional[Any] = None) -> list[RecordMixin]:
        records = [self.get(item["object_id"]) for item in self.list(object_type)]
        return [record for record in records if predicate is None or predicate(record)]

    def supersede(self, old_id: str, new_id: str, reason: str, authority: str) -> str:
        self.get(old_id)
        self.get(new_id)
        record = SupersedenceRecord(
            old_id=old_id,
            new_id=new_id,
            reason=reason,
            authority=authority,
            created_at=utc_now(),
        )
        record_id = self.register(record, event_type="egcf_object_superseded")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO supersedence(old_id, new_id, reason, authority, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (old_id, new_id, reason, authority, record.created_at),
            )
        return record_id

    def active_ids(self, object_type: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT object_id FROM objects WHERE object_type = ? "
                "AND object_id NOT IN (SELECT old_id FROM supersedence) ORDER BY object_id",
                (object_type,),
            ).fetchall()
        return [row[0] for row in rows]

    def rebuild_projection(self) -> None:
        if self.projection_path.exists():
            self.projection_path.unlink()
        self._ensure_projection()
        with self._connect() as connection:
            for envelope in self.objects.iter_envelopes():
                object_id = envelope["object_id"]
                _, digest = parse_typed_id(object_id)
                path = self.objects.path_for(object_id)
                connection.execute(
                    "INSERT INTO objects(object_id, object_type, digest, payload_json, path) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        object_id,
                        envelope["object_type"],
                        digest,
                        canonical_json(envelope["payload"]),
                        str(path.relative_to(self.state_root)),
                    ),
                )
                if envelope["object_type"] == "supersedence":
                    payload = envelope["payload"]
                    connection.execute(
                        "INSERT OR IGNORE INTO supersedence(old_id, new_id, reason, authority, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            payload["old_id"],
                            payload["new_id"],
                            payload["reason"],
                            payload["authority"],
                            payload["created_at"],
                        ),
                    )
            for event in self.events.events():
                connection.execute(
                    "INSERT INTO events(event_id, timestamp, previous_hash, event_hash, event_type, "
                    "payload_hash, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event["event_id"],
                        event["timestamp"],
                        event["previous_hash"],
                        event["event_hash"],
                        event["event_type"],
                        event["payload_hash"],
                        canonical_json(event["payload"]),
                    ),
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('rebuilt_at', ?)",
                (utc_now(),),
            )
