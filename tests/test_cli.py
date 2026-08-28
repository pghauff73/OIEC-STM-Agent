import unittest

from ourd import OURDAgent
from ourd.authority import scoped_write_authority
from ourd.cli import _validate_write_args, build_parser
from ourd.workspace import Workspace
from ourd.writing import writing_task_prompt
from tests.helpers import RepoFixture


class CliAndToolSchemaTests(unittest.TestCase):
    def test_cli_preserves_repo_contract_and_bounded_provider_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["workspace"])
        self.assertEqual("workspace", args.repo)
        self.assertEqual(0, args.transport_retries)
        self.assertGreaterEqual(args.context_budget, 256)
        self.assertEqual("oiec-stm-agent", parser.prog)
        self.assertFalse(args.write)
        self.assertEqual([], args.write_path)

    def test_bounded_write_mode_requires_explicit_scope(self) -> None:
        parser = build_parser()
        missing_scope = parser.parse_args(["workspace", "--write"])
        with self.assertRaises(SystemExit):
            _validate_write_args(parser, missing_scope)

        args = parser.parse_args(
            [
                "workspace",
                "--write",
                "--write-path",
                "docs/**",
                "--write-path",
                "README.md",
            ]
        )
        _validate_write_args(parser, args)
        self.assertTrue(args.write)
        self.assertEqual(["docs/**", "README.md"], args.write_path)

    def test_cli_write_authority_is_exact_snapshot_and_not_yolo(self) -> None:
        fixture = RepoFixture()
        try:
            workspace = Workspace(fixture.root)
            manifest = scoped_write_authority(
                workspace,
                allowed_paths=["docs/**", "README.md"],
                goal="Write project documentation",
                operator="test-user",
            )
            self.assertFalse(manifest.read_only)
            self.assertEqual(workspace.snapshot_hash(), manifest.source_snapshot_hash)
            self.assertEqual(["docs/**", "README.md"], manifest.allowed_paths)
            self.assertEqual([".ourd-agent/**"], manifest.forbidden_paths)
            self.assertEqual("L0", manifest.max_automatic_risk)
            self.assertFalse(manifest.allow_l1_auto_apply)
            self.assertFalse(manifest.allow_yolo)
            self.assertFalse(manifest.allow_interactive_l2)
            self.assertEqual("C3", manifest.semantic_capability_ceiling)
        finally:
            fixture.close()

    def test_writing_prompt_requires_governed_workspace_mutation(self) -> None:
        prompt = writing_task_prompt(
            "Write docs/overview.md explaining the project.",
            ["docs/**"],
        )
        self.assertIn("HUMAN-GRANTED BOUNDED WRITING MODE", prompt)
        self.assertIn("docs/**", prompt)
        self.assertIn("prepare candidate transaction", prompt)
        self.assertIn("natural, coherent human-readable prose", prompt)
        self.assertIn("Write docs/overview.md", prompt)

    def test_tool_schemas_are_strict_and_expose_only_staged_writes(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root) as agent:
                tools = agent.tool_specs()
            names = {tool["name"] for tool in tools}
            self.assertNotIn("write_file", names)
            self.assertNotIn("replace_text", names)
            self.assertIn("prepare_write_file", names)
            self.assertIn("prepare_replace_text", names)
            self.assertTrue(all(tool["strict"] for tool in tools))
            self.assertTrue(
                all(tool["parameters"]["additionalProperties"] is False for tool in tools)
            )
            eon = next(tool for tool in tools if tool["name"] == "propose_eon_action")
            self.assertIn("commands", eon["parameters"]["required"])
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
