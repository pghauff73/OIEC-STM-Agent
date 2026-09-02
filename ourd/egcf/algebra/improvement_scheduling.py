from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact


IMPROVEMENT_SCHEDULING_VERSION = "saa-improvement-scheduling-v1"
OPPORTUNITY_KINDS = {
    "FAILURE_PATTERN",
    "BENCHMARK_GAP",
    "INTEGRITY_SIGNAL",
    "RETRIEVAL_GAP",
    "EXPERIMENT_TRADEOFF",
    "SEMANTIC_CONTRADICTION",
}


def _bp(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000:
        raise EGCFError(f"{label} must be integer basis points in 0..10000")
    return int(value)


def _ground_evidence(store: Any, evidence_ids: Sequence[str]) -> tuple[Tuple[str, ...], Tuple[str, ...]]:
    grounded: list[str] = []
    groups: set[str] = set()
    for evidence_id in sorted({str(value).strip() for value in evidence_ids if str(value).strip()}):
        try:
            record = store.get(evidence_id)
        except Exception as exc:
            raise EGCFError(f"SAA-12.4 scheduling evidence is not registered: {evidence_id}") from exc
        if not isinstance(record, EvidenceArtifact):
            raise EGCFError("SAA-12.4 scheduling evidence must reference EvidenceArtifact")
        if record.success is not True or record.simulated:
            raise EGCFError("SAA-12.4 scheduling evidence must be successful and non-simulated")
        if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
            raise EGCFError("SAA-12.4 scheduling evidence must be deterministic/human grounded")
        grounded.append(evidence_id)
        if record.independence_group:
            groups.add(record.independence_group)
    if not grounded:
        raise EGCFError("SAA-12.4 improvement opportunity requires grounded evidence")
    return tuple(grounded), tuple(sorted(groups))


@dataclass(frozen=True)
class ImprovementOpportunity:
    opportunity_id: str
    kind: str
    source_signature: str
    objective: str
    evidence_value_bp: int
    expected_impact_bp: int
    uncertainty_reduction_bp: int
    cost_bp: int
    risk_bp: int
    priority_bp: int
    evidence_ids: Tuple[str, ...]
    independence_groups: Tuple[str, ...]
    blocked_reasons: Tuple[str, ...]
    opportunity_signature: str

    @property
    def eligible(self) -> bool:
        return not self.blocked_reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "kind": self.kind,
            "source_signature": self.source_signature,
            "objective": self.objective,
            "evidence_value_bp": self.evidence_value_bp,
            "expected_impact_bp": self.expected_impact_bp,
            "uncertainty_reduction_bp": self.uncertainty_reduction_bp,
            "cost_bp": self.cost_bp,
            "risk_bp": self.risk_bp,
            "priority_bp": self.priority_bp,
            "evidence_ids": list(self.evidence_ids),
            "independence_groups": list(self.independence_groups),
            "blocked_reasons": list(self.blocked_reasons),
            "opportunity_signature": self.opportunity_signature,
            "eligible": self.eligible,
        }


@dataclass(frozen=True)
class ImprovementSchedulingPolicy:
    max_selected: int = 4
    total_cost_budget_bp: int = 20000
    maximum_risk_bp: int = 6000
    minimum_priority_bp: int = 1000

    def canonical(self) -> "ImprovementSchedulingPolicy":
        selected = int(self.max_selected)
        if selected < 1 or selected > 16:
            raise EGCFError("SAA-12.4 max_selected outside bounded range")
        budget = int(self.total_cost_budget_bp)
        if budget < 0 or budget > 160000:
            raise EGCFError("SAA-12.4 total cost budget outside bounded range")
        risk = _bp(self.maximum_risk_bp, "maximum scheduling risk")
        priority = _bp(self.minimum_priority_bp, "minimum scheduling priority")
        return ImprovementSchedulingPolicy(selected, budget, risk, priority)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_selected": self.max_selected,
            "total_cost_budget_bp": self.total_cost_budget_bp,
            "maximum_risk_bp": self.maximum_risk_bp,
            "minimum_priority_bp": self.minimum_priority_bp,
        }


@dataclass(frozen=True)
class ImprovementScheduleEntry:
    opportunity_id: str
    opportunity_signature: str
    rank: int
    priority_bp: int
    allocated_cost_bp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "opportunity_signature": self.opportunity_signature,
            "rank": self.rank,
            "priority_bp": self.priority_bp,
            "allocated_cost_bp": self.allocated_cost_bp,
        }


@dataclass(frozen=True)
class ImprovementSchedule:
    selected: Tuple[ImprovementScheduleEntry, ...]
    deferred: Tuple[Tuple[str, str], ...]
    total_allocated_cost_bp: int
    status: str
    schedule_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": [item.to_dict() for item in self.selected],
            "deferred": [{"opportunity_id": key, "reason": reason} for key, reason in self.deferred],
            "total_allocated_cost_bp": self.total_allocated_cost_bp,
            "status": self.status,
            "schedule_signature": self.schedule_signature,
        }


def make_improvement_opportunity(
    store: Any,
    *,
    opportunity_id: str,
    kind: str,
    source_signature: str,
    objective: str,
    evidence_value_bp: int,
    expected_impact_bp: int,
    uncertainty_reduction_bp: int,
    cost_bp: int,
    risk_bp: int,
    evidence_ids: Sequence[str],
    blocked_reasons: Sequence[str] = (),
) -> ImprovementOpportunity:
    identifier = str(opportunity_id).strip()
    canonical_kind = str(kind).strip().upper()
    source = str(source_signature).strip().lower()
    goal = " ".join(str(objective).strip().split())
    if not identifier or not goal:
        raise EGCFError("SAA-12.4 opportunity id and objective are required")
    if canonical_kind not in OPPORTUNITY_KINDS:
        raise EGCFError(f"unsupported SAA-12.4 opportunity kind: {canonical_kind}")
    if len(source) != 64 or any(character not in "0123456789abcdef" for character in source):
        raise EGCFError("SAA-12.4 source_signature must be SHA-256")
    evidence_value = _bp(evidence_value_bp, "evidence value")
    impact = _bp(expected_impact_bp, "expected impact")
    uncertainty = _bp(uncertainty_reduction_bp, "uncertainty reduction")
    cost = _bp(cost_bp, "cost")
    risk = _bp(risk_bp, "risk")
    evidence, groups = _ground_evidence(store, evidence_ids)
    blockers = tuple(sorted({" ".join(str(value).strip().split()) for value in blocked_reasons if str(value).strip()}))
    benefit = (evidence_value * impact) // 10000
    burden = (cost + risk) // 2
    priority = max(0, min(10000, benefit + uncertainty // 4 - burden // 2))
    payload = {
        "version": IMPROVEMENT_SCHEDULING_VERSION,
        "opportunity_id": identifier,
        "kind": canonical_kind,
        "source_signature": source,
        "objective": goal,
        "evidence_value_bp": evidence_value,
        "expected_impact_bp": impact,
        "uncertainty_reduction_bp": uncertainty,
        "cost_bp": cost,
        "risk_bp": risk,
        "priority_bp": priority,
        "evidence_ids": list(evidence),
        "independence_groups": list(groups),
        "blocked_reasons": list(blockers),
    }
    return ImprovementOpportunity(
        opportunity_id=identifier,
        kind=canonical_kind,
        source_signature=source,
        objective=goal,
        evidence_value_bp=evidence_value,
        expected_impact_bp=impact,
        uncertainty_reduction_bp=uncertainty,
        cost_bp=cost,
        risk_bp=risk,
        priority_bp=priority,
        evidence_ids=evidence,
        independence_groups=groups,
        blocked_reasons=blockers,
        opportunity_signature=sha256_json(payload),
    )


def schedule_improvements(
    opportunities: Sequence[ImprovementOpportunity],
    policy: ImprovementSchedulingPolicy,
) -> ImprovementSchedule:
    canonical_policy = policy.canonical()
    if len({item.opportunity_signature for item in opportunities}) != len(opportunities):
        raise EGCFError("SAA-12.4 duplicate opportunity signatures cannot be scheduled twice")
    ranked = sorted(
        opportunities,
        key=lambda item: (-item.priority_bp, item.risk_bp, item.cost_bp, item.opportunity_id),
    )
    selected: list[ImprovementScheduleEntry] = []
    deferred: list[tuple[str, str]] = []
    allocated = 0
    for item in ranked:
        reason = ""
        if not item.eligible:
            reason = "BLOCKED:" + "; ".join(item.blocked_reasons)
        elif item.risk_bp > canonical_policy.maximum_risk_bp:
            reason = "RISK_CEILING_EXCEEDED"
        elif item.priority_bp < canonical_policy.minimum_priority_bp:
            reason = "PRIORITY_BELOW_THRESHOLD"
        elif len(selected) >= canonical_policy.max_selected:
            reason = "SELECTION_COUNT_BUDGET_EXHAUSTED"
        elif allocated + item.cost_bp > canonical_policy.total_cost_budget_bp:
            reason = "COST_BUDGET_EXHAUSTED"
        if reason:
            deferred.append((item.opportunity_id, reason))
            continue
        selected.append(
            ImprovementScheduleEntry(
                opportunity_id=item.opportunity_id,
                opportunity_signature=item.opportunity_signature,
                rank=len(selected) + 1,
                priority_bp=item.priority_bp,
                allocated_cost_bp=item.cost_bp,
            )
        )
        allocated += item.cost_bp
    status = "IMPROVEMENT_INVESTIGATIONS_SCHEDULED" if selected else "NO_ELIGIBLE_IMPROVEMENT_INVESTIGATION"
    payload = {
        "version": IMPROVEMENT_SCHEDULING_VERSION,
        "policy": canonical_policy.to_dict(),
        "selected": [item.to_dict() for item in selected],
        "deferred": deferred,
        "total_allocated_cost_bp": allocated,
        "status": status,
    }
    return ImprovementSchedule(
        selected=tuple(selected),
        deferred=tuple(deferred),
        total_allocated_cost_bp=allocated,
        status=status,
        schedule_signature=sha256_json(payload),
    )
