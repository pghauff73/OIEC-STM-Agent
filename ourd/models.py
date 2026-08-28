from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2}


def max_risk(*risks: str) -> str:
    invalid = [risk for risk in risks if risk not in RISK_ORDER]
    if invalid:
        raise ValueError(f"invalid risk values: {invalid}")
    return max(risks, key=RISK_ORDER.__getitem__)


@dataclass
class AuthorityManifest:
    schema_version: int = 1
    task_id: str = "read-only"
    goal: str = "Read-only repository inspection"
    source_snapshot_hash: str = ""
    allowed_paths: List[str] = field(default_factory=lambda: ["**"])
    forbidden_paths: List[str] = field(default_factory=lambda: [".ourd-agent/**"])
    read_capabilities: List[str] = field(
        default_factory=lambda: [
            "workspace.list",
            "workspace.read",
            "workspace.search",
            "git.status",
            "git.diff",
        ]
    )
    command_capabilities: List[str] = field(default_factory=list)
    semantic_capability_ceiling: str = "C1"
    semantic_capabilities: List[str] = field(default_factory=list)
    max_retries_per_action: int = 1
    max_automatic_risk: str = "L0"
    allow_l1_auto_apply: bool = False
    allow_interactive_l2: bool = False
    allow_yolo: bool = False
    mandatory_tests: List[str] = field(default_factory=list)
    mandatory_evidence: List[str] = field(default_factory=list)
    expires_at: str = ""
    operator: str = "unconfigured"
    authority_hash: str = ""
    read_only: bool = True


@dataclass
class GovernanceRecord:
    goal: str = ""
    constraints: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    relations: List[str] = field(default_factory=list)
    boundaries: List[str] = field(default_factory=list)
    excluded_scope: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    authority_hash: str = ""
    established: bool = False


@dataclass
class EvidenceArtifact:
    artifact_id: str
    kind: str
    description: str
    sha256: str
    action_id: str = ""
    source_snapshot_hash: str = ""
    source_event_id: str = ""
    path: str = ""
    command_capability: str = ""
    success: Optional[bool] = None


@dataclass
class TransactionRecord:
    transaction_id: str
    operation: str
    targets: List[str]
    source_snapshot_hash: str
    candidate_hash: str
    candidate_files: Dict[str, str]
    original_hashes: Dict[str, Optional[str]]
    diff: str
    authority_hash: str = ""
    status: str = "PREPARED"
    action_id: str = ""
    applied_hashes: Dict[str, str] = field(default_factory=dict)
    applied_snapshot_hash: str = ""
    backup_manifest: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    verification_evidence_ids: List[str] = field(default_factory=list)


@dataclass
class EONAction:
    action_id: str
    summary: str
    operation: str
    targets: List[str]
    preconditions: List[str]
    postconditions: List[str]
    preserve: List[str]
    evidence: List[str]
    model_risk: str
    effective_risk: str
    authority_hash: str
    source_snapshot_hash: str
    transaction_id: str = ""
    candidate_hash: str = ""
    command_capabilities: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    required_tests: List[str] = field(default_factory=list)
    expires_at: str = ""
    use_limit: int = 1
    use_count: int = 0


@dataclass
class GateDecision:
    decision_id: str
    action_id: str
    proposed_verdict: str
    verdict: str
    evidence_ids: List[str]
    evidence_categories: Dict[str, List[str]]
    satisfied_requirements: List[str]
    uncovered: List[str]
    limits: Dict[str, Any]
    reason: str


@dataclass
class CollisionRecord:
    collision_id: str
    timestamp: str
    action_id: str
    expected: str
    observed: str
    objects: List[str]
    boundary: str
    active_dimension: str
    frozen_dimensions: List[str]
    evidence_ids: List[str]
    proposed_correction: str
    falsifier: str
    retry_count: int
    disposition: str
    fingerprint: str


@dataclass
class RuntimeState:
    schema_version: int = 1
    authority: AuthorityManifest = field(default_factory=AuthorityManifest)
    governance: GovernanceRecord = field(default_factory=GovernanceRecord)
    pending_action: Optional[EONAction] = None
    last_gate: Optional[GateDecision] = None
    changed_files: List[str] = field(default_factory=list)
    evidence_registry: Dict[str, EvidenceArtifact] = field(default_factory=dict)
    transactions: Dict[str, TransactionRecord] = field(default_factory=dict)
    collisions: List[CollisionRecord] = field(default_factory=list)
    failed_attempts: Dict[str, int] = field(default_factory=dict)
    active_transaction_id: str = ""
    event_head: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RuntimeState":
        authority = AuthorityManifest(**payload.get("authority", {}))
        governance = GovernanceRecord(**payload.get("governance", {}))
        action_payload = payload.get("pending_action")
        gate_payload = payload.get("last_gate")
        evidence = {
            key: EvidenceArtifact(**value)
            for key, value in payload.get("evidence_registry", {}).items()
        }
        transactions = {
            key: TransactionRecord(**value)
            for key, value in payload.get("transactions", {}).items()
        }
        collisions = [CollisionRecord(**value) for value in payload.get("collisions", [])]
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            authority=authority,
            governance=governance,
            pending_action=EONAction(**action_payload) if action_payload else None,
            last_gate=GateDecision(**gate_payload) if gate_payload else None,
            changed_files=list(payload.get("changed_files", [])),
            evidence_registry=evidence,
            transactions=transactions,
            collisions=collisions,
            failed_attempts={
                str(key): int(value)
                for key, value in payload.get("failed_attempts", {}).items()
            },
            active_transaction_id=str(payload.get("active_transaction_id", "")),
            event_head=str(payload.get("event_head", "")),
        )
