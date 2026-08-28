from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ourd.egcf.engine import EGCFEngine
from ourd.egcf.models import ArtifactRecord
from ourd_gui.read_models import ReadOnlyEGCFRepository

from .fixtures_v1 import install_fixture_repository


class ReadModelCacheTests(unittest.TestCase):
    def test_cache_is_bounded_by_record_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = install_fixture_repository(root)
            repository = ReadOnlyEGCFRepository(
                root,
                max_cache_records=2,
                max_cache_bytes=10_000_000,
            )
            for identifier in list(bundle.ids.values())[:4]:
                repository.get(identifier)
            self.assertEqual(2, repository.cache_stats()["records"])

    def test_artifact_content_path_cannot_escape_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            repository = ReadOnlyEGCFRepository(root)
            record = ArtifactRecord(
                media_type="text/plain",
                sha256="a" * 64,
                size=0,
                source_ids=[],
                provenance={},
                created_at="2026-08-21T00:00:00Z",
                path="../../outside",
            )
            with self.assertRaisesRegex(ValueError, "escapes EGCF state root"):
                repository.artifact_content_path(record)

    def test_tampered_object_envelope_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = install_fixture_repository(root)
            repository = ReadOnlyEGCFRepository(root)
            identifier = bundle.ids["intent"]
            path = repository.object_path(identifier)
            content = path.read_text(encoding="utf-8").replace(
                "Implement AxialProfile",
                "Tampered objective",
                1,
            )
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                repository.get(identifier)

    def test_active_list_excludes_superseded_command_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root) as engine:
                previous = engine.commands.resolve("hrt.interpret@1")
                replacement = replace(previous, description="replacement definition")
                replacement_id = engine.store.register(replacement)
                engine.store.supersede(
                    previous.object_id,
                    replacement_id,
                    "test replacement",
                    "test",
                )
            repository = ReadOnlyEGCFRepository(root)
            all_matches = [
                record
                for record in repository.list("command-definition")
                if getattr(record, "command_id", "") == "hrt.interpret@1"
            ]
            active_matches = [
                record
                for record in repository.list("command-definition", active_only=True)
                if getattr(record, "command_id", "") == "hrt.interpret@1"
            ]
            self.assertEqual(2, len(all_matches))
            self.assertEqual([replacement_id], [record.object_id for record in active_matches])


if __name__ == "__main__":
    unittest.main()
