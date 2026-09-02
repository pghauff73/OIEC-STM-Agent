from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ourd.agent import OURDAgent
from ourd.interaction import compile_turn_execution_policy, route_interaction
from ourd.production_agent import ProductionOURDAgent
from ourd.providers.base import ProviderConfig
from ourd.workspace import Workspace


class CorpusSummaryProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(model="corpus-summary")
        self.requests = []

    def preflight(self):
        return {"status": "ready", "model": self.config.model}

    def create_response(self, *, instructions, input_items, tools):
        self.requests.append(
            {
                "instructions": instructions,
                "input_items": list(input_items),
                "tools": list(tools),
            }
        )
        prompt = json.loads(input_items[0]["content"])
        paths = [document["path"] for document in prompt["documents"]]
        text = "\n".join(
            [f"Coverage: {len(paths)}/{len(paths)} Markdown files"]
            + [f"- `{path}`: Source-grounded summary for {path}." for path in paths]
            + ["Limitation: These are model interpretations of deterministic outlines."]
        )
        return SimpleNamespace(output=[], output_text=text)


class SummarizationRecoveryInteractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("# A\n\nAlpha.\n", encoding="utf-8")
        (self.root / "docs" / "b.md").write_text("# B\n\nBeta.\n", encoding="utf-8")
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_incident_prompt_is_read_only_summarization(self) -> None:
        route = route_interaction("Summarise each /docs/ markdown file.", self.workspace)
        self.assertEqual("SUMMARIZE", route.intent.mode)
        self.assertEqual(("docs",), route.intent.target_paths)
        self.assertEqual("agent.read_only", route.target)
        self.assertEqual(("corpus_coverage", "evidence", "summary"), route.intent.requested_outputs)
        self.assertFalse(route.requires_confirmation)

    def test_summary_policy_exposes_only_read_and_corpus_tools(self) -> None:
        route = route_interaction("Summarize @folder[docs]", self.workspace)
        policy = compile_turn_execution_policy(
            route,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        with OURDAgent(self.root, turn_execution_policy=policy) as agent:
            names = {tool["name"] for tool in agent.tool_specs()}
        self.assertIn("build_corpus_manifest", names)
        self.assertIn("read_corpus_document", names)
        self.assertNotIn("establish_governance", names)
        self.assertNotIn("run_super_reasoning", names)
        self.assertNotIn("prepare_write_file", names)

    def test_production_summary_instructions_prefer_complete_attachments(self) -> None:
        route = route_interaction("Summarize @folder[docs]", self.workspace)
        policy = compile_turn_execution_policy(
            route,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        with ProductionOURDAgent(self.root, turn_execution_policy=policy) as agent:
            instructions = agent.instructions()
        self.assertIn("SUMMARIZATION EXECUTION:", instructions)
        self.assertIn("truncated=false", instructions)
        self.assertIn("no more than 35 words per bullet", instructions)
        self.assertIn("within 1,800 output tokens", instructions)
        self.assertIn("Do not use generic read_file calls", instructions)

    def test_specialized_corpus_summary_has_exact_coverage_and_bounded_prompt(self) -> None:
        route = route_interaction("Summarize @folder[docs]", self.workspace)
        policy = compile_turn_execution_policy(
            route,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        provider = CorpusSummaryProvider()
        events = []
        task = (
            "[OIEC-STM-SR-AgentICPI STRUCTURED REQUEST]\n"
            "Objective: Summarize every Markdown document.\n"
            "Original-Request: Summarize @folder[docs]\n"
            "[BOUNDED CONTEXT ATTACHMENTS]\n"
            + ("ATTACHMENT SECRET " * 10_000)
        )
        with ProductionOURDAgent(
            self.root,
            provider=provider,
            turn_execution_policy=policy,
            event_callback=events.append,
        ) as agent:
            result = agent.run_task(task)

        self.assertEqual(1, len(provider.requests))
        request = provider.requests[0]
        self.assertEqual([], request["tools"])
        prompt = json.loads(request["input_items"][0]["content"])
        self.assertEqual("Summarize @folder[docs]", prompt["objective"])
        self.assertNotIn("ATTACHMENT SECRET", request["input_items"][0]["content"])
        self.assertEqual(["docs/a.md", "docs/b.md"], [item["path"] for item in prompt["documents"]])
        self.assertIn("Coverage: 2/2 Markdown files", result)
        self.assertIn("`docs/a.md`", result)
        self.assertIn("`docs/b.md`", result)
        completed = next(
            event
            for event in events
            if event["event_type"] == "corpus_summary_specialized_completed"
        )
        self.assertEqual(2, completed["payload"]["document_count"])
        reports = [
            event for event in events if event["event_type"] == "corpus_summary_report"
        ]
        self.assertEqual("COMPLETE", reports[-1]["payload"]["coverage_status"])
        corpus_reads = [
            event
            for event in events
            if event["event_type"] == "tool_result"
            and event["payload"]["name"] == "read_corpus_document"
        ]
        self.assertTrue(corpus_reads)
        self.assertEqual(
            "<content stored only in model response; see evidence hash>",
            corpus_reads[0]["payload"]["result"]["content"],
        )

    def test_reasoning_policy_requires_governance_before_super_reasoning(self) -> None:
        route = route_interaction("Reason about competing explanations", self.workspace)
        policy = compile_turn_execution_policy(
            route,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        args = {
            "statement": "x",
            "goal": "x",
            "hypotheses": [],
            "evidence_ids": [],
            "uncertainty_bp": 0,
            "difficulty_bp": 0,
            "mutually_exclusive_hypotheses": False,
        }
        with OURDAgent(self.root, turn_execution_policy=policy) as agent:
            names = {tool["name"] for tool in agent.tool_specs()}
            self.assertIn("establish_governance", names)
            self.assertNotIn("run_super_reasoning", names)
            first = agent.dispatch("run_super_reasoning", args)
            collision_count = len(agent.state.collisions)
            second = agent.dispatch("run_super_reasoning", args)
            self.assertEqual("GOVERNANCE_REQUIRED", first["error_code"])
            self.assertEqual("PRECONDITION", first["failure_class"])
            self.assertTrue(first["recoverable"])
            self.assertEqual(collision_count, len(agent.state.collisions))
            self.assertEqual(first["collision_id"], second["collision_id"])
            agent.establish_governance(
                goal="Bound reasoning",
                constraints=[],
                assumptions=[],
                uncertainties=[],
                objects=["workspace"],
                relations=[],
                boundaries=["read-only"],
                excluded_scope=[],
                allowed_paths=["**"],
                dimensions=["explanation"],
                invariants=["no mutation"],
            )
            self.assertIn("run_super_reasoning", {tool["name"] for tool in agent.tool_specs()})


if __name__ == "__main__":
    unittest.main()
