"""Governed coding-agent core."""

from .agent import OURDAgent
from .authority import AuthorityManifest
from .errors import AgentCancelledError, PolicyError
from .models import (
    AttemptKey,
    BoundaryState,
    CollisionRecord,
    DimensionBudget,
    EONAction,
    EvidenceArtifact,
    FiniteEvidenceState,
    GateDecision,
    GovernanceRecord,
    ProgressCertificate,
    RuntimeState,
    SCORE_SCALE,
    TransactionRecord,
)
from .oiec import BoundedTransitionKernel
from .workspace import Workspace
from .egcf import EGCFEngine

__all__ = [
    "AuthorityManifest",
    "AgentCancelledError",
    "AttemptKey",
    "BoundaryState",
    "BoundedTransitionKernel",
    "CollisionRecord",
    "DimensionBudget",
    "EONAction",
    "EGCFEngine",
    "EvidenceArtifact",
    "FiniteEvidenceState",
    "GateDecision",
    "GovernanceRecord",
    "OURDAgent",
    "PolicyError",
    "ProgressCertificate",
    "RuntimeState",
    "SCORE_SCALE",
    "TransactionRecord",
    "Workspace",
]
