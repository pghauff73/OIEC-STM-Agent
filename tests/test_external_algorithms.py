from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from ourd.egcf.errors import EGCFError
from ourd.egcf.external_algorithms import capture_babcs_source, register_babcs_algorithm
from ourd.egcf.models import AlgorithmDefinition, ArtifactRecord
from ourd.egcf.registry import AlgorithmRegistry, CommandRegistry
from ourd.egcf.store import EGCFStore


class ExternalAlgorithmTests(unittest.TestCase):
    def make_babcs(self, root: Path) -> Path:
        package = root / "src" / "babcs"
        package.mkdir(parents=True)
        (root / "README.md").write_text("BAB-CS reference implementation\n", encoding="utf-8")
        (root / "IMPLEMENTATION_PLAN.md").write_text("# Plan\n", encoding="utf-8")
        (root / "pyproject.toml").write_text("[project]\nname='bab-cs'\n", encoding="utf-8")
        (root / "LICENSE").write_text("MPL-2.0\n", encoding="utf-8")
        (package / "_project.py").write_text('VERSION = "1.1.0"\n', encoding="utf-8")
        (package / "__init__.py").write_text(
            '__all__ = ["BABCSConfig", "BoundedIntegrator"]\n', encoding="utf-8"
        )
        (package / "bounded.py").write_text(
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True)\n"
            "class BABCSConfig:\n"
            "    maximum_rejections: int = 2\n"
            "class BoundedIntegrator:\n"
            "    pass\n",
            encoding="utf-8",
        )
        (package / "candidates.py").write_text(
            'CANDIDATE_METHODS = ("ab2", "heun")\n', encoding="utf-8"
        )
        for name in ("integrators.py", "model.py", "simulator.py"):
            (package / name).write_text(f"def {name[:-3]}():\n    return None\n", encoding="utf-8")
        return root

    def test_babcs_bundle_is_deterministic_and_retrievable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            babcs = self.make_babcs(base / "BAB-CS")
            workspace = base / "workspace"
            workspace.mkdir()
            first_snapshot, first_bundle = capture_babcs_source(babcs)
            second_snapshot, second_bundle = capture_babcs_source(babcs)
            self.assertEqual(first_snapshot, second_snapshot)
            self.assertEqual(first_bundle, second_bundle)
            registration = register_babcs_algorithm(workspace, babcs)
            repeated = register_babcs_algorithm(workspace, babcs)
            self.assertEqual(first_snapshot.bundle_digest, registration.snapshot.bundle_digest)
            self.assertEqual(registration.source_bundle_artifact_id, repeated.source_bundle_artifact_id)
            self.assertEqual(registration.algorithm_definition_id, repeated.algorithm_definition_id)
            with EGCFStore(workspace) as store:
                definition = store.get(registration.algorithm_definition_id)
                self.assertIsInstance(definition, AlgorithmDefinition)
                self.assertEqual("reference", definition.implementation_kind)
                self.assertEqual("PROPOSED", definition.status)
                artifact = store.get(registration.source_bundle_artifact_id)
                self.assertIsInstance(artifact, ArtifactRecord)
                stored_bytes = (store.state_root / artifact.path).read_bytes()
                self.assertEqual(first_bundle, stored_bytes)
                self.assertEqual(hashlib.sha256(stored_bytes).hexdigest(), artifact.sha256)

    def test_registry_allows_reference_but_refuses_privileged_or_self_qualified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with EGCFStore(workspace) as store:
                commands = CommandRegistry(store)
                registry = AlgorithmRegistry(store, commands)
                base = AlgorithmDefinition(
                    name="reference.example",
                    version=1,
                    implementation_kind="reference",
                    implementation_ref="artifact-record:artifact:sha256:" + "a" * 64,
                    implementation_digest="b" * 64,
                    command_ids=["experiment.analyse@1"],
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                    applicability={"execution": "reference-only"},
                    capability_requirements=["registry.read"],
                    capability_level="C0",
                    risk_floor="L0",
                    rollback_class="none",
                    invariants=[],
                    evidence_requirements=["source digest"],
                    qualification_policy={"reference_only": True},
                    owner="test",
                    provenance={"source": "unit-test"},
                    status="PROPOSED",
                )
                self.assertTrue(registry.register(base).startswith("algorithm-definition:sha256:"))
                with self.assertRaises(EGCFError):
                    registry.register(
                        AlgorithmDefinition(**{**base.to_dict(), "status": "QUALIFIED"})
                    )
                with self.assertRaises(EGCFError):
                    registry.register(
                        AlgorithmDefinition(
                            **{
                                **base.to_dict(),
                                "implementation_kind": "simulation",
                                "status": "PROPOSED",
                            }
                        )
                    )


if __name__ == "__main__":
    unittest.main()
