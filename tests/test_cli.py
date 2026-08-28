import unittest

from ourd import OURDAgent
from ourd.cli import build_parser
from tests.helpers import RepoFixture


class CliAndToolSchemaTests(unittest.TestCase):
    def test_cli_preserves_repo_contract_and_bounded_provider_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["workspace"])
        self.assertEqual("workspace", args.repo)
        self.assertEqual(0, args.transport_retries)
        self.assertGreaterEqual(args.context_budget, 256)
        self.assertEqual("oiec-stm-agent", parser.prog)

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
