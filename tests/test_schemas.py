import json
from pathlib import Path
import unittest

from ourd.egcf.catalog import command_catalog
from ourd.egcf.models import RECORD_TYPES


def assert_strict_object(test_case: unittest.TestCase, schema: dict, label: str) -> None:
    if schema.get("type") == "object" and "properties" in schema:
        test_case.assertIs(
            False,
            schema.get("additionalProperties"),
            f"{label} must refuse unknown fields",
        )
    for key, value in schema.items():
        if isinstance(value, dict):
            assert_strict_object(test_case, value, f"{label}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    assert_strict_object(test_case, item, f"{label}.{key}[{index}]")


class SchemaTests(unittest.TestCase):
    def test_versioned_schemas_are_present_and_strict(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for name in ("authority-v1.schema.json", "state-v1.schema.json", "event-v1.schema.json"):
            with self.subTest(name=name):
                payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual("object", payload["type"])
                self.assertFalse(payload["additionalProperties"])
                self.assertTrue(payload["required"])

    def test_egcf_schemas_are_strict_and_cover_runtime_records(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema_root = root / "schemas" / "egcf-v1"
        objects = json.loads((schema_root / "objects.schema.json").read_text(encoding="utf-8"))
        catalog = json.loads(
            (schema_root / "command-catalog.schema.json").read_text(encoding="utf-8")
        )
        workflow = json.loads((schema_root / "workflow.schema.json").read_text(encoding="utf-8"))
        for name, payload in (("objects", objects), ("catalog", catalog), ("workflow", workflow)):
            with self.subTest(name=name):
                self.assertEqual("object", payload["type"])
                self.assertTrue(payload["required"])
                assert_strict_object(self, payload, name)
        self.assertEqual(set(RECORD_TYPES), set(objects["$defs"]))

    def test_checked_in_catalog_is_versioned_and_matches_runtime(self) -> None:
        root = Path(__file__).resolve().parents[1]
        checked_in = json.loads(
            (root / "commands" / "v1" / "catalog.json").read_text(encoding="utf-8")
        )
        algorithms = json.loads(
            (root / "algorithms" / "v1" / "catalog.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, checked_in["schema_version"])
        self.assertEqual(command_catalog()["namespaces"], checked_in["namespaces"])
        self.assertEqual(1, algorithms["schema_version"])
        self.assertIn("reference", algorithms["implementation_kinds"])
        self.assertFalse(algorithms["floating_versions_allowed"])
        self.assertFalse(algorithms["direct_command_callbacks_allowed"])

    def test_governed_formal_writing_schema_is_strict_and_complete(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "schemas" / "formal_writing" / "governed-pipeline.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("object", payload["type"])
        self.assertFalse(payload["additionalProperties"])
        self.assertTrue(
            {
                "WritingTask",
                "ConceptDefinition",
                "Claim",
                "EvidenceLink",
                "ReasoningEdge",
                "CounterClaim",
                "Qualification",
                "ParagraphPlan",
                "ArgumentGraph",
                "DocumentPlan",
                "DraftSection",
                "WritingAudit",
            }
            <= set(payload["$defs"])
        )
        assert_strict_object(self, payload, "governed-formal-writing")


if __name__ == "__main__":
    unittest.main()
