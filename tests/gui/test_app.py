from __future__ import annotations

import unittest

from ourd_gui.app import build_parser


class GuiAppTests(unittest.TestCase):
    def test_parser_accepts_repository_authority_and_smoke_mode(self) -> None:
        args = build_parser().parse_args(
            [
                "--repo",
                "/tmp/example",
                "--authority",
                "/tmp/a.json",
                "--model",
                "qwen3.8:16b",
                "--base-url",
                "http://localhost:11434/v1",
                "--api-key",
                "ollama",
                "--reasoning-effort",
                "high",
                "--max-output-tokens",
                "4096",
                "--context-budget",
                "8192",
                "--timeout-seconds",
                "120",
                "--transport-retries",
                "2",
                "--max-steps",
                "24",
                "--smoke-test",
            ]
        )
        self.assertEqual("/tmp/example", args.repo)
        self.assertEqual("/tmp/a.json", str(args.authority))
        self.assertTrue(args.smoke_test)
        self.assertEqual("qwen3.8:16b", args.model)
        self.assertEqual(8192, args.context_budget)
        self.assertEqual("ollama", args.api_key)
        self.assertEqual("high", args.reasoning_effort)
        self.assertEqual(4096, args.max_output_tokens)
        self.assertEqual(120, args.timeout_seconds)
        self.assertEqual(2, args.transport_retries)
        self.assertEqual(24, args.max_steps)


if __name__ == "__main__":
    unittest.main()
