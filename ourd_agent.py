#!/usr/bin/env python3
"""Compatibility launcher and public imports for the OURD coding agent."""

from ourd import (
    AuthorityManifest,
    CollisionRecord,
    EONAction,
    EvidenceArtifact,
    GateDecision,
    GovernanceRecord,
    OURDAgent,
    PolicyError,
    RuntimeState,
    TransactionRecord,
    Workspace,
)
from ourd.cli import main

EvidenceGate = GateDecision

__all__ = [
    "AuthorityManifest",
    "CollisionRecord",
    "EONAction",
    "EvidenceArtifact",
    "EvidenceGate",
    "GateDecision",
    "GovernanceRecord",
    "OURDAgent",
    "PolicyError",
    "RuntimeState",
    "TransactionRecord",
    "Workspace",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
