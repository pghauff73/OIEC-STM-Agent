from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.engine import EGCFEngine
from ourd_gui.read_models import ReadOnlyEGCFRepository
from ourd_gui.selection_trace import SelectionTraceAssembler


class SelectionTraceTests(unittest.TestCase):
    def test_real_compilation_builds_exact_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root) as engine:
                result = engine.invoke(
                    "hrt.interpret",
                    {"text": "Inspect parser"},
                    {
                        "dry_run": True,
                        "why": True,
                        "graph": True,
                        "trace": True,
                        "record": True,
                    },
                )
                selection_id = result["why"]["selections"][0]
                compiled_id = result["compiled_workflow_id"]
                compiled = engine.store.get(compiled_id)
                workflow_prefix = compiled.workflow_id.rsplit("@", 1)[0].removeprefix(
                    "invocation-"
                )
                invocation = next(
                    item
                    for item in engine.store.find("command-invocation")
                    if item.object_id.partition(":sha256:")[2].startswith(workflow_prefix)
                )
                invocation_id = invocation.object_id
            repository = ReadOnlyEGCFRepository(root)
            trace = SelectionTraceAssembler(repository).assemble(
                selection_id,
                invocation_id=invocation_id,
                compiled_workflow_id=compiled_id,
            )
            self.assertEqual(selection_id, trace.selection_id)
            self.assertEqual(invocation_id, trace.invocation_id)
            self.assertEqual("hrt.interpret@1", trace.command_id)
            self.assertTrue(trace.candidates)
            selected = [candidate for candidate in trace.candidates if candidate.selected]
            self.assertEqual(1, len(selected))
            self.assertEqual(trace.selected_algorithm_id, selected[0].algorithm_id)
            self.assertEqual(trace.selected_algorithm_digest, selected[0].algorithm_digest)
            self.assertTrue(selected[0].qualified)
            self.assertTrue(selected[0].evidence_ids)
            self.assertEqual(trace.digest, trace.digest)


if __name__ == "__main__":
    unittest.main()

