from __future__ import annotations

import contextlib
import io
import unittest

from tools.docs_cli_catalog import PROGRAMS, RECIPES, REJECTED_RECIPES, validate_recipes


class DocumentationCliCatalogTests(unittest.TestCase):
    def test_program_aliases_and_recipes_match_real_parsers(self) -> None:
        validate_recipes()
        by_command = {program.command: program for program in PROGRAMS}
        self.assertEqual(by_command["ourd-agent"].alias_of, "agent")
        self.assertEqual(by_command["ourd-gui"].alias_of, "gui")
        self.assertEqual(len(RECIPES), len({recipe.command_id for recipe in RECIPES}))

    def test_rejected_write_recipes_remain_rejected(self) -> None:
        from ourd.cli import _validate_write_args, build_parser

        parser = build_parser()
        for recipe in REJECTED_RECIPES:
            with self.subTest(recipe=recipe.command_id):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit), contextlib.redirect_stderr(stderr):
                    args = parser.parse_args(list(recipe.argv[1:]))
                    _validate_write_args(parser, args)
                self.assertIn(recipe.reason_fragment, stderr.getvalue())

    def test_generated_recipes_do_not_contain_real_secrets(self) -> None:
        commands = "\n".join(recipe.command for recipe in RECIPES)
        self.assertNotIn("sk-", commands)
        self.assertNotIn("OPENAI_API_KEY=", commands)
        self.assertIn("--provider llama_cpp_process", commands)
        self.assertIn("--model-path ../Neuro-llama/Qwen3.8-27B-Q2_K.gguf", commands)


if __name__ == "__main__":
    unittest.main()
