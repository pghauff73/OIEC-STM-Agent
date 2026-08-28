from __future__ import annotations

import unittest

from ourd_gui.state import GuiTask
from ourd_gui.task_projections import domain_graph_for_task, iurm_for_task, semantic_outputs


class TaskProjectionTests(unittest.TestCase):
    def test_extracts_canonical_domain_graph(self) -> None:
        task = GuiTask(
            task_id="task-1",
            session_id="session-1",
            title="domain",
            last_result={
                "outputs": [
                    {
                        "command_id": "ourd.graph@1",
                        "result": {
                            "nodes": [{"id": "Parser", "type": "object"}],
                            "edges": [],
                        },
                    }
                ]
            },
        )
        projection = domain_graph_for_task(task)
        self.assertTrue(projection.canonical_relationships)
        self.assertEqual("Parser", projection.nodes[0]["id"])

    def test_iurm_projection_uses_returned_dimensions_and_pairs(self) -> None:
        task = GuiTask(
            task_id="task-1",
            session_id="session-1",
            title="experiment",
            last_result={
                "outputs": [
                    {
                        "command_id": "iurm.dimensions@1",
                        "result": {"dimensions": {"time": [0, 1], "angle": [-30, 30]}},
                    },
                    {
                        "command_id": "iurm.interactions@1",
                        "result": {"pairs": [["angle", "time"]]},
                    },
                ]
            },
        )
        projection = iurm_for_task(task)
        self.assertEqual(["angle", "time"], [item.name for item in projection.dimensions])
        self.assertEqual(("time",), projection.dimensions[0].interactions)
        self.assertEqual(2, len(semantic_outputs(task.last_result)))


if __name__ == "__main__":
    unittest.main()
