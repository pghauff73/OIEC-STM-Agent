from __future__ import annotations

import unittest

from ourd_gui.model_backend import model_backend_info


class ModelBackendTests(unittest.TestCase):
    def test_local_backend_and_quantization_are_observational(self) -> None:
        info = model_backend_info(
            model="qwen3.8:16b-q4_k_m",
            base_url="http://127.0.0.1:11434/v1",
            context_tokens=8192,
            environment={},
        )
        self.assertIn("Ollama", info.backend)
        self.assertEqual("Q4_K_M", info.quantization)
        self.assertFalse(info.authoritative)


if __name__ == "__main__":
    unittest.main()
