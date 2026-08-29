"""Public facade for SAA-10 unified mathematical and reasoning retrieval."""

from .algebra.unified_retrieval import (
    MAX_UNIFIED_MATHEMATICAL_RESULTS,
    UNIFIED_RETRIEVAL_VERSION,
    MathematicalFitAssessment,
    UnifiedProblemRequirements,
    UnifiedRetrievalDecision,
    evaluate_mathematical_fit,
    retrieve_unified_solution,
)

__all__ = [
    "MAX_UNIFIED_MATHEMATICAL_RESULTS",
    "UNIFIED_RETRIEVAL_VERSION",
    "MathematicalFitAssessment",
    "UnifiedProblemRequirements",
    "UnifiedRetrievalDecision",
    "evaluate_mathematical_fit",
    "retrieve_unified_solution",
]
