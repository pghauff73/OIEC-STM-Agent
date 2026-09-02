from __future__ import annotations

import json
import unittest

from ourd.context_budget import FIT, recover_context_request


class ContextBudgetSemanticArtifactTests(unittest.TestCase):
    def test_markdown_outline_survives_read_file_compaction(self) -> None:
        body = "\n".join(
            [
                "    1 | # Architecture",
                "    2 | The controller owns authoritative state.",
                "    3 | Views are read-only projections.",
                "    4 | Ignored detail " + "x" * 8_000,
                "    5 | ## Limitations",
                "    6 | Human approval remains external.",
            ]
        )
        call = {
            "type": "function_call",
            "name": "read_file",
            "arguments": "{}",
            "call_id": "read-call",
        }
        output = {
            "type": "function_call_output",
            "call_id": "read-call",
            "output": json.dumps(
                {
                    "ok": True,
                    "path": "docs/GUI_ARCHITECTURE.md",
                    "start_line": 1,
                    "end_line": 6,
                    "content": body,
                    "evidence_id": "evidence:read",
                }
            ),
        }
        result = recover_context_request(
            instructions="system",
            input_items=[{"role": "user", "content": "summarize"}, call, output],
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=900,
        )
        self.assertEqual(FIT, result.report.verdict)
        decoded = json.loads(result.input_items[2]["output"])
        outline = decoded["semantic_artifacts"]["document_outline"]
        self.assertEqual("docs/GUI_ARCHITECTURE.md", outline["path"])
        self.assertIn("# Architecture", outline["outline"])
        self.assertIn("Human approval remains external.", outline["outline"])

    def test_completed_summary_survives_compaction(self) -> None:
        call = {"type": "function_call", "name": "record_document_summary", "arguments": "{}", "call_id": "summary-call"}
        output = {
            "type": "function_call_output",
            "call_id": "summary-call",
            "output": json.dumps(
                {
                    "ok": True,
                    "context_preserve": True,
                    "evidence_ids": ["evidence:read"],
                    "summary": {
                        "summary_id": "summary:test",
                        "manifest_id": "corpus:test",
                        "path": "docs/a.md",
                        "summary_text": "important semantic summary " + "x" * 12000,
                        "summary_sha256": "a" * 64,
                        "source_read_evidence_ids": ["evidence:read-a", "evidence:read-b"],
                        "coverage_complete": True,
                        "epistemic_status": "MODEL_SUMMARY_BOUND_TO_VERIFIED_SOURCE",
                    },
                }
            ),
        }
        result = recover_context_request(
            instructions="system",
            input_items=[{"role": "user", "content": "summarize"}, call, output],
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=1600,
        )
        self.assertEqual(FIT, result.report.verdict)
        decoded = json.loads(result.input_items[2]["output"])
        self.assertEqual("summary:test", decoded["semantic_artifacts"]["document_summary"]["summary_id"])
        self.assertIn("important semantic summary", decoded["semantic_artifacts"]["document_summary"]["summary_text"])
        self.assertEqual(
            ["evidence:read-a", "evidence:read-b"],
            decoded["semantic_artifacts"]["document_summary"]["source_read_evidence_ids"],
        )


if __name__ == "__main__":
    unittest.main()
