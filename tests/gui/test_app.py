from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ourd.providers import QWEN38_Q2_K_SHA256
from ourd_gui.app import automatic_qwen_bootstrap_requested, build_parser, main
from ourd_gui.qwen_bootstrap import QwenBootstrapResult


class GuiAppTests(unittest.TestCase):
    def test_exact_product_alias_enables_implicit_qwen_bootstrap(self) -> None:
        self.assertTrue(
            automatic_qwen_bootstrap_requested(
                arguments=["--repo", "."],
                executable_name="oiec-stm-sr-AgentICPI",
                explicit_setting=None,
                environment={},
            )
        )
        self.assertFalse(
            automatic_qwen_bootstrap_requested(
                arguments=["--repo", ".", "--model", "another"],
                executable_name="oiec-stm-sr-AgentICPI",
                explicit_setting=None,
                environment={},
            )
        )
        self.assertFalse(
            automatic_qwen_bootstrap_requested(
                arguments=["--repo", "."],
                executable_name="oiec-stm-sr-agent-icpi",
                explicit_setting=None,
                environment={},
            )
        )
        self.assertTrue(
            automatic_qwen_bootstrap_requested(
                arguments=["--repo", ".", "--auto-qwen"],
                executable_name="python3",
                explicit_setting=True,
                environment={"OURD_MODEL": "another"},
            )
        )

    def test_exact_product_invocation_applies_verified_qwen_profile(self) -> None:
        captured = {}

        class FakeWorkbench:
            def __init__(self, repository_root, **kwargs):
                captured["repository_root"] = repository_root
                captured.update(kwargs)

            def update_idletasks(self):
                return None

            def update(self):
                return None

            def _close(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-leak"}, clear=True):
                with mock.patch("sys.argv", ["oiec-stm-sr-AgentICPI"]):
                    with mock.patch("ourd_gui.app.OURDWorkbench", FakeWorkbench):
                        exit_code = main(
                            [
                                "--repo",
                                temporary,
                                "--smoke-test",
                            ]
                        )
        self.assertEqual(0, exit_code)
        self.assertEqual(Path(temporary).resolve(), captured["repository_root"])
        self.assertEqual("llama_cpp_process", captured["provider_kind"])
        self.assertEqual("qwen3.8-27b-direct", captured["model"])
        self.assertEqual("", captured["base_url"])
        self.assertEqual("", captured["api_key"])
        self.assertEqual("none", captured["reasoning_effort"])
        self.assertEqual(6000, captured["context_budget"])
        self.assertEqual(8192, captured["runtime_context_tokens"])
        self.assertEqual(512, captured["context_safety_margin_tokens"])
        self.assertEqual(1400, captured["max_output_tokens"])
        result = captured["qwen_bootstrap_result"]
        self.assertIsInstance(result, QwenBootstrapResult)
        self.assertEqual("qwen3.8:27B-Fast", result.requested_model)
        self.assertEqual("qwen3.8-27b-direct", result.resolved_model)
        self.assertEqual(QWEN38_Q2_K_SHA256, result.model_digest)
        self.assertFalse(result.service_started)
        self.assertFalse(result.warmed)
        self.assertFalse(result.resident)

    def test_parser_accepts_repository_authority_and_smoke_mode(self) -> None:
        args = build_parser().parse_args(
            [
                "--repo",
                "/tmp/example",
                "--provider",
                "llama_cpp_process",
                "--authority",
                "/tmp/a.json",
                "--model",
                "qwen3.8:16b",
                "--reasoning-effort",
                "high",
                "--max-output-tokens",
                "4096",
                "--context-budget",
                "8192",
                "--runtime-context-tokens",
                "12288",
                "--context-safety-margin",
                "768",
                "--timeout-seconds",
                "120",
                "--transport-retries",
                "2",
                "--max-reasoning-samples",
                "12",
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
                "--llama-cpp-root",
                "/tmp/llama.cpp",
                "--llama-grammar-dir",
                "/tmp/grammars",
                "--llama-threads",
                "12",
                "--llama-seed",
                "1234",
                "--llama-temperature-bp",
                "0",
                "--llama-top-p-bp",
                "10000",
                "--llama-top-k",
                "1",
                "--max-steps",
                "24",
                "--smoke-test",
            ]
        )
        self.assertEqual("/tmp/example", args.repo)
        self.assertEqual("/tmp/a.json", str(args.authority))
        self.assertEqual("llama_cpp_process", args.provider)
        self.assertTrue(args.smoke_test)
        self.assertEqual("qwen3.8:16b", args.model)
        self.assertEqual(8192, args.context_budget)
        self.assertEqual(12288, args.runtime_context_tokens)
        self.assertEqual(768, args.context_safety_margin)
        self.assertEqual("", args.api_key)
        self.assertEqual("high", args.reasoning_effort)
        self.assertEqual(4096, args.max_output_tokens)
        self.assertEqual(120, args.timeout_seconds)
        self.assertEqual(2, args.transport_retries)
        self.assertEqual(12, args.max_reasoning_samples)
        self.assertEqual("/tmp/llama.cpp", args.llama_cpp_root)
        self.assertEqual("/tmp/grammars", args.llama_grammar_dir)
        self.assertEqual(12, args.llama_threads)
        self.assertEqual(0, args.llama_temperature_bp)
        self.assertEqual(10000, args.llama_top_p_bp)
        self.assertEqual(1, args.llama_top_k)
        self.assertEqual(24, args.max_steps)


if __name__ == "__main__":
    unittest.main()
