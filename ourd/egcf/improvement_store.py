from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from ..persistence import atomic_write_text
from .algebra.experiment_aggregation import RepeatedExperimentAggregate
from .algebra.intelligence_loop import IntelligenceImprovementDecision
from .algebra.multistep_evolution import (
    EvolutionStepQualification,
    MultiStepEvolutionAssessment,
    MultiStepEvolutionPlan,
)
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, utc_now
from .models import EvidenceArtifact


IMPROVEMENT_STORE_VERSION = "saa-improvement-ledger-v1"
IMPROVEMENT_STORE_SCHEMA_VERSION = 1


def _ref(kind: str, signature: str) -> str:
    return f"{kind}:sha256:{signature}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable improvement-ledger collision at {path}")
        return
    atomic_write_text(path, serialized)


class ImprovementLoopStore:
    """Persistent SAA-11.3/11.4/12 ledger over immutable improvement artifacts."""

    def __init__(self, egcf_store: Any, adaptation_store: Any):
        required = ("state_root", "projection_path", "events", "get")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("ImprovementLoopStore requires EGCFStore")
        if any(not hasattr(adaptation_store, name) for name in ("get_candidate", "experiment_results", "promotions")):
            raise EGCFError("ImprovementLoopStore requires AdaptationLineageStore")
        self.egcf_store = egcf_store
        self.adaptation_store = adaptation_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "improvement-loop"
        self.plan_root = self.root / "evolution-plans" / "sha256"
        self.qualification_root = self.root / "evolution-step-qualifications" / "sha256"
        self.assessment_root = self.root / "evolution-assessments" / "sha256"
        self.aggregate_root = self.root / "experiment-aggregates" / "sha256"
        self.decision_root = self.root / "loop-decisions" / "sha256"
        for path in (
            self.plan_root,
            self.qualification_root,
            self.assessment_root,
            self.aggregate_root,
            self.decision_root,
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
                CREATE TABLE IF NOT EXISTS improvement_evolution_plans (
                    plan_ref TEXT PRIMARY KEY,
                    plan_signature TEXT NOT NULL UNIQUE,
                    root_algorithm_ref TEXT NOT NULL,
                    final_candidate_ref TEXT NOT NULL,
                    step_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_plan_candidate_idx
                    ON improvement_evolution_plans(final_candidate_ref);

                CREATE TABLE IF NOT EXISTS improvement_step_qualifications (
                    qualification_ref TEXT PRIMARY KEY,
                    qualification_signature TEXT NOT NULL UNIQUE,
                    plan_signature TEXT NOT NULL,
                    candidate_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step_qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_qualification_plan_idx
                    ON improvement_step_qualifications(plan_signature);

                CREATE TABLE IF NOT EXISTS improvement_evolution_assessments (
                    assessment_ref TEXT PRIMARY KEY,
                    assessment_signature TEXT NOT NULL UNIQUE,
                    plan_signature TEXT NOT NULL,
                    final_candidate_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evolution_qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS improvement_experiment_aggregates (
                    aggregate_ref TEXT PRIMARY KEY,
                    aggregate_signature TEXT NOT NULL UNIQUE,
                    design_signature TEXT NOT NULL,
                    experiment_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    sustained_improvement_qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_aggregate_design_idx
                    ON improvement_experiment_aggregates(design_signature);

                CREATE TABLE IF NOT EXISTS improvement_loop_decisions (
                    decision_ref TEXT PRIMARY KEY,
                    decision_signature TEXT NOT NULL UNIQUE,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    terminal INTEGER NOT NULL,
                    candidate_ref TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_decision_status_idx
                    ON improvement_loop_decisions(status);

                CREATE TABLE IF NOT EXISTS improvement_store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM improvement_store_metadata WHERE key='schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(IMPROVEMENT_STORE_SCHEMA_VERSION):
            self.rebuild_projection()

    def _path(self, root: Path, object_ref: str, kind: str) -> Path:
        actual, digest = parse_typed_id(object_ref)
        if actual != kind:
            raise EGCFError(f"improvement ledger expected {kind} reference")
        return root / digest[:2] / f"{digest}.json"

    def _event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        try:
            event = self.egcf_store.events.append(event_type, dict(payload))
            if hasattr(self.egcf_store, "_index_event"):
                self.egcf_store._index_event(event)
        except Exception:
            pass

    def _verify_evidence(self, evidence_ids: tuple[str, ...]) -> None:
        for evidence_id in evidence_ids:
            try:
                record = self.egcf_store.get(evidence_id)
            except Exception as exc:
                raise EGCFError(f"improvement evidence is not registered: {evidence_id}") from exc
            if not isinstance(record, EvidenceArtifact):
                raise EGCFError("improvement evidence must reference EvidenceArtifact")
            if record.success is not True or record.simulated:
                raise EGCFError("improvement evidence must be successful and non-simulated")
            if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
                raise EGCFError("improvement evidence must be deterministic/human grounded")

    def _write(self, root: Path, kind: str, signature: str, payload: Mapping[str, Any]) -> tuple[str, Path, str]:
        object_ref = _ref(kind, signature)
        created_at = utc_now()
        envelope = {
            "schema_version": 1,
            "store_version": IMPROVEMENT_STORE_VERSION,
            "object_id": object_ref,
            "created_at": created_at,
            "payload": dict(payload),
        }
        path = self._path(root, object_ref, kind)
        _immutable_write(path, envelope)
        return object_ref, path, created_at

    def register_evolution_plan(self, plan: MultiStepEvolutionPlan) -> str:
        if not isinstance(plan, MultiStepEvolutionPlan):
            raise EGCFError("improvement ledger requires MultiStepEvolutionPlan")
        self.adaptation_store.get_candidate(plan.final_candidate_ref)
        plan_ref, path, created_at = self._write(
            self.plan_root, "evolution-plan", plan.plan_signature, plan.to_dict()
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO improvement_evolution_plans VALUES(?,?,?,?,?,?,?,?)",
                (
                    plan_ref,
                    plan.plan_signature,
                    plan.root_algorithm_ref,
                    plan.final_candidate_ref,
                    len(plan.steps),
                    canonical_json(plan.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO improvement_store_metadata(key,value) VALUES('schema_version',?)",
                (str(IMPROVEMENT_STORE_SCHEMA_VERSION),),
            )
        self._event("saa_multistep_evolution_plan_registered", {"plan_ref": plan_ref})
        return plan_ref

    def _plan_payload(self, plan_signature: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM improvement_evolution_plans WHERE plan_signature=?",
                (plan_signature,),
            ).fetchone()
        if row is None:
            raise EGCFError("evolution plan is not registered")
        return json.loads(row[0])

    def register_step_qualification(self, qualification: EvolutionStepQualification) -> str:
        if not isinstance(qualification, EvolutionStepQualification):
            raise EGCFError("improvement ledger requires EvolutionStepQualification")
        plan = self._plan_payload(qualification.plan_signature)
        candidate_refs = {item["candidate_ref"] for item in plan["steps"]}
        if qualification.candidate_ref not in candidate_refs:
            raise EGCFError("step qualification candidate is not part of registered plan")
        self._verify_evidence(qualification.grounded_evidence_ids)
        qualification_ref, path, created_at = self._write(
            self.qualification_root,
            "evolution-step-qualification",
            qualification.qualification_signature,
            qualification.to_dict(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO improvement_step_qualifications VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    qualification_ref,
                    qualification.qualification_signature,
                    qualification.plan_signature,
                    qualification.candidate_ref,
                    qualification.status,
                    int(qualification.step_qualified),
                    canonical_json(qualification.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        return qualification_ref

    def register_evolution_assessment(self, assessment: MultiStepEvolutionAssessment) -> str:
        if not isinstance(assessment, MultiStepEvolutionAssessment):
            raise EGCFError("improvement ledger requires MultiStepEvolutionAssessment")
        plan = self._plan_payload(assessment.plan_signature)
        if assessment.final_candidate_ref != plan["final_candidate_ref"]:
            raise EGCFError("evolution assessment final candidate differs from registered plan")
        if assessment.evolution_qualified:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT qualification_signature,candidate_ref,step_qualified FROM improvement_step_qualifications WHERE plan_signature=?",
                    (assessment.plan_signature,),
                ).fetchall()
            stored = {row[0]: (row[1], bool(row[2])) for row in rows}
            if set(assessment.qualification_signatures) != set(stored):
                raise EGCFError("qualified evolution assessment is not backed by the exact stored step qualifications")
            if not all(value[1] for value in stored.values()):
                raise EGCFError("qualified evolution assessment references an unqualified intermediate step")
            expected_candidates = {item["candidate_ref"] for item in plan["steps"]}
            if {value[0] for value in stored.values()} != expected_candidates:
                raise EGCFError("qualified evolution assessment does not cover every plan candidate")
        assessment_ref, path, created_at = self._write(
            self.assessment_root,
            "evolution-assessment",
            assessment.assessment_signature,
            assessment.to_dict(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO improvement_evolution_assessments VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    assessment_ref,
                    assessment.assessment_signature,
                    assessment.plan_signature,
                    assessment.final_candidate_ref,
                    assessment.status,
                    int(assessment.evolution_qualified),
                    canonical_json(assessment.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        self._event("saa_multistep_evolution_assessed", {"assessment_ref": assessment_ref, "status": assessment.status})
        return assessment_ref

    def register_experiment_aggregate(self, aggregate: RepeatedExperimentAggregate) -> str:
        if not isinstance(aggregate, RepeatedExperimentAggregate):
            raise EGCFError("improvement ledger requires RepeatedExperimentAggregate")
        registered = {
            item["payload"]["result_signature"]: item["payload"]
            for item in self.adaptation_store.experiment_results(aggregate.design_signature)
        }
        if set(aggregate.result_signatures) != set(registered):
            raise EGCFError("experiment aggregate must bind exactly the registered repeated results for its design")
        if aggregate.sustained_improvement_qualified:
            if not all(payload.get("candidate_improvement_qualified") for payload in registered.values()):
                raise EGCFError("sustained improvement cannot be registered over an unqualified constituent result")
        aggregate_ref, path, created_at = self._write(
            self.aggregate_root,
            "experiment-aggregate",
            aggregate.aggregate_signature,
            aggregate.to_dict(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO improvement_experiment_aggregates VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    aggregate_ref,
                    aggregate.aggregate_signature,
                    aggregate.design_signature,
                    aggregate.experiment_count,
                    aggregate.status,
                    int(aggregate.sustained_improvement_qualified),
                    canonical_json(aggregate.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        self._event("saa_repeated_experiment_aggregate_registered", {"aggregate_ref": aggregate_ref, "status": aggregate.status})
        return aggregate_ref

    def register_loop_decision(self, decision: IntelligenceImprovementDecision) -> str:
        if not isinstance(decision, IntelligenceImprovementDecision):
            raise EGCFError("improvement ledger requires IntelligenceImprovementDecision")
        if decision.evolution_assessment_signature:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM improvement_evolution_assessments WHERE assessment_signature=?",
                    (decision.evolution_assessment_signature,),
                ).fetchone()
            if row is None:
                raise EGCFError("loop decision references an unregistered evolution assessment")
        if decision.experiment_aggregate_signature:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM improvement_experiment_aggregates WHERE aggregate_signature=?",
                    (decision.experiment_aggregate_signature,),
                ).fetchone()
            if row is None:
                raise EGCFError("loop decision references an unregistered experiment aggregate")
        if decision.promotion_ref:
            promotion_refs = {item["promotion_ref"] for item in self.adaptation_store.promotions()}
            if decision.promotion_ref not in promotion_refs:
                raise EGCFError("loop decision references an unregistered adaptation promotion")
        if decision.status == "CLOSED_LOOP_IMPROVEMENT_VERIFIED":
            if not decision.promotion_ref or not decision.post_promotion_receipt_signature:
                raise EGCFError("closed-loop verification requires promotion and post-promotion retrieval")
        decision_ref, path, created_at = self._write(
            self.decision_root,
            "improvement-loop-decision",
            decision.decision_signature,
            decision.to_dict(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO improvement_loop_decisions VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    decision_ref,
                    decision.decision_signature,
                    decision.phase,
                    decision.status,
                    int(decision.terminal),
                    decision.candidate_ref or "",
                    canonical_json(decision.to_dict()),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )
        self._event("saa_intelligence_improvement_loop_decision", {"decision_ref": decision_ref, "status": decision.status})
        return decision_ref

    def decisions(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT decision_ref,payload_json FROM improvement_loop_decisions ORDER BY created_at,decision_ref"
            ).fetchall()
        return [{"decision_ref": row[0], "payload": json.loads(row[1])} for row in rows]

    def aggregates(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT aggregate_ref,payload_json FROM improvement_experiment_aggregates ORDER BY aggregate_ref"
            ).fetchall()
        return [{"aggregate_ref": row[0], "payload": json.loads(row[1])} for row in rows]

    def rebuild_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS improvement_evolution_plans (
                    plan_ref TEXT PRIMARY KEY,plan_signature TEXT NOT NULL UNIQUE,root_algorithm_ref TEXT NOT NULL,
                    final_candidate_ref TEXT NOT NULL,step_count INTEGER NOT NULL,payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_plan_candidate_idx ON improvement_evolution_plans(final_candidate_ref);
                CREATE TABLE IF NOT EXISTS improvement_step_qualifications (
                    qualification_ref TEXT PRIMARY KEY,qualification_signature TEXT NOT NULL UNIQUE,
                    plan_signature TEXT NOT NULL,candidate_ref TEXT NOT NULL,status TEXT NOT NULL,
                    step_qualified INTEGER NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_qualification_plan_idx ON improvement_step_qualifications(plan_signature);
                CREATE TABLE IF NOT EXISTS improvement_evolution_assessments (
                    assessment_ref TEXT PRIMARY KEY,assessment_signature TEXT NOT NULL UNIQUE,plan_signature TEXT NOT NULL,
                    final_candidate_ref TEXT NOT NULL,status TEXT NOT NULL,evolution_qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS improvement_experiment_aggregates (
                    aggregate_ref TEXT PRIMARY KEY,aggregate_signature TEXT NOT NULL UNIQUE,design_signature TEXT NOT NULL,
                    experiment_count INTEGER NOT NULL,status TEXT NOT NULL,sustained_improvement_qualified INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_aggregate_design_idx ON improvement_experiment_aggregates(design_signature);
                CREATE TABLE IF NOT EXISTS improvement_loop_decisions (
                    decision_ref TEXT PRIMARY KEY,decision_signature TEXT NOT NULL UNIQUE,phase TEXT NOT NULL,status TEXT NOT NULL,
                    terminal INTEGER NOT NULL,candidate_ref TEXT NOT NULL,payload_json TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS improvement_decision_status_idx ON improvement_loop_decisions(status);
                CREATE TABLE IF NOT EXISTS improvement_store_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                DELETE FROM improvement_evolution_plans;
                DELETE FROM improvement_step_qualifications;
                DELETE FROM improvement_evolution_assessments;
                DELETE FROM improvement_experiment_aggregates;
                DELETE FROM improvement_loop_decisions;
                DELETE FROM improvement_store_metadata;
                """
            )
            specs = (
                (self.plan_root, "evolution-plan", "improvement_evolution_plans"),
                (self.qualification_root, "evolution-step-qualification", "improvement_step_qualifications"),
                (self.assessment_root, "evolution-assessment", "improvement_evolution_assessments"),
                (self.aggregate_root, "experiment-aggregate", "improvement_experiment_aggregates"),
                (self.decision_root, "improvement-loop-decision", "improvement_loop_decisions"),
            )
            for root, kind, table in specs:
                for path in sorted(root.glob("*/*.json")):
                    envelope = json.loads(path.read_text(encoding="utf-8"))
                    object_ref = envelope["object_id"]
                    actual, _ = parse_typed_id(object_ref)
                    if actual != kind:
                        raise EGCFError(f"invalid improvement-ledger object kind: {path}")
                    payload = envelope["payload"]
                    relative = str(path.relative_to(self.state_root))
                    created = envelope["created_at"]
                    if table == "improvement_evolution_plans":
                        connection.execute(
                            "INSERT INTO improvement_evolution_plans VALUES(?,?,?,?,?,?,?,?)",
                            (object_ref,payload["plan_signature"],payload["root_algorithm_ref"],payload["final_candidate_ref"],len(payload["steps"]),canonical_json(payload),relative,created),
                        )
                    elif table == "improvement_step_qualifications":
                        connection.execute(
                            "INSERT INTO improvement_step_qualifications VALUES(?,?,?,?,?,?,?,?,?)",
                            (object_ref,payload["qualification_signature"],payload["plan_signature"],payload["candidate_ref"],payload["status"],int(payload["step_qualified"]),canonical_json(payload),relative,created),
                        )
                    elif table == "improvement_evolution_assessments":
                        connection.execute(
                            "INSERT INTO improvement_evolution_assessments VALUES(?,?,?,?,?,?,?,?,?)",
                            (object_ref,payload["assessment_signature"],payload["plan_signature"],payload["final_candidate_ref"],payload["status"],int(payload["evolution_qualified"]),canonical_json(payload),relative,created),
                        )
                    elif table == "improvement_experiment_aggregates":
                        connection.execute(
                            "INSERT INTO improvement_experiment_aggregates VALUES(?,?,?,?,?,?,?,?,?)",
                            (object_ref,payload["aggregate_signature"],payload["design_signature"],payload["experiment_count"],payload["status"],int(payload["sustained_improvement_qualified"]),canonical_json(payload),relative,created),
                        )
                    else:
                        connection.execute(
                            "INSERT INTO improvement_loop_decisions VALUES(?,?,?,?,?,?,?,?,?)",
                            (object_ref,payload["decision_signature"],payload["phase"],payload["status"],int(payload["terminal"]),payload.get("candidate_ref") or "",canonical_json(payload),relative,created),
                        )
            connection.execute(
                "INSERT INTO improvement_store_metadata(key,value) VALUES('schema_version',?)",
                (str(IMPROVEMENT_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO improvement_store_metadata(key,value) VALUES('rebuilt_at',?)",
                (utc_now(),),
            )
