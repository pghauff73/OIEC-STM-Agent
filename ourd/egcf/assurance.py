from __future__ import annotations

from typing import Any, Dict

from .decisions import DecisionManager
from .evidence import EvidenceManager
from .ids import utc_now
from .invariants import InvariantManager
from .models import AssuranceCase
from .store import EGCFStore


class AssuranceManager:
    def __init__(
        self,
        store: EGCFStore,
        evidence: EvidenceManager,
        invariants: InvariantManager,
        decisions: DecisionManager,
    ):
        self.store = store
        self.evidence = evidence
        self.invariants = invariants
        self.decisions = decisions

    def generate(
        self,
        subject_id: str,
        top_claim: str,
        *,
        capability_facts: Dict[str, Any] | None = None,
        approval_facts: Dict[str, Any] | None = None,
        rollback_argument: Dict[str, Any] | None = None,
        uncertainties: list[str] | None = None,
    ) -> AssuranceCase:
        artifacts = self.evidence.artifacts(subject_id)
        confidence = self.evidence.confidence(subject_id)
        evidence_conflicts = self.evidence.conflicts(subject_id)
        invariant_conflicts = self.invariants.conflicts()
        decision_conflicts = self.decisions.conflicts()
        active_invariants = self.invariants.records(active_only=True)
        active_decisions = self.decisions.records(active_only=True)
        supporting = [artifact.object_id for artifact in artifacts if artifact.success is not False]
        refuting = [artifact.object_id for artifact in artifacts if artifact.success is False]
        gaps = list(confidence.blocking_gaps)
        conflicts = [
            *[item["reason"] for item in evidence_conflicts],
            *[item["reason"] for item in invariant_conflicts],
            *[item["reason"] for item in decision_conflicts],
        ]
        approval = dict(approval_facts or {})
        rollback = dict(rollback_argument or {})
        if not approval.get("satisfied", False):
            gaps.append("approval not satisfied")
        if rollback.get("required", False) and not rollback.get("covered", False):
            gaps.append("rollback coverage missing")
        conclusion = "SUPPORTED" if supporting and not refuting and not gaps and not conflicts else "NOT_SUPPORTED"
        case = AssuranceCase(
            subject_id=subject_id,
            top_claim=top_claim,
            subclaims=[
                {"claim": "capability requirements are authorized", "status": bool(capability_facts)},
                {"claim": "evidence requirements are covered", "status": not confidence.blocking_gaps},
                {"claim": "approval requirements are satisfied", "status": approval.get("satisfied", False)},
                {"claim": "rollback requirements are covered", "status": not rollback.get("required", False) or rollback.get("covered", False)},
            ],
            arguments=[
                {"kind": "confidence", "assessment_id": confidence.object_id, "conclusion": confidence.conclusion},
            ],
            supporting_evidence=supporting,
            refuting_evidence=refuting,
            invariant_ids=[record.object_id for record in active_invariants],
            decision_ids=[record.object_id for record in active_decisions],
            capability_facts=dict(capability_facts or {}),
            approval_facts=approval,
            rollback_argument=rollback,
            gaps=sorted(set(gaps)),
            conflicts=sorted(set(conflicts)),
            uncertainties=list(uncertainties or confidence.known_unknowns),
            conclusion=conclusion,
            created_at=utc_now(),
        )
        self.store.register(case)
        return case
