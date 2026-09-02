from __future__ import annotations

from types import SimpleNamespace
import json
import unittest

from ourd.agent import OURDAgent as BaseOURDAgent
from ourd.context_budget import (
    DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE,
    FIT,
    INSUFFICIENT_CONTEXT_BUDGET,
    effective_input_budget,
    estimate_tokens,
    format_context_budget_error,
    recover_context_request,
)
from ourd.errors import ContextBudgetError
from ourd.providers.base import ProviderConfig
from tests.helpers import RepoFixture


class RecordingProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.calls = 0
        self.requests = []

    def preflight(self):
        return {"status": "ready", "model": self.config.model}

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        self.requests.append(
            {
                "instructions": instructions,
                "input_items": list(input_items),
                "tools": list(tools),
            }
        )
        return SimpleNamespace(output=[], output_text="done")


class MinimalAgent(BaseOURDAgent):
    def instructions(self) -> str:
        return "minimal-system"

    def tool_specs(self):
        return []


class ContextBudgetTests(unittest.TestCase):
    def test_effective_budget_reserves_output_and_margin(self) -> None:
        self.assertEqual(
            6_980,
            effective_input_budget(
                configured_input_budget_tokens=8_000,
                runtime_context_tokens=8_192,
                reserved_output_tokens=700,
                safety_margin_tokens=512,
            ),
        )
        self.assertEqual(
            6_000,
            effective_input_budget(
                configured_input_budget_tokens=6_000,
                runtime_context_tokens=8_192,
                reserved_output_tokens=700,
                safety_margin_tokens=512,
            ),
        )

    def test_request_that_already_fits_is_unchanged(self) -> None:
        items = ({"role": "user", "content": "inspect"},)
        result = recover_context_request(
            instructions="system",
            input_items=items,
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=1_000,
        )
        self.assertEqual(FIT, result.report.verdict)
        self.assertEqual(items, result.input_items)
        self.assertEqual((), result.report.reduction_steps)

    def test_oldest_whole_unpinned_turn_is_removed(self) -> None:
        history = [
            {"role": "user", "content": "old-user-" + ("x" * 600)},
            {"role": "assistant", "content": "old-assistant-" + ("y" * 600)},
            {"role": "user", "content": "new-user"},
            {"role": "assistant", "content": "new-assistant"},
        ]
        current = {"role": "user", "content": "current-task"}
        retained = history[2:] + [current]
        budget = estimate_tokens(
            {"instructions": "system", "input": retained, "tools": []}
        )
        result = recover_context_request(
            instructions="system",
            input_items=[*history, current],
            tools=(),
            history_item_count=len(history),
            configured_input_budget_tokens=budget,
        )
        self.assertEqual(FIT, result.report.verdict)
        self.assertEqual(tuple(retained), result.input_items)
        self.assertEqual(2, result.history_item_count)
        self.assertEqual(2, result.report.removed_history_item_count)
        self.assertEqual(1, len(result.report.reduction_steps))
        self.assertEqual(2, result.report.reduction_steps[0].affected_item_count)

    def test_completed_tool_outputs_are_compacted_with_evidence_binding(self) -> None:
        current = {"role": "user", "content": "current-task"}
        first_call = {
            "type": "function_call",
            "name": "list_files",
            "arguments": "{}",
            "call_id": "call-1",
        }
        first_output = {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": '{"ok":true,"evidence_id":"ev-1","files":"'
            + ("x" * 24_000)
            + '"}',
        }
        second_call = {
            "type": "function_call",
            "name": "git_status",
            "arguments": "{}",
            "call_id": "call-2",
        }
        second_output = {
            "type": "function_call_output",
            "call_id": "call-2",
            "output": '{"ok":true,"evidence_id":"ev-2","stdout":"'
            + ("y" * 24_000)
            + '"}',
        }
        result = recover_context_request(
            instructions="system",
            input_items=[current, first_call, first_output, second_call, second_output],
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=1_500,
        )
        self.assertEqual(FIT, result.report.verdict)
        self.assertEqual(2, result.report.compacted_tool_output_count)
        self.assertEqual(current, result.input_items[0])
        self.assertEqual(first_call, result.input_items[1])
        self.assertEqual(second_call, result.input_items[3])
        for index, evidence_id in ((2, "ev-1"), (4, "ev-2")):
            projected = result.input_items[index]
            self.assertEqual(f"call-{1 if index == 2 else 2}", projected["call_id"])
            decoded = json.loads(projected["output"])
            self.assertTrue(decoded["context_budget_compacted"])
            self.assertIn(evidence_id, decoded["evidence_ids"])
            self.assertTrue(decoded["original_output_sha256"])
            self.assertGreater(decoded["original_output_character_count"], 20_000)

    def test_forced_compaction_never_increases_serialized_request_size(self) -> None:
        current = {"role": "user", "content": "current-task"}
        call = {
            "type": "function_call",
            "name": "read_file",
            "arguments": "{}",
            "call_id": "call-1",
        }
        output = {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": json.dumps(
                {
                    "ok": True,
                    "path": "ourd/formal_writing.py",
                    "content": "x" * 436,
                    "evidence_id": "evidence:test",
                }
            ),
        }
        items = [current, call, output]
        initial_tokens = estimate_tokens(
            {"instructions": "system", "input": items, "tools": []}
        )
        result = recover_context_request(
            instructions="system",
            input_items=items,
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=initial_tokens - 1,
        )
        self.assertEqual(FIT, result.report.verdict)
        self.assertEqual(0, result.report.compacted_tool_output_count)
        self.assertEqual(1, result.report.dropped_tool_exchange_count)
        self.assertEqual((current,), result.input_items)

    def test_cumulative_outputs_are_reprojected_to_fit_small_overage(self) -> None:
        current = {"role": "user", "content": "current-task"}
        initial_items = [current]
        for index in range(2):
            call_id = f"call-{index}"
            initial_items.extend(
                [
                    {
                        "type": "function_call",
                        "name": "list_files",
                        "arguments": "{}",
                        "call_id": call_id,
                    },
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(
                            {
                                "ok": True,
                                "evidence_id": f"ev-{index}",
                                "content": chr(97 + index) * 8_000,
                            }
                        ),
                    },
                ]
            )
        initial = recover_context_request(
            instructions="system",
            input_items=initial_items,
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=1_500,
        )
        self.assertEqual(FIT, initial.report.verdict)
        self.assertEqual(2, initial.report.compacted_tool_output_count)
        for item in initial.input_items:
            if isinstance(item, dict) and item.get("type") == "function_call_output":
                self.assertEqual("bounded", json.loads(item["output"])["projection_level"])

        items = list(initial.input_items)
        for index in range(2, 6):
            call_id = f"call-{index}"
            items.extend(
                [
                    {
                        "type": "function_call",
                        "name": "read_file",
                        "arguments": "{}",
                        "call_id": call_id,
                    },
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(
                            {
                                "ok": True,
                                "evidence_id": f"ev-{index}",
                                "content": chr(97 + index) * 800,
                            }
                        ),
                    },
                ]
            )
        initial_tokens = estimate_tokens(
            {"instructions": "system", "input": items, "tools": []}
        )
        result = recover_context_request(
            instructions="system",
            input_items=items,
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=initial_tokens - 476,
        )
        self.assertEqual(FIT, result.report.verdict)
        self.assertGreater(result.report.compacted_tool_output_count, 0)
        self.assertEqual(current, result.input_items[0])
        projections = [
            json.loads(item["output"])
            for item in result.input_items
            if isinstance(item, dict)
            and item.get("type") == "function_call_output"
            and json.loads(item["output"]).get("context_budget_compacted")
        ]
        self.assertTrue(projections)
        self.assertTrue(
            any(item["projection_level"] == "minimal" for item in projections)
        )
        self.assertTrue(all(item["original_output_sha256"] for item in projections))
        self.assertTrue(all(item["evidence_ids"] for item in projections))

    def test_oldest_evidence_exchange_is_dropped_after_projection_is_exhausted(self) -> None:
        current = {"role": "user", "content": "current-task"}
        items = [current]
        for index in range(4):
            call_id = f"call-{index}"
            items.extend(
                [
                    {
                        "type": "function_call",
                        "name": "read_file",
                        "arguments": json.dumps({"path": f"file-{index}.md"}),
                        "call_id": call_id,
                    },
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(
                            {
                                "ok": True,
                                "evidence_id": f"ev-{index}",
                                "content": chr(97 + index) * 300,
                            }
                        ),
                    },
                ]
            )
        initial_tokens = estimate_tokens(
            {"instructions": "system", "input": items, "tools": []}
        )
        result = recover_context_request(
            instructions="system",
            input_items=items,
            tools=(),
            history_item_count=0,
            configured_input_budget_tokens=initial_tokens - 123,
        )
        self.assertEqual(FIT, result.report.verdict)
        self.assertGreaterEqual(result.report.dropped_tool_exchange_count, 1)
        self.assertEqual(current, result.input_items[0])
        retained_call_ids = {
            item["call_id"]
            for item in result.input_items
            if isinstance(item, dict) and item.get("type") == "function_call"
        }
        self.assertNotIn("call-0", retained_call_ids)
        self.assertIn("call-3", retained_call_ids)
        self.assertTrue(
            any(
                step.kind == DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE
                for step in result.report.reduction_steps
            )
        )

    def test_irreducible_current_task_fails_without_truncation(self) -> None:
        current = {"role": "user", "content": "required-" + ("z" * 4_000)}
        result = recover_context_request(
            instructions="system",
            input_items=[
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "reply"},
                current,
            ],
            tools=(),
            history_item_count=2,
            configured_input_budget_tokens=50,
        )
        self.assertEqual(INSUFFICIENT_CONTEXT_BUDGET, result.report.verdict)
        self.assertEqual((current,), result.input_items)
        self.assertEqual(0, result.history_item_count)
        self.assertIn("report_signature=", format_context_budget_error(result.report))

    def test_recovery_signatures_are_deterministic(self) -> None:
        arguments = {
            "instructions": "system",
            "input_items": [
                {"role": "user", "content": "old-" + ("x" * 400)},
                {"role": "assistant", "content": "reply-" + ("y" * 400)},
                {"role": "user", "content": "current"},
            ],
            "tools": (),
            "history_item_count": 2,
            "configured_input_budget_tokens": 100,
        }
        first = recover_context_request(**arguments)
        second = recover_context_request(**arguments)
        self.assertEqual(first.report.signature, second.report.signature)
        self.assertEqual(
            tuple(item.signature for item in first.report.reduction_steps),
            tuple(item.signature for item in second.report.reduction_steps),
        )

    def test_agent_recovers_before_provider_transport(self) -> None:
        fixture = RepoFixture()
        try:
            retained = [
                {"role": "user", "content": "new-user"},
                {"role": "assistant", "content": "new-assistant"},
                {"role": "user", "content": "current-task"},
            ]
            budget = estimate_tokens(
                {
                    "instructions": "minimal-system",
                    "input": retained,
                    "tools": [],
                }
            )
            provider = RecordingProvider(
                ProviderConfig(
                    model="recording",
                    context_budget_tokens=budget,
                    max_output_tokens=1,
                )
            )
            history = [
                {"role": "user", "content": "old-user-" + ("x" * 600)},
                {"role": "assistant", "content": "old-assistant-" + ("y" * 600)},
                *retained[:2],
            ]
            with MinimalAgent(fixture.root, provider=provider) as agent:
                self.assertEqual(
                    "done",
                    agent.run_task("current-task", conversation_history=history),
                )
                assert agent.last_context_budget_report is not None
                self.assertEqual(2, agent.last_context_budget_report.removed_history_item_count)
            self.assertEqual(1, provider.calls)
            self.assertEqual(retained, provider.requests[0]["input_items"])
        finally:
            fixture.close()

    def test_agent_blocks_irreducible_request_before_transport(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RecordingProvider(
                ProviderConfig(
                    model="recording",
                    context_budget_tokens=1,
                    max_output_tokens=1,
                )
            )
            with MinimalAgent(fixture.root, provider=provider) as agent:
                with self.assertRaises(ContextBudgetError) as context:
                    agent.run_task("required-" + ("z" * 2_000))
            self.assertEqual(0, provider.calls)
            self.assertEqual(
                INSUFFICIENT_CONTEXT_BUDGET,
                context.exception.report["verdict"],
            )
            self.assertTrue(context.exception.report["signature"])
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
