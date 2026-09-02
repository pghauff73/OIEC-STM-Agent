from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd_gui.qwen_bootstrap import (
    QWEN38_DIRECT_MODEL_ID,
    QWEN38_FAST_PRODUCT_ALIAS,
    QwenBootstrapError,
    canonical_qwen_model,
    ensure_qwen38_fast,
    sha256_file,
)


class QwenBootstrapTests(unittest.TestCase):
    def test_product_alias_resolves_to_direct_process_model_id(self) -> None:
        self.assertEqual(QWEN38_DIRECT_MODEL_ID, canonical_qwen_model(QWEN38_FAST_PRODUCT_ALIAS))

    def test_direct_profile_without_paths_is_non_resident_and_service_free(self) -> None:
        result = ensure_qwen38_fast(requested_model=QWEN38_FAST_PRODUCT_ALIAS)
        self.assertEqual(QWEN38_FAST_PRODUCT_ALIAS, result.requested_model)
        self.assertEqual(QWEN38_DIRECT_MODEL_ID, result.resolved_model)
        self.assertFalse(result.service_started)
        self.assertFalse(result.warmed)
        self.assertFalse(result.resident)
        self.assertEqual("not_applicable", result.ollama_version)

    def test_direct_profile_binds_model_digest_and_size_when_model_path_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "oiec-llama-runner"
            model = root / "qwen3.8.gguf"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            model.write_bytes(b"qwen3.8")
            digest = sha256_file(model)

            result = ensure_qwen38_fast(
                requested_model=QWEN38_FAST_PRODUCT_ALIAS,
                runner_path=str(runner),
                model_path=str(model),
                expected_model_sha256=digest,
                base_url="ignored",
                urlopen=lambda *args, **kwargs: self.fail("network must not be used"),
            )

        self.assertEqual(digest, result.model_digest)
        self.assertEqual(7, result.model_size)
        self.assertTrue(result.resident)
        self.assertFalse(result.service_started)

    def test_missing_runner_fails_closed_when_runner_path_is_declared(self) -> None:
        with self.assertRaisesRegex(QwenBootstrapError, "runner is missing"):
            ensure_qwen38_fast(
                requested_model=QWEN38_FAST_PRODUCT_ALIAS,
                runner_path="/missing/oiec-llama-runner",
            )

    def test_missing_model_fails_closed_when_model_path_is_declared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "oiec-llama-runner"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            with self.assertRaisesRegex(QwenBootstrapError, "GGUF is missing"):
                ensure_qwen38_fast(
                    requested_model=QWEN38_FAST_PRODUCT_ALIAS,
                    runner_path=str(runner),
                    model_path="/missing/qwen3.8.gguf",
                )

    def test_digest_mismatch_fails_closed_before_profile_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "oiec-llama-runner"
            model = root / "qwen3.8.gguf"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            model.write_bytes(b"qwen3.8")
            with self.assertRaisesRegex(QwenBootstrapError, "digest mismatch"):
                ensure_qwen38_fast(
                    requested_model=QWEN38_FAST_PRODUCT_ALIAS,
                    runner_path=str(runner),
                    model_path=str(model),
                    expected_model_sha256="0" * 64,
                )

    def test_non_alias_model_is_rejected_for_automatic_profile(self) -> None:
        with self.assertRaisesRegex(QwenBootstrapError, "exact product alias"):
            ensure_qwen38_fast(requested_model="qwen3.8:16b")


if __name__ == "__main__":
    unittest.main()
