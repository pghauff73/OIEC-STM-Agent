from __future__ import annotations

import unittest

from ourd_gui.events import AgentEvent, AgentEventBus, AgentEventType


class AgentEventBusTests(unittest.TestCase):
    def test_delivery_is_ordered_and_unsubscribe_stops_delivery(self) -> None:
        bus = AgentEventBus()
        observed: list[int] = []
        token = bus.subscribe(lambda event: observed.append(event.sequence))
        first = bus.emit(AgentEventType.AGENT_STEP)
        second = bus.emit(AgentEventType.TASK_FINISHED)
        delivered, failures = bus.drain()
        self.assertEqual([first.sequence, second.sequence], observed)
        self.assertEqual([first, second], delivered)
        self.assertEqual([], failures)
        bus.unsubscribe(token)
        bus.emit(AgentEventType.AGENT_STEP)
        bus.drain()
        self.assertEqual([first.sequence, second.sequence], observed)

    def test_subscriber_failure_is_isolated(self) -> None:
        bus = AgentEventBus()
        observed: list[str] = []
        bus.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe(lambda event: observed.append(event.event_type.value))
        bus.emit(AgentEventType.AGENT_STEP)
        delivered, failures = bus.drain()
        self.assertEqual(1, len(delivered))
        self.assertEqual(["AGENT_STEP"], observed)
        self.assertEqual(1, len(failures))

    def test_event_round_trip(self) -> None:
        bus = AgentEventBus()
        event = bus.make_event(
            AgentEventType.SELECTION_UPDATED,
            session_id="session",
            task_id="task",
            authoritative=True,
            core_event_hash="abc",
            object_ids=["selection:sha256:1"],
            payload={"answer": 42},
        )
        self.assertEqual(event, AgentEvent.from_dict(event.to_dict()))

    def test_unknown_event_type_is_preserved_as_agent_step(self) -> None:
        bus = AgentEventBus()
        payload = bus.make_event(AgentEventType.AGENT_STEP).to_dict()
        payload["event_type"] = "FUTURE_EVENT"
        event = AgentEvent.from_dict(payload)
        self.assertEqual(AgentEventType.AGENT_STEP, event.event_type)
        self.assertEqual("FUTURE_EVENT", event.payload["unknown_gui_event_type"])

    def test_unsupported_schema_version_fails_closed(self) -> None:
        bus = AgentEventBus()
        payload = bus.make_event(AgentEventType.AGENT_STEP).to_dict()
        payload["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported GUI event schema"):
            AgentEvent.from_dict(payload)

    def test_authoritative_event_requires_core_provenance(self) -> None:
        bus = AgentEventBus()
        with self.assertRaisesRegex(ValueError, "require a core event hash"):
            bus.make_event(AgentEventType.AGENT_STEP, authoritative=True)


if __name__ == "__main__":
    unittest.main()
