from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .ids import typed_id


class RecordMixin:
    object_type = "record"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def object_id(self) -> str:
        return typed_id(self.object_type, self.to_dict())


@dataclass
class IntentRecord(RecordMixin):
    object_type = "intent"
    raw_request: str
    raw_request_hash: str
    actor: str
    objective: str
    assumptions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class CommandDefinition(RecordMixin):
    object_type = "command-definition"
    namespace: str
    name: str
    version: int
    intent_kinds: List[str]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    preconditions: List[str]
    postconditions: List[str]
    invariants: List[str]
    evidence_requirements: List[str]
    capability_query: Dict[str, Any]
    algorithm_query: Dict[str, Any]
    risk_policy: str
    rollback_policy: str
    budget_policy: Dict[str, Any]
    approval_policy: str
    lifecycle_policy: Dict[str, Any]
    description: str = ""
    aliases: List[str] = field(default_factory=list)

    @property
    def command_id(self) -> str:
        return f"{self.namespace}.{self.name}@{self.version}"


@dataclass
class CommandInvocation(RecordMixin):
    object_type = "command-invocation"
    command_id: str
    inputs: Dict[str, Any]
    modifiers: Dict[str, Any]
    scope: List[str]
    command_definition_id: str = ""
    intent_id: str = ""
    actor: str = "user"
    created_at: str = ""


@dataclass
class CapabilitySpec(RecordMixin):
    object_type = "capability-spec"
    name: str
    level: str
    facet: str
    description: str
    resource_schema: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityGrant(RecordMixin):
    object_type = "capability-grant"
    subject: str
    capability_ceiling: str
    capabilities: List[str]
    scope: List[str]
    resources: Dict[str, Any]
    expires_at: str
    budget: Dict[str, Any]
    approval_modes: List[str]
    issuer: str
    authority_hash: str
    use_limit: int = 1
    use_count: int = 0


@dataclass
class AlgorithmDefinition(RecordMixin):
    object_type = "algorithm-definition"
    name: str
    version: int
    implementation_kind: str
    implementation_ref: str
    implementation_digest: str
    command_ids: List[str]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    applicability: Dict[str, Any]
    capability_requirements: List[str]
    capability_level: str
    risk_floor: str
    rollback_class: str
    invariants: List[str]
    evidence_requirements: List[str]
    qualification_policy: Dict[str, Any]
    owner: str
    provenance: Dict[str, Any]
    status: str = "PROPOSED"
    known_failures: List[str] = field(default_factory=list)

    @property
    def algorithm_id(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass
class QualificationRecord(RecordMixin):
    object_type = "qualification"
    algorithm_id: str
    algorithm_digest: str
    context: Dict[str, Any]
    context_hash: str
    evidence_ids: List[str]
    tests: List[Dict[str, Any]]
    benchmarks: List[Dict[str, Any]]
    known_failures: List[str]
    status: str
    qualified_by: str
    created_at: str
    expires_at: str = ""


@dataclass
class SelectionDecision(RecordMixin):
    object_type = "selection-decision"
    command_id: str
    context_hash: str
    candidates: List[Dict[str, Any]]
    excluded: List[Dict[str, Any]]
    selected_algorithm_id: str
    selected_algorithm_digest: str
    ranking: List[str]
    tie_break: str
    evidence_ids: List[str]
    created_at: str
    score_components: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaimRecord(RecordMixin):
    object_type = "claim"
    subject_id: str
    statement: str
    scope: List[str]
    falsifier: str
    confidence_policy: Dict[str, Any]
    status: str = "OPEN"


@dataclass
class EvidenceRequirement(RecordMixin):
    object_type = "evidence-requirement"
    subject_id: str
    name: str
    category: str
    oracle: str
    freshness_seconds: int
    independence_group: str
    mandatory: bool = True


@dataclass
class EvidenceArtifact(RecordMixin):
    object_type = "egcf-evidence"
    subject_id: str
    claim_ids: List[str]
    requirement_ids: List[str]
    category: str
    producer: str
    method: str
    source_snapshot_hash: str
    target: str
    oracle: str
    environment: Dict[str, Any]
    command_id: str
    algorithm_id: str
    created_at: str
    sha256: str
    success: Optional[bool]
    limitations: List[str]
    independence_group: str
    simulated: bool = False
    path: str = ""
    content: Any = None


@dataclass
class ConfidenceAssessment(RecordMixin):
    object_type = "confidence-assessment"
    subject_id: str
    policy: str
    dimensions: Dict[str, float]
    blocking_gaps: List[str]
    conflicts: List[str]
    known_unknowns: List[str]
    conclusion: str
    evidence_ids: List[str]
    created_at: str


@dataclass
class InvariantRecord(RecordMixin):
    object_type = "invariant"
    name: str
    statement: str
    scope: List[str]
    status: str
    validator: Dict[str, Any]
    evidence_ids: List[str]
    falsifier: str
    counterexamples: List[str]
    authority: str
    created_at: str
    supersedes: str = ""


@dataclass
class DecisionRecord(RecordMixin):
    object_type = "decision"
    question: str
    alternatives: List[str]
    choice: str
    rationale: str
    evidence_ids: List[str]
    constraints: List[str]
    owner: str
    scope: List[str]
    status: str
    created_at: str
    supersedes: str = ""


@dataclass
class WorkflowNode(RecordMixin):
    object_type = "workflow-node"
    node_id: str
    command_id: str
    inputs: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)
    when: Dict[str, Any] = field(default_factory=dict)
    retry_limit: int = 0
    checkpoint: bool = False


@dataclass
class WorkflowDefinition(RecordMixin):
    object_type = "workflow-definition"
    name: str
    version: int
    parameters: Dict[str, Any]
    nodes: List[WorkflowNode]
    outputs: Dict[str, Any]
    description: str = ""

    @property
    def workflow_id(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass
class CompiledWorkflow(RecordMixin):
    object_type = "compiled-workflow"
    workflow_id: str
    source_snapshot_hash: str
    command_context: Dict[str, Any]
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, str]]
    execution_order: List[str]
    capability_level: str
    capability_requirements: List[str]
    risk: str
    evidence_requirements: List[str]
    approval_policy: str
    budget: Dict[str, Any]
    rollback_graph: Dict[str, Any]
    unresolved: List[str]
    created_at: str
    graph_hash: str = ""


@dataclass
class ExecutionPlan(RecordMixin):
    object_type = "execution-plan"
    compiled_workflow_id: str
    graph_hash: str
    source_snapshot_hash: str
    node_order: List[str]
    eon_action_ids: List[str]
    algorithm_digests: List[str]
    capability_grant_id: str
    evidence_ids: List[str]
    budget: Dict[str, Any]
    rollback_graph: Dict[str, Any]
    approval_policy: str
    expires_at: str
    created_at: str


@dataclass
class ApprovalRecord(RecordMixin):
    object_type = "approval"
    plan_id: str
    plan_hash: str
    approver: str
    authority: str
    constraints: Dict[str, Any]
    created_at: str
    expires_at: str
    use_limit: int = 1
    use_count: int = 0
    human: bool = True


@dataclass
class ExecutionRecord(RecordMixin):
    object_type = "execution"
    plan_id: str
    node_id: str
    algorithm_id: str
    executor: str
    inputs_hash: str
    output: Any
    status: str
    usage: Dict[str, Any]
    evidence_ids: List[str]
    started_at: str
    completed_at: str
    simulated: bool = False


@dataclass
class RollbackRecord(RecordMixin):
    object_type = "rollback"
    plan_id: str
    execution_ids: List[str]
    rollback_class: str
    pre_state: Dict[str, Any]
    post_state: Dict[str, Any]
    restored_state: Dict[str, Any]
    failures: List[str]
    status: str
    created_at: str


@dataclass
class FailureRecord(RecordMixin):
    object_type = "failure"
    subject_id: str
    expected: str
    observed: str
    active_dimension: str
    frozen_dimensions: List[str]
    evidence_ids: List[str]
    retry_count: int
    status: str
    created_at: str


@dataclass
class AssuranceCase(RecordMixin):
    object_type = "assurance-case"
    subject_id: str
    top_claim: str
    subclaims: List[Dict[str, Any]]
    arguments: List[Dict[str, Any]]
    supporting_evidence: List[str]
    refuting_evidence: List[str]
    invariant_ids: List[str]
    decision_ids: List[str]
    capability_facts: Dict[str, Any]
    approval_facts: Dict[str, Any]
    rollback_argument: Dict[str, Any]
    gaps: List[str]
    conflicts: List[str]
    uncertainties: List[str]
    conclusion: str
    created_at: str


@dataclass
class ArtifactRecord(RecordMixin):
    object_type = "artifact"
    media_type: str
    sha256: str
    size: int
    source_ids: List[str]
    provenance: Dict[str, Any]
    created_at: str
    path: str = ""


@dataclass
class SupersedenceRecord(RecordMixin):
    object_type = "supersedence"
    old_id: str
    new_id: str
    reason: str
    authority: str
    created_at: str


RECORD_TYPES = {
    record_class.object_type: record_class
    for record_class in (
        IntentRecord,
        CommandDefinition,
        CommandInvocation,
        CapabilitySpec,
        CapabilityGrant,
        AlgorithmDefinition,
        QualificationRecord,
        SelectionDecision,
        ClaimRecord,
        EvidenceRequirement,
        EvidenceArtifact,
        ConfidenceAssessment,
        InvariantRecord,
        DecisionRecord,
        WorkflowNode,
        WorkflowDefinition,
        CompiledWorkflow,
        ExecutionPlan,
        ApprovalRecord,
        ExecutionRecord,
        RollbackRecord,
        FailureRecord,
        AssuranceCase,
        ArtifactRecord,
        SupersedenceRecord,
    )
}
