from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from ..persistence import atomic_write_text
from .algebra.brain_feed import (
    BRAIN_FEED_SCHEMA_VERSION,
    BRAIN_FEED_VERSION,
    BrainFeedBatchReceipt,
    BrainFeedDisposition,
    BrainFeedItem,
)
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, utc_now


BRAIN_FEED_STORE_VERSION = "saa-batch-brain-feed-store-v1"


def _ref(kind: str, signature: str) -> str:
    return f"{kind}:sha256:{signature}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read existing brain-feed object {path}: {exc}") from exc
        comparable_existing = dict(existing)
        comparable_new = dict(envelope)
        comparable_new["created_at"] = comparable_existing.get("created_at", comparable_new.get("created_at", ""))
        if canonical_json(comparable_existing) != canonical_json(comparable_new):
            raise EGCFError(f"immutable brain-feed collision at {path}")
        return str(existing.get("created_at", ""))
    atomic_write_text(path, json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return str(envelope.get("created_at", ""))


class BrainFeedStore:
    """Immutable raw/staged/quarantine ledger for SAA batch brain feeding."""

    def __init__(self, egcf_store: Any):
        required = ("state_root", "projection_path", "events")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("BrainFeedStore requires EGCFStore")
        self.egcf_store = egcf_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "brain-feed"
        self.item_root = self.root / "items" / "sha256"
        self.disposition_root = self.root / "dispositions" / "sha256"
        self.batch_root = self.root / "batches" / "sha256"
        for path in (self.item_root, self.disposition_root, self.batch_root):
            path.mkdir(parents=True, exist_ok=True)
        self.projection_path = Path(egcf_store.projection_path)
        self._ensure_projection()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.projection_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _path(self, root: Path, object_ref: str, expected_kind: str) -> Path:
        kind, digest = parse_typed_id(object_ref)
        if kind != expected_kind:
            raise EGCFError(f"brain-feed store expected {expected_kind} reference")
        return root / digest[:2] / f"{digest}.json"

    def _ensure_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS brain_feed_items (
                    item_ref TEXT PRIMARY KEY,
                    item_signature TEXT NOT NULL UNIQUE,
                    content_signature TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS brain_feed_content_idx ON brain_feed_items(content_signature);
                CREATE INDEX IF NOT EXISTS brain_feed_kind_idx ON brain_feed_items(kind);

                CREATE TABLE IF NOT EXISTS brain_feed_dispositions (
                    disposition_ref TEXT PRIMARY KEY,
                    disposition_signature TEXT NOT NULL UNIQUE,
                    item_signature TEXT NOT NULL UNIQUE,
                    content_signature TEXT NOT NULL,
                    status TEXT NOT NULL,
                    route TEXT NOT NULL,
                    target_refs_json TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS brain_feed_disposition_status_idx ON brain_feed_dispositions(status);
                CREATE INDEX IF NOT EXISTS brain_feed_disposition_content_idx ON brain_feed_dispositions(content_signature);

                CREATE TABLE IF NOT EXISTS brain_feed_batches (
                    batch_ref TEXT PRIMARY KEY,
                    batch_signature TEXT NOT NULL UNIQUE,
                    batch_id TEXT NOT NULL,
                    source_signature TEXT NOT NULL,
                    status TEXT NOT NULL,
                    item_count INTEGER NOT NULL,
                    admitted_count INTEGER NOT NULL,
                    staged_count INTEGER NOT NULL,
                    quarantined_count INTEGER NOT NULL,
                    duplicate_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS brain_feed_batch_id_idx ON brain_feed_batches(batch_id);

                CREATE TABLE IF NOT EXISTS brain_feed_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM brain_feed_metadata WHERE key='schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(BRAIN_FEED_SCHEMA_VERSION):
            self.rebuild_projection()

    def _event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        try:
            event = self.egcf_store.events.append(event_type, dict(payload))
            if hasattr(self.egcf_store, "_index_event"):
                self.egcf_store._index_event(event)
        except Exception:
            pass

    def register_item(self, item: BrainFeedItem) -> str:
        if not isinstance(item, BrainFeedItem):
            raise EGCFError("brain-feed item registration requires BrainFeedItem")
        item_ref = _ref("brain-feed-item", item.item_signature)
        envelope = {
            "schema_version": BRAIN_FEED_SCHEMA_VERSION,
            "feed_version": BRAIN_FEED_VERSION,
            "store_version": BRAIN_FEED_STORE_VERSION,
            "object_id": item_ref,
            "created_at": utc_now(),
            "payload": item.to_dict(),
        }
        path = self._path(self.item_root, item_ref, "brain-feed-item")
        created_at = _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO brain_feed_items VALUES(?,?,?,?,?,?,?,?)",
                (
                    item_ref,
                    item.item_signature,
                    item.content_signature,
                    item.item_id,
                    item.kind,
                    canonical_json(item.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO brain_feed_metadata(key,value) VALUES('schema_version',?)",
                (str(BRAIN_FEED_SCHEMA_VERSION),),
            )
        return item_ref

    def register_disposition(self, disposition: BrainFeedDisposition) -> str:
        if not isinstance(disposition, BrainFeedDisposition):
            raise EGCFError("brain-feed disposition registration requires BrainFeedDisposition")
        disposition_ref = _ref("brain-feed-disposition", disposition.disposition_signature)
        envelope = {
            "schema_version": BRAIN_FEED_SCHEMA_VERSION,
            "feed_version": BRAIN_FEED_VERSION,
            "store_version": BRAIN_FEED_STORE_VERSION,
            "object_id": disposition_ref,
            "created_at": utc_now(),
            "payload": disposition.to_dict(),
        }
        path = self._path(self.disposition_root, disposition_ref, "brain-feed-disposition")
        created_at = _immutable_write(path, envelope)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT disposition_signature FROM brain_feed_dispositions WHERE item_signature=?",
                (disposition.item_signature,),
            ).fetchone()
            if existing is not None and existing[0] != disposition.disposition_signature:
                raise EGCFError("one brain-feed item cannot have conflicting immutable dispositions")
            connection.execute(
                "INSERT OR IGNORE INTO brain_feed_dispositions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    disposition_ref,
                    disposition.disposition_signature,
                    disposition.item_signature,
                    disposition.content_signature,
                    disposition.status,
                    disposition.route,
                    canonical_json(list(disposition.target_refs)),
                    canonical_json(list(disposition.reasons)),
                    canonical_json(disposition.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        return disposition_ref

    def register_batch(self, receipt: BrainFeedBatchReceipt) -> str:
        if not isinstance(receipt, BrainFeedBatchReceipt):
            raise EGCFError("brain-feed batch registration requires BrainFeedBatchReceipt")
        batch_ref = _ref("brain-feed-batch", receipt.batch_signature)
        envelope = {
            "schema_version": BRAIN_FEED_SCHEMA_VERSION,
            "feed_version": BRAIN_FEED_VERSION,
            "store_version": BRAIN_FEED_STORE_VERSION,
            "object_id": batch_ref,
            "created_at": utc_now(),
            "payload": receipt.to_dict(),
        }
        path = self._path(self.batch_root, batch_ref, "brain-feed-batch")
        created_at = _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO brain_feed_batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    batch_ref,
                    receipt.batch_signature,
                    receipt.batch_id,
                    receipt.source_signature,
                    receipt.status,
                    receipt.item_count,
                    receipt.admitted_count,
                    receipt.staged_count,
                    receipt.quarantined_count,
                    receipt.duplicate_count,
                    canonical_json(receipt.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        self._event(
            "saa_brain_feed_batch_recorded",
            {
                "batch_ref": batch_ref,
                "batch_id": receipt.batch_id,
                "status": receipt.status,
                "items": receipt.item_count,
                "quarantined": receipt.quarantined_count,
            },
        )
        return batch_ref

    def disposition_for_item_signature(self, item_signature: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT disposition_ref,payload_json FROM brain_feed_dispositions WHERE item_signature=?",
                (str(item_signature),),
            ).fetchone()
        if row is None:
            return None
        return {"disposition_ref": row[0], "payload": json.loads(row[1])}

    def disposition_for_content_signature(self, content_signature: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT disposition_ref,payload_json FROM brain_feed_dispositions WHERE content_signature=? ORDER BY created_at LIMIT 1",
                (str(content_signature),),
            ).fetchone()
        if row is None:
            return None
        return {"disposition_ref": row[0], "payload": json.loads(row[1])}

    def dispositions(self, *, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT disposition_ref,payload_json,created_at FROM brain_feed_dispositions"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            params = (str(status).strip().upper(),)
        query += " ORDER BY created_at, disposition_ref"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {"disposition_ref": row[0], "payload": json.loads(row[1]), "created_at": row[2]}
            for row in rows
        ]

    def quarantined(self) -> list[dict[str, Any]]:
        return self.dispositions(status="QUARANTINED")

    def batches(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT batch_ref,payload_json,created_at FROM brain_feed_batches ORDER BY created_at,batch_ref"
            ).fetchall()
        return [
            {"batch_ref": row[0], "payload": json.loads(row[1]), "created_at": row[2]}
            for row in rows
        ]

    def rebuild_projection(self) -> None:
        self._ensure_tables_without_rebuild()
        with self._connect() as connection:
            connection.executescript(
                """
                DELETE FROM brain_feed_items;
                DELETE FROM brain_feed_dispositions;
                DELETE FROM brain_feed_batches;
                DELETE FROM brain_feed_metadata;
                """
            )
            for path in sorted(self.item_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); payload = env["payload"]
                connection.execute(
                    "INSERT INTO brain_feed_items VALUES(?,?,?,?,?,?,?,?)",
                    (
                        env["object_id"], payload["item_signature"], payload["content_signature"],
                        payload["item_id"], payload["kind"], canonical_json(payload),
                        str(path.relative_to(self.state_root)), env["created_at"],
                    ),
                )
            for path in sorted(self.disposition_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); payload = env["payload"]
                connection.execute(
                    "INSERT INTO brain_feed_dispositions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        env["object_id"], payload["disposition_signature"], payload["item_signature"],
                        payload["content_signature"], payload["status"], payload["route"],
                        canonical_json(payload.get("target_refs", [])), canonical_json(payload.get("reasons", [])),
                        canonical_json(payload), str(path.relative_to(self.state_root)), env["created_at"],
                    ),
                )
            for path in sorted(self.batch_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); payload = env["payload"]
                connection.execute(
                    "INSERT INTO brain_feed_batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        env["object_id"], payload["batch_signature"], payload["batch_id"],
                        payload["source_signature"], payload["status"], payload["item_count"],
                        payload["admitted_count"], payload["staged_count"], payload["quarantined_count"],
                        payload["duplicate_count"], canonical_json(payload),
                        str(path.relative_to(self.state_root)), env["created_at"],
                    ),
                )
            connection.execute(
                "INSERT OR REPLACE INTO brain_feed_metadata(key,value) VALUES('schema_version',?)",
                (str(BRAIN_FEED_SCHEMA_VERSION),),
            )

    def _ensure_tables_without_rebuild(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS brain_feed_items (
                    item_ref TEXT PRIMARY KEY,item_signature TEXT NOT NULL UNIQUE,content_signature TEXT NOT NULL,
                    item_id TEXT NOT NULL,kind TEXT NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS brain_feed_dispositions (
                    disposition_ref TEXT PRIMARY KEY,disposition_signature TEXT NOT NULL UNIQUE,item_signature TEXT NOT NULL UNIQUE,
                    content_signature TEXT NOT NULL,status TEXT NOT NULL,route TEXT NOT NULL,target_refs_json TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS brain_feed_batches (
                    batch_ref TEXT PRIMARY KEY,batch_signature TEXT NOT NULL UNIQUE,batch_id TEXT NOT NULL,source_signature TEXT NOT NULL,
                    status TEXT NOT NULL,item_count INTEGER NOT NULL,admitted_count INTEGER NOT NULL,staged_count INTEGER NOT NULL,
                    quarantined_count INTEGER NOT NULL,duplicate_count INTEGER NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS brain_feed_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                """
            )
