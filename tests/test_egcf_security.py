from __future__ import annotations

import unittest

from ourd.egcf.context import CommandContext
from ourd.egcf.engine import EGCFEngine
from ourd.egcf.errors import ApprovalError, CompilationError, EGCFError
from ourd.egcf.ids import sha256_json, utc_now
from ourd.egcf.models import (
    AlgorithmDefinition,
    CommandDefinition,
    QualificationRecord,
    WorkflowDefinition,
    WorkflowNode,
)
from tests.helpers import RepoFixture


class EGCFSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def _authority(self, level: str, capabilities: list[str]):
        return self.fixture.authority(
            allowed_paths=["README.md", "src/**"],
            overrides={
                "semantic_capability_ceiling": level,
                "semantic_capabilities": capabilities,
            },
        )

    @staticmethod
    def _algorithm(command_id: str, name: str, **updates):
        values = {
            "name": name,
            "version": 1,
            "implementation_kind": "builtin",
            "implementation_ref": f"builtin:{name}",
            "implementation_digest": sha256_json({"name": name}),
            "command_ids": [command_id],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "applicability": {},
            "capability_requirements": ["filesystem.read"],
            "capability_level": "C0",
            "risk_floor": "L0",
            "rollback_class": "none",
            "invariants": [],
            "evidence_requirements": [],
            "qualification_policy": {"tests_required": True},
            "owner": "unit-test",
            "provenance": {"source": "test"},
            "status": "CANDIDATE",
            "known_failures": [],
        }
        values.update(updates)
        return AlgorithmDefinition(**values)

    def test_registry_rejects_privileged_executor_injection(self) -> None:
        with EGCFEngine(self.fixture.root) as engine:
            candidate = self._algorithm(
                "repo.metrics@1",
                "malicious",
                implementation_kind="eon",
                implementation_ref="shell:rm -rf",
            )
            with self.assertRaises(EGCFError):
                engine.algorithms.register(candidate)

    def test_reported_tests_cannot_self_qualify_algorithm(self) -> None:
        with EGCFEngine(self.fixture.root) as engine:
            candidate = self._algorithm("repo.metrics@1", "candidate.metrics")
            engine.algorithms.register(candidate)
            qualification_id = engine.algorithms.qualify(
                candidate.algorithm_id,
                context={},
                evidence_ids=[],
                tests=[{"name": "model says pass", "success": True}],
                qualified_by="model",
            )
            qualification = engine.store.get(qualification_id)
            self.assertEqual("CANDIDATE", qualification.status)
            decision = engine.handlers.selector.select(
                "repo.metrics@1",
                context={"workspace_snapshot": engine.workspace.snapshot_hash()},
                capability_ceiling=engine.grant.capability_ceiling,
                allowed_capabilities=engine.grant.capabilities,
            )
            self.assertNotEqual(candidate.algorithm_id, decision.selected_algorithm_id)

    def test_algorithm_substitution_after_compilation_fails(self) -> None:
        with EGCFEngine(self.fixture.root) as engine:
            compiled, _, _ = engine.compile_command("repo.metrics", {})
            plan = engine.create_execution_plan(compiled, prepare_mutations=False)
            node = compiled.nodes[0]
            original = engine.algorithms.resolve(node["algorithm_id"])
            replacement = self._algorithm(
                original.command_ids[0],
                original.name,
                version=original.version,
                implementation_digest="0" * 64,
                status="QUALIFIED",
            )
            replacement_id = engine.store.register(replacement)
            engine.store.supersede(
                original.object_id,
                replacement_id,
                "injected replacement",
                "test",
            )
            with self.assertRaises(EGCFError):
                engine.execute_plan(plan.object_id)

    def test_c4_and_c5_are_fail_closed(self) -> None:
        authority = self._authority("C5", ["network.write", "governance.admin"])
        with EGCFEngine(self.fixture.root, authority_path=authority) as engine:
            command = CommandDefinition(
                namespace="external",
                name="mutate",
                version=1,
                intent_kinds=["external.mutate"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={"type": "object"},
                preconditions=[],
                postconditions=[],
                invariants=["authority_not_broadened"],
                evidence_requirements=[],
                capability_query={"level": "C4", "facets": ["network.write"]},
                algorithm_query={"command_id": "external.mutate@1"},
                risk_policy="L2",
                rollback_policy="compensating",
                budget_policy={"actions": 1},
                approval_policy="human",
                lifecycle_policy={},
            )
            engine.commands.register(command)
            algorithm = self._algorithm(
                command.command_id,
                "external.mutate",
                capability_requirements=["network.write"],
                capability_level="C4",
                risk_floor="L2",
                rollback_class="compensating",
                status="QUALIFIED",
            )
            algorithm_id = engine.algorithms.register(algorithm)
            engine.store.register(
                QualificationRecord(
                    algorithm_id=algorithm.algorithm_id,
                    algorithm_digest=algorithm.implementation_digest,
                    context={"builtin": True},
                    context_hash=sha256_json({"builtin": True}),
                    evidence_ids=[],
                    tests=[{"name": "test-only qualification", "success": True}],
                    benchmarks=[],
                    known_failures=[],
                    status="QUALIFIED",
                    qualified_by="test-fixture",
                    created_at=utc_now(),
                )
            )
            self.assertTrue(algorithm_id)
            with self.assertRaises(CompilationError):
                engine.invoke("external.mutate", {})
            with self.assertRaises(CompilationError):
                engine.invoke("capability.grant", {})

    def test_approval_use_limit_prevents_replay(self) -> None:
        authority = self._authority("C3", ["governance.write"])
        with EGCFEngine(self.fixture.root, authority_path=authority) as engine:
            proposal = engine.invoke(
                "decision.create",
                {"question": "Parser mode?", "alternatives": ["a", "b"], "choice": "a"},
            )
            proposal_id = proposal["outputs"][-1]["result"]["decision_id"]
            pending = engine.invoke(
                "decision.supersede",
                {"old_id": proposal_id, "choice": "b", "rationale": "validated"},
            )
            approval_id = engine.authorize(
                pending["execution_plan_id"],
                approver="human",
                authority="one use",
                use_limit=1,
            )
            first = engine.execute_plan(pending["execution_plan_id"], approval_id)
            self.assertEqual("COMPLETED", first["status"])
            with self.assertRaises(ApprovalError):
                engine.execute_plan(pending["execution_plan_id"], approval_id)

    def test_budget_and_unbounded_mutating_retry_are_refused(self) -> None:
        authority = self._authority("C3", ["filesystem.write", "process.execute"])
        workflow = WorkflowDefinition(
            name="retry",
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(
                    node_id="write",
                    command_id="eon.execute",
                    inputs={"changes": [{"type": "write", "path": "README.md", "content": "x"}]},
                    retry_limit=1,
                )
            ],
            outputs={},
        )
        with EGCFEngine(self.fixture.root, authority_path=authority) as engine:
            with self.assertRaises(CompilationError):
                engine.compiler.compile(
                    workflow,
                    context=CommandContext.from_mapping({"budget": {"actions": 1, "retries": 1}}),
                    grant=engine.grant,
                )


if __name__ == "__main__":
    unittest.main()
