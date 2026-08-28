from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from ourd.egcf.ids import canonical_json, sha256_bytes, sha256_json
from ourd.egcf.models import (
    AlgorithmDefinition,
    ApprovalRecord,
    ArtifactRecord,
    AssuranceCase,
    CapabilityGrant,
    CommandDefinition,
    CommandInvocation,
    CompiledWorkflow,
    ConfidenceAssessment,
    EvidenceArtifact,
    EvidenceRequirement,
    ExecutionPlan,
    ExecutionRecord,
    FailureRecord,
    IntentRecord,
    QualificationRecord,
    RecordMixin,
    SelectionDecision,
)
from ourd.egcf.store import ObjectStore
from ourd.persistence import sha256_text
from ourd.workspace import Workspace


FIXTURE_SCHEMA_VERSION = 1
FIXTURE_SOURCE_SNAPSHOT = "19be01c14d9a7a02a438e0ab2770bc1e795c6043cd9a1f2b4af9b63fc23b336b"
FIXTURE_BUNDLE_SHA256 = "4c217e07d70d8feb3e479d8ec1d4d36e6d4ef8f4548ccfc6dc1796d5161c7813"


@dataclass(frozen=True)
class GuiFixtureBundle:
    schema_version: int
    source_snapshot_hash: str
    records: tuple[RecordMixin, ...]
    ids: Mapping[str, str]
    artifact_content: Mapping[str, bytes]

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "schema_version": self.schema_version,
                "source_snapshot_hash": self.source_snapshot_hash,
                "records": [
                    {
                        "object_type": record.object_type,
                        "object_id": record.object_id,
                        "payload": asdict(record),
                    }
                    for record in self.records
                ],
                "artifacts": {
                    path: sha256_bytes(content)
                    for path, content in sorted(self.artifact_content.items())
                },
            }
        )


def build_fixture_bundle() -> GuiFixtureBundle:
    created_at = "2026-08-21T00:00:00Z"
    command = CommandDefinition(
        namespace="hrt",
        name="interpret",
        version=1,
        intent_kinds=["analysis"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        preconditions=["repository readable"],
        postconditions=["intent represented"],
        invariants=["no mutation"],
        evidence_requirements=["provenance"],
        capability_query={"all": ["analysis.reason"]},
        algorithm_query={"command_id": "hrt.interpret@1"},
        risk_policy="L0",
        rollback_policy="none",
        budget_policy={"wall_seconds": 30},
        approval_policy="automatic",
        lifecycle_policy={"record": True},
        description="Deterministic GUI fixture command",
    )
    intent = IntentRecord(
        raw_request="Implement AxialProfile",
        raw_request_hash=sha256_text("Implement AxialProfile"),
        actor="fixture-user",
        objective="Implement AxialProfile",
        assumptions=["repository is readable"],
        ambiguities=[],
        provenance={"fixture_schema": FIXTURE_SCHEMA_VERSION},
        created_at=created_at,
    )
    selected_algorithm = AlgorithmDefinition(
        name="fixture.axial-profile",
        version=1,
        implementation_kind="python",
        implementation_ref="fixture:axial-profile",
        implementation_digest="a" * 64,
        command_ids=[command.command_id],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        applicability={"domain": "geometry"},
        capability_requirements=["analysis.geometry"],
        capability_level="C1",
        risk_floor="L0",
        rollback_class="none",
        invariants=["no mutation"],
        evidence_requirements=["fixture-boundary"],
        qualification_policy={"minimum_successes": 1},
        owner="fixture",
        provenance={"fixture_schema": FIXTURE_SCHEMA_VERSION},
        status="QUALIFIED",
    )
    rejected_algorithm = AlgorithmDefinition(
        name="fixture.axial-profile-unbounded",
        version=1,
        implementation_kind="python",
        implementation_ref="fixture:axial-profile-unbounded",
        implementation_digest="b" * 64,
        command_ids=[command.command_id],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        applicability={"domain": "geometry"},
        capability_requirements=["filesystem.write"],
        capability_level="C3",
        risk_floor="L2",
        rollback_class="snapshot",
        invariants=["preserve authored geometry"],
        evidence_requirements=["fixture-boundary"],
        qualification_policy={"minimum_successes": 3},
        owner="fixture",
        provenance={"fixture_schema": FIXTURE_SCHEMA_VERSION},
        status="PROPOSED",
        known_failures=["scope exceeds read-only fixture authority"],
    )
    requirement = EvidenceRequirement(
        subject_id=selected_algorithm.object_id,
        name="fixture-boundary",
        category="boundary",
        oracle="exact fixture assertion",
        freshness_seconds=0,
        independence_group="deterministic-fixture",
        mandatory=True,
    )
    evidence_content = b'{"fixture":"gui-v1","status":"pass"}\n'
    evidence_digest = sha256_bytes(evidence_content)
    evidence_path = f"artifacts/sha256/{evidence_digest[:2]}/{evidence_digest}"
    evidence = EvidenceArtifact(
        subject_id=selected_algorithm.object_id,
        claim_ids=[],
        requirement_ids=[requirement.object_id],
        category="boundary",
        producer="tests.gui.fixtures_v1",
        method="deterministic fixture assertion",
        source_snapshot_hash=FIXTURE_SOURCE_SNAPSHOT,
        target="fixture.axial-profile@1",
        oracle="exact fixture assertion",
        environment={"network": False, "model": False},
        command_id=command.command_id,
        algorithm_id=selected_algorithm.algorithm_id,
        created_at=created_at,
        sha256=evidence_digest,
        success=True,
        limitations=["fixture evidence is synthetic and test-only"],
        independence_group="deterministic-fixture",
        simulated=False,
        path=evidence_path,
        content={"status": "pass"},
    )
    qualification = QualificationRecord(
        algorithm_id=selected_algorithm.algorithm_id,
        algorithm_digest=selected_algorithm.implementation_digest,
        context={"domain": "geometry", "mode": "fixture"},
        context_hash=sha256_json({"domain": "geometry", "mode": "fixture"}),
        evidence_ids=[evidence.object_id],
        tests=[{"name": "fixture-boundary", "passed": True}],
        benchmarks=[{"name": "fixture-latency", "milliseconds": 1}],
        known_failures=[],
        status="QUALIFIED",
        qualified_by="deterministic-fixture",
        created_at=created_at,
    )
    selection = SelectionDecision(
        command_id=command.command_id,
        context_hash=qualification.context_hash,
        candidates=[
            {
                "algorithm_id": selected_algorithm.algorithm_id,
                "algorithm_digest": selected_algorithm.implementation_digest,
                "qualification_ids": [qualification.object_id],
                "score_components": {
                    "qualification_strength": 1.0,
                    "expected_correctness": 0.95,
                },
                "status": "QUALIFIED",
                "rollback_class": selected_algorithm.rollback_class,
                "known_failures": [],
            }
        ],
        excluded=[
            {
                "algorithm_id": rejected_algorithm.algorithm_id,
                "algorithm_digest": rejected_algorithm.implementation_digest,
                "qualification_ids": [],
                "score_components": {"qualification_strength": 0.0},
                "status": "EXCLUDED",
                "rollback_class": rejected_algorithm.rollback_class,
                "known_failures": list(rejected_algorithm.known_failures),
                "reasons": ["required capability C3 exceeds fixture authority C1"],
            }
        ],
        selected_algorithm_id=selected_algorithm.algorithm_id,
        selected_algorithm_digest=selected_algorithm.implementation_digest,
        ranking=[
            "qualification strength",
            "expected correctness",
            "stable algorithm ID",
        ],
        tie_break="algorithm_id then implementation_digest",
        evidence_ids=[qualification.object_id, evidence.object_id],
        created_at=created_at,
        score_components={
            "selected": {
                "qualification_strength": 1.0,
                "expected_correctness": 0.95,
            }
        },
    )
    invocation = CommandInvocation(
        command_id=command.command_id,
        inputs={"text": intent.objective},
        modifiers={
            "dry_run": True,
            "why": True,
            "graph": True,
            "trace": True,
            "record": True,
        },
        scope=["**"],
        command_definition_id=command.object_id,
        intent_id=intent.object_id,
        actor="fixture-user",
        created_at=created_at,
    )
    compiled = CompiledWorkflow(
        workflow_id=f"invocation-{invocation.object_id.partition(':sha256:')[2][:16]}@1",
        source_snapshot_hash=FIXTURE_SOURCE_SNAPSHOT,
        command_context={"dry_run": True, "scope": ["**"]},
        nodes=[
            {
                "node_id": "command",
                "command_id": command.command_id,
                "command_definition_id": command.object_id,
                "algorithm_id": selected_algorithm.algorithm_id,
                "algorithm_digest": selected_algorithm.implementation_digest,
                "algorithm_definition_id": selected_algorithm.object_id,
                "selection_id": selection.object_id,
                "capability_level": "C1",
                "capability_requirements": ["analysis.geometry"],
                "risk": "L0",
                "scope": ["**"],
                "inputs": {"text": intent.objective},
                "depends_on": [],
            }
        ],
        edges=[],
        execution_order=["command"],
        capability_level="C1",
        capability_requirements=["analysis.geometry"],
        risk="L0",
        evidence_requirements=[requirement.object_id],
        approval_policy="human",
        budget={"wall_seconds": 30, "tokens": 0},
        rollback_graph={"class": "none"},
        unresolved=["mutation remains outside fixture scope"],
        created_at=created_at,
        graph_hash=sha256_json({"nodes": ["command"], "edges": []}),
    )
    grant = CapabilityGrant(
        subject="fixture-user",
        capability_ceiling="C1",
        capabilities=["filesystem.read", "analysis.geometry"],
        scope=["**"],
        resources={"repository": "fixture"},
        expires_at="2099-01-01T00:00:00Z",
        budget={"wall_seconds": 30},
        approval_modes=["human"],
        issuer="fixture-authority",
        authority_hash="c" * 64,
        use_limit=3,
        use_count=0,
    )
    plan = ExecutionPlan(
        compiled_workflow_id=compiled.object_id,
        graph_hash=compiled.graph_hash,
        source_snapshot_hash=FIXTURE_SOURCE_SNAPSHOT,
        node_order=["command"],
        eon_action_ids=[],
        algorithm_digests=[selected_algorithm.implementation_digest],
        capability_grant_id=grant.object_id,
        evidence_ids=[selection.object_id, qualification.object_id, evidence.object_id],
        budget={"wall_seconds": 30, "tokens": 0},
        rollback_graph={"class": "none", "available": True},
        approval_policy="human",
        expires_at="2099-01-01T00:00:00Z",
        created_at=created_at,
    )
    approval = ApprovalRecord(
        plan_id=plan.object_id,
        plan_hash=plan.object_id.partition(":sha256:")[2],
        approver="fixture-human",
        authority="fixture-authority",
        constraints={"scope": ["**"], "simulation": False},
        created_at=created_at,
        expires_at="2099-01-01T00:00:00Z",
        use_limit=1,
        use_count=0,
        human=True,
    )
    execution = ExecutionRecord(
        plan_id=plan.object_id,
        node_id="command",
        algorithm_id=selected_algorithm.algorithm_id,
        executor="fixture-executor",
        inputs_hash=sha256_json({"text": intent.objective}),
        output={"status": "ok", "changed_files": []},
        status="SUCCEEDED",
        usage={"wall_seconds": 0.001, "tokens": 0},
        evidence_ids=[evidence.object_id],
        started_at=created_at,
        completed_at="2026-08-21T00:00:01Z",
        simulated=False,
    )
    failure = FailureRecord(
        subject_id=plan.object_id,
        expected="legacy token preserved",
        observed="legacy token rejected",
        active_dimension="grammar compatibility",
        frozen_dimensions=["repository snapshot", "algorithm digest"],
        evidence_ids=[evidence.object_id],
        retry_count=1,
        status="OPEN",
        created_at=created_at,
    )
    confidence = ConfidenceAssessment(
        subject_id=plan.object_id,
        policy="fixture",
        dimensions={"invariant": 1.0, "boundary": 1.0, "regression": 0.0},
        blocking_gaps=[],
        conflicts=[],
        known_unknowns=["mutation path is intentionally not exercised"],
        conclusion="MEDIUM",
        evidence_ids=[evidence.object_id],
        created_at=created_at,
    )
    assurance = AssuranceCase(
        subject_id=plan.object_id,
        top_claim="The fixture preserves exact traceability without mutation.",
        subclaims=[{"claim": "selection is exact", "status": True}],
        arguments=[{"type": "fixture", "evidence_id": evidence.object_id}],
        supporting_evidence=[evidence.object_id],
        refuting_evidence=[],
        invariant_ids=[],
        decision_ids=[],
        capability_facts={"ceiling": "C1"},
        approval_facts={"approval_id": approval.object_id},
        rollback_argument={"class": "none"},
        gaps=["real mutation not exercised"],
        conflicts=[],
        uncertainties=["fixture-only evidence"],
        conclusion="SUPPORTED_WITH_LIMITS",
        created_at=created_at,
    )
    report_content = b"GUI fixture assurance report\n"
    report_digest = sha256_bytes(report_content)
    report_path = f"artifacts/sha256/{report_digest[:2]}/{report_digest}"
    artifact = ArtifactRecord(
        media_type="text/plain",
        sha256=report_digest,
        size=len(report_content),
        source_ids=[execution.object_id, assurance.object_id],
        provenance={"fixture_schema": FIXTURE_SCHEMA_VERSION},
        created_at=created_at,
        path=report_path,
    )
    records: tuple[RecordMixin, ...] = (
        command,
        intent,
        selected_algorithm,
        rejected_algorithm,
        requirement,
        evidence,
        qualification,
        selection,
        invocation,
        compiled,
        grant,
        plan,
        approval,
        execution,
        failure,
        confidence,
        assurance,
        artifact,
    )
    ids = {
        "command": command.object_id,
        "intent": intent.object_id,
        "selected_algorithm": selected_algorithm.object_id,
        "rejected_algorithm": rejected_algorithm.object_id,
        "evidence_requirement": requirement.object_id,
        "evidence": evidence.object_id,
        "qualification": qualification.object_id,
        "selection": selection.object_id,
        "invocation": invocation.object_id,
        "compiled_workflow": compiled.object_id,
        "capability_grant": grant.object_id,
        "execution_plan": plan.object_id,
        "approval": approval.object_id,
        "execution": execution.object_id,
        "failure": failure.object_id,
        "confidence": confidence.object_id,
        "assurance": assurance.object_id,
        "artifact": artifact.object_id,
    }
    return GuiFixtureBundle(
        schema_version=FIXTURE_SCHEMA_VERSION,
        source_snapshot_hash=FIXTURE_SOURCE_SNAPSHOT,
        records=records,
        ids=ids,
        artifact_content={
            evidence_path: evidence_content,
            report_path: report_content,
        },
    )


def install_fixture_repository(root: Path) -> GuiFixtureBundle:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# GUI Fixture\n\nvalue = 1\n", encoding="utf-8")
    observed_snapshot = Workspace(root).snapshot_hash()
    if observed_snapshot != FIXTURE_SOURCE_SNAPSHOT:
        raise AssertionError(
            f"fixture source snapshot changed: {observed_snapshot} != {FIXTURE_SOURCE_SNAPSHOT}"
        )
    bundle = build_fixture_bundle()
    object_store = ObjectStore(root / ".ourd-agent" / "egcf" / "objects" / "sha256")
    for record in bundle.records:
        object_store.put(record.object_type, asdict(record))
    state_root = root / ".ourd-agent" / "egcf"
    for relative_path, content in bundle.artifact_content.items():
        destination = state_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return bundle


def fixture_manifest_json() -> str:
    bundle = build_fixture_bundle()
    return canonical_json(
        {
            "schema_version": bundle.schema_version,
            "source_snapshot_hash": bundle.source_snapshot_hash,
            "bundle_sha256": bundle.digest,
            "ids": dict(sorted(bundle.ids.items())),
        }
    )
