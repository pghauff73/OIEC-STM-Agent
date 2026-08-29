"""Public facade for SAA-10 unified retrieval, transfer and explainable fit."""

from .algebra.algorithm_transfer import (
    ALGORITHM_TRANSFER_VERSION,
    AlgorithmDomainContract,
    AlgorithmTransferAssessment,
    assess_algorithm_transfer,
)
from .algebra.retrieval_explanation import (
    RETRIEVAL_EXPLANATION_VERSION,
    CounterfactualFitChange,
    RetrievalExplanation,
    explain_unified_retrieval,
)
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
    "ALGORITHM_TRANSFER_VERSION",
    "RETRIEVAL_EXPLANATION_VERSION",
    "MAX_UNIFIED_MATHEMATICAL_RESULTS",
    "UNIFIED_RETRIEVAL_VERSION",
    "AlgorithmDomainContract",
    "AlgorithmTransferAssessment",
    "CounterfactualFitChange",
    "RetrievalExplanation",
    "MathematicalFitAssessment",
    "UnifiedProblemRequirements",
    "UnifiedRetrievalDecision",
    "assess_algorithm_transfer",
    "explain_unified_retrieval",
    "evaluate_mathematical_fit",
    "retrieve_unified_solution",
]
