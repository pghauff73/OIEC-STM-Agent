from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from ourd.errors import ContextBudgetError, StateError
from ourd.production_agent import ProductionOURDAgent
from ourd.providers.base import ProviderConfig
from ourd.providers.openai_responses import estimate_tokens
from tests.helpers import RepoFixture


class FinalOnlyProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(model="final-only")

    def preflight(self):
        return {"status": "ready", "model": "final-only"}

    def create_response(self, *, instructions, input_items, tools):
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="A model conclusion.")],
                )
            ],
            output_text="A model conclusion.",
        )


class RepeatReadProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(model="repeat-read")
        self.calls = 0

    def preflight(self):
        return {"status": "ready", "model": "repeat-read"}

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="read_file",
                    arguments=json.dumps(
                        {"path": "README.md", "start_line": 1, "end_line": 20}
                    ),
                    call_id=f"call-{self.calls}",
                )
            ],
            output_text="",
        )


class HypothesisChurnProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(model="hypothesis-churn")
        self.calls = 0

    def preflight(self):
        return {"status": "ready", "model": "hypothesis-churn"}

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        proposition = f"Control-only hypothesis {self.calls}"
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="propose_hypotheses",
                    arguments=json.dumps(
                        {
                            "hypotheses": [
                                {
                                    "proposition": proposition,
                                    "model_prior_bp": 5000,
                                    "assumptions": [],
                                    "predictions": [],
                                    "falsifiers": [],
                                }
                            ]
                        }
                    ),
                    call_id=f"hypothesis-{self.calls}",
                )
            ],
            output_text="",
        )


class PaginatedListProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(model="paginated-list")
        self.calls = 0

    def preflight(self):
        return {"status": "ready", "model": "paginated-list"}

    @staticmethod
    def latest_result(input_items):
        for item in reversed(input_items):
            if isinstance(item, dict) and item.get("type") == "function_call_output":
                return json.loads(item["output"])
        return None

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        previous = self.latest_result(input_items)
        if previous is not None and not previous["has_more"]:
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", text="Inventory complete.")],
                    )
                ],
                output_text="Inventory complete.",
            )
        offset = 0 if previous is None else previous["next_offset"]
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="list_files",
                    arguments=json.dumps(
                        {
                            "path": ".",
                            "max_depth": 2,
                            "offset": offset,
                            "max_results": 2,
                        }
                    ),
                    call_id=f"page-{self.calls}",
                )
            ],
            output_text="",
        )


class NamedFileDiscussionProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(
            model="named-file-discussion",
            context_budget_tokens=6000,
        )
        self.calls = 0
        self.first_tool_names: set[str] = set()
        self.second_tool_names: set[str] = set()
        self.second_request_tokens = 0
        self.recovered_content = ""

    def preflight(self):
        return {"status": "ready", "model": "named-file-discussion"}

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        tool_names = {tool["name"] for tool in tools}
        if self.calls == 1:
            self.first_tool_names = tool_names
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="read_file",
                        arguments=json.dumps(
                            {
                                "path": "ourd/formal_writing.py",
                                "start_line": 1,
                                "end_line": 2000,
                            }
                        ),
                        call_id="named-file-read",
                    )
                ],
                output_text="",
            )

        self.second_tool_names = tool_names
        self.second_request_tokens = estimate_tokens(
            {"instructions": instructions, "input": input_items, "tools": tools}
        )
        if self.second_request_tokens > self.config.context_budget_tokens:
            raise ContextBudgetError("named-file source was not retained within budget")
        latest_output = next(
            item
            for item in reversed(input_items)
            if isinstance(item, dict) and item.get("type") == "function_call_output"
        )
        self.recovered_content = json.loads(latest_output["output"])["content"]
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(
                            type="output_text",
                            text="Formal-writing discussion complete.",
                        )
                    ],
                )
            ],
            output_text="Formal-writing discussion complete.",
        )


class ProductionAgentTests(unittest.TestCase):
    def test_named_file_discussion_retains_complete_source_within_context_budget(self) -> None:
        fixture = RepoFixture()
        fixture.write(
            "ourd/formal_writing.py",
            (Path(__file__).parents[1] / "ourd" / "formal_writing.py").read_text(
                encoding="utf-8"
            ),
        )
        try:
            provider = NamedFileDiscussionProvider()
            with ProductionOURDAgent(fixture.root, provider=provider) as agent:
                result = agent.run_task("Discuss ourd/formal_writing.py")
            events = [
                json.loads(line)
                for line in (fixture.root / ".ourd-agent" / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            context_modes = [
                event["payload"]["tool_context_mode"]
                for event in events
                if event["event_type"] == "model_request"
            ]
            self.assertEqual("Formal-writing discussion complete.", result)
            self.assertEqual(2, provider.calls)
            self.assertEqual(["full", "named_file_read"], context_modes)
            self.assertIn("prepare_write_file", provider.first_tool_names)
            self.assertEqual(
                {"list_files", "read_file", "search_text"},
                provider.second_tool_names,
            )
            self.assertLessEqual(
                provider.second_request_tokens,
                provider.config.context_budget_tokens,
            )
            self.assertIn("class ArgumentTopology", provider.recovered_content)
            self.assertIn("def profile_dimensions", provider.recovered_content)
        finally:
            fixture.close()

    def test_terminal_model_output_is_labelled_unverified_and_certified_transition(self) -> None:
        fixture = RepoFixture()
        try:
            events = []
            with ProductionOURDAgent(
                fixture.root,
                provider=FinalOnlyProvider(),
                event_callback=events.append,
            ) as agent:
                result = agent.run_task("Answer from the model")
                progress = agent.state.last_progress
            self.assertEqual("A model conclusion.", result)
            self.assertIsNotNone(progress)
            self.assertTrue(progress.terminal)
            event_types = [event["event_type"] for event in events]
            self.assertIn("model_belief", event_types)
            self.assertIn("progress_certificate", event_types)
            final = next(event for event in events if event["event_type"] == "final")
            self.assertEqual("MODEL_OUTPUT_UNVERIFIED", final["payload"]["epistemic_status"])
        finally:
            fixture.close()

    def test_identical_second_read_is_stopped_for_no_verified_progress(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RepeatReadProvider()
            with ProductionOURDAgent(fixture.root, provider=provider, max_steps=5) as agent:
                with self.assertRaises(StateError) as context:
                    agent.run_task("Read the same thing forever")
                self.assertIn("CYCLE_STOP", str(context.exception))
                self.assertEqual(2, provider.calls)
                self.assertIsNotNone(agent.state.last_progress)
                self.assertFalse(agent.state.last_progress.accepted)
                self.assertTrue(
                    any(collision.disposition == "CYCLE_STOP" for collision in agent.state.collisions)
                )
        finally:
            fixture.close()

    def test_paginated_file_loop_advances_until_terminal_response(self) -> None:
        fixture = RepoFixture()
        fixture.write("alpha.txt", "alpha\n")
        fixture.write("beta.txt", "beta\n")
        fixture.write("gamma.txt", "gamma\n")
        try:
            provider = PaginatedListProvider()
            with ProductionOURDAgent(
                fixture.root,
                provider=provider,
                max_steps=6,
            ) as agent:
                result = agent.run_task("Inventory every file with a bounded loop")
            self.assertEqual("Inventory complete.", result)
            self.assertEqual(3, provider.calls)
        finally:
            fixture.close()

    def test_hypothesis_tools_preserve_unverified_proposition_boundary(self) -> None:
        fixture = RepoFixture()
        try:
            with ProductionOURDAgent(fixture.root, provider=FinalOnlyProvider()) as agent:
                proposed = agent.propose_hypotheses(
                    [
                        {
                            "proposition": "README contains a title",
                            "model_prior_bp": 5000,
                            "assumptions": [],
                            "predictions": ["a heading is observable"],
                            "falsifiers": ["no heading exists"],
                        }
                    ]
                )
                hypothesis_id = proposed["added_hypothesis_ids"][0]
                evidence_id = agent.read_file("README.md")["evidence_id"]
                linked = agent.link_hypothesis_evidence(
                    hypothesis_id=hypothesis_id,
                    evidence_id=evidence_id,
                    relation="supports",
                )
                projection = linked["hypothesis_state"]["hypotheses"][0]
            self.assertEqual("UNVERIFIED_PROPOSITION", projection["verification_status"])
            self.assertEqual("SUPPORTED_BY_LINKED_EVIDENCE", projection["status"])
            self.assertEqual(
                "MODEL_PROPOSED_RELATION_TO_VERIFIED_EVIDENCE",
                projection["evidence_links"][0]["relation_epistemic_status"],
            )
        finally:
            fixture.close()

    def test_third_control_only_hypothesis_step_is_stopped_and_streak_persists(self) -> None:
        fixture = RepoFixture()
        try:
            provider = HypothesisChurnProvider()
            with ProductionOURDAgent(
                fixture.root,
                provider=provider,
                max_steps=6,
                max_control_only_progress=2,
            ) as agent:
                with self.assertRaises(StateError) as context:
                    agent.run_task("Keep inventing hypotheses without evidence")
                self.assertIn("CONTROL_ONLY_BUDGET_EXHAUSTED", str(context.exception))
                self.assertEqual(3, provider.calls)
                self.assertEqual(3, agent.state.control_only_progress_streak)
                self.assertIsNotNone(agent.state.hypothesis_state)
                self.assertEqual(3, len(agent.state.hypothesis_state.hypotheses))

            with ProductionOURDAgent(fixture.root, provider=FinalOnlyProvider()) as reopened:
                self.assertEqual(3, reopened.state.control_only_progress_streak)
                self.assertEqual(3, len(reopened.state.hypothesis_state.hypotheses))
        finally:
            fixture.close()

    def test_production_instructions_and_tools_expose_epistemic_boundary(self) -> None:
        fixture = RepoFixture()
        try:
            with ProductionOURDAgent(fixture.root, provider=FinalOnlyProvider()) as agent:
                instructions = agent.instructions()
                tool_names = {tool["name"] for tool in agent.tool_specs()}
            self.assertIn("MODEL BELIEF/PROPOSAL", instructions)
            self.assertIn("UNVERIFIED_PROPOSITION", instructions)
            self.assertIn("cannot self-certify progress", instructions)
            self.assertIn("Bounded for-style iteration", instructions)
            self.assertIn("names an exact repository-relative file path", instructions)
            self.assertIn("cannot prove that a named file is absent", instructions)
            self.assertIn("start_line=1 and end_line=2000", instructions)
            self.assertIn("narrows the next model request", instructions)
            self.assertIn("propose_hypotheses", tool_names)
            self.assertIn("link_hypothesis_evidence", tool_names)
            self.assertIn("list_hypotheses", tool_names)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
