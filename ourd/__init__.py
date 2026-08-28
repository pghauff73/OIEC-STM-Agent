"""Governed coding-agent core."""

from .agent import OURDAgent
from .authority import AuthorityManifest
from .errors import AgentCancelledError, PolicyError
from .formal_writing import (
    ArgumentEdge,
    ArgumentNode,
    ArgumentTopology,
    WRITING_PROFILES,
    profile_dimensions,
    research_backed_profile,
)
from .loop_control import (
    LoopProgressController,
    TransitionAssessment,
    VerifiedProjection,
    model_belief_record,
    semantic_step_signature,
    verified_projection,
)
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
from .production_agent import ProductionOURDAgent
from .workspace import Workspace
from .egcf import EGCFEngine

__all__ = [
    "ArgumentEdge",
    "ArgumentNode",
    "ArgumentTopology",
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
    "LoopProgressController",
    "OURDAgent",
    "PolicyError",
    "ProductionOURDAgent",
    "ProgressCertificate",
    "RuntimeState",
    "SCORE_SCALE",
    "TransactionRecord",
    "TransitionAssessment",
    "VerifiedProjection",
    "WRITING_PROFILES",
    "Workspace",
    "model_belief_record",
    "profile_dimensions",
    "research_backed_profile",
    "semantic_step_signature",
    "verified_projection",
]
