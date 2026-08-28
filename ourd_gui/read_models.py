from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping

from ourd.egcf.ids import canonical_json, parse_typed_id, typed_id
from ourd.egcf.models import ArtifactRecord, RecordMixin
from ourd.egcf.schemas import construct_record, validate_record_payload
from ourd.workspace import Workspace

from .persistence import CoreEventTailer


@dataclass(frozen=True)
class ObjectDiagnostic:
    code: str
    message: str
    object_id: str = ""
    blocking: bool = False


class ReadOnlyEGCFRepository:
    """Read canonical EGCF objects without acquiring the writer lock."""

    def __init__(
        self,
        repository_root: Path,
        *,
        max_cache_records: int = 2_048,
        max_cache_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.workspace = Workspace(self.repository_root)
        self.state_root = self.repository_root / ".ourd-agent" / "egcf"
        self.object_root = self.state_root / "objects" / "sha256"
        self.projection_path = self.state_root / "projection.sqlite3"
        self.max_cache_records = max(1, int(max_cache_records))
        self.max_cache_bytes = max(1, int(max_cache_bytes))
        self._cache: OrderedDict[str, tuple[RecordMixin, int]] = OrderedDict()
        self._cache_bytes = 0

    def source_snapshot(self) -> str:
        return self.workspace.snapshot_hash()

    def event_head(self) -> str:
        tailer = CoreEventTailer(self.repository_root)
        tailer.reset_to_end()
        return tailer.head

    def object_path(self, object_id: str) -> Path:
        _, digest = parse_typed_id(object_id)
        return self.object_root / digest[:2] / f"{digest}.json"

    def get_envelope(self, object_id: str) -> Dict[str, Any]:
        path = self.object_path(object_id)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope.get("object_id") != object_id:
            raise ValueError(f"object identity mismatch: {object_id}")
        object_type = str(envelope.get("object_type", ""))
        payload = envelope.get("payload")
        validate_record_payload(object_type, payload)
        if typed_id(object_type, payload) != object_id:
            raise ValueError(f"object content hash mismatch: {object_id}")
        return envelope

    def get(self, object_id: str) -> RecordMixin:
        cached = self._cache.get(object_id)
        if cached is not None:
            self._cache.move_to_end(object_id)
            return cached[0]
        envelope = self.get_envelope(object_id)
        record = construct_record(envelope["object_type"], envelope["payload"])
        size = len(canonical_json(envelope).encode("utf-8"))
        self._cache[object_id] = (record, size)
        self._cache_bytes += size
        while (
            len(self._cache) > self.max_cache_records
            or self._cache_bytes > self.max_cache_bytes
        ):
            _, (_, evicted_size) = self._cache.popitem(last=False)
            self._cache_bytes -= evicted_size
        return record

    def cache_stats(self) -> Mapping[str, int]:
        return {
            "records": len(self._cache),
            "bytes": self._cache_bytes,
            "max_records": self.max_cache_records,
            "max_bytes": self.max_cache_bytes,
        }

    def _projected_rows(
        self,
        object_type: str | None = None,
        *,
        active_only: bool = False,
    ) -> Iterator[tuple[str, str]]:
        if not self.projection_path.exists():
            return iter(())
        uri = f"file:{self.projection_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            if object_type:
                query = "SELECT object_id, object_type FROM objects WHERE object_type = ?"
                if active_only:
                    query += " AND object_id NOT IN (SELECT old_id FROM supersedence)"
                rows = connection.execute(query + " ORDER BY object_id", (object_type,)).fetchall()
            else:
                query = "SELECT object_id, object_type FROM objects"
                if active_only:
                    query += " WHERE object_id NOT IN (SELECT old_id FROM supersedence)"
                rows = connection.execute(query + " ORDER BY object_type, object_id").fetchall()
            return iter((str(row[0]), str(row[1])) for row in rows)
        finally:
            connection.close()

    def _scanned_rows(self, object_type: str | None = None) -> Iterator[tuple[str, str]]:
        if not self.object_root.exists():
            return iter(())
        rows: list[tuple[str, str]] = []
        for path in sorted(self.object_root.glob("*/*.json")):
            envelope = json.loads(path.read_text(encoding="utf-8"))
            observed_type = str(envelope.get("object_type", ""))
            if object_type and observed_type != object_type:
                continue
            rows.append((str(envelope.get("object_id", "")), observed_type))
        return iter(rows)

    def list(
        self,
        object_type: str | None = None,
        *,
        active_only: bool = False,
    ) -> list[RecordMixin]:
        try:
            rows = list(self._projected_rows(object_type, active_only=active_only))
        except sqlite3.DatabaseError:
            rows = []
        if not rows:
            rows = list(self._scanned_rows(object_type))
            if active_only:
                superseded_ids = {
                    str(getattr(record, "old_id", ""))
                    for record in self.list("supersedence")
                }
                rows = [row for row in rows if row[0] not in superseded_ids]
        return [self.get(object_id) for object_id, _ in rows]

    def find(
        self,
        object_type: str,
        predicate: Any | None = None,
    ) -> list[RecordMixin]:
        records = self.list(object_type)
        return [record for record in records if predicate is None or predicate(record)]

    def artifact_content_path(self, artifact: ArtifactRecord) -> Path:
        path = (self.state_root / artifact.path).resolve(strict=False)
        try:
            path.relative_to(self.state_root)
        except ValueError as exc:
            raise ValueError("artifact path escapes EGCF state root") from exc
        return path

    def object_counts(self) -> Mapping[str, int]:
        counts: Dict[str, int] = {}
        for record in self.list():
            counts[record.object_type] = counts.get(record.object_type, 0) + 1
        return counts
