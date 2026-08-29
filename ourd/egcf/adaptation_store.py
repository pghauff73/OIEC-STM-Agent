from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..persistence import atomic_write_text
from .algebra.adaptation_lineage import (
    ADAPTATION_LINEAGE_VERSION,
    MAX_LINEAGE_DEPTH,
    AdaptationLineageEdge,
    AdaptationPromotionRecord,
    adapted_candidate_ref,
    make_adaptation_lineage_edge,
)
from .algebra.algorithm_adaptation import AdaptationStep, AdaptedAlgorithmCandidate
from .algebra.algorithm_experiment import AlgorithmABExperimentDesign, AlgorithmABExperimentResult
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, utc_now
from .models import EvidenceArtifact


ADAPTATION_STORE_VERSION = "saa-adaptation-lineage-store-v1"
ADAPTATION_STORE_SCHEMA_VERSION = 1


def _typed_ref(kind: str, signature: str) -> str:
    return f"{kind}:sha256:{signature}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable adaptation-store collision at {path}")
        return
    atomic_write_text(path, serialized)


class AdaptationLineageStore:
    """Persistent SAA-11.1/11.2 lineage graph and controlled experiment ledger."""

    def __init__(self, egcf_store: Any):
        required = ("state_root", "projection_path", "events", "get")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("AdaptationLineageStore requires EGCFStore")
        self.egcf_store = egcf_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "adaptation-lineage"
        self.candidate_root = self.root / "candidates" / "sha256"
        self.edge_root = self.root / "edges" / "sha256"
        self.promotion_root = self.root / "promotions" / "sha256"
        self.experiment_root = self.root / "experiments" / "sha256"
        self.result_root = self.root / "experiment-results" / "sha256"
        for path in (
            self.candidate_root,
            self.edge_root,
            self.promotion_root,
            self.experiment_root,
            self.result_root,
        ):
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
                CREATE TABLE IF NOT EXISTS adaptation_candidates (
                    candidate_ref TEXT PRIMARY KEY,
                    candidate_signature TEXT NOT NULL UNIQUE,
                    base_algorithm_id TEXT NOT NULL,
                    component TEXT NOT NULL,
                    changed_dimension TEXT NOT NULL,
                    parent_candidate_signature TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_candidates_base_idx
                    ON adaptation_candidates(base_algorithm_id);
                CREATE INDEX IF NOT EXISTS adaptation_candidates_dimension_idx
                    ON adaptation_candidates(changed_dimension);

                CREATE TABLE IF NOT EXISTS adaptation_lineage_edges (
                    edge_ref TEXT PRIMARY KEY,
                    edge_signature TEXT NOT NULL UNIQUE,
                    parent_ref TEXT NOT NULL,
                    child_ref TEXT NOT NULL UNIQUE,
                    relation TEXT NOT NULL,
                    changed_dimension TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_edges_parent_idx
                    ON adaptation_lineage_edges(parent_ref);
                CREATE INDEX IF NOT EXISTS adaptation_edges_child_idx
                    ON adaptation_lineage_edges(child_ref);

                CREATE TABLE IF NOT EXISTS adaptation_promotions (
                    promotion_ref TEXT PRIMARY KEY,
                    promotion_signature TEXT NOT NULL UNIQUE,
                    candidate_ref TEXT NOT NULL,
                    canonical_algorithm_ref TEXT NOT NULL,
                    qualification_signature TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_promotions_candidate_idx
                    ON adaptation_promotions(candidate_ref);

                CREATE TABLE IF NOT EXISTS adaptation_experiments (
                    experiment_ref TEXT PRIMARY KEY,
                    design_signature TEXT NOT NULL UNIQUE,
                    baseline_ref TEXT NOT NULL,
                    candidate_ref TEXT NOT NULL,
                    context_signature TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_experiments_candidate_idx
                    ON adaptation_experiments(candidate_ref);

                CREATE TABLE IF NOT EXISTS adaptation_experiment_results (
                    result_ref TEXT PRIMARY KEY,
                    result_signature TEXT NOT NULL UNIQUE,
                    design_signature TEXT NOT NULL,
                    status TEXT NOT NULL,
                    candidate_improvement_qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_results_design_idx
                    ON adaptation_experiment_results(design_signature);

                CREATE TABLE IF NOT EXISTS adaptation_store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM adaptation_store_metadata WHERE key='schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(ADAPTATION_STORE_SCHEMA_VERSION):
            self.rebuild_projection()

    def _path(self, root: Path, object_ref: str, expected_kind: str) -> Path:
        kind, digest = parse_typed_id(object_ref)
        if kind != expected_kind:
            raise EGCFError(f"adaptation store expected {expected_kind} reference")
        return root / digest[:2] / f"{digest}.json"

    def _event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        try:
            event = self.egcf_store.events.append(event_type, dict(payload))
            if hasattr(self.egcf_store, "_index_event"):
                self.egcf_store._index_event(event)
        except Exception:
            pass

    def _candidate_exists(self, candidate_ref: str) -> bool:
        with self._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM adaptation_candidates WHERE candidate_ref=?",
                (candidate_ref,),
            ).fetchone() is not None

    def register_candidate(
        self,
        candidate: AdaptedAlgorithmCandidate,
        step: AdaptationStep,
        *,
        source_explanation_signature: str,
    ) -> tuple[str, str]:
        edge = make_adaptation_lineage_edge(
            candidate,
            step,
            source_explanation_signature=source_explanation_signature,
        )
        candidate_ref = edge.child_ref
        if edge.parent_candidate_signature and not self._candidate_exists(edge.parent_ref):
            raise EGCFError("SAA-11.1 parent adapted candidate is not registered")
        if edge.parent_ref == candidate_ref:
            raise EGCFError("SAA-11.1 lineage cycle detected")
        if edge.parent_candidate_signature and candidate_ref in self.ancestors(edge.parent_ref):
            raise EGCFError("SAA-11.1 lineage registration would create a cycle")
        candidate_payload = candidate.to_dict()
        candidate_envelope = {
            "schema_version": 1,
            "store_version": ADAPTATION_STORE_VERSION,
            "object_id": candidate_ref,
            "created_at": utc_now(),
            "payload": candidate_payload,
        }
        candidate_path = self._path(self.candidate_root, candidate_ref, "adapted-candidate")
        _immutable_write(candidate_path, candidate_envelope)
        edge_ref = _typed_ref("adaptation-edge", edge.edge_signature)
        edge_envelope = {
            "schema_version": 1,
            "store_version": ADAPTATION_STORE_VERSION,
            "object_id": edge_ref,
            "created_at": utc_now(),
            "payload": edge.to_dict(),
        }
        edge_path = self._path(self.edge_root, edge_ref, "adaptation-edge")
        _immutable_write(edge_path, edge_envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO adaptation_candidates(candidate_ref,candidate_signature,base_algorithm_id,component,changed_dimension,parent_candidate_signature,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    candidate_ref,
                    candidate.candidate_signature,
                    candidate.base_algorithm_id,
                    candidate.component,
                    candidate.changed_dimension,
                    candidate.parent_candidate_signature,
                    canonical_json(candidate_payload),
                    str(candidate_path.relative_to(self.state_root)),
                    candidate_envelope["created_at"],
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO adaptation_lineage_edges(edge_ref,edge_signature,parent_ref,child_ref,relation,changed_dimension,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    edge_ref,
                    edge.edge_signature,
                    edge.parent_ref,
                    edge.child_ref,
                    edge.relation,
                    edge.changed_dimension,
                    canonical_json(edge.to_dict()),
                    str(edge_path.relative_to(self.state_root)),
                    edge_envelope["created_at"],
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO adaptation_store_metadata(key,value) VALUES('schema_version',?)",
                (str(ADAPTATION_STORE_SCHEMA_VERSION),),
            )
        self._event(
            "saa_adaptation_candidate_registered",
            {"candidate_ref": candidate_ref, "edge_ref": edge_ref, "parent_ref": edge.parent_ref},
        )
        return candidate_ref, edge_ref

    def get_candidate(self, candidate_ref: str) -> dict[str, Any]:
        path = self._path(self.candidate_root, candidate_ref, "adapted-candidate")
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read adaptation candidate {candidate_ref}: {exc}") from exc
        if envelope.get("object_id") != candidate_ref:
            raise EGCFError("adaptation candidate identity mismatch")
        return envelope

    def candidates(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT candidate_ref,base_algorithm_id,component,changed_dimension,parent_candidate_signature,payload_json,created_at FROM adaptation_candidates ORDER BY candidate_ref"
            ).fetchall()
        return [
            {
                "candidate_ref": row[0],
                "base_algorithm_id": row[1],
                "component": row[2],
                "changed_dimension": row[3],
                "parent_candidate_signature": row[4],
                "payload": json.loads(row[5]),
                "created_at": row[6],
            }
            for row in rows
        ]

    def edges(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT edge_ref,parent_ref,child_ref,changed_dimension,payload_json FROM adaptation_lineage_edges ORDER BY edge_ref"
            ).fetchall()
        return [
            {
                "edge_ref": row[0],
                "parent_ref": row[1],
                "child_ref": row[2],
                "changed_dimension": row[3],
                "payload": json.loads(row[4]),
            }
            for row in rows
        ]

    def parent(self, candidate_ref: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT parent_ref FROM adaptation_lineage_edges WHERE child_ref=?",
                (candidate_ref,),
            ).fetchone()
        return str(row[0]) if row else None

    def children(self, ref: str) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT child_ref FROM adaptation_lineage_edges WHERE parent_ref=? ORDER BY child_ref",
                (str(ref),),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def ancestors(self, candidate_ref: str) -> tuple[str, ...]:
        current = str(candidate_ref)
        result: list[str] = []
        seen = {current}
        for _ in range(MAX_LINEAGE_DEPTH):
            parent = self.parent(current)
            if parent is None:
                return tuple(result)
            if parent in seen:
                raise EGCFError("SAA-11.1 stored adaptation lineage contains a cycle")
            seen.add(parent)
            result.append(parent)
            if not parent.startswith("adapted-candidate:sha256:"):
                return tuple(result)
            current = parent
        raise EGCFError("SAA-11.1 lineage exceeds bounded depth")

    def descends_from(self, candidate_ref: str, ancestor_ref: str) -> bool:
        return str(ancestor_ref) in self.ancestors(candidate_ref)

    def register_promotion(self, promotion: AdaptationPromotionRecord) -> str:
        if not isinstance(promotion, AdaptationPromotionRecord):
            raise EGCFError("SAA-11.1 promotion store requires AdaptationPromotionRecord")
        self.get_candidate(promotion.candidate_ref)
        for evidence_id in promotion.evidence_ids:
            try:
                record = self.egcf_store.get(evidence_id)
            except Exception as exc:
                raise EGCFError(f"promotion evidence is not registered: {evidence_id}") from exc
            if not isinstance(record, EvidenceArtifact):
                raise EGCFError("promotion evidence must reference EvidenceArtifact")
            if record.success is not True or record.simulated:
                raise EGCFError("promotion evidence must be successful and non-simulated")
            if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
                raise EGCFError("promotion evidence must be deterministic/human grounded")
        promotion_ref = _typed_ref("adaptation-promotion", promotion.promotion_signature)
        envelope = {
            "schema_version": 1,
            "store_version": ADAPTATION_STORE_VERSION,
            "object_id": promotion_ref,
            "created_at": utc_now(),
            "payload": promotion.to_dict(),
        }
        path = self._path(self.promotion_root, promotion_ref, "adaptation-promotion")
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO adaptation_promotions(promotion_ref,promotion_signature,candidate_ref,canonical_algorithm_ref,qualification_signature,evidence_json,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    promotion_ref,
                    promotion.promotion_signature,
                    promotion.candidate_ref,
                    promotion.canonical_algorithm_ref,
                    promotion.qualification_signature,
                    canonical_json(list(promotion.evidence_ids)),
                    canonical_json(promotion.to_dict()),
                    str(path.relative_to(self.state_root)),
                    envelope["created_at"],
                ),
            )
        self._event("saa_adaptation_candidate_promoted", {"promotion_ref": promotion_ref, **promotion.to_dict()})
        return promotion_ref

    def promotions(self, candidate_ref: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT promotion_ref,payload_json FROM adaptation_promotions"
        params: tuple[Any, ...] = ()
        if candidate_ref is not None:
            query += " WHERE candidate_ref=?"
            params = (candidate_ref,)
        query += " ORDER BY promotion_ref"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{"promotion_ref": row[0], "payload": json.loads(row[1])} for row in rows]

    def register_experiment_design(self, design: AlgorithmABExperimentDesign) -> str:
        if not isinstance(design, AlgorithmABExperimentDesign):
            raise EGCFError("SAA-11.2 store requires AlgorithmABExperimentDesign")
        self.get_candidate(design.candidate_ref)
        if not self.descends_from(design.candidate_ref, design.baseline_ref):
            raise EGCFError("SAA-11.2 candidate must descend from the experiment baseline")
        experiment_ref = _typed_ref("adaptation-experiment", design.design_signature)
        envelope = {
            "schema_version": 1,
            "store_version": ADAPTATION_STORE_VERSION,
            "object_id": experiment_ref,
            "created_at": utc_now(),
            "payload": design.to_dict(),
        }
        path = self._path(self.experiment_root, experiment_ref, "adaptation-experiment")
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO adaptation_experiments(experiment_ref,design_signature,baseline_ref,candidate_ref,context_signature,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    experiment_ref,
                    design.design_signature,
                    design.baseline_ref,
                    design.candidate_ref,
                    design.context_signature,
                    canonical_json(design.to_dict()),
                    str(path.relative_to(self.state_root)),
                    envelope["created_at"],
                ),
            )
        self._event("saa_adaptation_experiment_registered", {"experiment_ref": experiment_ref, "candidate_ref": design.candidate_ref})
        return experiment_ref

    def register_experiment_result(self, result: AlgorithmABExperimentResult) -> str:
        if not isinstance(result, AlgorithmABExperimentResult):
            raise EGCFError("SAA-11.2 store requires AlgorithmABExperimentResult")
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM adaptation_experiments WHERE design_signature=?",
                (result.design_signature,),
            ).fetchone()
        if exists is None:
            raise EGCFError("SAA-11.2 experiment result references an unregistered design")
        result_ref = _typed_ref("adaptation-experiment-result", result.result_signature)
        envelope = {
            "schema_version": 1,
            "store_version": ADAPTATION_STORE_VERSION,
            "object_id": result_ref,
            "created_at": utc_now(),
            "payload": result.to_dict(),
        }
        path = self._path(self.result_root, result_ref, "adaptation-experiment-result")
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO adaptation_experiment_results(result_ref,result_signature,design_signature,status,candidate_improvement_qualified,payload_json,path,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    result_ref,
                    result.result_signature,
                    result.design_signature,
                    result.status,
                    int(result.candidate_improvement_qualified),
                    canonical_json(result.to_dict()),
                    str(path.relative_to(self.state_root)),
                    envelope["created_at"],
                ),
            )
        self._event(
            "saa_adaptation_experiment_result_registered",
            {"result_ref": result_ref, "status": result.status, "candidate_improvement_qualified": result.candidate_improvement_qualified},
        )
        return result_ref

    def experiments(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT experiment_ref,payload_json FROM adaptation_experiments ORDER BY experiment_ref"
            ).fetchall()
        return [{"experiment_ref": row[0], "payload": json.loads(row[1])} for row in rows]

    def experiment_results(self, design_signature: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT result_ref,payload_json FROM adaptation_experiment_results"
        params: tuple[Any, ...] = ()
        if design_signature is not None:
            query += " WHERE design_signature=?"
            params = (design_signature,)
        query += " ORDER BY result_ref"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{"result_ref": row[0], "payload": json.loads(row[1])} for row in rows]

    def rebuild_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS adaptation_candidates (
                    candidate_ref TEXT PRIMARY KEY,candidate_signature TEXT NOT NULL UNIQUE,
                    base_algorithm_id TEXT NOT NULL,component TEXT NOT NULL,changed_dimension TEXT NOT NULL,
                    parent_candidate_signature TEXT NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_candidates_base_idx ON adaptation_candidates(base_algorithm_id);
                CREATE INDEX IF NOT EXISTS adaptation_candidates_dimension_idx ON adaptation_candidates(changed_dimension);
                CREATE TABLE IF NOT EXISTS adaptation_lineage_edges (
                    edge_ref TEXT PRIMARY KEY,edge_signature TEXT NOT NULL UNIQUE,parent_ref TEXT NOT NULL,
                    child_ref TEXT NOT NULL UNIQUE,relation TEXT NOT NULL,changed_dimension TEXT NOT NULL,
                    payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_edges_parent_idx ON adaptation_lineage_edges(parent_ref);
                CREATE INDEX IF NOT EXISTS adaptation_edges_child_idx ON adaptation_lineage_edges(child_ref);
                CREATE TABLE IF NOT EXISTS adaptation_promotions (
                    promotion_ref TEXT PRIMARY KEY,promotion_signature TEXT NOT NULL UNIQUE,candidate_ref TEXT NOT NULL,
                    canonical_algorithm_ref TEXT NOT NULL,qualification_signature TEXT NOT NULL,evidence_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_promotions_candidate_idx ON adaptation_promotions(candidate_ref);
                CREATE TABLE IF NOT EXISTS adaptation_experiments (
                    experiment_ref TEXT PRIMARY KEY,design_signature TEXT NOT NULL UNIQUE,baseline_ref TEXT NOT NULL,
                    candidate_ref TEXT NOT NULL,context_signature TEXT NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_experiments_candidate_idx ON adaptation_experiments(candidate_ref);
                CREATE TABLE IF NOT EXISTS adaptation_experiment_results (
                    result_ref TEXT PRIMARY KEY,result_signature TEXT NOT NULL UNIQUE,design_signature TEXT NOT NULL,
                    status TEXT NOT NULL,candidate_improvement_qualified INTEGER NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS adaptation_results_design_idx ON adaptation_experiment_results(design_signature);
                CREATE TABLE IF NOT EXISTS adaptation_store_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                DELETE FROM adaptation_candidates;
                DELETE FROM adaptation_lineage_edges;
                DELETE FROM adaptation_promotions;
                DELETE FROM adaptation_experiments;
                DELETE FROM adaptation_experiment_results;
                DELETE FROM adaptation_store_metadata;
                """
            )
            for path in sorted(self.candidate_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                candidate_ref = envelope["object_id"]
                if adapted_candidate_ref(payload["candidate_signature"]) != candidate_ref:
                    raise EGCFError(f"invalid adaptation candidate entry: {path}")
                connection.execute(
                    "INSERT INTO adaptation_candidates VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        candidate_ref,payload["candidate_signature"],payload["base_algorithm_id"],payload["component"],
                        payload["changed_dimension"],payload["parent_candidate_signature"],canonical_json(payload),
                        str(path.relative_to(self.state_root)),envelope["created_at"],
                    ),
                )
            for path in sorted(self.edge_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO adaptation_lineage_edges VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        envelope["object_id"],payload["edge_signature"],payload["parent_ref"],payload["child_ref"],
                        payload["relation"],payload["changed_dimension"],canonical_json(payload),
                        str(path.relative_to(self.state_root)),envelope["created_at"],
                    ),
                )
            for path in sorted(self.promotion_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO adaptation_promotions VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        envelope["object_id"],payload["promotion_signature"],payload["candidate_ref"],
                        payload["canonical_algorithm_ref"],payload["qualification_signature"],
                        canonical_json(payload["evidence_ids"]),canonical_json(payload),
                        str(path.relative_to(self.state_root)),envelope["created_at"],
                    ),
                )
            for path in sorted(self.experiment_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO adaptation_experiments VALUES(?,?,?,?,?,?,?,?)",
                    (
                        envelope["object_id"],payload["design_signature"],payload["baseline_ref"],payload["candidate_ref"],
                        payload["context_signature"],canonical_json(payload),str(path.relative_to(self.state_root)),envelope["created_at"],
                    ),
                )
            for path in sorted(self.result_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO adaptation_experiment_results VALUES(?,?,?,?,?,?,?,?)",
                    (
                        envelope["object_id"],payload["result_signature"],payload["design_signature"],payload["status"],
                        int(payload["candidate_improvement_qualified"]),canonical_json(payload),
                        str(path.relative_to(self.state_root)),envelope["created_at"],
                    ),
                )
            connection.execute(
                "INSERT INTO adaptation_store_metadata(key,value) VALUES('schema_version',?)",
                (str(ADAPTATION_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO adaptation_store_metadata(key,value) VALUES('rebuilt_at',?)",
                (utc_now(),),
            )
