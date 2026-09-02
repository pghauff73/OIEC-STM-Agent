from __future__ import annotations

import json
import sqlite3
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..persistence import atomic_write_text
from .algebra.semantic_alignment import SemanticAlignmentAssessment
from .algebra.semantic_revision import SemanticRequalification
from .algebra.semantic_units import PhysicalDimensionVector, PhysicalUnit, SemanticConcept
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, utc_now


SEMANTIC_ONTOLOGY_VERSION = "saa-semantic-ontology-v1"
SEMANTIC_ONTOLOGY_SCHEMA_VERSION = 1


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _concept_id(signature: str) -> str:
    return f"semantic-concept:sha256:{signature}"


def _alignment_id(signature: str) -> str:
    return f"semantic-alignment:sha256:{signature}"


def _revision_id(signature: str) -> str:
    return f"semantic-requalification:sha256:{signature}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable semantic-ontology collision at {path}")
        return
    atomic_write_text(path, serialized)


def _fraction(payload: Sequence[int]) -> Fraction:
    return Fraction(int(payload[0]), int(payload[1]))


def _concept_from_payload(payload: Mapping[str, Any]) -> SemanticConcept:
    dimension_payload = payload.get("physical_dimension")
    dimension = (
        PhysicalDimensionVector(tuple(int(value) for value in dimension_payload["exponents"]))
        if dimension_payload
        else None
    )
    unit_payload = payload.get("canonical_unit")
    unit = None
    if unit_payload:
        unit_dimension = PhysicalDimensionVector(
            tuple(int(value) for value in unit_payload["dimension"]["exponents"])
        )
        unit = PhysicalUnit(
            symbol=unit_payload["symbol"],
            name=unit_payload["name"],
            dimension=unit_dimension,
            scale_to_si=_fraction(unit_payload["scale_to_si"]),
            offset_to_si=_fraction(unit_payload["offset_to_si"]),
        )
    return SemanticConcept(
        canonical_name=payload["canonical_name"],
        meaning=payload["meaning"],
        domain=payload["domain"],
        quantity_kind=payload["quantity_kind"],
        aliases=tuple(payload.get("aliases", ())),
        physical_dimension=dimension,
        canonical_unit=unit,
        evidence_ids=tuple(payload.get("evidence_ids", ())),
        semantic_status=payload["semantic_status"],
        concept_signature=payload["concept_signature"],
        canonical_eligible=bool(payload["canonical_eligible"]),
    )


class SemanticOntologyStore:
    """Persistent SAA-9 ontology for qualified concepts, revisions and alignments."""

    def __init__(self, egcf_store: Any):
        required = ("state_root", "projection_path", "events", "get")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("SemanticOntologyStore requires EGCFStore")
        self.egcf_store = egcf_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "semantic-ontology"
        self.concept_root = self.root / "concepts" / "sha256"
        self.alignment_root = self.root / "alignments" / "sha256"
        self.revision_root = self.root / "revisions" / "sha256"
        for path in (self.concept_root, self.alignment_root, self.revision_root):
            path.mkdir(parents=True, exist_ok=True)
        self.projection_path = Path(egcf_store.projection_path)
        self._ensure_projection()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.projection_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS semantic_ontology_concepts (
                    concept_id TEXT PRIMARY KEY,
                    concept_signature TEXT NOT NULL UNIQUE,
                    canonical_name TEXT NOT NULL,
                    meaning TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    quantity_kind TEXT NOT NULL,
                    dimension_signature TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS semantic_ontology_name_idx ON semantic_ontology_concepts(canonical_name);
                CREATE INDEX IF NOT EXISTS semantic_ontology_meaning_idx ON semantic_ontology_concepts(meaning);
                CREATE INDEX IF NOT EXISTS semantic_ontology_quantity_idx ON semantic_ontology_concepts(quantity_kind);

                CREATE TABLE IF NOT EXISTS semantic_ontology_alignments (
                    alignment_id TEXT PRIMARY KEY,
                    left_concept_id TEXT NOT NULL,
                    right_concept_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exact_substitution_eligible INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS semantic_ontology_alignment_left_idx ON semantic_ontology_alignments(left_concept_id);
                CREATE INDEX IF NOT EXISTS semantic_ontology_alignment_right_idx ON semantic_ontology_alignments(right_concept_id);

                CREATE TABLE IF NOT EXISTS semantic_ontology_revisions (
                    revision_id TEXT PRIMARY KEY,
                    source_concept_id TEXT NOT NULL,
                    replacement_concept_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS semantic_ontology_revision_source_idx ON semantic_ontology_revisions(source_concept_id);

                CREATE TABLE IF NOT EXISTS semantic_ontology_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM semantic_ontology_metadata WHERE key='schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(SEMANTIC_ONTOLOGY_SCHEMA_VERSION):
            self.rebuild_projection()

    def _path(self, root: Path, object_id: str, kind: str) -> Path:
        parsed_kind, digest = parse_typed_id(object_id)
        if parsed_kind != kind:
            raise EGCFError(f"semantic ontology expected {kind} ID")
        return root / digest[:2] / f"{digest}.json"

    def _event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        try:
            event = self.egcf_store.events.append(event_type, dict(payload))
            if hasattr(self.egcf_store, "_index_event"):
                self.egcf_store._index_event(event)
        except Exception:
            pass

    def admit_concept(self, concept: SemanticConcept) -> str:
        if not isinstance(concept, SemanticConcept):
            raise EGCFError("semantic ontology admission requires SemanticConcept")
        if not concept.canonical_eligible or concept.semantic_status != "SEMANTICALLY_RESOLVED":
            raise EGCFError("semantic ontology admits only evidence-grounded resolved concepts")
        if not concept.evidence_ids:
            raise EGCFError("semantic ontology concept requires evidence references")
        concept_id = _concept_id(concept.concept_signature)
        payload = concept.to_dict()
        created_at = utc_now()
        envelope = {
            "schema_version": 1,
            "ontology_version": SEMANTIC_ONTOLOGY_VERSION,
            "object_id": concept_id,
            "created_at": created_at,
            "payload": payload,
        }
        path = self._path(self.concept_root, concept_id, "semantic-concept")
        existed = path.exists()
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO semantic_ontology_concepts(concept_id,concept_signature,canonical_name,meaning,domain,quantity_kind,dimension_signature,aliases_json,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    concept_id,
                    concept.concept_signature,
                    concept.canonical_name,
                    concept.meaning,
                    concept.domain,
                    concept.quantity_kind,
                    concept.physical_dimension.signature if concept.physical_dimension else "",
                    canonical_json(list(concept.aliases)),
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO semantic_ontology_metadata(key,value) VALUES('schema_version',?)",
                (str(SEMANTIC_ONTOLOGY_SCHEMA_VERSION),),
            )
        if not existed:
            self._event("saa_semantic_concept_admitted", {"concept_id": concept_id, "concept_signature": concept.concept_signature})
        return concept_id

    def load_concept(self, concept_id: str) -> SemanticConcept:
        path = self._path(self.concept_root, concept_id, "semantic-concept")
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read semantic concept {concept_id}: {exc}") from exc
        if envelope.get("object_id") != concept_id:
            raise EGCFError("semantic concept object identity mismatch")
        concept = _concept_from_payload(envelope["payload"])
        if _concept_id(concept.concept_signature) != concept_id:
            raise EGCFError("semantic concept signature does not match object ID")
        return concept

    def concepts(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT concept_id,payload_json,created_at FROM semantic_ontology_concepts ORDER BY concept_id"
            ).fetchall()
        return [
            {"concept_id": row[0], "payload": json.loads(row[1]), "created_at": row[2]}
            for row in rows
        ]

    def resolve_text(self, text: str) -> tuple[str, ...]:
        target = _text(text)
        if not target:
            return ()
        matches: list[str] = []
        for item in self.concepts():
            payload = item["payload"]
            names = {
                payload["canonical_name"],
                payload["meaning"],
                *payload.get("aliases", ()),
            }
            if target in {_text(value) for value in names}:
                matches.append(item["concept_id"])
        return tuple(sorted(matches))

    def admit_alignment(self, assessment: SemanticAlignmentAssessment) -> str:
        if not isinstance(assessment, SemanticAlignmentAssessment):
            raise EGCFError("semantic ontology alignment admission requires SemanticAlignmentAssessment")
        if not assessment.canonical_alignment_eligible:
            raise EGCFError("unresolved semantic alignment cannot enter canonical ontology")
        left_id = _concept_id(assessment.left_concept_signature)
        right_id = _concept_id(assessment.right_concept_signature)
        self.load_concept(left_id)
        self.load_concept(right_id)
        alignment_id = _alignment_id(assessment.alignment_signature)
        payload = assessment.to_dict()
        created_at = utc_now()
        envelope = {
            "schema_version": 1,
            "ontology_version": SEMANTIC_ONTOLOGY_VERSION,
            "object_id": alignment_id,
            "created_at": created_at,
            "payload": payload,
        }
        path = self._path(self.alignment_root, alignment_id, "semantic-alignment")
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO semantic_ontology_alignments(alignment_id,left_concept_id,right_concept_id,relation,status,exact_substitution_eligible,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    alignment_id,
                    left_id,
                    right_id,
                    assessment.relation,
                    assessment.status,
                    int(assessment.exact_substitution_eligible),
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        self._event("saa_semantic_alignment_admitted", {"alignment_id": alignment_id, "left": left_id, "right": right_id, "relation": assessment.relation})
        return alignment_id

    def alignments(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT alignment_id,left_concept_id,right_concept_id,relation,status,exact_substitution_eligible,payload_json FROM semantic_ontology_alignments ORDER BY alignment_id"
            ).fetchall()
        return [
            {
                "alignment_id": row[0],
                "left_concept_id": row[1],
                "right_concept_id": row[2],
                "relation": row[3],
                "status": row[4],
                "exact_substitution_eligible": bool(row[5]),
                "payload": json.loads(row[6]),
            }
            for row in rows
        ]

    def admit_revision(self, requalification: SemanticRequalification) -> str:
        if not isinstance(requalification, SemanticRequalification):
            raise EGCFError("semantic ontology revision admission requires SemanticRequalification")
        if not requalification.canonical_replacement_eligible or requalification.replacement_concept is None:
            raise EGCFError("blocked semantic requalification cannot enter canonical ontology")
        source_id = _concept_id(requalification.source_concept_signature)
        self.load_concept(source_id)
        replacement_id = self.admit_concept(requalification.replacement_concept)
        revision_id = _revision_id(requalification.requalification_signature)
        payload = {**requalification.to_dict(), "source_concept_id": source_id, "replacement_concept_id": replacement_id}
        created_at = utc_now()
        envelope = {
            "schema_version": 1,
            "ontology_version": SEMANTIC_ONTOLOGY_VERSION,
            "object_id": revision_id,
            "created_at": created_at,
            "payload": payload,
        }
        path = self._path(self.revision_root, revision_id, "semantic-requalification")
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO semantic_ontology_revisions(revision_id,source_concept_id,replacement_concept_id,payload_json,path,created_at) VALUES(?,?,?,?,?,?)",
                (
                    revision_id,
                    source_id,
                    replacement_id,
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        self._event("saa_semantic_concept_requalified", {"revision_id": revision_id, "source": source_id, "replacement": replacement_id})
        return revision_id

    def revisions(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT revision_id,source_concept_id,replacement_concept_id,payload_json FROM semantic_ontology_revisions ORDER BY revision_id"
            ).fetchall()
        return [
            {"revision_id": row[0], "source_concept_id": row[1], "replacement_concept_id": row[2], "payload": json.loads(row[3])}
            for row in rows
        ]

    def equivalent_concept_ids(self, concept_id: str) -> tuple[str, ...]:
        self.load_concept(concept_id)
        adjacency: dict[str, set[str]] = {}
        for item in self.alignments():
            if not item["exact_substitution_eligible"]:
                continue
            left = item["left_concept_id"]
            right = item["right_concept_id"]
            adjacency.setdefault(left, set()).add(right)
            adjacency.setdefault(right, set()).add(left)
        seen = {concept_id}
        queue = [concept_id]
        while queue:
            current = queue.pop(0)
            for neighbor in sorted(adjacency.get(current, ())):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return tuple(sorted(seen))

    def meanings_equivalent(self, left: str, right: str) -> bool:
        if _text(left) == _text(right):
            return True
        left_ids = self.resolve_text(left)
        right_ids = set(self.resolve_text(right))
        for left_id in left_ids:
            if right_ids.intersection(self.equivalent_concept_ids(left_id)):
                return True
        return False

    def rebuild_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS semantic_ontology_concepts (
                    concept_id TEXT PRIMARY KEY, concept_signature TEXT NOT NULL UNIQUE,
                    canonical_name TEXT NOT NULL, meaning TEXT NOT NULL, domain TEXT NOT NULL,
                    quantity_kind TEXT NOT NULL, dimension_signature TEXT NOT NULL,
                    aliases_json TEXT NOT NULL, payload_json TEXT NOT NULL, path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS semantic_ontology_name_idx ON semantic_ontology_concepts(canonical_name);
                CREATE INDEX IF NOT EXISTS semantic_ontology_meaning_idx ON semantic_ontology_concepts(meaning);
                CREATE INDEX IF NOT EXISTS semantic_ontology_quantity_idx ON semantic_ontology_concepts(quantity_kind);
                CREATE TABLE IF NOT EXISTS semantic_ontology_alignments (
                    alignment_id TEXT PRIMARY KEY, left_concept_id TEXT NOT NULL,
                    right_concept_id TEXT NOT NULL, relation TEXT NOT NULL, status TEXT NOT NULL,
                    exact_substitution_eligible INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    path TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS semantic_ontology_alignment_left_idx ON semantic_ontology_alignments(left_concept_id);
                CREATE INDEX IF NOT EXISTS semantic_ontology_alignment_right_idx ON semantic_ontology_alignments(right_concept_id);
                CREATE TABLE IF NOT EXISTS semantic_ontology_revisions (
                    revision_id TEXT PRIMARY KEY, source_concept_id TEXT NOT NULL,
                    replacement_concept_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    path TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS semantic_ontology_revision_source_idx ON semantic_ontology_revisions(source_concept_id);
                CREATE TABLE IF NOT EXISTS semantic_ontology_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                DELETE FROM semantic_ontology_concepts;
                DELETE FROM semantic_ontology_alignments;
                DELETE FROM semantic_ontology_revisions;
                DELETE FROM semantic_ontology_metadata;
                """
            )
            for path in sorted(self.concept_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                concept = _concept_from_payload(envelope["payload"])
                concept_id = envelope["object_id"]
                if _concept_id(concept.concept_signature) != concept_id:
                    raise EGCFError(f"invalid semantic concept entry: {path}")
                connection.execute(
                    "INSERT INTO semantic_ontology_concepts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        concept_id,
                        concept.concept_signature,
                        concept.canonical_name,
                        concept.meaning,
                        concept.domain,
                        concept.quantity_kind,
                        concept.physical_dimension.signature if concept.physical_dimension else "",
                        canonical_json(list(concept.aliases)),
                        canonical_json(envelope["payload"]),
                        str(path.relative_to(self.state_root)),
                        envelope["created_at"],
                    ),
                )
            for path in sorted(self.alignment_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                left_id = _concept_id(payload["left_concept_signature"])
                right_id = _concept_id(payload["right_concept_signature"])
                connection.execute(
                    "INSERT INTO semantic_ontology_alignments VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        envelope["object_id"], left_id, right_id, payload["relation"], payload["status"],
                        int(payload["exact_substitution_eligible"]), canonical_json(payload),
                        str(path.relative_to(self.state_root)), envelope["created_at"],
                    ),
                )
            for path in sorted(self.revision_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO semantic_ontology_revisions VALUES(?,?,?,?,?,?)",
                    (
                        envelope["object_id"], payload["source_concept_id"], payload["replacement_concept_id"],
                        canonical_json(payload), str(path.relative_to(self.state_root)), envelope["created_at"],
                    ),
                )
            connection.execute(
                "INSERT INTO semantic_ontology_metadata(key,value) VALUES('schema_version',?)",
                (str(SEMANTIC_ONTOLOGY_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO semantic_ontology_metadata(key,value) VALUES('rebuilt_at',?)",
                (utc_now(),),
            )
