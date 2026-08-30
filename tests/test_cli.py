import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from ourd import OURDAgent
from ourd.authority import scoped_write_authority
from ourd.cli import (
    LOOP_COMPLETE_SENTINEL,
    MAX_LOOP_ITERATIONS,
    _validate_write_args,
    build_parser,
    main as cli_main,
    parse_loop_command,
    run_loop_command,
)
from ourd.workspace import Workspace
from ourd.writing import writing_task_prompt
from tests.helpers import RepoFixture


class CliAndToolSchemaTests(unittest.TestCase):
    def test_loop_command_parses_bounded_count_and_placeholders(self) -> None:
        command = parse_loop_command(
            "/LoOp 3 Inspect repository page {index} of {count}"
        )
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(3, command.iterations)
        prompt = command.prompt(2)
        self.assertIn("iteration 2 of 3", prompt)
        self.assertIn("Inspect repository page 2 of 3", prompt)
        self.assertIn(LOOP_COMPLETE_SENTINEL, prompt)
        self.assertIn("cycle controls remain active", prompt)

    def test_loop_parser_ignores_ordinary_tasks_and_rejects_invalid_bounds(self) -> None:
        self.assertIsNone(parse_loop_command("Inspect the repository"))
        invalid_commands = (
            "/loop",
            "/loop 2",
            "/loop many inspect",
            "/loop 0 inspect",
            f"/loop {MAX_LOOP_ITERATIONS + 1} inspect",
        )
        for text in invalid_commands:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_loop_command(text)

    def test_loop_runner_stops_on_exact_completion_sentinel(self) -> None:
        class FakeAgent:
            def __init__(self) -> None:
                self.responses = ["first result", LOOP_COMPLETE_SENTINEL, "unused"]
                self.prompts: list[str] = []

            def run_chat_turn(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return self.responses.pop(0)

        agent = FakeAgent()
        command = parse_loop_command("/loop 3 Inspect page {index}/{count}")
        assert command is not None
        emitted: list[str] = []
        result = run_loop_command(
            agent,
            command,
            lambda prompt: f"bounded::{prompt}",
            emitted.append,
        )
        self.assertEqual(2, len(agent.prompts))
        self.assertIn("bounded::ICPI bounded CLI loop iteration 1 of 3", agent.prompts[0])
        self.assertIn("Inspect page 2/3", agent.prompts[1])
        self.assertEqual("completion_sentinel", result.stop_reason)
        self.assertEqual(2, result.completed_iterations)
        self.assertNotIn(LOOP_COMPLETE_SENTINEL, emitted)
        self.assertEqual("[loop completed at 2/3]", emitted[-1])

    def test_loop_runner_stops_at_iteration_limit_and_propagates_errors(self) -> None:
        class FakeAgent:
            def __init__(self, fail_at: int = 0) -> None:
                self.fail_at = fail_at
                self.calls = 0

            def run_chat_turn(self, prompt: str) -> str:
                self.calls += 1
                if self.calls == self.fail_at:
                    raise RuntimeError("provider failure")
                return f"result {self.calls}"

        command = parse_loop_command("/loop 3 Inspect")
        assert command is not None
        complete_agent = FakeAgent()
        result = run_loop_command(
            complete_agent,
            command,
            lambda prompt: prompt,
            lambda output: None,
        )
        self.assertEqual(3, complete_agent.calls)
        self.assertEqual("iteration_limit", result.stop_reason)
        self.assertEqual(3, result.completed_iterations)

        failing_agent = FakeAgent(fail_at=2)
        with self.assertRaisesRegex(RuntimeError, "provider failure"):
            run_loop_command(
                failing_agent,
                command,
                lambda prompt: prompt,
                lambda output: None,
            )
        self.assertEqual(2, failing_agent.calls)

    def test_interactive_cli_dispatches_loop_through_chat_turns(self) -> None:
        fixture = RepoFixture()
        try:
            class FakeAgent:
                def __init__(self) -> None:
                    self.ws = SimpleNamespace(root=fixture.root)
                    self.model = "test-model"
                    self.state = SimpleNamespace(
                        authority=SimpleNamespace(task_id="test-authority")
                    )
                    self.prompts: list[str] = []

                def __enter__(self) -> "FakeAgent":
                    return self

                def __exit__(self, exc_type, exc, traceback) -> None:
                    return None

                def run_chat_turn(self, prompt: str) -> str:
                    self.prompts.append(prompt)
                    return f"result {len(self.prompts)}"

            agent = FakeAgent()
            output = io.StringIO()
            with (
                mock.patch("ourd.cli.OURDAgent", return_value=agent),
                mock.patch(
                    "builtins.input",
                    side_effect=["/loop 2 Inspect {index}/{count}", "/exit"],
                ),
                redirect_stdout(output),
            ):
                status = cli_main([str(fixture.root)])
            self.assertEqual(0, status)
            self.assertEqual(2, len(agent.prompts))
            self.assertIn("Inspect 1/2", agent.prompts[0])
            self.assertIn("Inspect 2/2", agent.prompts[1])
            self.assertIn("[loop 1/2]", output.getvalue())
            self.assertIn("result 2", output.getvalue())
        finally:
            fixture.close()

    def test_cli_preserves_repo_contract_and_bounded_provider_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["workspace"])
        self.assertEqual("workspace", args.repo)
        self.assertEqual(0, args.transport_retries)
        self.assertGreaterEqual(args.context_budget, 256)
        self.assertEqual("oiec-stm-agent", parser.prog)
        self.assertFalse(args.write)
        self.assertEqual([], args.write_path)
        self.assertEqual("general", args.writing_profile)

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

    def test_formal_profile_requires_write_mode_and_is_forwarded_to_prompt(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["workspace", "--writing-profile", "scientific-essay"]
        )
        with self.assertRaises(SystemExit):
            _validate_write_args(parser, args)

        args = parser.parse_args(
            [
                "workspace",
                "--write",
                "--write-path",
                "essay.md",
                "--writing-profile",
                "argumentative-essay",
            ]
        )
        _validate_write_args(parser, args)
        self.assertEqual("argumentative-essay", args.writing_profile)

        prompt = writing_task_prompt(
            "Write an argumentative essay.",
            ["essay.md"],
            profile=args.writing_profile,
        )
        self.assertIn("Writing profile: argumentative-essay", prompt)
        self.assertIn("LOGIC TOPOLOGY PROFILE", prompt)
        self.assertIn("counterclaim", prompt.lower())

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
        self.assertIn("human readability", prompt)
        self.assertIn("Write docs/overview.md", prompt)

    def test_scientific_writing_prompt_embeds_research_backed_dimensions(self) -> None:
        prompt = writing_task_prompt(
            "Write a scientific essay on the evidence for a proposed mechanism.",
            ["essay.md"],
            profile="scientific-essay",
        )
        self.assertIn("SCIENTIFIC ESSAY PROFILE", prompt)
        self.assertIn("scientific claim calibration", prompt)
        self.assertIn("causal inference", prompt)
        self.assertIn("reproducibility", prompt.lower())
        self.assertIn("never invent references", prompt.lower())

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
            list_files = next(tool for tool in tools if tool["name"] == "list_files")
            self.assertIn("offset", list_files["parameters"]["properties"])
            self.assertIn("max_results", list_files["parameters"]["properties"])
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
