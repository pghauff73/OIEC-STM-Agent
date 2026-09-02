from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.interaction import route_interaction
from ourd.workspace import Workspace


class InteractionRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "parser.py").write_text("pass\n", encoding="utf-8")
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_routes_projection_command(self) -> None:
        route = route_interaction("/topology", self.workspace)
        self.assertEqual("COMMAND", route.kind)
        self.assertEqual("projection.topology", route.target)
        self.assertFalse(route.requires_confirmation)

    def test_routes_attach_and_detach_to_context_state(self) -> None:
        self.assertEqual(
            "context.attach",
            route_interaction("/attach parser.py", self.workspace).target,
        )
        self.assertEqual(
            "context.detach",
            route_interaction("/detach parser.py", self.workspace).target,
        )

    def test_privileged_command_requires_confirmation(self) -> None:
        route = route_interaction("/approve plan-1", self.workspace)
        self.assertEqual("governance.approve", route.target)
        self.assertTrue(route.requires_confirmation)

    def test_routes_read_only_and_governed_intents(self) -> None:
        inspect_route = route_interaction("inspect @parser.py", self.workspace)
        write_route = route_interaction("fix @parser.py", self.workspace)
        execute_route = route_interaction("commit the candidate", self.workspace)
        self.assertEqual("agent.read_only", inspect_route.target)
        self.assertEqual("agent.governed_candidate", write_route.target)
        self.assertEqual("agent.governed_action", execute_route.target)
        self.assertTrue(write_route.requires_confirmation)
        self.assertTrue(execute_route.requires_confirmation)

    def test_route_is_non_authoritative_and_deterministic(self) -> None:
        first = route_interaction("compare parser alternatives", self.workspace)
        second = route_interaction("compare parser alternatives", self.workspace)
        self.assertFalse(first.authoritative)
        self.assertEqual(first.route_id, second.route_id)
        self.assertEqual(first.signature, second.signature)


if __name__ == "__main__":
    unittest.main()
