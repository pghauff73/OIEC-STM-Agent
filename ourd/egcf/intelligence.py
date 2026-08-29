"""Public facade for the SAA-12 closed qualified intelligence-improvement loop."""

from .algebra.intelligence_loop import (
    INTELLIGENCE_LOOP_VERSION,
    IntelligenceImprovementDecision,
    evaluate_intelligence_improvement_loop,
)
from .improvement_store import (
    IMPROVEMENT_STORE_SCHEMA_VERSION,
    IMPROVEMENT_STORE_VERSION,
    ImprovementLoopStore,
)

__all__ = [
    "INTELLIGENCE_LOOP_VERSION",
    "IMPROVEMENT_STORE_VERSION",
    "IMPROVEMENT_STORE_SCHEMA_VERSION",
    "IntelligenceImprovementDecision",
    "ImprovementLoopStore",
    "evaluate_intelligence_improvement_loop",
]
