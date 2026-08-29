"""Public facade for SAA-11 controlled algorithm adaptation."""

from .algebra.algorithm_adaptation import (
    ALGORITHM_ADAPTATION_VERSION,
    ALLOWED_ADAPTATION_DIMENSIONS,
    MAX_ADAPTATION_STEPS,
    AdaptationStep,
    AdaptedAlgorithmCandidate,
    ControlledAdaptationPlan,
    build_controlled_adaptation_plan,
    create_adapted_candidate,
)

__all__ = [
    "ALGORITHM_ADAPTATION_VERSION",
    "ALLOWED_ADAPTATION_DIMENSIONS",
    "MAX_ADAPTATION_STEPS",
    "AdaptationStep",
    "AdaptedAlgorithmCandidate",
    "ControlledAdaptationPlan",
    "build_controlled_adaptation_plan",
    "create_adapted_candidate",
]
