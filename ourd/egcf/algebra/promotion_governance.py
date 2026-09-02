from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .knowledge_integrity import KnowledgeIntegrityTrajectory
from .oiec_bench_gate import OIECBenchGateAssessment


PROMOTION_GOVERNANCE_VERSION = "saa-canonical-promotion-governance-v1"


@dataclass(frozen=True)
class CanonicalPromotionGovernanceAssessment:
    candidate_ref: str
    benchmark_gate_signature: str
    integrity_trajectory_signature: str
    benchmark_required: bool
    integrity_required: bool
    blocking_reasons: Tuple[str, ...]
    status: str
    canonical_promotion_allowed: bool
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "benchmark_gate_signature": self.benchmark_gate_signature,
            "integrity_trajectory_signature": self.integrity_trajectory_signature,
            "benchmark_required": self.benchmark_required,
            "integrity_required": self.integrity_required,
            "blocking_reasons": list(self.blocking_reasons),
            "status": self.status,
            "canonical_promotion_allowed": self.canonical_promotion_allowed,
            "assessment_signature": self.assessment_signature,
        }


def assess_canonical_promotion_governance(
    *,
    candidate_ref: str,
    benchmark_gate: OIECBenchGateAssessment | None = None,
    integrity_trajectory: KnowledgeIntegrityTrajectory | None = None,
    require_benchmark_gate: bool = True,
    require_integrity_gate: bool = True,
) -> CanonicalPromotionGovernanceAssessment:
    candidate = str(candidate_ref).strip()
    if not candidate:
        raise EGCFError("canonical promotion governance requires candidate_ref")
    blockers: list[str] = []
    benchmark_signature = ""
    integrity_signature = ""
    if require_benchmark_gate:
        if benchmark_gate is None:
            blockers.append("OIEC_BENCH_GATE_MISSING")
        else:
            if benchmark_gate.candidate_ref != candidate:
                raise EGCFError("OIEC-Bench gate belongs to a different candidate")
            benchmark_signature = benchmark_gate.assessment_signature
            if not benchmark_gate.canonical_promotion_eligible:
                blockers.append(f"OIEC_BENCH_GATE:{benchmark_gate.status}")
    elif benchmark_gate is not None:
        if benchmark_gate.candidate_ref != candidate:
            raise EGCFError("OIEC-Bench gate belongs to a different candidate")
        benchmark_signature = benchmark_gate.assessment_signature

    if require_integrity_gate:
        if integrity_trajectory is None:
            blockers.append("KNOWLEDGE_INTEGRITY_GATE_MISSING")
        else:
            integrity_signature = integrity_trajectory.trajectory_signature
            if not integrity_trajectory.knowledge_integrity_qualified:
                blockers.append(f"KNOWLEDGE_INTEGRITY:{integrity_trajectory.status}")
    elif integrity_trajectory is not None:
        integrity_signature = integrity_trajectory.trajectory_signature

    allowed = not blockers
    status = "CANONICAL_PROMOTION_GOVERNANCE_PASSED" if allowed else "CANONICAL_PROMOTION_GOVERNANCE_BLOCKED"
    payload = {
        "version": PROMOTION_GOVERNANCE_VERSION,
        "candidate_ref": candidate,
        "benchmark_gate_signature": benchmark_signature,
        "integrity_trajectory_signature": integrity_signature,
        "benchmark_required": bool(require_benchmark_gate),
        "integrity_required": bool(require_integrity_gate),
        "blocking_reasons": blockers,
        "status": status,
    }
    return CanonicalPromotionGovernanceAssessment(
        candidate_ref=candidate,
        benchmark_gate_signature=benchmark_signature,
        integrity_trajectory_signature=integrity_signature,
        benchmark_required=bool(require_benchmark_gate),
        integrity_required=bool(require_integrity_gate),
        blocking_reasons=tuple(blockers),
        status=status,
        canonical_promotion_allowed=allowed,
        assessment_signature=sha256_json(payload),
    )
