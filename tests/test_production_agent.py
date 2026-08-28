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
                    content=[
                        SimpleNamespace(type="output_text", text="A model conclusion.")
                    ],
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
                        {
                            "path": "README.md",
                            "start_line": 1,
                            "end_line": 20,
                        }
                    ),
                    call_id=f"call-{self.calls}",
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
            self.assertEqual(
                "MODEL_OUTPUT_UNVERIFIED",
                final["payload"]["epistemic_status"],
            )
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
                    any(
                        collision.disposition == "CYCLE_STOP"
                        for collision in agent.state.collisions
                    )
                )
        finally:
            fixture.close()

    def test_production_instructions_separate_belief_from_verification(self) -> None:
        fixture = RepoFixture()
        try:
            with ProductionOURDAgent(fixture.root, provider=FinalOnlyProvider()) as agent:
                instructions = agent.instructions()
            self.assertIn("MODEL BELIEF/PROPOSAL", instructions)
            self.assertIn("cannot self-certify progress", instructions)
            self.assertIn("ProgressCertificate", instructions)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
