from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ourd.egcf.brain_feed_store import BrainFeedStore
from ourd.egcf.repository_brain_feed import RepositoryScanPolicy, chunk_repository_plan, scan_repository
from ourd.egcf.store import EGCFStore
from ourd.entrypoint import main as entrypoint_main
from ourd.repo_brain_cli import main as repo_main


class SAARepositoryBrainFeedTests(unittest.TestCase):
    def _make_repo(self, root: Path) -> Path:
        source = root / "source-repo"
        (source / "tests").mkdir(parents=True)
        (source / "calc.py").write_text(
            '"""Small arithmetic module."""\n\n'
            'def add(left: float, right: float) -> float:\n'
            '    """Return the sum of two measurable values."""\n'
            '    return left + right\n',
            encoding="utf-8",
        )
        (source / "tests" / "test_calc.py").write_text(
            'from calc import add\n\n'
            'def test_add():\n'
            '    assert add(2, 3) == 5\n',
            encoding="utf-8",
        )
        (source / "README.md").write_text(
            "# Calculator\n\nAdds two values and includes a regression test.\n",
            encoding="utf-8",
        )
        return source

    def test_repository_feed_routes_source_evidence_and_stages_code_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_repo(root)
            brain = root / "brain"
            output = io.StringIO()
            with redirect_stdout(output):
                status = repo_main([str(source), "--repo", str(brain), "--json"])
            self.assertEqual(0, status)
            payload = json.loads(output.getvalue())
            self.assertEqual(0, payload["canonical_algorithm_admissions"])
            self.assertEqual(3, payload["scan"]["file_count"])
            self.assertGreaterEqual(payload["scan"]["symbol_count"], 2)
            self.assertEqual(3, payload["admitted_count"])
            self.assertGreaterEqual(payload["staged_count"], 4)
            with EGCFStore(brain) as egcf:
                dispositions = BrainFeedStore(egcf).dispositions()
                statuses = {item["payload"]["status"] for item in dispositions}
                self.assertIn("REGISTERED_EVIDENCE", statuses)
                self.assertIn("STAGED_ALGORITHM_CANDIDATE_QUALIFICATION_REQUIRED", statuses)
                self.assertIn("STAGED_EXPERIMENT_CANDIDATE_QUALIFICATION_REQUIRED", statuses)
                self.assertIn("STAGED_INVARIANT_CANDIDATE_QUALIFICATION_REQUIRED", statuses)
                for item in dispositions:
                    self.assertFalse(item["payload"]["canonical_algorithm_admission_attempted"])

    def test_repository_scanner_never_executes_or_imports_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "dangerous-source"
            source.mkdir()
            marker = source / "EXECUTED.txt"
            (source / "danger.py").write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("executed")\n\n'
                'def harmless_candidate(value):\n'
                '    return value * 2\n',
                encoding="utf-8",
            )
            self.assertEqual(0, repo_main([str(source), "--scan-only", "--json"]))
            self.assertFalse(marker.exists())
            brain = root / "brain"
            self.assertEqual(0, repo_main([str(source), "--repo", str(brain), "--json"]))
            self.assertFalse(marker.exists())

    def test_generic_javascript_function_is_extracted_as_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "js-repo"
            source.mkdir()
            (source / "math.js").write_text(
                "export function scaleDistance(distance, factor) { return distance * factor; }\n",
                encoding="utf-8",
            )
            plan = scan_repository(source)
            names = {symbol.name for symbol in plan.symbols}
            self.assertIn("scaleDistance", names)
            self.assertIn("JavaScript", dict(plan.language_counts))
            algorithm_items = [
                item
                for group in plan.file_groups
                for item in group
                if item.kind == "ALGORITHM_CANDIDATE"
            ]
            self.assertEqual(1, len(algorithm_items))
            self.assertEqual("UNRESOLVED_FROM_SOURCE_CODE", algorithm_items[0].payload["meanings"]["status"])

    def test_small_batch_limit_preserves_file_evidence_with_dependent_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "dense-repo"
            source.mkdir()
            (source / "many.py").write_text(
                "\n".join(
                    f"def function_{index}(value):\n    return value + {index}\n"
                    for index in range(10)
                ),
                encoding="utf-8",
            )
            plan = scan_repository(
                source,
                RepositoryScanPolicy(max_items_per_batch=4),
            )
            batches = chunk_repository_plan(plan)
            self.assertGreater(len(batches), 1)
            for batch in batches:
                self.assertLessEqual(len(batch), 4)
                ids = {item.item_id for item in batch}
                for item in batch:
                    for evidence_id in item.evidence_from:
                        self.assertIn(evidence_id, ids)

    def test_self_feed_signature_is_stable_when_brain_state_is_added(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "module.py").write_text("def identity(x):\n    return x\n", encoding="utf-8")
            first = scan_repository(source)
            self.assertEqual(0, repo_main([str(source), "--repo", str(source), "--json"]))
            second = scan_repository(source)
            self.assertEqual(first.repository_signature, second.repository_signature)
            self.assertTrue((source / ".ourd-agent" / "egcf").exists())

    def test_strict_mode_reports_python_parse_incompleteness(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "broken"
            source.mkdir()
            (source / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                status = repo_main([str(source), "--scan-only", "--strict", "--json"])
            self.assertEqual(2, status)
            payload = json.loads(output.getvalue())
            reasons = {item["reason"] for item in payload["material_scan_warnings"]}
            self.assertTrue(any(reason.startswith("PYTHON_PARSE_ERROR:") for reason in reasons))
            self.assertEqual(0, payload["canonical_algorithm_admissions"])

    def test_top_level_brain_dispatch_exposes_repository_feeding(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = entrypoint_main(["brain", "--help"])
        self.assertEqual(0, status)
        self.assertIn("repo", output.getvalue())
        self.assertIn("static", output.getvalue().casefold())


if __name__ == "__main__":
    unittest.main()
