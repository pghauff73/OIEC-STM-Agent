from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from tools.icpi_chat_scenario_generator import (
    CORPUS_ID,
    DEFAULT_CAMPAIGN_SEED,
    EXPECTED_SCENARIO_COUNT,
    FAULT_INJECTIONS,
    PASS_FAIL_GATES,
    build_scenarios,
    corpus_manifest,
    corpus_signature,
    render_jsonl,
    render_markdown,
    scenario_seed,
    select_scenarios,
)


ROOT = Path(__file__).resolve().parents[2]


EXPECTED_SIGNATURE = "2f34e90363afc81b6572c670d22c4e2c7a0366540f11f2363cfdaf306744542e"
EXPECTED_CATEGORY_COUNTS = {
    "chat_lifecycle": 10,
    "context_stress": 12,
    "corpus_summarization": 12,
    "fault_injection": 16,
    "formal_writing": 12,
    "governance_scope": 12,
    "page_reference": 8,
    "routing_icpi": 10,
    "security_untrusted_text": 5,
    "startup_control": 8,
    "visual_formatting": 15,
}


class ChatScenarioGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenarios = build_scenarios()

    def test_canonical_corpus_count_categories_and_signature(self) -> None:
        self.assertEqual(EXPECTED_SCENARIO_COUNT, len(self.scenarios))
        self.assertEqual(
            EXPECTED_CATEGORY_COUNTS,
            dict(sorted(Counter(item.category for item in self.scenarios).items())),
        )
        self.assertEqual(EXPECTED_SIGNATURE, corpus_signature(self.scenarios))
        self.assertEqual(len(self.scenarios), len({item.scenario_id for item in self.scenarios}))

    def test_exact_seed_examples_are_stable(self) -> None:
        expected = {
            "CTL-001": 1357045309,
            "SUM-001": 540364181,
            "FLT-016": 703283804,
            "VIS-015": 76035231,
        }
        observed = {item.scenario_id: item.seed for item in self.scenarios}
        for scenario_id, seed in expected.items():
            self.assertEqual(seed, observed[scenario_id])
            self.assertEqual(seed, scenario_seed(DEFAULT_CAMPAIGN_SEED, scenario_id))

    def test_faults_themes_and_gates_have_exact_coverage(self) -> None:
        fault_ids = [item.fault_id for item in self.scenarios if item.fault_id]
        self.assertEqual(list(FAULT_INJECTIONS), fault_ids)
        theme_tags = [
            tag
            for item in self.scenarios
            for tag in item.tags
            if tag.startswith("theme:")
        ]
        self.assertEqual(15, len(theme_tags))
        self.assertEqual(15, len(set(theme_tags)))
        self.assertEqual([f"G{index:02d}" for index in range(1, 10)], [
            gate["gate_id"] for gate in PASS_FAIL_GATES
        ])

    def test_lane_and_category_filters_preserve_original_seeds(self) -> None:
        live = select_scenarios(self.scenarios, lane="live", categories=())
        visual = select_scenarios(
            self.scenarios,
            lane="deterministic",
            categories=("visual_formatting",),
        )
        self.assertEqual(67, len(live))
        self.assertEqual(15, len(visual))
        original = {item.scenario_id: item.seed for item in self.scenarios}
        self.assertTrue(all(original[item.scenario_id] == item.seed for item in live))
        self.assertTrue(all(original[item.scenario_id] == item.seed for item in visual))

    def test_jsonl_and_manifest_are_machine_readable(self) -> None:
        rows = [json.loads(line) for line in render_jsonl(self.scenarios).splitlines()]
        self.assertEqual(EXPECTED_SCENARIO_COUNT, len(rows))
        self.assertTrue(all(row["corpus_id"] == CORPUS_ID for row in rows))
        manifest = corpus_manifest(self.scenarios, DEFAULT_CAMPAIGN_SEED)
        self.assertEqual(EXPECTED_SIGNATURE, manifest["scenario_signature"])
        self.assertEqual(EXPECTED_CATEGORY_COUNTS, manifest["category_counts"])
        self.assertEqual(16, len(manifest["fault_injections"]))
        self.assertEqual(9, len(manifest["pass_fail_gates"]))

    def test_plan_appendix_matches_generated_inventory_exactly(self) -> None:
        plan = (ROOT / "ICPI_SUPERVISOR_HEAVY_TEST_PLAN.md").read_text(encoding="utf-8")
        appendix = plan.split("## Appendix A: Exact Scenario Inventory\n", 1)[1].split(
            "\n## Appendix B:", 1
        )[0]
        observed = "\n".join(
            line
            for line in appendix.splitlines()
            if line.startswith("|")
        ) + "\n"
        self.assertEqual(render_markdown(self.scenarios), observed)


if __name__ == "__main__":
    unittest.main()
