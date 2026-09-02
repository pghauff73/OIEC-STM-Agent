import unittest

from ourd import OURDAgent
from ourd.authority import scoped_write_authority
from ourd.cli import _compile_formal_write_request, _validate_write_args, build_parser
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
        self.assertEqual(0, args.runtime_context_tokens)
        self.assertEqual(512, args.context_safety_margin)
        self.assertEqual("oiec-stm-agent", parser.prog)
        self.assertFalse(args.write)
        self.assertEqual([], args.write_path)
        self.assertEqual("general", args.writing_profile)
        self.assertEqual("llama_cpp_process", args.provider)

    def test_cli_accepts_direct_qwen_process_configuration(self) -> None:
        args = build_parser().parse_args(
            [
                "workspace",
                "--provider",
                "llama_cpp_process",
                "--model",
                "qwen3.8-27b-direct",
                "--runner-path",
                "/tmp/oiec-llama-runner",
                "--model-path",
                "/tmp/qwen3.8.gguf",
                "--expected-model-sha256",
                "a" * 64,
                "--llama-context",
                "4096",
                "--llama-gpu-layers",
                "32",
                "--llama-temperature-bp",
                "0",
                "--llama-top-p-bp",
                "10000",
                "--llama-top-k",
                "1",
            ]
        )
        self.assertEqual("llama_cpp_process", args.provider)
        self.assertEqual("qwen3.8-27b-direct", args.model)
        self.assertEqual(32, args.llama_gpu_layers)
        self.assertEqual(0, args.llama_temperature_bp)
        self.assertEqual(10000, args.llama_top_p_bp)
        self.assertEqual(1, args.llama_top_k)

    def test_cli_exposes_bounded_super_reasoning_controls(self) -> None:
        args = build_parser().parse_args(
            [
                "workspace",
                "--sr-max-candidates",
                "8",
                "--sr-max-provider-calls",
                "32",
                "--sr-minimum-voi-bp",
                "250",
                "--disable-super-reasoning",
            ]
        )
        self.assertEqual(8, args.sr_max_candidates)
        self.assertEqual(32, args.sr_max_provider_calls)
        self.assertEqual(250, args.sr_minimum_voi_bp)
        self.assertTrue(args.disable_super_reasoning)

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

    def test_existing_write_cli_compiles_shared_formal_request(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "workspace",
                "--write",
                "--write-path",
                "essay.md",
                "--source",
                "research/paper.md",
                "--rubric",
                "assignment/rubric.md",
                "--writing-profile",
                "scientific-essay",
                "--citation-style",
                "apa-7",
                "--word-target",
                "2500",
            ]
        )
        _validate_write_args(parser, args)
        request = _compile_formal_write_request(
            args,
            "Evaluate the proposed mechanism.",
            authority_binding="authority:test",
        )
        self.assertEqual("WRITE", request.operation)
        self.assertEqual(("research/paper.md",), request.source_paths)
        self.assertEqual(("assignment/rubric.md",), request.rubric_paths)
        self.assertEqual(("essay.md",), request.output_paths)
        self.assertEqual("apa-7", request.citation_style)
        self.assertEqual(2500, request.word_target)
        self.assertEqual("authority:test", request.authority_binding)

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
            self.assertNotIn("run_super_reasoning", names)
            self.assertTrue(all(tool["strict"] for tool in tools))
            self.assertTrue(
                all(tool["parameters"]["additionalProperties"] is False for tool in tools)
            )
            eon = next(tool for tool in tools if tool["name"] == "propose_eon_action")
            self.assertIn("commands", eon["parameters"]["required"])
        finally:
            fixture.close()

    def test_disabled_super_reasoning_is_not_exposed_as_a_tool(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, super_reasoning_enabled=False) as agent:
                names = {tool["name"] for tool in agent.tool_specs()}
            self.assertNotIn("run_super_reasoning", names)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
