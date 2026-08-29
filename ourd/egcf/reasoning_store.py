from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Tuple

from ..persistence import atomic_write_text
from .algebra.reasoning import CanonicalReasoningAlgorithm, REASONING_ALGEBRA_VERSION
from .algebra.reasoning_outcome import ReasoningOutcomeQualification
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, sha256_json, utc_now


REASONING_STORE_VERSION = "saa-canonical-reasoning-store-v1"
REASONING_STORE_SCHEMA_VERSION = 1


def _sha(value: str, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EGCFError(f"{label} must be an exact SHA-256 digest")
    return digest


def _reasoning_id(signature: str) -> str:
    return f"canonical-reasoning:sha256:{_sha(signature, 'canonical reasoning signature')}"


def _qualification_id(signature: str) -> str:
    return f"reasoning-qualification:sha256:{_sha(signature, 'reasoning qualification signature')}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable reasoning-store collision at {path}")
        return
    atomic_write_text(path, serialized)


@dataclass(frozen=True)
class ReasoningStoreLookup:
    status: str
    exact_ids: Tuple[str, ...]
    topology_match_ids: Tuple[str, ...]
    semantic_match_ids: Tuple[str, ...]

    @property
    def unique(self) -> bool:
        return not self.exact_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exact_ids": list(self.exact_ids),
            "topology_match_ids": list(self.topology_match_ids),
            "semantic_match_ids": list(self.semantic_match_ids),
            "unique": self.unique,
        }


@dataclass(frozen=True)
class ReasoningStoreAdmission:
    status: str
    reasoning_id: str
    qualification_id: str
    store_generation: int
    lookup: ReasoningStoreLookup

    @property
    def admitted_new(self) -> bool:
        return self.status == "ADMITTED_NEW_CANONICAL_REASONING"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasoning_id": self.reasoning_id,
            "qualification_id": self.qualification_id,
            "store_generation": self.store_generation,
            "lookup": self.lookup.to_dict(),
            "admitted_new": self.admitted_new,
        }


class CanonicalReasoningStore:
    """Persistent SAA-8.3 store for evidence-qualified public reasoning algorithms."""

    def __init__(self, egcf_store: Any):
        required = ("state_root", "projection_path", "events", "get")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("CanonicalReasoningStore requires EGCFStore")
        self.egcf_store = egcf_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "canonical-reasoning"
        self.algorithm_root = self.root / "objects" / "sha256"
        self.qualification_root = self.root / "qualifications" / "sha256"
        self.algorithm_root.mkdir(parents=True, exist_ok=True)
        self.qualification_root.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS canonical_reasoning_algorithms (
                    reasoning_id TEXT PRIMARY KEY,
                    canonical_reasoning_signature TEXT NOT NULL UNIQUE,
                    topology_signature TEXT NOT NULL,
                    semantic_signature TEXT NOT NULL,
                    canonicalization_strength TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    applicability_json TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_reasoning_topology_idx
                    ON canonical_reasoning_algorithms(topology_signature);
                CREATE INDEX IF NOT EXISTS canonical_reasoning_semantic_idx
                    ON canonical_reasoning_algorithms(semantic_signature);

                CREATE TABLE IF NOT EXISTS canonical_reasoning_qualifications (
                    qualification_id TEXT PRIMARY KEY,
                    reasoning_id TEXT NOT NULL,
                    outcome_signature TEXT NOT NULL,
                    qualification_signature TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_reasoning_qual_reasoning_idx
                    ON canonical_reasoning_qualifications(reasoning_id);

                CREATE TABLE IF NOT EXISTS canonical_reasoning_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM canonical_reasoning_metadata WHERE key='schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(REASONING_STORE_SCHEMA_VERSION):
            self.rebuild_projection()

    def _algorithm_path(self, reasoning_id: str) -> Path:
        kind, digest = parse_typed_id(reasoning_id)
        if kind != "canonical-reasoning":
            raise EGCFError("reasoning store ID has wrong type")
        return self.algorithm_root / digest[:2] / f"{digest}.json"

    def _qualification_path(self, qualification_id: str) -> Path:
        kind, digest = parse_typed_id(qualification_id)
        if kind != "reasoning-qualification":
            raise EGCFError("reasoning qualification ID has wrong type")
        return self.qualification_root / digest[:2] / f"{digest}.json"

    def _verify_algorithm(self, algorithm: CanonicalReasoningAlgorithm) -> None:
        if not isinstance(algorithm, CanonicalReasoningAlgorithm):
            raise EGCFError("SAA-8.3 admission requires CanonicalReasoningAlgorithm")
        if algorithm.reasoning_version != REASONING_ALGEBRA_VERSION:
            raise EGCFError("unsupported reasoning algebra version")
        if algorithm.canonicalization_strength != "EXACT_BOUNDED_GRAPH_CANONICALIZATION":
            raise EGCFError("canonical reasoning store admits only exact bounded graph canonicalization")
        if not algorithm.public_artifact_only:
            raise EGCFError("canonical reasoning store accepts public reasoning artifacts only")
        for label, value in (
            ("topology signature", algorithm.topology_signature),
            ("semantic signature", algorithm.semantic_signature),
            ("canonical reasoning signature", algorithm.canonical_reasoning_signature),
        ):
            _sha(value, label)
        expected = sha256_json(
            {
                "version": REASONING_ALGEBRA_VERSION,
                "topology_signature": algorithm.topology_signature,
                "semantic_signature": algorithm.semantic_signature,
                "canonicalization_strength": algorithm.canonicalization_strength,
            }
        )
        if expected != algorithm.canonical_reasoning_signature:
            raise EGCFError("canonical reasoning signature mismatch")
        if int(algorithm.termination.get("max_steps", 0)) < 1:
            raise EGCFError("canonical reasoning algorithm has no bounded termination")

    def _verify_qualification(
        self,
        algorithm: CanonicalReasoningAlgorithm,
        qualification: ReasoningOutcomeQualification,
    ) -> None:
        if not isinstance(qualification, ReasoningOutcomeQualification):
            raise EGCFError("SAA-8.3 requires ReasoningOutcomeQualification")
        if qualification.canonical_reasoning_signature != algorithm.canonical_reasoning_signature:
            raise EGCFError("reasoning qualification belongs to a different algorithm")
        if qualification.status != "QUALIFIED_REASONING_OUTCOME":
            raise EGCFError("reasoning store admission requires QUALIFIED_REASONING_OUTCOME")
        if not qualification.canonical_reuse_eligible:
            raise EGCFError("reasoning outcome is not canonical-reuse eligible")
        if qualification.evidence_requirement_coverage_bp != 10000:
            raise EGCFError("reasoning qualification has incomplete evidence coverage")
        if not qualification.grounded_evidence_ids or not qualification.independence_groups:
            raise EGCFError("reasoning qualification lacks grounded independent evidence")
        _sha(qualification.qualification_signature, "reasoning qualification signature")

    def current_generation(self) -> int:
        self._ensure_projection()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(store_generation), 0) FROM canonical_reasoning_algorithms"
            ).fetchone()
        return int(row[0]) if row else 0

    def lookup(self, algorithm: CanonicalReasoningAlgorithm) -> ReasoningStoreLookup:
        self._verify_algorithm(algorithm)
        self._ensure_projection()
        with self._connect() as connection:
            exact = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT reasoning_id FROM canonical_reasoning_algorithms "
                    "WHERE canonical_reasoning_signature=? ORDER BY reasoning_id",
                    (algorithm.canonical_reasoning_signature,),
                ).fetchall()
            )
            topology = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT reasoning_id FROM canonical_reasoning_algorithms "
                    "WHERE topology_signature=? AND canonical_reasoning_signature!=? ORDER BY reasoning_id",
                    (algorithm.topology_signature, algorithm.canonical_reasoning_signature),
                ).fetchall()
            )
            semantic = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT reasoning_id FROM canonical_reasoning_algorithms "
                    "WHERE semantic_signature=? AND canonical_reasoning_signature!=? ORDER BY reasoning_id",
                    (algorithm.semantic_signature, algorithm.canonical_reasoning_signature),
                ).fetchall()
            )
        if exact:
            status = "REASONING_EQUIVALENT_ALREADY_STORED"
        elif topology and semantic:
            status = "MULTIPLE_REASONING_NEIGHBOR_MATCHES"
        elif topology:
            status = "REASONING_TOPOLOGY_MATCH_SEMANTIC_DIFFERENCE"
        elif semantic:
            status = "REASONING_SEMANTIC_MATCH_TOPOLOGY_DIFFERENCE"
        else:
            status = "UNIQUE_CANONICAL_REASONING_CANDIDATE"
        return ReasoningStoreLookup(status, exact, topology, semantic)

    def _algorithm_payload(self, algorithm: CanonicalReasoningAlgorithm) -> dict[str, Any]:
        return algorithm.to_dict()

    def _persist_qualification(
        self,
        reasoning_id: str,
        qualification: ReasoningOutcomeQualification,
    ) -> str:
        qualification_id = _qualification_id(qualification.qualification_signature)
        created_at = utc_now()
        payload = {
            **qualification.to_dict(),
            "reasoning_id": reasoning_id,
        }
        envelope = {
            "schema_version": 1,
            "store_version": REASONING_STORE_VERSION,
            "object_id": qualification_id,
            "created_at": created_at,
            "payload": payload,
        }
        path = self._qualification_path(qualification_id)
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO canonical_reasoning_qualifications(" 
                "qualification_id, reasoning_id, outcome_signature, qualification_signature, evidence_json, "
                "payload_json, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    qualification_id,
                    reasoning_id,
                    qualification.outcome_signature,
                    qualification.qualification_signature,
                    canonical_json(list(qualification.grounded_evidence_ids)),
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        return qualification_id

    def admit(
        self,
        algorithm: CanonicalReasoningAlgorithm,
        qualification: ReasoningOutcomeQualification,
    ) -> ReasoningStoreAdmission:
        self._verify_algorithm(algorithm)
        self._verify_qualification(algorithm, qualification)
        lookup = self.lookup(algorithm)
        if lookup.exact_ids:
            reasoning_id = lookup.exact_ids[0]
            qualification_id = self._persist_qualification(reasoning_id, qualification)
            generation = self._generation_for(reasoning_id)
            return ReasoningStoreAdmission(
                "REUSED_EXISTING_CANONICAL_REASONING",
                reasoning_id,
                qualification_id,
                generation,
                lookup,
            )

        generation = self.current_generation() + 1
        reasoning_id = _reasoning_id(algorithm.canonical_reasoning_signature)
        payload = self._algorithm_payload(algorithm)
        created_at = utc_now()
        envelope = {
            "schema_version": 1,
            "store_version": REASONING_STORE_VERSION,
            "object_id": reasoning_id,
            "store_generation": generation,
            "created_at": created_at,
            "payload": payload,
        }
        path = self._algorithm_path(reasoning_id)
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO canonical_reasoning_algorithms(" 
                "reasoning_id, canonical_reasoning_signature, topology_signature, semantic_signature, "
                "canonicalization_strength, input_json, output_json, applicability_json, max_steps, "
                "store_generation, payload_json, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reasoning_id,
                    algorithm.canonical_reasoning_signature,
                    algorithm.topology_signature,
                    algorithm.semantic_signature,
                    algorithm.canonicalization_strength,
                    canonical_json(list(algorithm.input_semantics)),
                    canonical_json(list(algorithm.output_semantics)),
                    canonical_json(list(algorithm.applicability)),
                    int(algorithm.termination["max_steps"]),
                    generation,
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO canonical_reasoning_metadata(key,value) VALUES ('schema_version',?)",
                (str(REASONING_STORE_SCHEMA_VERSION),),
            )
        qualification_id = self._persist_qualification(reasoning_id, qualification)
        try:
            event = self.egcf_store.events.append(
                "saa_canonical_reasoning_admitted",
                {
                    "reasoning_id": reasoning_id,
                    "qualification_id": qualification_id,
                    "store_generation": generation,
                    "canonical_reasoning_signature": algorithm.canonical_reasoning_signature,
                },
            )
            if hasattr(self.egcf_store, "_index_event"):
                self.egcf_store._index_event(event)
        except Exception:
            pass
        return ReasoningStoreAdmission(
            "ADMITTED_NEW_CANONICAL_REASONING",
            reasoning_id,
            qualification_id,
            generation,
            lookup,
        )

    def _generation_for(self, reasoning_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT store_generation FROM canonical_reasoning_algorithms WHERE reasoning_id=?",
                (reasoning_id,),
            ).fetchone()
        if row is None:
            raise EGCFError(f"unknown canonical reasoning algorithm: {reasoning_id}")
        return int(row[0])

    def get(self, reasoning_id: str) -> dict[str, Any]:
        path = self._algorithm_path(reasoning_id)
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read canonical reasoning algorithm {reasoning_id}: {exc}") from exc
        if envelope.get("object_id") != reasoning_id:
            raise EGCFError("canonical reasoning object identity mismatch")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise EGCFError("canonical reasoning payload is invalid")
        if payload.get("canonical_reasoning_signature") != parse_typed_id(reasoning_id)[1]:
            raise EGCFError("canonical reasoning signature does not match object ID")
        return envelope

    def load_algorithm(self, reasoning_id: str) -> CanonicalReasoningAlgorithm:
        payload = self.get(reasoning_id)["payload"]
        return CanonicalReasoningAlgorithm(
            schema_version=int(payload["schema_version"]),
            reasoning_version=payload["reasoning_version"],
            input_semantics=tuple(payload["input_semantics"]),
            output_semantics=tuple(payload["output_semantics"]),
            canonical_nodes=tuple(payload["canonical_nodes"]),
            canonical_edges=tuple(payload["canonical_edges"]),
            invariants=tuple(payload["invariants"]),
            termination=dict(payload["termination"]),
            applicability=tuple(payload["applicability"]),
            topology_signature=payload["topology_signature"],
            semantic_signature=payload["semantic_signature"],
            canonical_reasoning_signature=payload["canonical_reasoning_signature"],
            canonicalization_strength=payload["canonicalization_strength"],
            canonical_permutations_evaluated=int(payload["canonical_permutations_evaluated"]),
            public_artifact_only=bool(payload["public_artifact_only"]),
            warnings=tuple(payload.get("warnings", ())),
        )

    def list(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT reasoning_id, store_generation, payload_json, created_at "
                "FROM canonical_reasoning_algorithms ORDER BY store_generation, reasoning_id"
            ).fetchall()
        return [
            {
                "reasoning_id": row[0],
                "store_generation": int(row[1]),
                "payload": json.loads(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]

    def qualifications(self, reasoning_id: str | None = None) -> list[dict[str, Any]]:
        self._ensure_projection()
        query = "SELECT payload_json FROM canonical_reasoning_qualifications"
        parameters: tuple[Any, ...] = ()
        if reasoning_id is not None:
            query += " WHERE reasoning_id=?"
            parameters = (reasoning_id,)
        query += " ORDER BY qualification_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [json.loads(row[0]) for row in rows]

    def rebuild_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS canonical_reasoning_algorithms (
                    reasoning_id TEXT PRIMARY KEY,
                    canonical_reasoning_signature TEXT NOT NULL UNIQUE,
                    topology_signature TEXT NOT NULL,
                    semantic_signature TEXT NOT NULL,
                    canonicalization_strength TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    applicability_json TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_reasoning_topology_idx ON canonical_reasoning_algorithms(topology_signature);
                CREATE INDEX IF NOT EXISTS canonical_reasoning_semantic_idx ON canonical_reasoning_algorithms(semantic_signature);
                CREATE TABLE IF NOT EXISTS canonical_reasoning_qualifications (
                    qualification_id TEXT PRIMARY KEY,
                    reasoning_id TEXT NOT NULL,
                    outcome_signature TEXT NOT NULL,
                    qualification_signature TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_reasoning_qual_reasoning_idx ON canonical_reasoning_qualifications(reasoning_id);
                CREATE TABLE IF NOT EXISTS canonical_reasoning_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                DELETE FROM canonical_reasoning_algorithms;
                DELETE FROM canonical_reasoning_qualifications;
                DELETE FROM canonical_reasoning_metadata;
                """
            )
            for path in sorted(self.algorithm_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                reasoning_id = envelope["object_id"]
                if payload["canonical_reasoning_signature"] != parse_typed_id(reasoning_id)[1]:
                    raise EGCFError(f"invalid canonical reasoning entry: {path}")
                connection.execute(
                    "INSERT INTO canonical_reasoning_algorithms(reasoning_id, canonical_reasoning_signature, "
                    "topology_signature, semantic_signature, canonicalization_strength, input_json, output_json, "
                    "applicability_json, max_steps, store_generation, payload_json, path, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        reasoning_id,
                        payload["canonical_reasoning_signature"],
                        payload["topology_signature"],
                        payload["semantic_signature"],
                        payload["canonicalization_strength"],
                        canonical_json(payload["input_semantics"]),
                        canonical_json(payload["output_semantics"]),
                        canonical_json(payload["applicability"]),
                        int(payload["termination"]["max_steps"]),
                        int(envelope["store_generation"]),
                        canonical_json(payload),
                        str(path.relative_to(self.state_root)),
                        envelope["created_at"],
                    ),
                )
            for path in sorted(self.qualification_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO canonical_reasoning_qualifications(qualification_id, reasoning_id, "
                    "outcome_signature, qualification_signature, evidence_json, payload_json, path, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope["object_id"],
                        payload["reasoning_id"],
                        payload["outcome_signature"],
                        payload["qualification_signature"],
                        canonical_json(payload["grounded_evidence_ids"]),
                        canonical_json(payload),
                        str(path.relative_to(self.state_root)),
                        envelope["created_at"],
                    ),
                )
            connection.execute(
                "INSERT INTO canonical_reasoning_metadata(key,value) VALUES ('schema_version',?)",
                (str(REASONING_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO canonical_reasoning_metadata(key,value) VALUES ('rebuilt_at',?)",
                (utc_now(),),
            )
