from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from .models import (
    CandidateSet,
    ContradictionRecord,
    ReasoningPath,
    SCORE_SCALE,
)


CRITICAL_CONTRADICTION_BP = 7_500


def _path_evidence(path: ReasoningPath) -> tuple[str, ...]:
    return tuple(
        sorted({evidence_id for step in path.steps for evidence_id in step.evidence_ids})
    )


def build_contradiction_records(candidates: CandidateSet) -> tuple[ContradictionRecord, ...]:
    paths = {path.path_id: path for path in candidates.paths}
    records = []
    for report in candidates.verifier_reports:
        path = paths[report.path_id]
        for index, contradiction in enumerate(report.contradictions):
            records.append(
                ContradictionRecord(
                    left_claim_id=f"{path.path_id}:conclusion",
                    right_claim_id=f"{report.report_id}:contradiction:{index}",
                    evidence_left=_path_evidence(path),
                    conflict_type="logical",
                    severity_bp=8_000,
                )
            )
    for report in candidates.falsifier_reports:
        path = paths[report.path_id]
        for index, _counterexample in enumerate(report.counterexamples):
            records.append(
                ContradictionRecord(
                    left_claim_id=f"{path.path_id}:conclusion",
                    right_claim_id=f"{report.report_id}:counterexample:{index}",
                    evidence_left=_path_evidence(path),
                    conflict_type="empirical",
                    severity_bp=max(6_000, report.severity_bp),
                )
            )
        for index, _alternative in enumerate(report.alternative_explanations):
            records.append(
                ContradictionRecord(
                    left_claim_id=f"{path.path_id}:conclusion",
                    right_claim_id=f"{report.report_id}:alternative:{index}",
                    evidence_left=_path_evidence(path),
                    conflict_type="causal",
                    severity_bp=max(5_000, report.severity_bp),
                )
            )
        for index, _direction in enumerate(report.reversed_causal_directions):
            records.append(
                ContradictionRecord(
                    left_claim_id=f"{path.path_id}:conclusion",
                    right_claim_id=f"{report.report_id}:causal-direction:{index}",
                    evidence_left=_path_evidence(path),
                    conflict_type="causal",
                    severity_bp=max(7_000, report.severity_bp),
                )
            )
    return tuple(sorted(records, key=lambda item: item.contradiction_id))


def resolve_contradiction(
    record: ContradictionRecord,
    *,
    resolution_evidence_ids: Iterable[str],
    status: str = "RESOLVED",
) -> ContradictionRecord:
    return replace(
        record,
        contradiction_id="",
        resolution_status=status,
        resolution_evidence_ids=tuple(resolution_evidence_ids),
        signature="",
    )


def unresolved_critical_contradictions(
    records: Sequence[ContradictionRecord],
) -> tuple[ContradictionRecord, ...]:
    return tuple(
        record
        for record in records
        if record.resolution_status == "UNRESOLVED"
        and record.severity_bp >= CRITICAL_CONTRADICTION_BP
    )


def cap_confidence_for_contradictions(
    confidence_bp: int,
    records: Sequence[ContradictionRecord],
) -> int:
    critical = unresolved_critical_contradictions(records)
    if critical:
        return min(int(confidence_bp), 4_999)
    unresolved = sum(
        1 for record in records if record.resolution_status == "UNRESOLVED"
    )
    return max(0, min(SCORE_SCALE, int(confidence_bp) - unresolved * 500))


__all__ = [
    "CRITICAL_CONTRADICTION_BP",
    "build_contradiction_records",
    "cap_confidence_for_contradictions",
    "resolve_contradiction",
    "unresolved_critical_contradictions",
]
