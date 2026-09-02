from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from ..persistence import atomic_write_text
from .algebra.failure_algebra import (
    CanonicalFailurePattern,
    FailureMatchAssessment,
    FailureObservation,
    canonicalize_failure,
    compare_failure_to_pattern,
)
from .algebra.improvement_scheduling import ImprovementOpportunity, ImprovementSchedule
from .algebra.knowledge_integrity import KnowledgeIntegritySnapshot, KnowledgeIntegrityTrajectory
from .algebra.oiec_bench_gate import OIECBenchGateAssessment
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, utc_now
from .models import EvidenceArtifact


KNOWLEDGE_GOVERNANCE_STORE_VERSION = "saa-knowledge-governance-store-v1"
KNOWLEDGE_GOVERNANCE_STORE_SCHEMA_VERSION = 1


def _ref(kind: str, signature: str) -> str:
    return f"{kind}:sha256:{signature}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable knowledge-governance collision at {path}")
        return
    atomic_write_text(path, serialized)


class KnowledgeGovernanceStore:
    """Persistent SAA-12.1-12.4 failure, benchmark, integrity and scheduling ledger."""

    def __init__(self, egcf_store: Any):
        required = ("state_root", "projection_path", "events", "get")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("KnowledgeGovernanceStore requires EGCFStore")
        self.egcf_store = egcf_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "knowledge-governance"
        self.pattern_root = self.root / "failure-patterns" / "sha256"
        self.occurrence_root = self.root / "failure-occurrences" / "sha256"
        self.benchmark_root = self.root / "benchmark-gates" / "sha256"
        self.snapshot_root = self.root / "integrity-snapshots" / "sha256"
        self.trajectory_root = self.root / "integrity-trajectories" / "sha256"
        self.opportunity_root = self.root / "improvement-opportunities" / "sha256"
        self.schedule_root = self.root / "improvement-schedules" / "sha256"
        for path in (
            self.pattern_root,
            self.occurrence_root,
            self.benchmark_root,
            self.snapshot_root,
            self.trajectory_root,
            self.opportunity_root,
            self.schedule_root,
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
                CREATE TABLE IF NOT EXISTS saa_failure_patterns (
                    pattern_ref TEXT PRIMARY KEY,
                    pattern_signature TEXT NOT NULL UNIQUE,
                    failure_class TEXT NOT NULL,
                    component TEXT NOT NULL,
                    mechanism TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS saa_failure_patterns_class_idx ON saa_failure_patterns(failure_class);
                CREATE INDEX IF NOT EXISTS saa_failure_patterns_component_idx ON saa_failure_patterns(component);

                CREATE TABLE IF NOT EXISTS saa_failure_occurrences (
                    occurrence_ref TEXT PRIMARY KEY,
                    observation_signature TEXT NOT NULL UNIQUE,
                    pattern_signature TEXT NOT NULL,
                    provenance_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS saa_failure_occurrence_pattern_idx ON saa_failure_occurrences(pattern_signature);

                CREATE TABLE IF NOT EXISTS saa_benchmark_gates (
                    gate_ref TEXT PRIMARY KEY,
                    assessment_signature TEXT NOT NULL UNIQUE,
                    candidate_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    promotion_eligible INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS saa_benchmark_candidate_idx ON saa_benchmark_gates(candidate_ref);

                CREATE TABLE IF NOT EXISTS saa_integrity_snapshots (
                    snapshot_ref TEXT PRIMARY KEY,
                    snapshot_signature TEXT NOT NULL UNIQUE,
                    generation INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saa_integrity_trajectories (
                    trajectory_ref TEXT PRIMARY KEY,
                    trajectory_signature TEXT NOT NULL UNIQUE,
                    latest_generation INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saa_improvement_opportunities (
                    opportunity_ref TEXT PRIMARY KEY,
                    opportunity_signature TEXT NOT NULL UNIQUE,
                    opportunity_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    priority_bp INTEGER NOT NULL,
                    eligible INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS saa_opportunity_kind_idx ON saa_improvement_opportunities(kind);

                CREATE TABLE IF NOT EXISTS saa_improvement_schedules (
                    schedule_ref TEXT PRIMARY KEY,
                    schedule_signature TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saa_knowledge_governance_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM saa_knowledge_governance_metadata WHERE key='schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(KNOWLEDGE_GOVERNANCE_STORE_SCHEMA_VERSION):
            self.rebuild_projection()

    def _path(self, root: Path, object_ref: str, expected_kind: str) -> Path:
        kind, digest = parse_typed_id(object_ref)
        if kind != expected_kind:
            raise EGCFError(f"knowledge governance store expected {expected_kind} reference")
        return root / digest[:2] / f"{digest}.json"

    def _write(self, root: Path, kind: str, signature: str, payload: Mapping[str, Any]) -> tuple[str, Path, str]:
        object_ref = _ref(kind, signature)
        created_at = utc_now()
        path = self._path(root, object_ref, kind)
        _immutable_write(
            path,
            {
                "schema_version": 1,
                "store_version": KNOWLEDGE_GOVERNANCE_STORE_VERSION,
                "object_id": object_ref,
                "created_at": created_at,
                "payload": dict(payload),
            },
        )
        return object_ref, path, created_at

    def _event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        try:
            event = self.egcf_store.events.append(event_type, dict(payload))
            if hasattr(self.egcf_store, "_index_event"):
                self.egcf_store._index_event(event)
        except Exception:
            pass

    def _ground_failure_evidence(self, observation: FailureObservation) -> None:
        for evidence_id in observation.evidence_ids:
            try:
                record = self.egcf_store.get(evidence_id)
            except Exception as exc:
                raise EGCFError(f"SAA-12.1 failure evidence is not registered: {evidence_id}") from exc
            if not isinstance(record, EvidenceArtifact):
                raise EGCFError("SAA-12.1 failure evidence must reference EvidenceArtifact")
            if record.success is not True or record.simulated:
                raise EGCFError("SAA-12.1 failure evidence must be successful and non-simulated")
            if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
                raise EGCFError("SAA-12.1 failure evidence must be deterministic/human grounded")

    def register_failure_observation(self, observation: FailureObservation) -> tuple[str, str, bool]:
        if not isinstance(observation, FailureObservation):
            raise EGCFError("failure registration requires FailureObservation")
        self._ground_failure_evidence(observation)
        pattern = canonicalize_failure(observation)
        pattern_ref, pattern_path, pattern_created = self._write(
            self.pattern_root, "failure-pattern", pattern.pattern_signature, pattern.to_dict()
        )
        occurrence_ref, occurrence_path, occurrence_created = self._write(
            self.occurrence_root, "failure-occurrence", observation.observation_signature,
            {**observation.to_dict(), "pattern_signature": pattern.pattern_signature},
        )
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT COUNT(*) FROM saa_failure_occurrences WHERE pattern_signature=?",
                (pattern.pattern_signature,),
            ).fetchone()[0]
            connection.execute(
                "INSERT OR IGNORE INTO saa_failure_patterns VALUES(?,?,?,?,?,?,?,?)",
                (
                    pattern_ref, pattern.pattern_signature, pattern.failure_class, pattern.component,
                    pattern.mechanism, canonical_json(pattern.to_dict()),
                    str(pattern_path.relative_to(self.state_root)), pattern_created,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO saa_failure_occurrences VALUES(?,?,?,?,?,?,?)",
                (
                    occurrence_ref, observation.observation_signature, pattern.pattern_signature,
                    observation.provenance_id, canonical_json({**observation.to_dict(), "pattern_signature": pattern.pattern_signature}),
                    str(occurrence_path.relative_to(self.state_root)), occurrence_created,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO saa_knowledge_governance_metadata(key,value) VALUES('schema_version',?)",
                (str(KNOWLEDGE_GOVERNANCE_STORE_SCHEMA_VERSION),),
            )
        repeated = int(existing) > 0
        self._event("saa_failure_observed", {"pattern_ref": pattern_ref, "occurrence_ref": occurrence_ref, "repeated": repeated})
        return pattern_ref, occurrence_ref, repeated

    def failure_patterns(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT pattern_ref,pattern_signature,payload_json FROM saa_failure_patterns ORDER BY pattern_ref"
            ).fetchall()
        return [{"pattern_ref": row[0], "pattern_signature": row[1], "payload": json.loads(row[2])} for row in rows]

    def failure_occurrence_count(self, pattern_signature: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM saa_failure_occurrences WHERE pattern_signature=?",
                (str(pattern_signature),),
            ).fetchone()
        return int(row[0])

    def assess_failure_retry(self, observation: FailureObservation) -> FailureMatchAssessment | None:
        candidate = canonicalize_failure(observation)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM saa_failure_patterns WHERE pattern_signature=?",
                (candidate.pattern_signature,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        pattern = CanonicalFailurePattern(
            failure_class=payload["failure_class"],
            component=payload["component"],
            mechanism=payload["mechanism"],
            semantic_roles=tuple(payload["semantic_roles"]),
            violated_invariants=tuple(payload["violated_invariants"]),
            boundary_signature=payload["boundary_signature"],
            context_signature=payload["context_signature"],
            pattern_signature=payload["pattern_signature"],
        )
        return compare_failure_to_pattern(
            observation, pattern,
            prior_occurrence_count=self.failure_occurrence_count(pattern.pattern_signature),
        )

    def register_benchmark_gate(self, assessment: OIECBenchGateAssessment) -> str:
        if not isinstance(assessment, OIECBenchGateAssessment):
            raise EGCFError("benchmark gate registration requires OIECBenchGateAssessment")
        ref, path, created = self._write(self.benchmark_root, "oiec-bench-gate", assessment.assessment_signature, assessment.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO saa_benchmark_gates VALUES(?,?,?,?,?,?,?,?)",
                (
                    ref, assessment.assessment_signature, assessment.candidate_ref, assessment.status,
                    int(assessment.canonical_promotion_eligible), canonical_json(assessment.to_dict()),
                    str(path.relative_to(self.state_root)), created,
                ),
            )
        self._event("saa_oiec_bench_gate_recorded", {"gate_ref": ref, "status": assessment.status})
        return ref

    def register_integrity_snapshot(self, snapshot: KnowledgeIntegritySnapshot) -> str:
        if not isinstance(snapshot, KnowledgeIntegritySnapshot):
            raise EGCFError("integrity snapshot registration requires KnowledgeIntegritySnapshot")
        ref, path, created = self._write(self.snapshot_root, "knowledge-integrity-snapshot", snapshot.snapshot_signature, snapshot.to_dict())
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT snapshot_signature FROM saa_integrity_snapshots WHERE generation=?",
                (snapshot.generation,),
            ).fetchone()
            if existing is not None and existing[0] != snapshot.snapshot_signature:
                raise EGCFError("SAA-12.3 one generation cannot have conflicting integrity snapshots")
            connection.execute(
                "INSERT OR IGNORE INTO saa_integrity_snapshots VALUES(?,?,?,?,?,?)",
                (
                    ref, snapshot.snapshot_signature, snapshot.generation, canonical_json(snapshot.to_dict()),
                    str(path.relative_to(self.state_root)), created,
                ),
            )
        return ref

    def register_integrity_trajectory(self, trajectory: KnowledgeIntegrityTrajectory) -> str:
        if not isinstance(trajectory, KnowledgeIntegrityTrajectory):
            raise EGCFError("integrity trajectory registration requires KnowledgeIntegrityTrajectory")
        with self._connect() as connection:
            known = {row[0] for row in connection.execute("SELECT snapshot_signature FROM saa_integrity_snapshots").fetchall()}
        if not set(trajectory.snapshot_signatures).issubset(known):
            raise EGCFError("SAA-12.3 trajectory references unregistered integrity snapshots")
        ref, path, created = self._write(self.trajectory_root, "knowledge-integrity-trajectory", trajectory.trajectory_signature, trajectory.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO saa_integrity_trajectories VALUES(?,?,?,?,?,?,?,?)",
                (
                    ref, trajectory.trajectory_signature, trajectory.latest_generation, trajectory.status,
                    int(trajectory.knowledge_integrity_qualified), canonical_json(trajectory.to_dict()),
                    str(path.relative_to(self.state_root)), created,
                ),
            )
        return ref

    def register_opportunity(self, opportunity: ImprovementOpportunity) -> str:
        if not isinstance(opportunity, ImprovementOpportunity):
            raise EGCFError("improvement opportunity registration requires ImprovementOpportunity")
        ref, path, created = self._write(self.opportunity_root, "improvement-opportunity", opportunity.opportunity_signature, opportunity.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO saa_improvement_opportunities VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ref, opportunity.opportunity_signature, opportunity.opportunity_id, opportunity.kind,
                    opportunity.priority_bp, int(opportunity.eligible), canonical_json(opportunity.to_dict()),
                    str(path.relative_to(self.state_root)), created,
                ),
            )
        return ref

    def register_schedule(self, schedule: ImprovementSchedule) -> str:
        if not isinstance(schedule, ImprovementSchedule):
            raise EGCFError("improvement schedule registration requires ImprovementSchedule")
        with self._connect() as connection:
            known = {row[0] for row in connection.execute("SELECT opportunity_signature FROM saa_improvement_opportunities").fetchall()}
        if any(item.opportunity_signature not in known for item in schedule.selected):
            raise EGCFError("SAA-12.4 schedule selects an unregistered improvement opportunity")
        ref, path, created = self._write(self.schedule_root, "improvement-schedule", schedule.schedule_signature, schedule.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO saa_improvement_schedules VALUES(?,?,?,?,?,?)",
                (
                    ref, schedule.schedule_signature, schedule.status, canonical_json(schedule.to_dict()),
                    str(path.relative_to(self.state_root)), created,
                ),
            )
        self._event("saa_improvement_schedule_recorded", {"schedule_ref": ref, "selected_count": len(schedule.selected)})
        return ref

    def rebuild_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                DELETE FROM saa_failure_patterns;
                DELETE FROM saa_failure_occurrences;
                DELETE FROM saa_benchmark_gates;
                DELETE FROM saa_integrity_snapshots;
                DELETE FROM saa_integrity_trajectories;
                DELETE FROM saa_improvement_opportunities;
                DELETE FROM saa_improvement_schedules;
                DELETE FROM saa_knowledge_governance_metadata;
                """
            )
            for path in sorted(self.pattern_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_failure_patterns VALUES(?,?,?,?,?,?,?,?)",
                    (env["object_id"], p["pattern_signature"], p["failure_class"], p["component"], p["mechanism"], canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            for path in sorted(self.occurrence_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_failure_occurrences VALUES(?,?,?,?,?,?,?)",
                    (env["object_id"], p["observation_signature"], p["pattern_signature"], p["provenance_id"], canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            for path in sorted(self.benchmark_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_benchmark_gates VALUES(?,?,?,?,?,?,?,?)",
                    (env["object_id"], p["assessment_signature"], p["candidate_ref"], p["status"], int(p["canonical_promotion_eligible"]), canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            for path in sorted(self.snapshot_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_integrity_snapshots VALUES(?,?,?,?,?,?)",
                    (env["object_id"], p["snapshot_signature"], p["generation"], canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            for path in sorted(self.trajectory_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_integrity_trajectories VALUES(?,?,?,?,?,?,?,?)",
                    (env["object_id"], p["trajectory_signature"], p["latest_generation"], p["status"], int(p["knowledge_integrity_qualified"]), canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            for path in sorted(self.opportunity_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_improvement_opportunities VALUES(?,?,?,?,?,?,?,?,?)",
                    (env["object_id"], p["opportunity_signature"], p["opportunity_id"], p["kind"], p["priority_bp"], int(p["eligible"]), canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            for path in sorted(self.schedule_root.glob("*/*.json")):
                env = json.loads(path.read_text(encoding="utf-8")); p = env["payload"]
                connection.execute(
                    "INSERT INTO saa_improvement_schedules VALUES(?,?,?,?,?,?)",
                    (env["object_id"], p["schedule_signature"], p["status"], canonical_json(p), str(path.relative_to(self.state_root)), env["created_at"]),
                )
            connection.execute(
                "INSERT INTO saa_knowledge_governance_metadata(key,value) VALUES('schema_version',?)",
                (str(KNOWLEDGE_GOVERNANCE_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO saa_knowledge_governance_metadata(key,value) VALUES('rebuilt_at',?)",
                (utc_now(),),
            )
