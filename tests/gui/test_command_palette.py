from __future__ import annotations

import unittest

from ourd_gui.command_palette import CommandPaletteRegistry, PaletteCommand


class CommandPaletteTests(unittest.TestCase):
    def test_search_matches_all_terms_and_executes_exact_command(self) -> None:
        called: list[str] = []
        registry = CommandPaletteRegistry(
            [
                PaletteCommand(
                    "ieps.gate",
                    "Run Evidence Gate",
                    "IEPS",
                    "Inspect evidence before authority",
                    lambda: called.append("gate"),
                ),
                PaletteCommand(
                    "algorithm.trace",
                    "Show Selection Trace",
                    "Algorithm",
                    "Explain qualified algorithm selection",
                    lambda: called.append("trace"),
                ),
            ]
        )
        self.assertEqual(
            ["algorithm.trace"],
            [item.command_id for item in registry.search("qualified trace")],
        )
        registry.execute("ieps.gate")
        self.assertEqual(["gate"], called)

    def test_duplicate_command_ids_are_rejected(self) -> None:
        command = PaletteCommand("x", "X", "Test", "", lambda: None)
        registry = CommandPaletteRegistry([command])
        with self.assertRaises(ValueError):
            registry.register(command)


if __name__ == "__main__":
    unittest.main()
