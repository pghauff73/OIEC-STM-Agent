from __future__ import annotations

import unittest

from ourd_gui.paging import incremental_window


class PagingTests(unittest.TestCase):
    def test_selected_task_remains_visible_outside_incremental_window(self) -> None:
        identifiers = [f"TASK-{index:04d}" for index in range(1_200)]
        visible = incremental_window(
            identifiers,
            limit=500,
            selected_id="TASK-1199",
        )
        self.assertEqual(501, len(visible))
        self.assertEqual("TASK-1199", visible[-1])
        self.assertEqual(len(visible), len(set(visible)))


if __name__ == "__main__":
    unittest.main()
