import unittest

from tools.evaluate_egcf_qwen import (
    build_raw_request,
    evaluate_response_quality,
    model_blob_digests,
)


class EGCFQwenEvaluationTests(unittest.TestCase):
    def test_exact_ollama_model_is_bound_to_raw_request(self) -> None:
        request = build_raw_request(
            model="qwen3.8-27b-fast:latest",
            prompt="review",
            context="evidence",
            temperature=0.2,
            top_p=0.8,
            max_new_tokens=100,
        )
        self.assertEqual("qwen3.8-27b-fast:latest", request["model"])
        self.assertTrue(request["raw"])
        self.assertEqual(8192, request["options"]["num_ctx"])
        self.assertEqual(["<|im_end|>"], request["options"]["stop"])

    def test_full_model_blob_digests_are_extracted(self) -> None:
        first = "a" * 64
        second = "b" * 64
        self.assertEqual(
            [first, second],
            model_blob_digests(f"FROM /models/sha256-{second}\nFROM sha256-{first}\n"),
        )

    def test_quality_gate_rejects_empty_cli_fallback(self) -> None:
        self.assertFalse(evaluate_response_quality("No response.")["ok"])
        response = (
            "</think> Strength: typed commands improve auditability. "
            "Counterexample: stale evidence could authorize an outdated graph. "
            "A missing test should mutate a referenced artifact after compilation. "
            "This report does not constitute approval. Release remains blocked pending human review."
        )
        self.assertTrue(evaluate_response_quality(response, "stop")["ok"])
        self.assertFalse(evaluate_response_quality(response, "length")["ok"])


if __name__ == "__main__":
    unittest.main()
