#!/usr/bin/env python3
"""Canonical launcher and public imports for OIEC-STM-Agent."""

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
