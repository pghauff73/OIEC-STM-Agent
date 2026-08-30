from __future__ import annotations

import re
import unittest
from pathlib import Path


class DocumentationSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"
        cls.javascript = (cls.docs_root / "assets" / "site.js").read_text(encoding="utf-8")

    def test_learning_tools_have_no_network_or_execution_path(self) -> None:
        for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket(", "EventSource(", "eval(", "new Function("):
            self.assertNotIn(forbidden, self.javascript)
        tools = (self.docs_root / "tools.html").read_text(encoding="utf-8")
        self.assertNotIn("OPENAI_API_KEY", tools)
        self.assertNotIn("sk-", tools)
        self.assertIn("not executed by the browser", self.javascript)

    def test_local_storage_is_limited_to_display_preferences(self) -> None:
        keys = set(re.findall(r'"(oiec-docs-[a-z-]+)"', self.javascript))
        self.assertTrue(keys)
        self.assertTrue(
            all(
                key.startswith(("oiec-docs-view", "oiec-docs-depth", "oiec-docs-teacher", "oiec-docs-vocab-"))
                for key in keys
            )
        )
        for forbidden in ("api-key", "repository-path", "task-text", "command-text"):
            self.assertNotIn(f'oiec-docs-{forbidden}', self.javascript)

    def test_untrusted_decoder_output_uses_text_content(self) -> None:
        decoder_start = self.javascript.index("function setupStatusDecoder")
        decoder_end = self.javascript.index("function shellQuote", decoder_start)
        decoder = self.javascript[decoder_start:decoder_end]
        self.assertIn("textContent", decoder)
        self.assertNotIn("innerHTML", decoder)


if __name__ == "__main__":
    unittest.main()
