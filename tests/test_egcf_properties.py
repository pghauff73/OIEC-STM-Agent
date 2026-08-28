from __future__ import annotations

import itertools
import random
import time
import unittest

from ourd.egcf.context import CommandContext, narrow_scope
from ourd.egcf.engine import EGCFEngine
from ourd.egcf.errors import CompilationError, SchemaError
from ourd.egcf.experiments import ExperimentDesigner
from ourd.egcf.ieps import IEPS
from ourd.egcf.models import WorkflowDefinition, WorkflowNode
from tests.helpers import RepoFixture


class EGCFPropertyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.fixture.write("src/parser.py", "def parse(value):\n    return value\n")

    def tearDown(self) -> None:
        self.fixture.close()

    def test_scope_narrowing_property(self) -> None:
        random.seed(20260821)
        parents = ["**", "src/**", "tests/**", "README.md"]
        children = ["src/parser.py", "src/sub/module.py", "tests/test_parser.py", "README.md"]
        for _ in range(100):
            parent = random.choice(parents)
            child = random.choice(children)
            if parent == "**" or child == parent or (
                parent.endswith("/**") and child.startswith(parent[:-3].rstrip("/") + "/")
            ):
                self.assertEqual([child], narrow_scope([parent], [child]))
            else:
                with self.assertRaises(CompilationError):
                    narrow_scope([parent], [child])

    def test_pairwise_covering_contains_every_pair(self) -> None:
        parameters = {"a": [0, 1], "b": ["x", "y", "z"], "c": [False, True]}
        rows = ExperimentDesigner().covering(parameters)
        for left, right in itertools.combinations(parameters, 2):
            observed = {(row[left], row[right]) for row in rows}
            expected = set(itertools.product(parameters[left], parameters[right]))
            self.assertEqual(expected, observed)

    def test_graph_hash_changes_only_for_executable_semantics(self) -> None:
        workflow = WorkflowDefinition(
            name="identity",
            version=1,
            parameters={},
            nodes=[WorkflowNode(node_id="interpret", command_id="hrt.interpret", inputs={"text": "a"})],
            outputs={},
        )
        changed = WorkflowDefinition(
            name="identity",
            version=1,
            parameters={},
            nodes=[WorkflowNode(node_id="interpret", command_id="hrt.interpret", inputs={"text": "b"})],
            outputs={},
        )
        with EGCFEngine(self.fixture.root) as engine:
            baseline = engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)
            projection_only = engine.compiler.compile(
                workflow,
                context=CommandContext(why=True, graph=True, json_output=True, trace=True),
                grant=engine.grant,
            )
            executable_change = engine.compiler.compile(changed, context=CommandContext(), grant=engine.grant)
            self.assertEqual(baseline.graph_hash, projection_only.graph_hash)
            self.assertNotEqual(baseline.graph_hash, executable_change.graph_hash)

    def test_replay_recompiles_and_reports_same_graph_on_same_snapshot(self) -> None:
        with EGCFEngine(self.fixture.root) as engine:
            compiled, _, _ = engine.compile_command("repo.metrics", {})
            plan = engine.create_execution_plan(compiled, prepare_mutations=False)
            replay = engine.replay(plan.object_id, {"why": True, "graph": True})
            self.assertTrue(replay["same_snapshot"])
            self.assertTrue(replay["same_graph"])
            self.assertNotEqual(plan.object_id, replay["replayed_plan_id"])

    def test_schema_fuzz_unknown_fields_fail_closed(self) -> None:
        with EGCFEngine(self.fixture.root) as engine:
            for index in range(25):
                with self.subTest(index=index):
                    with self.assertRaises(SchemaError):
                        engine.compile_command("hrt.interpret", {f"unknown_{index}": index})

    def test_differential_repo_metrics_and_compile_performance(self) -> None:
        with EGCFEngine(self.fixture.root) as engine:
            response = engine.invoke("repo.metrics", {})
            observed = response["outputs"][-1]["result"]["file_count"]
            expected = len(list(engine.workspace.iter_files()))
            self.assertEqual(expected, observed)
            workflow = WorkflowDefinition(
                name="performance",
                version=1,
                parameters={},
                nodes=[
                    WorkflowNode(
                        node_id=f"node-{index:02d}",
                        command_id="hrt.summary",
                        inputs={"text": str(index)},
                        depends_on=[f"node-{index - 1:02d}"] if index else [],
                    )
                    for index in range(30)
                ],
                outputs={},
            )
            started = time.monotonic()
            compiled = engine.compiler.compile(workflow, context=CommandContext(), grant=engine.grant)
            elapsed = time.monotonic() - started
            self.assertEqual(30, len(compiled.nodes))
            self.assertLess(elapsed, 10.0)

    def test_mutation_score_preserves_survivors(self) -> None:
        result = IEPS.mutation(
            [
                {"name": "flip comparison", "detected": True},
                {"name": "remove approval check", "detected": False},
            ]
        )
        self.assertEqual(0.5, result["mutation_score"])
        self.assertEqual("remove approval check", result["survivors"][0]["name"])


if __name__ == "__main__":
    unittest.main()
