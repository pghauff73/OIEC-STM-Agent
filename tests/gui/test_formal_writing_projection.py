from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from ourd.formal_writing import FormalWritingService, compile_formal_writing_request
from ourd.writing_engine.pipeline_models import WritingAudit
from ourd_gui.formal_writing_projection import (
    FormalWritingProjectionStore,
    WritingAuditProjection,
    argument_graph_projection,
)


class FormalWritingProjectionTests(unittest.TestCase):
    def test_projection_reads_persisted_draft_audit_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text("# Source\n\nA grounded claim with evidence.\n", encoding="utf-8")
            request = compile_formal_writing_request(
                operation="draft",
                objective="grounded claim evidence",
                source_paths=("source.md",),
            )
            result = FormalWritingService(root).execute(request)
            store = FormalWritingProjectionStore(root)
            results = store.results()
            pages = store.source_pages()
            self.assertEqual(1, len(results))
            self.assertTrue(results[0].draft_text)
            self.assertTrue(results[0].integrity_report)
            self.assertTrue(results[0].graph_nodes)
            self.assertTrue(results[0].graph_edges)
            self.assertTrue(results[0].audit.audit_id)
            self.assertEqual("reflowable", pages[0].display_page_label)
            graph = results[0].argument_graph
            expected_node_ids = {
                *(str(item["claim_id"]) for item in graph.get("claims", ())),
                *(str(item["evidence_link_id"]) for item in graph.get("evidence_links", ())),
                *(str(item["qualification_id"]) for item in graph.get("qualifications", ())),
            }
            expected_node_ids.update(
                str(item.get("claim", {}).get("claim_id", ""))
                for item in graph.get("counterclaims", ())
                if item.get("claim", {}).get("claim_id")
            )
            self.assertEqual(expected_node_ids, {node.node_id for node in results[0].graph_nodes})
            self.assertEqual(
                len(results[0].graph_edges),
                len({(edge.source, edge.target, edge.label) for edge in results[0].graph_edges}),
            )
            expected_trace_count = sum(
                len(section.sentence_claim_map)
                for section in result.qualified_document.draft_sections
            )
            self.assertEqual(expected_trace_count, len(results[0].sentence_traces))
            self.assertEqual(
                tuple(item.status for item in result.qualified_document.novelty_assessments),
                tuple(str(item["status"]) for item in results[0].novelty_assessments),
            )
            self.assertEqual(
                result.qualified_document.reasoning_algorithm_proposal.status,
                results[0].reasoning_algorithm_proposal["status"],
            )
            self.assertEqual(
                result.qualified_document.plan.selected_path_id,
                results[0].selected_reasoning_path["path_id"],
            )

            (root / "source.md").write_text("changed", encoding="utf-8")
            drifted = store.source_pages()
            self.assertEqual("DRIFTED", drifted[0].freshness)

    def test_projection_rejects_malformed_and_signature_invalid_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_dir = root / ".ourd-agent" / "writing" / "results"
            result_dir.mkdir(parents=True)
            (result_dir / "broken.json").write_text("{", encoding="utf-8")
            (root / "source.md").write_text("# Source\n\nGrounded evidence.\n", encoding="utf-8")
            result = FormalWritingService(root).execute(
                compile_formal_writing_request(
                    operation="draft",
                    objective="Grounded evidence",
                    source_paths=("source.md",),
                )
            )
            path = result_dir / f"{result.request.request_id.replace(':', '-')}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["request"]["objective"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = FormalWritingProjectionStore(root).snapshot()
            self.assertEqual((), snapshot.results)
            categories = {item.category for item in snapshot.diagnostics}
            self.assertEqual({"INVALID_RESULT_ARTIFACT"}, categories)
            self.assertTrue(all(item.observed_at.endswith("Z") for item in snapshot.diagnostics))

    def test_projection_accepts_unknown_fields_and_rejects_new_schema_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text("# Source\n\nGrounded evidence.\n", encoding="utf-8")
            result = FormalWritingService(root).execute(
                compile_formal_writing_request(
                    operation="draft",
                    objective="Grounded evidence",
                    source_paths=("source.md",),
                )
            )
            result_path = next((root / ".ourd-agent" / "writing" / "results").glob("*.json"))
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["future_additive_field"] = {"ignored": True}
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            additive = FormalWritingProjectionStore(root).snapshot()
            self.assertEqual((result.request.request_id,), tuple(item.request_id for item in additive.results))
            self.assertEqual((), additive.diagnostics)

            payload["request"]["schema_version"] = 2
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            incompatible = FormalWritingProjectionStore(root).snapshot()
            self.assertEqual((), incompatible.results)
            self.assertEqual("INVALID_RESULT_ARTIFACT", incompatible.diagnostics[0].category)
            self.assertIn("schema_version must be 1", incompatible.diagnostics[0].message)

    def test_audit_statuses_are_projected_without_laundering(self) -> None:
        for status in (
            "QUALIFIED_FORMAL_DOCUMENT",
            "REVISION_REQUIRED",
            "EVIDENCE_INSUFFICIENT",
        ):
            with self.subTest(status=status):
                audit = WritingAudit(document_plan_id="document-plan:test", status=status)
                self.assertEqual(status, WritingAuditProjection.from_audit(audit).status)

    def test_large_graph_projection_is_complete_and_bounded(self) -> None:
        claims = tuple(
            {
                "claim_id": f"claim:{index}",
                "statement": f"Claim {index}",
                "claim_type": "FACTUAL",
                "status": "SUPPORTED",
            }
            for index in range(500)
        )
        reasoning_edges = tuple(
            {
                "edge_id": f"edge:{index}",
                "source_id": f"claim:{index % 499}",
                "target_id": f"claim:{(index % 499) + 1}",
                "relation": f"SUPPORTS_{index // 499}",
            }
            for index in range(1_000)
        )
        started = time.perf_counter()
        nodes, edges = argument_graph_projection(
            {
                "thesis_claim_id": "claim:499",
                "claims": claims,
                "reasoning_edges": reasoning_edges,
            }
        )
        elapsed = time.perf_counter() - started
        self.assertEqual(500, len(nodes))
        self.assertEqual(1_000, len(edges))
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
