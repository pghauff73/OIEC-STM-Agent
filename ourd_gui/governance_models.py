from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

from ourd.egcf.capabilities import CAPABILITY_ORDER
from ourd.egcf.models import (
    ApprovalRecord,
    AssuranceCase,
    CapabilityGrant,
    CapabilitySpec,
    ConfidenceAssessment,
    EvidenceArtifact,
    EvidenceRequirement,
    ExecutionPlan,
    QualificationRecord,
    SelectionDecision,
)

from .read_models import ReadOnlyEGCFRepository


CAPABILITY_DESCRIPTIONS = {
    "C0": "Observe only",
    "C1": "Analyse",
    "C2": "Simulate",
    "C3": "Local mutation",
    "C4": "External mutation",
    "C5": "Critical / destructive",
}


@dataclass(frozen=True)
class CapabilityLevelView:
    level: str
    description: str
    status: str
    reason: str
    capability_names: tuple[str, ...]
    grant_ids: tuple[str, ...]
    capability_specs: tuple[Mapping[str, object], ...]
    grant_details: tuple[Mapping[str, object], ...]


def _expired(value: str, now: datetime) -> bool:
    if not value:
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= now


def build_capability_ladder(
    repository: ReadOnlyEGCFRepository,
    *,
    plan: ExecutionPlan | None = None,
    now: datetime | None = None,
) -> tuple[CapabilityLevelView, ...]:
    now = now or datetime.now(timezone.utc)
    specs = [
        record
        for record in repository.list("capability-spec")
        if isinstance(record, CapabilitySpec)
    ]
    grants = [
        record
        for record in repository.list("capability-grant")
        if isinstance(record, CapabilityGrant) and not _expired(record.expires_at, now)
    ]
    spec_level = {spec.name: spec.level for spec in specs}
    levels: list[CapabilityLevelView] = []
    for level in CAPABILITY_ORDER:
        eligible_grants = [
            grant
            for grant in grants
            if CAPABILITY_ORDER.get(grant.capability_ceiling, -1) >= CAPABILITY_ORDER[level]
        ]
        names = sorted(
            {
                capability
                for grant in eligible_grants
                for capability in grant.capabilities
                if spec_level.get(capability) == level
            }
        )
        grant_ids = tuple(grant.object_id for grant in eligible_grants)
        level_specs = tuple(
            {"object_id": spec.object_id, **asdict(spec)}
            for spec in specs
            if spec.level == level
        )
        grant_details = tuple(
            {"object_id": grant.object_id, **asdict(grant)}
            for grant in eligible_grants
        )
        if not eligible_grants:
            status = "blocked"
            reason = "No active grant reaches this capability level."
        elif level in {"C0", "C1"}:
            status = "available"
            reason = "Active authority grant permits deterministic read and analysis operations."
        elif not names:
            status = "blocked"
            reason = "The active grant ceiling reaches this level but grants no matching capability."
        elif level == "C2":
            status = "available"
            reason = "Simulation is authorized without filesystem mutation."
        else:
            needs_approval = level in {"C4", "C5"} or any(
                "human" in grant.approval_modes for grant in eligible_grants
            )
            if plan is not None and plan.approval_policy in {"human", "quorum"}:
                needs_approval = True
            status = "gated" if needs_approval else "available"
            reason = (
                "Evidence and exact scoped human approval are required."
                if needs_approval
                else "The active grant permits this level within its recorded scope."
            )
        levels.append(
            CapabilityLevelView(
                level=level,
                description=CAPABILITY_DESCRIPTIONS[level],
                status=status,
                reason=reason,
                capability_names=tuple(names),
                grant_ids=grant_ids,
                capability_specs=level_specs,
                grant_details=grant_details,
            )
        )
    return tuple(levels)


COVERAGE_DIMENSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("C_I", "Invariant", ("invariant",)),
    ("C_D", "Dimension", ("dimension", "nominal", "test", "observation")),
    ("C_B", "Boundary", ("boundary",)),
    ("C_T", "Interaction", ("interaction",)),
    ("C_M", "Mutation", ("mutation",)),
    ("C_R", "Regression", ("regression",)),
)


@dataclass(frozen=True)
class CoverageDimensionView:
    code: str
    name: str
    coverage: float | None
    covered: int
    total: int


@dataclass(frozen=True)
class EvidenceDashboardModel:
    evidence_ids: tuple[str, ...]
    subject_ids: tuple[str, ...]
    dimensions: tuple[CoverageDimensionView, ...]
    classes: Mapping[str, int]
    verdict: str
    blocking_gaps: tuple[str, ...]
    known_unknowns: tuple[str, ...]
    conflicts: tuple[str, ...]
    simulated_evidence_ids: tuple[str, ...]


def _expand_evidence_ids(
    repository: ReadOnlyEGCFRepository,
    identifiers: Iterable[str],
) -> tuple[str, ...]:
    pending = list(dict.fromkeys(str(item) for item in identifiers if item))
    resolved: list[str] = []
    seen: set[str] = set()
    while pending:
        identifier = pending.pop(0)
        if identifier in seen:
            continue
        seen.add(identifier)
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            resolved.append(identifier)
            continue
        if isinstance(record, EvidenceArtifact):
            resolved.append(identifier)
        elif isinstance(record, (QualificationRecord, SelectionDecision, ConfidenceAssessment)):
            pending.extend(record.evidence_ids)
        elif isinstance(record, AssuranceCase):
            pending.extend(record.supporting_evidence)
            pending.extend(record.refuting_evidence)
        elif isinstance(record, ExecutionPlan):
            pending.extend(record.evidence_ids)
        else:
            resolved.append(identifier)
    return tuple(dict.fromkeys(resolved))


def build_evidence_dashboard(
    repository: ReadOnlyEGCFRepository,
    identifiers: Iterable[str],
) -> EvidenceDashboardModel:
    requested_ids = tuple(dict.fromkeys(str(item) for item in identifiers if item))
    expanded_ids = _expand_evidence_ids(repository, requested_ids)
    artifacts: list[EvidenceArtifact] = []
    blocking_gaps: list[str] = []
    known_unknowns: list[str] = []
    conflicts: list[str] = []
    assurance_conclusions: list[str] = []
    confidence_conclusions: list[str] = []
    for identifier in requested_ids:
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            continue
        if isinstance(record, ConfidenceAssessment):
            blocking_gaps.extend(record.blocking_gaps)
            known_unknowns.extend(record.known_unknowns)
            conflicts.extend(record.conflicts)
            confidence_conclusions.append(record.conclusion)
        elif isinstance(record, AssuranceCase):
            blocking_gaps.extend(record.gaps)
            known_unknowns.extend(record.uncertainties)
            conflicts.extend(record.conflicts)
            assurance_conclusions.append(record.conclusion)
    for identifier in expanded_ids:
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            continue
        if isinstance(record, EvidenceArtifact):
            artifacts.append(record)
            known_unknowns.extend(record.limitations)
    subject_ids = tuple(sorted({artifact.subject_id for artifact in artifacts if artifact.subject_id}))
    requirements = [
        record
        for record in repository.list("evidence-requirement")
        if isinstance(record, EvidenceRequirement) and record.subject_id in subject_ids
    ]
    dimensions: list[CoverageDimensionView] = []
    for code, name, categories in COVERAGE_DIMENSIONS:
        category_requirements = [
            requirement
            for requirement in requirements
            if requirement.category.casefold() in categories
        ]
        category_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.category.casefold() in categories and not artifact.simulated
        ]
        if category_requirements:
            covered = sum(
                any(
                    requirement.object_id in artifact.requirement_ids
                    and artifact.success is not False
                    for artifact in category_artifacts
                )
                for requirement in category_requirements
            )
            total = len(category_requirements)
            coverage: float | None = covered / total
        elif category_artifacts:
            covered = sum(artifact.success is not False for artifact in category_artifacts)
            total = len(category_artifacts)
            coverage = covered / total
        else:
            covered = 0
            total = 0
            coverage = None
        dimensions.append(CoverageDimensionView(code, name, coverage, covered, total))
    class_names = {
        "nominal": "Nominal",
        "test": "Nominal",
        "observation": "Nominal",
        "dimension": "Nominal",
        "boundary": "Boundary",
        "counterexample": "Counterexample",
        "interaction": "Interaction",
        "regression": "Regression",
    }
    classes = {name: 0 for name in (*class_names.values(), "Unknown", "Simulated")}
    for artifact in artifacts:
        if artifact.simulated:
            classes["Simulated"] += 1
        else:
            classes[class_names.get(artifact.category.casefold(), "Unknown")] += 1
    simulated_evidence_ids = tuple(
        artifact.object_id for artifact in artifacts if artifact.simulated
    )
    real_artifacts = [artifact for artifact in artifacts if not artifact.simulated]
    if simulated_evidence_ids:
        known_unknowns.append("simulated evidence does not establish real execution")
    refuting = any(artifact.success is False for artifact in real_artifacts)
    if simulated_evidence_ids and not real_artifacts:
        verdict = "SIMULATION_ONLY"
    elif conflicts or refuting or "NOT_SUPPORTED" in assurance_conclusions:
        verdict = "REFUSE"
    elif blocking_gaps or "BLOCKED" in confidence_conclusions:
        verdict = "BLOCKED"
    elif "SUPPORTED" in assurance_conclusions or "HIGH" in confidence_conclusions:
        verdict = "APPROVE"
    elif artifacts:
        verdict = "APPROVE_WITH_LIMITS"
    else:
        verdict = "UNKNOWN"
    return EvidenceDashboardModel(
        evidence_ids=expanded_ids,
        subject_ids=subject_ids,
        dimensions=tuple(dimensions),
        classes=classes,
        verdict=verdict,
        blocking_gaps=tuple(dict.fromkeys(blocking_gaps)),
        known_unknowns=tuple(dict.fromkeys(known_unknowns)),
        conflicts=tuple(dict.fromkeys(conflicts)),
        simulated_evidence_ids=simulated_evidence_ids,
    )


def matching_approval(
    repository: ReadOnlyEGCFRepository,
    plan: ExecutionPlan,
    approval_ids: Iterable[str],
    *,
    now: datetime | None = None,
) -> ApprovalRecord | None:
    now = now or datetime.now(timezone.utc)
    for approval_id in reversed(tuple(approval_ids)):
        try:
            approval = repository.get(approval_id)
        except (OSError, ValueError, KeyError):
            continue
        if not isinstance(approval, ApprovalRecord):
            continue
        if approval.plan_id != plan.object_id or approval.plan_hash != plan.object_id.partition(":sha256:")[2]:
            continue
        if not approval.human or _expired(approval.expires_at, now):
            continue
        if approval.use_count >= approval.use_limit:
            continue
        return approval
    return None
