from __future__ import annotations

import unittest

from ourd.egcf.context import CommandContext
from ourd.egcf.engine import EGCFEngine
from ourd.egcf.errors import CompilationError, QualificationError
from ourd.egcf.models import WorkflowDefinition, WorkflowNode
from tests.helpers import RepoFixture


class EGCFCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def _c3_authority(self):
        return self.fixture.authority(
            allowed_paths=["README.md", "src/**"],
            overrides={
                "semantic_capability_ceiling": "C3",
                "semantic_capabilities": [
                    "filesystem.write",
                    "process.execute",
                    "workflow.execute",
                    "governance.write",
                    "registry.admin",
                    "simulation.run",
                ],
            },
        )

    def test_stable_graph_hash_ignores_receipt_timestamps(self) -> None:
        workflow = WorkflowDefinition(
            name="stable",
            version=1,
            parameters={},
            nodes=[WorkflowNode(node_id="read", command_id="repo.metrics", inputs={})],
            outputs={"result": {"$from": "read"}},
        )
        with EGCFEngine(self.fixture.root) as engine:
            first = engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)
            second = engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)
            self.assertEqual(first.graph_hash, second.graph_hash)

    def test_reference_must_follow_dependency(self) -> None:
        workflow = WorkflowDefinition(
            name="bad-reference",
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(node_id="first", command_id="hrt.interpret", inputs={"text": "hello"}),
                WorkflowNode(
                    node_id="second",
                    command_id="hrt.summary",
                    inputs={"text": {"$from": "first", "path": ["result", "objective"]}},
                ),
            ],
            outputs={},
        )
        with EGCFEngine(self.fixture.root) as engine:
            with self.assertRaises(CompilationError):
                engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)

    def test_cycles_and_parallel_mutation_conflicts_fail(self) -> None:
        cyclic = WorkflowDefinition(
            name="cycle",
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(node_id="a", command_id="hrt.summary", inputs={}, depends_on=["b"]),
                WorkflowNode(node_id="b", command_id="hrt.summary", inputs={}, depends_on=["a"]),
            ],
            outputs={},
        )
        authority = self._c3_authority()
        with EGCFEngine(self.fixture.root, authority_path=authority) as engine:
            with self.assertRaises(CompilationError):
                engine.compiler.compile(cyclic, context=CommandContext(), grant=engine.grant)
            conflicting = WorkflowDefinition(
                name="conflict",
                version=1,
                parameters={},
                nodes=[
                    WorkflowNode(
                        node_id="left",
                        command_id="eon.execute",
                        inputs={"changes": [{"type": "write", "path": "README.md", "content": "left"}]},
                    ),
                    WorkflowNode(
                        node_id="right",
                        command_id="eon.execute",
                        inputs={"changes": [{"type": "write", "path": "README.md", "content": "right"}]},
                    ),
                ],
                outputs={},
            )
            with self.assertRaises(CompilationError):
                engine.compiler.compile(
                    conflicting,
                    context=CommandContext(strict=True),
                    grant=engine.grant,
                )

    def test_child_or_algorithm_cannot_broaden_capability(self) -> None:
        workflow = WorkflowDefinition(
            name="mutation",
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(
                    node_id="write",
                    command_id="eon.execute",
                    inputs={"changes": [{"type": "write", "path": "README.md", "content": "changed"}]},
                )
            ],
            outputs={},
        )
        with EGCFEngine(self.fixture.root) as engine:
            with self.assertRaises(QualificationError):
                engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)

    def test_conditional_checkpoint_pause_and_resume(self) -> None:
        workflow = WorkflowDefinition(
            name="checkpoint",
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(
                    node_id="first",
                    command_id="hrt.interpret",
                    inputs={"text": "hello"},
                    checkpoint=True,
                ),
                WorkflowNode(
                    node_id="second",
                    command_id="hrt.summary",
                    inputs={"text": {"$from": "first", "path": ["result", "objective"]}},
                    depends_on=["first"],
                    when={
                        "value": {"$from": "first", "path": ["result", "objective"]},
                        "equals": "hello",
                    },
                ),
            ],
            outputs={"summary": {"$from": "second", "path": ["result", "summary"]}},
        )
        with EGCFEngine(self.fixture.root) as engine:
            compiled = engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)
            plan = engine.create_execution_plan(compiled, prepare_mutations=False)
            paused = engine.execute_plan(plan.object_id, pause_at_checkpoint=True)
            self.assertEqual("PAUSED", paused["status"])
            resumed = engine.execute_plan(plan.object_id, resume=True)
            self.assertEqual("COMPLETED", resumed["status"])
            self.assertEqual("hello", resumed["outputs"][0]["result"]["summary"])


if __name__ == "__main__":
    unittest.main()
