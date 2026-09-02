from types import SimpleNamespace
from contextlib import contextmanager
import hashlib
import json
import unittest
from unittest import mock

from ourd import AgentCancelledError, OURDAgent
from ourd.context_budget import estimate_tokens
from ourd.providers.base import ProviderConfig
from tests.helpers import RepoFixture


class FakeProvider:
    def __init__(self):
        self.config = ProviderConfig(model="fake")
        self.calls = 0

    def preflight(self):
        return {"status": "ready", "model": "fake"}

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="list_files",
                        arguments='{"path":".","max_depth":2}',
                        call_id="call-1",
                    )
                ],
                output_text="",
            )
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="Read-only inspection complete.")],
                )
            ],
            output_text="",
        )


class MalformedArgumentsProvider:
    def __init__(self):
        self.config = ProviderConfig(model="malformed")
        self.calls = 0

    def preflight(self):
        return {"status": "ready", "model": "malformed"}

    def create_response(self, *, instructions, input_items, tools):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="read_file",
                        arguments="{",
                        call_id="malformed-1",
                    )
                ],
                output_text="",
            )
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="Stopped safely.")],
                )
            ],
            output_text="",
        )


class RecordingChatProvider:
    def __init__(self, responses=None, config=None):
        self.config = config or ProviderConfig(model="chat-recording")
        self.responses = list(responses or ["ok"])
        self.requests = []
        self.preflight_calls = 0

    def preflight(self):
        self.preflight_calls += 1
        return {"status": "ready", "model": self.config.model}

    def create_response(self, *, instructions, input_items, tools):
        self.requests.append(list(input_items))
        text = self.responses.pop(0)
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text=text)],
                )
            ],
            output_text="",
        )


class RecoveryReportingProvider:
    def __init__(self):
        self.config = ProviderConfig(model="recovery-reporting")
        self.report = {
            "schema_version": 1,
            "kind": "OLLAMA_TRUNCATED_TOOL_JSON_OUTPUT_EXPANSION",
            "tool_name": "run_super_reasoning",
            "signature": "recovery-signature",
        }

    def preflight(self):
        return {"status": "ready", "model": self.config.model}

    def create_response(self, *, instructions, input_items, tools):
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="Recovered response.")],
                )
            ],
            output_text="Recovered response.",
        )

    def consume_last_recovery_report(self):
        report = dict(self.report)
        self.report = {}
        return report


class ProviderTests(unittest.TestCase):
    def test_token_estimate_is_bounded_and_nonzero(self) -> None:
        self.assertGreater(estimate_tokens({"text": "hello"}), 0)

    def test_agent_context_closes_owned_provider(self) -> None:
        class ClosableProvider(RecordingChatProvider):
            def __init__(self) -> None:
                super().__init__(["ok"], ProviderConfig(model="closable"))
                self.closed = False

            def close(self) -> None:
                self.closed = True

        fixture = RepoFixture()
        try:
            provider = ClosableProvider()
            with mock.patch("ourd.agent.create_provider", return_value=provider):
                with OURDAgent(fixture.root, provider_config=provider.config) as agent:
                    agent.provider_preflight()
            self.assertTrue(provider.closed)
        finally:
            fixture.close()

    def test_fake_provider_completes_non_stateful_tool_loop(self) -> None:
        fixture = RepoFixture()
        try:
            provider = FakeProvider()
            with OURDAgent(fixture.root, provider=provider) as agent:
                result = agent.run_task("Inspect only")
            self.assertEqual("Read-only inspection complete.", result)
            self.assertEqual(2, provider.calls)
        finally:
            fixture.close()

    def test_chat_turn_reuses_bounded_conversation_history(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RecordingChatProvider(["first answer", "second answer"])
            with OURDAgent(fixture.root, provider=provider) as agent:
                self.assertEqual("first answer", agent.run_chat_turn("first question"))
                self.assertEqual("second answer", agent.run_chat_turn("follow up"))
                self.assertEqual(
                    (
                        {"role": "user", "content": "first question"},
                        {"role": "assistant", "content": "first answer"},
                    ),
                    tuple(provider.requests[1][:-1]),
                )
                self.assertEqual(
                    {"role": "user", "content": "follow up"},
                    provider.requests[1][-1],
                )
        finally:
            fixture.close()

    def test_chat_history_keeps_newest_whole_messages_within_budget(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RecordingChatProvider(
                config=ProviderConfig(
                    model="chat-recording",
                    context_budget_tokens=1000,
                )
            )
            with OURDAgent(fixture.root, provider=provider) as agent:
                history = agent._bounded_conversation_history(
                    [
                        {"role": "user", "content": "a" * 1200},
                        {"role": "assistant", "content": "b" * 1200},
                        {"role": "system", "content": "ignored"},
                    ]
                )
            self.assertEqual(1, len(history))
            self.assertEqual("assistant", history[0]["role"])
            self.assertEqual("b" * 1200, history[0]["content"])
        finally:
            fixture.close()

    def test_cancelled_turn_stops_before_provider_preflight(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RecordingChatProvider()
            with OURDAgent(fixture.root, provider=provider) as agent:
                with self.assertRaises(AgentCancelledError):
                    agent.run_task("stop", cancel_check=lambda: True)
            self.assertEqual(0, provider.preflight_calls)
            self.assertEqual([], provider.requests)
        finally:
            fixture.close()

    def test_trace_callback_receives_redacted_hash_chained_events(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RecordingChatProvider(["done"])
            events = []
            with OURDAgent(
                fixture.root,
                provider=provider,
                event_callback=events.append,
            ) as agent:
                self.assertEqual("done", agent.run_task("inspect"))
            self.assertEqual(
                ["provider_preflight", "run_started", "model_request", "final"],
                [event["event_type"] for event in events],
            )
            self.assertTrue(all(event["event_hash"] for event in events))
            self.assertEqual(events[0]["event_hash"], events[1]["previous_hash"])
        finally:
            fixture.close()

    def test_run_started_trace_binds_task_without_persisting_task_body(self) -> None:
        fixture = RepoFixture()
        try:
            provider = RecordingChatProvider(["done"])
            events = []
            task = "SENSITIVE-CONTEXT-PREVIEW\nsecond line"
            with OURDAgent(
                fixture.root,
                provider=provider,
                event_callback=events.append,
            ) as agent:
                self.assertEqual("done", agent.run_task(task))
            run_started = next(
                event for event in events if event["event_type"] == "run_started"
            )
            serialized = json.dumps(run_started, sort_keys=True)
            self.assertNotIn("SENSITIVE-CONTEXT-PREVIEW", serialized)
            persisted_events = (fixture.root / ".ourd-agent" / "events.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("SENSITIVE-CONTEXT-PREVIEW", persisted_events)
            self.assertEqual(
                hashlib.sha256(task.encode("utf-8")).hexdigest(),
                run_started["payload"]["task_sha256"],
            )
            self.assertFalse(run_started["payload"]["task_body_persisted"])
        finally:
            fixture.close()

    def test_agent_traces_successful_provider_response_recovery(self) -> None:
        fixture = RepoFixture()
        try:
            events = []
            with OURDAgent(
                fixture.root,
                provider=RecoveryReportingProvider(),
                event_callback=events.append,
            ) as agent:
                result = agent.run_task("Inspect")
            self.assertEqual("Recovered response.", result)
            recovery = next(
                event
                for event in events
                if event["event_type"] == "provider_response_recovery"
            )
            self.assertEqual(
                "run_super_reasoning",
                recovery["payload"]["tool_name"],
            )
            self.assertEqual(
                "recovery-signature",
                recovery["payload"]["signature"],
            )
        finally:
            fixture.close()

    def test_invalid_tool_arguments_return_structured_error(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root) as agent:
                result = agent.dispatch("read_file", {})
            self.assertFalse(result["ok"])
            self.assertIn("TypeError", result["error"])
        finally:
            fixture.close()

    def test_model_request_metadata_is_traced(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, provider=FakeProvider()) as agent:
                run_id = agent.run_id
                agent.run_task("Inspect only")
            events = [
                json.loads(line)
                for line in (fixture.root / ".ourd-agent" / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            requests = [event for event in events if event["event_type"] == "model_request"]
            self.assertEqual(2, len(requests))
            self.assertTrue(all(event["run_id"] == run_id for event in requests))
            self.assertEqual("fake", requests[0]["payload"]["model"])
            self.assertIn("context_budget_tokens", requests[0]["payload"])
        finally:
            fixture.close()

    def test_malformed_tool_json_becomes_collision_evidence(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, provider=MalformedArgumentsProvider()) as agent:
                result = agent.run_task("Inspect")
                collisions = list(agent.state.collisions)
            self.assertEqual("Stopped safely.", result)
            self.assertTrue(any(item.boundary == "tool protocol" for item in collisions))
        finally:
            fixture.close()

    def test_unchanged_failed_tool_call_is_blocked(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root) as agent:
                from tests.helpers import governance_args

                agent.establish_governance(**governance_args())
                first = agent.dispatch(
                    "prepare_write_file", {"path": "README.md", "content": "changed"}
                )
                second = agent.dispatch(
                    "prepare_write_file", {"path": "README.md", "content": "changed"}
                )
                self.assertFalse(first["ok"])
                self.assertIn("unchanged failed action", second["error"])
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
