from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2}
SCORE_SCALE = 10_000


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
    requirement_ids: List[str] = field(default_factory=list)
    quality_bp: int = SCORE_SCALE
    polarity: str = "support"

    def __post_init__(self) -> None:
        self.requirement_ids = list(dict.fromkeys(str(value) for value in self.requirement_ids))
        self.quality_bp = int(self.quality_bp)
        if not 0 <= self.quality_bp <= SCORE_SCALE:
            raise ValueError("evidence quality must be 0..10000")
        if self.polarity not in {"support", "counterexample", "conflict"}:
            raise ValueError("evidence polarity must be support, counterexample, or conflict")


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
    varied_dimensions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.varied_dimensions = list(
            dict.fromkeys(str(value) for value in self.varied_dimensions if str(value))
        )


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
    severity_bp: int = 0
    attempt_key: str = ""
    boundary_signature: str = ""
    dimension_signature: str = ""

    def __post_init__(self) -> None:
        self.severity_bp = int(self.severity_bp)
        if not 0 <= self.severity_bp <= SCORE_SCALE:
            raise ValueError("collision severity must be 0..10000")


def _canonical_strings(values: Any) -> Tuple[str, ...]:
    return tuple(sorted({str(value) for value in values or () if str(value)}))


def _stable_strings(values: Any) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values or () if str(value)))


def _canonical_score_pairs(values: Any) -> Tuple[Tuple[str, int], ...]:
    normalized: Dict[str, int] = {}
    for name, value in values or ():
        key = str(name)
        if not key:
            raise ValueError("OIEC score keys must be non-empty")
        normalized[key] = int(value)
    return tuple(sorted(normalized.items()))


@dataclass(frozen=True)
class BoundaryState:
    schema_version: int = 1
    authority_hash: str = ""
    source_snapshot_hash: str = ""
    semantic_objects: Tuple[str, ...] = ()
    semantic_relations: Tuple[str, ...] = ()
    authority_allowed_patterns: Tuple[str, ...] = ()
    authority_forbidden_patterns: Tuple[str, ...] = ()
    governance_allowed_patterns: Tuple[str, ...] = ()
    governance_excluded_patterns: Tuple[str, ...] = ()
    experimental_dimensions: Tuple[str, ...] = ()
    semantic_membership_bp: Tuple[Tuple[str, int], ...] = ()
    boundary_uncertainty_bp: int = 0
    signature: str = ""

    def __post_init__(self) -> None:
        for name in (
            "semantic_objects",
            "semantic_relations",
            "authority_allowed_patterns",
            "authority_forbidden_patterns",
            "governance_allowed_patterns",
            "governance_excluded_patterns",
            "experimental_dimensions",
        ):
            object.__setattr__(self, name, _canonical_strings(getattr(self, name)))
        memberships = _canonical_score_pairs(self.semantic_membership_bp)
        if any(not 0 <= value <= SCORE_SCALE for _, value in memberships):
            raise ValueError("boundary membership must be 0..10000")
        object.__setattr__(self, "semantic_membership_bp", memberships)
        if not 0 <= int(self.boundary_uncertainty_bp) <= SCORE_SCALE:
            raise ValueError("boundary uncertainty must be 0..10000")


@dataclass(frozen=True)
class DimensionBudget:
    schema_version: int = 1
    max_active_objects: int = 64
    max_active_relations: int = 256
    max_active_dimensions: int = 16
    max_active_hypotheses: int = 16
    max_quantization_levels: int = 17
    max_interaction_order: int = 1
    max_candidate_actions: int = 16
    max_active_evidence_atoms: int = 128
    max_decomposition_depth: int = 8
    max_branch_factor: int = 16
    max_retries_per_attempt: int = 1
    selected_dimensions: Tuple[str, ...] = ()
    dimension_utility_bp: Tuple[Tuple[str, int], ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        positive = (
            self.max_active_objects,
            self.max_active_relations,
            self.max_active_dimensions,
            self.max_active_hypotheses,
            self.max_quantization_levels,
            self.max_candidate_actions,
            self.max_active_evidence_atoms,
            self.max_decomposition_depth,
            self.max_branch_factor,
        )
        if any(int(value) < 1 for value in positive):
            raise ValueError("OIEC active-state limits must be positive")
        if not 1 <= int(self.max_interaction_order) <= int(self.max_active_dimensions):
            raise ValueError("OIEC interaction order must fit within active dimensions")
        if int(self.max_retries_per_attempt) < 0:
            raise ValueError("OIEC retry limit cannot be negative")
        selected = _stable_strings(self.selected_dimensions)
        if len(selected) > int(self.max_active_dimensions):
            raise ValueError("selected dimensions exceed the OIEC budget")
        object.__setattr__(self, "selected_dimensions", selected)
        object.__setattr__(
            self,
            "dimension_utility_bp",
            _canonical_score_pairs(self.dimension_utility_bp),
        )


@dataclass(frozen=True)
class FiniteEvidenceState:
    schema_version: int = 1
    atoms: Tuple[str, ...] = ()
    present_mask: int = 0
    conflict_mask: int = 0
    quality_bp: Tuple[int, ...] = ()
    representative_ids: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        source_atoms = tuple(str(value) for value in self.atoms)
        source_quality = tuple(int(value) for value in self.quality_bp)
        source_representatives = tuple(str(value) for value in self.representative_ids)
        if len(source_quality) != len(source_atoms) or len(source_representatives) != len(source_atoms):
            raise ValueError("finite evidence arrays must align with the atom universe")
        if any(not atom for atom in source_atoms) or len(set(source_atoms)) != len(source_atoms):
            raise ValueError("finite evidence atoms must be unique and non-empty")
        order = sorted(range(len(source_atoms)), key=source_atoms.__getitem__)
        old_to_new = {old_index: new_index for new_index, old_index in enumerate(order)}
        atoms = tuple(source_atoms[index] for index in order)
        quality = tuple(source_quality[index] for index in order)
        representatives = tuple(source_representatives[index] for index in order)
        present_mask = sum(
            1 << old_to_new[index]
            for index in range(len(source_atoms))
            if self.present_mask & (1 << index)
        )
        conflict_mask = sum(
            1 << old_to_new[index]
            for index in range(len(source_atoms))
            if self.conflict_mask & (1 << index)
        )
        object.__setattr__(self, "atoms", atoms)
        object.__setattr__(self, "quality_bp", quality)
        object.__setattr__(self, "representative_ids", representatives)
        object.__setattr__(self, "present_mask", present_mask)
        object.__setattr__(self, "conflict_mask", conflict_mask)
        if any(not 0 <= value <= SCORE_SCALE for value in quality):
            raise ValueError("evidence quality must be 0..10000")
        valid_mask = (1 << len(atoms)) - 1 if atoms else 0
        if self.present_mask < 0 or self.conflict_mask < 0:
            raise ValueError("evidence masks cannot be negative")
        if self.present_mask & ~valid_mask or self.conflict_mask & ~valid_mask:
            raise ValueError("evidence mask refers outside the finite universe")


@dataclass(frozen=True)
class AttemptKey:
    source_snapshot_hash: str = ""
    action_id: str = ""
    evidence_signature: str = ""
    boundary_signature: str = ""
    dimension_signature: str = ""
    digest: str = ""


@dataclass(frozen=True)
class ProgressCertificate:
    schema_version: int = 1
    evidence_gain_bp: int = 0
    uncertainty_reduction_bp: int = 0
    goal_improvement_bp: int = 0
    residual_risk_reduction_bp: int = 0
    boundary_uncertainty_reduction_bp: int = 0
    expected_information_gain_bp: int = 0
    novel_evidence: bool = False
    novel_experiment: bool = False
    terminal: bool = False
    accepted: bool = False
    reasons: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        for name in ("evidence_gain_bp", "expected_information_gain_bp"):
            if not 0 <= int(getattr(self, name)) <= SCORE_SCALE:
                raise ValueError(f"{name} must be 0..10000")
        for name in (
            "uncertainty_reduction_bp",
            "goal_improvement_bp",
            "residual_risk_reduction_bp",
            "boundary_uncertainty_reduction_bp",
        ):
            if not -SCORE_SCALE <= int(getattr(self, name)) <= SCORE_SCALE:
                raise ValueError(f"{name} must be -10000..10000")
        object.__setattr__(self, "reasons", _canonical_strings(self.reasons))


@dataclass
class RuntimeState:
    schema_version: int = 2
    authority: AuthorityManifest = field(default_factory=AuthorityManifest)
    governance: GovernanceRecord = field(default_factory=GovernanceRecord)
    pending_action: Optional[EONAction] = None
    last_gate: Optional[GateDecision] = None
    changed_files: List[str] = field(default_factory=list)
    evidence_registry: Dict[str, EvidenceArtifact] = field(default_factory=dict)
    transactions: Dict[str, TransactionRecord] = field(default_factory=dict)
    collisions: List[CollisionRecord] = field(default_factory=list)
    failed_attempts: Dict[str, int] = field(default_factory=dict)
    boundary_state: Optional[BoundaryState] = None
    dimension_budget: Optional[DimensionBudget] = None
    finite_evidence: Optional[FiniteEvidenceState] = None
    last_progress: Optional[ProgressCertificate] = None
    transition_index: int = 0
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
        boundary_payload = payload.get("boundary_state")
        budget_payload = payload.get("dimension_budget")
        finite_evidence_payload = payload.get("finite_evidence")
        progress_payload = payload.get("last_progress")
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
            boundary_state=BoundaryState(**boundary_payload) if boundary_payload else None,
            dimension_budget=DimensionBudget(**budget_payload) if budget_payload else None,
            finite_evidence=(
                FiniteEvidenceState(**finite_evidence_payload)
                if finite_evidence_payload
                else None
            ),
            last_progress=(
                ProgressCertificate(**progress_payload) if progress_payload else None
            ),
            transition_index=int(payload.get("transition_index", 0)),
            active_transaction_id=str(payload.get("active_transaction_id", "")),
            event_head=str(payload.get("event_head", "")),
        )
