from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import platform
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Optional

from .catalog import command_catalog, command_contract
from .errors import EGCFError, QualificationError
from .ids import sha256_bytes, sha256_json, utc_now
from .models import (
    AlgorithmDefinition,
    CommandDefinition,
    EvidenceArtifact,
    QualificationRecord,
    SelectionDecision,
)
from .store import EGCFStore


def _version_key(identifier: str) -> tuple[str, int]:
    name, separator, raw_version = identifier.rpartition("@")
    if not separator:
        return identifier, 0


def runtime_qualification_context() -> Dict[str, Any]:
    return {
        "operating_system": platform.system().lower() or "unknown",
        "architecture": platform.machine().lower() or "unknown",
        "runtime": platform.python_implementation().lower(),
        "runtime_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "hardware_profile": "stdlib-portable",
        "grant_policy": "bounded-by-selection",
        "evidence_policy": "content-addressed",
        "budget_policy": "bounded-by-plan",
    }
    try:
        return name, int(raw_version)
    except ValueError:
        return identifier, 0


class CommandRegistry:
    def __init__(self, store: EGCFStore):
        self.store = store
        self.aliases: Dict[str, str] = {}
        self._resolve_cache: Dict[str, CommandDefinition] = {}
        self.bootstrap()

    def bootstrap(self) -> None:
        catalog = command_catalog()
        self.aliases = dict(catalog["aliases"])
        for namespace, verbs in catalog["namespaces"].items():
            defaults = dict(catalog["defaults"][namespace])
            for verb in verbs:
                key = f"{namespace}.{verb}"
                settings = {**defaults, **catalog["overrides"].get(key, {})}
                contract = command_contract(namespace, verb)
                definition = CommandDefinition(
                    namespace=namespace,
                    name=verb,
                    version=1,
                    intent_kinds=[key, namespace],
                    input_schema=contract["input_schema"],
                    output_schema=contract["output_schema"],
                    preconditions=contract["preconditions"],
                    postconditions=contract["postconditions"],
                    invariants=contract["invariants"],
                    evidence_requirements=contract["evidence_requirements"],
                    capability_query={
                        "level": settings["level"],
                        "facets": settings["facets"],
                    },
                    algorithm_query={"command_id": f"{key}@1"},
                    risk_policy=settings["risk"],
                    rollback_policy=settings["rollback"],
                    budget_policy={"actions": 1, "retries": 0},
                    approval_policy=settings["approval"],
                    lifecycle_policy={"compressible": settings["level"] in {"C0", "C1"}},
                    description=f"EGCF semantic command {key}",
                    aliases=[alias for alias, target in self.aliases.items() if target == f"{key}@1"],
                )
                active = [
                    item
                    for item in self.definitions(active_only=True)
                    if item.command_id == definition.command_id
                ]
                definition_id = self.store.register(definition)
                for previous in active:
                    if previous.object_id != definition_id:
                        self.store.supersede(
                            previous.object_id,
                            definition_id,
                            "built-in command definition updated",
                            "egcf-core-bootstrap",
                        )

    def register(self, definition: CommandDefinition) -> str:
        self._resolve_cache.clear()
        return self.store.register(definition)

    def definitions(self, *, active_only: bool = False) -> list[CommandDefinition]:
        active = set(self.store.active_ids("command-definition")) if active_only else None
        return [
            record
            for record in self.store.find("command-definition")
            if isinstance(record, CommandDefinition)
            and (active is None or record.object_id in active)
        ]

    def resolve(self, identifier: str) -> CommandDefinition:
        resolved = self.aliases.get(identifier, identifier)
        cached = self._resolve_cache.get(resolved)
        if cached is not None:
            return cached
        if "." not in resolved and "@" not in resolved:
            raise EGCFError(f"unknown command or alias: {identifier}")
        candidates = [
            definition
            for definition in self.definitions(active_only=True)
            if definition.command_id == resolved
        ]
        if candidates:
            self._resolve_cache[resolved] = candidates[-1]
            return candidates[-1]
        base, version = _version_key(resolved)
        if version:
            raise EGCFError(f"unknown command version: {resolved}")
        matching = [
            definition
            for definition in self.definitions(active_only=True)
            if definition.command_id.startswith(f"{base}@")
        ]
        if not matching:
            raise EGCFError(f"unknown command: {identifier}")
        selected = max(matching, key=lambda item: item.version)
        self._resolve_cache[resolved] = selected
        return selected

    def describe(self, identifier: str) -> Dict[str, Any]:
        definition = self.resolve(identifier)
        return {"object_id": definition.object_id, **definition.to_dict(), "command_id": definition.command_id}


class AlgorithmRegistry:
    def __init__(self, store: EGCFStore, commands: CommandRegistry):
        self.store = store
        self.commands = commands
        self._search_cache: Dict[str, list[AlgorithmDefinition]] = {}
        self._qualification_cache: Dict[tuple[str, str], list[QualificationRecord]] = {}
        self.bootstrap()
        self._search_cache.clear()
        self._qualification_cache.clear()

    def bootstrap(self) -> None:
        qualification_context = runtime_qualification_context()
        context_hash = sha256_json(qualification_context)
        package_root = Path(__file__).resolve().parent
        repository_root = package_root.parent.parent
        evidence_content = {
            "qualification_context": qualification_context,
            "sources": [
                {
                    "path": path.relative_to(repository_root).as_posix(),
                    "sha256": sha256_bytes(path.read_bytes()),
                }
                for path in (
                    package_root / "registry.py",
                    package_root / "engine.py",
                    package_root / "approval.py",
                    package_root / "handlers.py",
                    package_root / "simulation.py",
                    package_root / "adapters" / "semantic.py",
                    package_root / "adapters" / "simulation.py",
                    package_root / "adapters" / "eon.py",
                    package_root / "adapters" / "control.py",
                )
            ],
        }
        bootstrap_evidence = EvidenceArtifact(
            subject_id="egcf-core-builtins@1",
            claim_ids=[],
            requirement_ids=[],
            category="test",
            producer="deterministic-egcf-core",
            method="source-contract-validation",
            source_snapshot_hash=sha256_json(evidence_content["sources"]),
            target="ourd.egcf built-in algorithm set",
            oracle="schema-and-source-digest",
            environment=qualification_context,
            command_id="algorithm.qualify@1",
            algorithm_id="egcf-core-builtins@1",
            created_at="2026-08-21T00:00:00Z",
            sha256=sha256_json(evidence_content),
            success=True,
            limitations=["qualification is local to the recorded runtime context"],
            independence_group="builtin-contract:egcf-core",
            content=evidence_content,
        )
        bootstrap_evidence_id = self.store.register(bootstrap_evidence)
        for command in self.commands.definitions(active_only=True):
            implementation_kind = "builtin"
            if command.command_id in {"eon.execute@1", "eon.rollback@1"}:
                implementation_kind = "eon"
            elif command.command_id in {"eon.authorise@1", "workflow.execute@1"}:
                implementation_kind = "engine-control"
            elif command.namespace == "simulate" or command.command_id == "eon.simulate@1":
                implementation_kind = "simulation"
            implementation_ref = f"{implementation_kind}:{command.namespace}.{command.name}"
            implementation_digest = self._implementation_digest(
                implementation_kind,
                command.command_id,
            )
            algorithm = AlgorithmDefinition(
                name=f"builtin.{command.namespace}.{command.name}",
                version=1,
                implementation_kind=implementation_kind,
                implementation_ref=implementation_ref,
                implementation_digest=implementation_digest,
                command_ids=[command.command_id],
                input_schema=command.input_schema,
                output_schema=(
                    command.output_schema
                    if implementation_kind == "builtin"
                    else {"type": "object"}
                ),
                applicability={},
                capability_requirements=list(command.capability_query.get("facets", [])),
                capability_level=str(command.capability_query.get("level", "C1")),
                risk_floor=command.risk_policy,
                rollback_class=command.rollback_policy,
                invariants=list(command.invariants),
                evidence_requirements=list(command.evidence_requirements),
                qualification_policy={"tests_required": True, "contextual": True},
                owner="egcf-core",
                provenance={"catalog": "commands-v1", "command_id": command.command_id},
                status="QUALIFIED",
            )
            active = [
                item
                for item in self.algorithms(active_only=True)
                if item.algorithm_id == algorithm.algorithm_id
            ]
            if active and active[-1].status == "RETIRED":
                continue
            algorithm_definition_id = self.store.register(algorithm)
            for previous in active:
                if previous.object_id != algorithm_definition_id:
                    self.store.supersede(
                        previous.object_id,
                        algorithm_definition_id,
                        "built-in implementation digest updated",
                        "egcf-core-bootstrap",
                    )
            qualification = QualificationRecord(
                algorithm_id=algorithm.algorithm_id,
                algorithm_digest=algorithm.implementation_digest,
                context=qualification_context,
                context_hash=context_hash,
                evidence_ids=[bootstrap_evidence_id],
                tests=[
                    {
                        "name": "builtin source and schema contract",
                        "success": True,
                        "evidence_id": bootstrap_evidence_id,
                    }
                ],
                benchmarks=[],
                known_failures=[],
                status="QUALIFIED",
                qualified_by="egcf-core-deterministic-bootstrap",
                created_at="2026-08-21T00:00:00Z",
                expires_at="2030-01-01T00:00:00Z",
            )
            self.store.register(qualification)

    @staticmethod
    def _implementation_digest(implementation_kind: str, command_id: str) -> str:
        package_root = Path(__file__).resolve().parent
        repository_root = package_root.parent.parent
        if implementation_kind == "eon":
            paths = [
                package_root / "adapters" / "eon.py",
                repository_root / "ourd" / "agent.py",
                repository_root / "ourd" / "transactions.py",
                repository_root / "ourd" / "policy.py",
            ]
        elif implementation_kind == "engine-control":
            paths = [
                package_root / "engine.py",
                package_root / "approval.py",
                package_root / "adapters" / "control.py",
            ]
        elif implementation_kind == "simulation":
            paths = [
                package_root / "simulation.py",
                package_root / "adapters" / "simulation.py",
            ]
        else:
            paths = [package_root / "handlers.py", package_root / "adapters" / "semantic.py"]
        material = {
            "command_id": command_id,
            "implementation_kind": implementation_kind,
            "sources": [
                {
                    "path": path.relative_to(repository_root).as_posix(),
                    "sha256": sha256_bytes(path.read_bytes()),
                }
                for path in paths
            ],
        }
        return sha256_json(material)

    def register(self, definition: AlgorithmDefinition) -> str:
        if definition.implementation_kind not in {"builtin", "reference"}:
            raise EGCFError(
                "non-core algorithm proposals cannot select privileged executor kinds"
            )
        if definition.implementation_kind == "reference" and definition.status not in {
            "PROPOSED",
            "CANDIDATE",
        }:
            raise EGCFError("external algorithm references cannot self-qualify")
        forbidden = ("shell", "subprocess", "callback", "callable", "exec(", "eval(")
        if any(marker in definition.implementation_ref.lower() for marker in forbidden):
            raise EGCFError("algorithm implementation reference contains a forbidden executor marker")
        if len(definition.implementation_digest) != 64 or any(
            character not in "0123456789abcdef"
            for character in definition.implementation_digest.lower()
        ):
            raise EGCFError("algorithm implementation digest must be an exact SHA-256 digest")
        for command_id in definition.command_ids:
            self.commands.resolve(command_id)
        self._search_cache.clear()
        self._qualification_cache.clear()
        return self.store.register(definition)

    def algorithms(self, *, active_only: bool = False) -> list[AlgorithmDefinition]:
        active = set(self.store.active_ids("algorithm-definition")) if active_only else None
        return [
            record
            for record in self.store.find("algorithm-definition")
            if isinstance(record, AlgorithmDefinition)
            and (active is None or record.object_id in active)
        ]

    def qualifications(self, algorithm: AlgorithmDefinition) -> list[QualificationRecord]:
        cache_key = (algorithm.algorithm_id, algorithm.implementation_digest)
        cached = self._qualification_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        records = [
            record
            for record in self.store.find(
                "qualification",
                lambda item: isinstance(item, QualificationRecord)
                and item.algorithm_id == algorithm.algorithm_id
                and item.algorithm_digest == algorithm.implementation_digest,
            )
            if isinstance(record, QualificationRecord)
        ]
        self._qualification_cache[cache_key] = records
        return list(records)

    def search(self, command_id: str) -> list[AlgorithmDefinition]:
        cached = self._search_cache.get(command_id)
        if cached is not None:
            return list(cached)
        records = sorted(
            [
                algorithm
                for algorithm in self.algorithms(active_only=True)
                if command_id in algorithm.command_ids
            ],
            key=lambda item: (item.name, item.version, item.implementation_digest),
        )
        self._search_cache[command_id] = records
        return list(records)

    def qualify(
        self,
        algorithm_id: str,
        *,
        context: Dict[str, Any],
        evidence_ids: Iterable[str],
        tests: Iterable[Dict[str, Any]],
        benchmarks: Iterable[Dict[str, Any]] = (),
        known_failures: Iterable[str] = (),
        qualified_by: str,
        expires_at: str = "",
    ) -> str:
        algorithm = self.resolve(algorithm_id)
        test_list = list(tests)
        evidence = []
        grounded_tests = True
        for item in test_list:
            evidence_id = str(item.get("evidence_id", ""))
            if not evidence_id:
                grounded_tests = False
                continue
            artifact = self.store.get(evidence_id)
            if not isinstance(artifact, EvidenceArtifact):
                grounded_tests = False
                continue
            evidence.append(artifact)
            grounded_tests = grounded_tests and bool(
                item.get("success")
                and artifact.success is True
                and not artifact.simulated
                and artifact.algorithm_id == algorithm.algorithm_id
                and artifact.producer.startswith(("deterministic-", "human-"))
                and artifact.method != "reported"
            )
        status = "QUALIFIED" if test_list and grounded_tests else "CANDIDATE"
        record = QualificationRecord(
            algorithm_id=algorithm.algorithm_id,
            algorithm_digest=algorithm.implementation_digest,
            context=context,
            context_hash=sha256_json(context),
            evidence_ids=list(
                dict.fromkeys([*evidence_ids, *(item.object_id for item in evidence)])
            ),
            tests=test_list,
            benchmarks=list(benchmarks),
            known_failures=list(known_failures),
            status=status,
            qualified_by=qualified_by,
            created_at=utc_now(),
            expires_at=expires_at,
        )
        qualification_id = self.store.register(record)
        self._qualification_cache.clear()
        return qualification_id

    def resolve(self, identifier: str) -> AlgorithmDefinition:
        candidates = [
            algorithm
            for algorithm in self.algorithms(active_only=True)
            if algorithm.algorithm_id == identifier
        ]
        if candidates:
            return candidates[-1]
        base, version = _version_key(identifier)
        if version:
            raise EGCFError(f"unknown algorithm version: {identifier}")
        matching = [
            algorithm
            for algorithm in self.algorithms(active_only=True)
            if algorithm.name == base
        ]
        if not matching:
            raise EGCFError(f"unknown algorithm: {identifier}")
        return max(matching, key=lambda item: item.version)

    def retire(self, algorithm_id: str, *, authority: str) -> str:
        if not authority:
            raise EGCFError("algorithm retirement requires exact external authority")
        algorithm = self.resolve(algorithm_id)
        retired = replace(algorithm, status="RETIRED")
        retired_id = self.store.register(retired)
        self.store.supersede(algorithm.object_id, retired_id, "algorithm retired", authority)
        self._search_cache.clear()
        self._qualification_cache.clear()
        return retired_id


class SelectionEngine:
    ROLLBACK_SCORE = {"exact": 3, "compensating": 2, "best_effort": 1, "none": 0, "irreversible": -1}
    STATUS_SCORE = {"QUALIFIED": 3, "CANDIDATE": 1, "PROPOSED": 0, "DEPRECATED": -1, "RETIRED": -2}

    def __init__(self, store: EGCFStore, algorithms: AlgorithmRegistry):
        self.store = store
        self.algorithms = algorithms

    @staticmethod
    def _expired(expires_at: str) -> bool:
        if not expires_at:
            return False
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= datetime.now(timezone.utc)

    @staticmethod
    def _context_matches(required: Dict[str, Any], observed: Dict[str, Any]) -> bool:
        return all(key in observed and observed[key] == value for key, value in required.items())

    def select(
        self,
        command_id: str,
        *,
        context: Dict[str, Any],
        capability_ceiling: str,
        allowed_capabilities: Iterable[str],
        invariant_names: Iterable[str] = (),
        budget: Optional[Dict[str, Any]] = None,
    ) -> SelectionDecision:
        from .capabilities import CAPABILITY_ORDER

        observed_context = {**runtime_qualification_context(), **context}
        candidates: list[Dict[str, Any]] = []
        excluded: list[Dict[str, Any]] = []
        allowed = set(allowed_capabilities)
        active_invariants = set(invariant_names)
        for algorithm in self.algorithms.search(command_id):
            reasons: list[str] = []
            if algorithm.status in {"RETIRED", "DEPRECATED", "PROPOSED"}:
                reasons.append(f"status={algorithm.status}")
            if CAPABILITY_ORDER[algorithm.capability_level] > CAPABILITY_ORDER[capability_ceiling]:
                reasons.append("capability ceiling exceeded")
            missing_capabilities = sorted(set(algorithm.capability_requirements) - allowed)
            if missing_capabilities:
                reasons.append(f"missing capabilities: {missing_capabilities}")
            incompatible = [
                key for key, expected in algorithm.applicability.items()
                if key not in observed_context or observed_context[key] != expected
            ]
            if incompatible:
                reasons.append(f"context mismatch: {incompatible}")
            missing_invariants = sorted(set(algorithm.invariants) - active_invariants)
            if active_invariants and missing_invariants:
                reasons.append(f"invariant mismatch: {missing_invariants}")
            qualifications = [
                qualification for qualification in self.algorithms.qualifications(algorithm)
                if qualification.status == "QUALIFIED" and not self._expired(qualification.expires_at)
                and self._context_matches(qualification.context, observed_context)
            ]
            if not qualifications:
                reasons.append("no current qualification")
            qualification_strength = sum(len(item.evidence_ids) for item in qualifications)
            passed_tests = sum(
                1
                for qualification in qualifications
                for test in qualification.tests
                if test.get("success") is True
            )
            benchmark_strength = sum(len(item.benchmarks) for item in qualifications)
            score_components = {
                "qualification_strength": qualification_strength,
                "invariant_compatibility": int(not missing_invariants),
                "expected_correctness": passed_tests,
                "rollback_quality": self.ROLLBACK_SCORE.get(algorithm.rollback_class, -2),
                "evidence_freshness": int(bool(qualifications)),
                "deterministic_performance_fit": benchmark_strength,
                "resource_cost": int(algorithm.applicability.get("resource_cost", 0)),
                "known_failure_count": len(algorithm.known_failures),
            }
            item = {
                "algorithm_id": algorithm.algorithm_id,
                "algorithm_digest": algorithm.implementation_digest,
                "status": algorithm.status,
                "rollback_class": algorithm.rollback_class,
                "qualification_ids": [qualification.object_id for qualification in qualifications],
                "known_failures": algorithm.known_failures,
                "score_components": score_components,
            }
            if reasons:
                excluded.append({**item, "reasons": reasons})
            else:
                candidates.append(item)
        if not candidates:
            raise QualificationError(
                f"no qualified algorithm for {command_id}: {excluded}"
            )
        candidates.sort(
            key=lambda item: (
                -item["score_components"]["qualification_strength"],
                -item["score_components"]["invariant_compatibility"],
                -item["score_components"]["expected_correctness"],
                -item["score_components"]["rollback_quality"],
                -item["score_components"]["evidence_freshness"],
                -item["score_components"]["deterministic_performance_fit"],
                item["score_components"]["resource_cost"],
                item["score_components"]["known_failure_count"],
                item["algorithm_id"],
                item["algorithm_digest"],
            )
        )
        selected = candidates[0]
        decision = SelectionDecision(
            command_id=command_id,
            context_hash=sha256_json(observed_context),
            candidates=candidates,
            excluded=excluded,
            selected_algorithm_id=selected["algorithm_id"],
            selected_algorithm_digest=selected["algorithm_digest"],
            ranking=[
                "qualification strength",
                "invariant compatibility",
                "expected correctness",
                "rollback quality",
                "evidence freshness",
                "deterministic performance fit",
                "resource cost",
                "stable algorithm ID",
            ],
            tie_break="algorithm_id then implementation_digest",
            evidence_ids=list(selected["qualification_ids"]),
            created_at=utc_now(),
            score_components={
                "selected": dict(selected["score_components"]),
                "candidate_vectors": {
                    item["algorithm_id"]: dict(item["score_components"])
                    for item in candidates
                },
            },
        )
        self.store.register(decision)
        return decision
