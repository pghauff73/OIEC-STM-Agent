"""Public facade for SAA-12 closed improvement and knowledge governance."""

from .algebra.failure_algebra import (
    FAILURE_ALGEBRA_VERSION,
    FAILURE_CLASSES,
    CanonicalFailurePattern,
    FailureMatchAssessment,
    FailureObservation,
    canonicalize_failure,
    compare_failure_to_pattern,
    make_failure_observation,
)
from .algebra.improvement_scheduling import (
    IMPROVEMENT_SCHEDULING_VERSION,
    OPPORTUNITY_KINDS,
    ImprovementOpportunity,
    ImprovementSchedule,
    ImprovementScheduleEntry,
    ImprovementSchedulingPolicy,
    make_improvement_opportunity,
    schedule_improvements,
)
from .algebra.intelligence_loop import (
    INTELLIGENCE_LOOP_VERSION,
    IntelligenceImprovementDecision,
    evaluate_intelligence_improvement_loop,
)
from .algebra.knowledge_integrity import (
    KNOWLEDGE_INTEGRITY_VERSION,
    KnowledgeIntegrityPolicy,
    KnowledgeIntegritySnapshot,
    KnowledgeIntegrityTrajectory,
    assess_integrity_trajectory,
    make_integrity_snapshot,
)
from .algebra.oiec_bench_gate import (
    OIEC_BENCH_GATE_VERSION,
    OIEC_BENCH_TRACKS,
    OIECBenchGateAssessment,
    OIECBenchGatePolicy,
    OIECBenchProfile,
    make_oiec_bench_profile,
    qualify_oiec_bench_gate,
)
from .improvement_store import (
    IMPROVEMENT_STORE_SCHEMA_VERSION,
    IMPROVEMENT_STORE_VERSION,
    ImprovementLoopStore,
)
from .knowledge_governance_store import (
    KNOWLEDGE_GOVERNANCE_STORE_SCHEMA_VERSION,
    KNOWLEDGE_GOVERNANCE_STORE_VERSION,
    KnowledgeGovernanceStore,
)

__all__ = [
    "INTELLIGENCE_LOOP_VERSION",
    "IMPROVEMENT_STORE_VERSION",
    "IMPROVEMENT_STORE_SCHEMA_VERSION",
    "FAILURE_ALGEBRA_VERSION",
    "OIEC_BENCH_GATE_VERSION",
    "KNOWLEDGE_INTEGRITY_VERSION",
    "IMPROVEMENT_SCHEDULING_VERSION",
    "KNOWLEDGE_GOVERNANCE_STORE_VERSION",
    "KNOWLEDGE_GOVERNANCE_STORE_SCHEMA_VERSION",
    "FAILURE_CLASSES",
    "OIEC_BENCH_TRACKS",
    "OPPORTUNITY_KINDS",
    "IntelligenceImprovementDecision",
    "ImprovementLoopStore",
    "FailureObservation",
    "CanonicalFailurePattern",
    "FailureMatchAssessment",
    "OIECBenchProfile",
    "OIECBenchGatePolicy",
    "OIECBenchGateAssessment",
    "KnowledgeIntegritySnapshot",
    "KnowledgeIntegrityPolicy",
    "KnowledgeIntegrityTrajectory",
    "ImprovementOpportunity",
    "ImprovementSchedulingPolicy",
    "ImprovementScheduleEntry",
    "ImprovementSchedule",
    "KnowledgeGovernanceStore",
    "evaluate_intelligence_improvement_loop",
    "make_failure_observation",
    "canonicalize_failure",
    "compare_failure_to_pattern",
    "make_oiec_bench_profile",
    "qualify_oiec_bench_gate",
    "make_integrity_snapshot",
    "assess_integrity_trajectory",
    "make_improvement_opportunity",
    "schedule_improvements",
]
