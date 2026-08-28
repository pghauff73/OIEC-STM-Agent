from __future__ import annotations

import json
from pathlib import Path
import unittest

from ourd.egcf.adapters.registry import adapter_inventory
from ourd.egcf.context import CommandContext
from ourd.egcf.domains import built_in_domain_packs
from ourd.egcf.engine import EGCFEngine
from ourd.egcf.lifecycle import CANONICAL_STAGES, Lifecycle
from ourd.egcf.ids import sha256_json
from ourd.egcf.models import AlgorithmDefinition, CommandInvocation, SelectionDecision
from ourd.egcf.registry import runtime_qualification_context
from tests.helpers import RepoFixture
from tools.generate_egcf_reference import GENERATED


class EGCFCompletionTests(unittest.TestCase):
    def test_typed_contracts_lifecycle_and_generated_reference_are_complete(self) -> None:
        fixture = RepoFixture()
        try:
            with EGCFEngine(fixture.root) as engine:
                definitions = engine.commands.definitions(active_only=True)
                self.assertTrue(definitions)
                for definition in definitions:
                    with self.subTest(command=definition.command_id):
                        self.assertTrue(definition.preconditions)
                        self.assertTrue(definition.postconditions)
                        self.assertTrue(definition.invariants)
                        self.assertTrue(definition.evidence_requirements)
                        self.assertTrue(
                            all("type" in schema for schema in definition.input_schema["properties"].values())
                        )
                generic = []
                routed = {}
                for definition in definitions:
                    algorithm = engine.algorithms.search(definition.command_id)[0]
                    routed[definition.command_id] = algorithm.implementation_kind
                    if algorithm.implementation_kind != "builtin":
                        continue
                    exact = hasattr(
                        engine.handlers,
                        f"_{definition.namespace}_{definition.name.replace('-', '_')}",
                    )
                    grouped = hasattr(engine.handlers, f"_{definition.namespace}")
                    if not exact and not grouped:
                        generic.append(definition.command_id)
                self.assertEqual(["capability.grant@1", "capability.revoke@1"], sorted(generic))
                self.assertEqual("engine-control", routed["eon.authorise@1"])
                self.assertEqual("engine-control", routed["workflow.execute@1"])
                self.assertEqual("assurance.generate@1", engine.commands.resolve("prove").command_id)
                compiled, context, lifecycle = engine.compile_command(
                    "capability.list",
                    {},
                    {"dry_run": True, "evidence": ["evidence:sha256:declared"]},
                )
                invocations = engine.store.find("command-invocation")
                invocation = invocations[-1]
                self.assertIsInstance(invocation, CommandInvocation)
                self.assertEqual(
                    engine.commands.resolve(invocation.command_id).object_id,
                    invocation.command_definition_id,
                )
                plan = engine.create_execution_plan(compiled, prepare_mutations=False)
                self.assertIn("evidence:sha256:declared", plan.evidence_ids)
                selection = engine.store.get(compiled.nodes[0]["selection_id"])
                self.assertIsInstance(selection, SelectionDecision)
                self.assertTrue(selection.score_components["selected"])
                self.assertTrue(set(selection.evidence_ids).issubset(set(plan.evidence_ids)))
                self.assertEqual("COMPILED", lifecycle.state)
        finally:
            fixture.close()

        lifecycle = Lifecycle()
        lifecycle.compress(["INTERPRETED", "MODELLED", "RESOLVED", "QUALIFIED", "COMPILED"])
        lifecycle.transition("COMPLETED")
        projection = lifecycle.projection()
        self.assertEqual(list(CANONICAL_STAGES), [item["stage"] for item in projection])
        self.assertTrue(all(item["status"] in {"completed", "not_required"} for item in projection))

        root = Path(__file__).resolve().parents[1]
        for relative_path, renderer in GENERATED.items():
            with self.subTest(generated=relative_path.as_posix()):
                self.assertEqual(renderer(), (root / relative_path).read_text(encoding="utf-8"))

    def test_qualification_adapter_and_domain_contracts_are_context_bound(self) -> None:
        fixture = RepoFixture()
        try:
            with EGCFEngine(fixture.root) as engine:
                algorithm = engine.algorithms.search("repo.metrics@1")[0]
                qualifications = engine.algorithms.qualifications(algorithm)
                self.assertTrue(qualifications)
                qualification = qualifications[-1]
                self.assertEqual(runtime_qualification_context(), qualification.context)
                self.assertEqual("2030-01-01T00:00:00Z", qualification.expires_at)
                self.assertTrue(qualification.evidence_ids)
                self.assertTrue(all(test.get("evidence_id") for test in qualification.tests))

                command = engine.commands.resolve("repo.metrics")

                def candidate(name: str, applicability: dict) -> AlgorithmDefinition:
                    return AlgorithmDefinition(
                        name=name,
                        version=1,
                        implementation_kind="builtin",
                        implementation_ref=f"builtin:{name}",
                        implementation_digest=sha256_json(name),
                        command_ids=[command.command_id],
                        input_schema=command.input_schema,
                        output_schema=command.output_schema,
                        applicability=applicability,
                        capability_requirements=list(command.capability_query["facets"]),
                        capability_level=str(command.capability_query["level"]),
                        risk_floor=command.risk_policy,
                        rollback_class=command.rollback_policy,
                        invariants=list(command.invariants),
                        evidence_requirements=list(command.evidence_requirements),
                        qualification_policy={"contextual": True},
                        owner="unit-test",
                        provenance={"test": True},
                        status="QUALIFIED",
                    )

                expired = candidate("candidate.expired", {})
                engine.algorithms.register(expired)
                expired_evidence = engine.handlers.evidence.collect(
                    subject_id=expired.object_id,
                    content={"candidate": expired.algorithm_id},
                    category="test",
                    producer="deterministic-unit-test",
                    method="unit-test",
                    source_snapshot_hash=engine.workspace.snapshot_hash(),
                    target=expired.algorithm_id,
                    oracle="unit-test",
                    environment=runtime_qualification_context(),
                    command_id=command.command_id,
                    algorithm_id=expired.algorithm_id,
                    success=True,
                    independence_group="unit-test-expired",
                )
                engine.algorithms.qualify(
                    expired.algorithm_id,
                    context=runtime_qualification_context(),
                    evidence_ids=[expired_evidence],
                    tests=[{"name": "expired", "success": True, "evidence_id": expired_evidence}],
                    qualified_by="unit-test",
                    expires_at="2026-08-20T00:00:00Z",
                )
                mismatch = candidate("candidate.mismatch", {"operating_system": "not-this-host"})
                engine.algorithms.register(mismatch)
                retired = candidate("candidate.retired", {})
                engine.algorithms.register(retired)
                engine.algorithms.retire(retired.algorithm_id, authority="unit-test")
                decision = engine.handlers.selector.select(
                    command.command_id,
                    context=runtime_qualification_context(),
                    capability_ceiling=engine.grant.capability_ceiling,
                    allowed_capabilities=engine.grant.capabilities,
                )
                excluded = {item["algorithm_id"]: item["reasons"] for item in decision.excluded}
                self.assertIn("no current qualification", excluded[expired.algorithm_id])
                self.assertTrue(any(reason.startswith("context mismatch") for reason in excluded[mismatch.algorithm_id]))
                self.assertIn("status=RETIRED", excluded[retired.algorithm_id])
        finally:
            fixture.close()

        required_adapter_fields = {
            "input_schema", "side_effects", "idempotency", "data_boundary", "rollback",
        }
        inventory = adapter_inventory(Path.cwd())
        for name, contract in inventory.items():
            with self.subTest(adapter=name):
                self.assertTrue(required_adapter_fields.issubset(contract))
                self.assertFalse(contract["direct_command_access"])

        packs = built_in_domain_packs()
        samples = {
            "grammar@1": ("parse", {"text": "a+b"}),
            "physics@1": ("simulate", {"duration": 1.0}),
            "geometry@1": ("analyse", {"points": [[0, 0], [1, 0], [1, 1]]}),
            "vision@1": ("segment", {"pixels": [[0.2, 0.8]], "threshold": 0.5}),
            "robotics@1": ("plan", {"grid": [[0, 0]], "start": [0, 0], "goal": [0, 1]}),
            "cad@1": ("validate", {"vertices": [[0, 0, 0]], "faces": []}),
        }
        for pack_id, (command, inputs) in samples.items():
            with self.subTest(pack=pack_id):
                description = packs.describe(pack_id)
                self.assertFalse(description["authority_transfer"])
                self.assertTrue(description["evidence_policy"]["oracle"])
                self.assertFalse(description["evidence_policy"]["model_narrative_qualifies"])
                result = packs.execute(pack_id, command, inputs)
                self.assertEqual(pack_id, result["domain_pack"])

        contracts = json.loads((Path(__file__).resolve().parents[1] / "commands/v1/contracts.json").read_text(encoding="utf-8"))
        self.assertEqual(183, len(contracts["commands"]))


if __name__ == "__main__":
    unittest.main()
