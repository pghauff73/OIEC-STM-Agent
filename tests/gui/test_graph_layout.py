from __future__ import annotations

import time
import unittest

from ourd_gui.widgets.graph_view import GraphNode, GraphView


class GraphLayoutTests(unittest.TestCase):
    def test_layout_is_deterministic_and_layered(self) -> None:
        nodes = [
            GraphNode("candidate-b", "B", 2, 1),
            GraphNode("intent", "Intent", 0, 0),
            GraphNode("candidate-a", "A", 2, 0),
            GraphNode("capability", "Capability", 1, 0),
        ]
        first = GraphView.layout(nodes)
        second = GraphView.layout(reversed(nodes))
        self.assertEqual(first, second)
        self.assertLess(first["intent"][0], first["capability"][0])
        self.assertLess(first["capability"][0], first["candidate-a"][0])
        self.assertLess(first["candidate-a"][1], first["candidate-b"][1])

    def test_layout_of_one_hundred_candidates_is_bounded(self) -> None:
        nodes = [
            GraphNode(
                node_id=f"candidate-{index}",
                label=f"Candidate {index}",
                layer=2,
                order=index,
            )
            for index in range(100)
        ]
        started = time.perf_counter()
        layout = GraphView.layout(nodes)
        elapsed = time.perf_counter() - started
        self.assertEqual(100, len(layout))
        self.assertLess(elapsed, 0.1)


if __name__ == "__main__":
    unittest.main()
