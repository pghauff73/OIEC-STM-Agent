from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from ourd.errors import StateError
from ourd.production_agent import ProductionOURDAgent
from ourd.providers.base import ProviderConfig
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


class ProductionAgentTests(unittest.TestCase):
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
            self.assertIn("propose_hypotheses", tool_names)
            self.assertIn("link_hypothesis_evidence", tool_names)
            self.assertIn("list_hypotheses", tool_names)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
