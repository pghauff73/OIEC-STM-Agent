from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from ..persistence import redact
from .ids import sha256_json, utc_now
from .models import ConfidenceAssessment, EvidenceArtifact, EvidenceRequirement
from .store import EGCFStore


class EvidenceManager:
    DIMENSIONS = (
        "coverage",
        "relevance",
        "oracle_strength",
        "source_authority",
        "reproducibility",
        "independence",
        "freshness",
        "counterexample_coverage",
        "conflict_resistance",
    )

    def __init__(self, store: EGCFStore):
        self.store = store

    def add_requirement(self, requirement: EvidenceRequirement) -> str:
        return self.store.register(requirement)

    def requirements(self, subject_id: str) -> list[tuple[str, EvidenceRequirement]]:
        return [
            (record.object_id, record)
            for record in self.store.find(
                "evidence-requirement",
                lambda item: isinstance(item, EvidenceRequirement) and item.subject_id == subject_id,
            )
            if isinstance(record, EvidenceRequirement)
        ]

    def collect(
        self,
        *,
        subject_id: str,
        content: Any,
        category: str,
        producer: str,
        method: str,
        source_snapshot_hash: str,
        target: str = "",
        oracle: str = "",
        environment: Dict[str, Any] | None = None,
        command_id: str = "",
        algorithm_id: str = "",
        claim_ids: Iterable[str] = (),
        requirement_ids: Iterable[str] = (),
        success: bool | None = None,
        limitations: Iterable[str] = (),
        independence_group: str = "",
        simulated: bool = False,
        path: str = "",
    ) -> str:
        safe_content = redact(content)
        artifact = EvidenceArtifact(
            subject_id=subject_id,
            claim_ids=list(dict.fromkeys(claim_ids)),
            requirement_ids=list(dict.fromkeys(requirement_ids)),
            category=category,
            producer=producer,
            method=method,
            source_snapshot_hash=source_snapshot_hash,
            target=target,
            oracle=oracle,
            environment=redact(environment or {}),
            command_id=command_id,
            algorithm_id=algorithm_id,
            created_at=utc_now(),
            sha256=sha256_json(safe_content),
            success=success,
            limitations=list(limitations),
            independence_group=independence_group or f"producer:{producer}",
            simulated=simulated,
            path=path,
            content=safe_content,
        )
        return self.store.register(artifact, event_type="egcf_evidence_collected")

    def artifacts(self, subject_id: str) -> list[EvidenceArtifact]:
        return [
            record
            for record in self.store.find(
                "egcf-evidence",
                lambda item: isinstance(item, EvidenceArtifact) and item.subject_id == subject_id,
            )
            if isinstance(record, EvidenceArtifact)
        ]

    @staticmethod
    def _is_fresh(artifact: EvidenceArtifact, freshness_seconds: int) -> bool:
        if freshness_seconds <= 0:
            return True
        created = datetime.fromisoformat(artifact.created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).total_seconds() <= freshness_seconds

    def coverage(self, subject_id: str) -> Dict[str, Any]:
        requirements = self.requirements(subject_id)
        artifacts = self.artifacts(subject_id)
        matrix: list[Dict[str, Any]] = []
        missing: list[str] = []
        used_artifact_ids: set[str] = set()
        for requirement_id, requirement in requirements:
            matches = [
                artifact
                for artifact in artifacts
                if requirement_id in artifact.requirement_ids
                and artifact.category == requirement.category
                and self._is_fresh(artifact, requirement.freshness_seconds)
                and (not requirement.oracle or artifact.oracle == requirement.oracle)
                and (
                    not requirement.independence_group
                    or artifact.independence_group == requirement.independence_group
                )
                and (not artifact.simulated or requirement.category.startswith("simulation"))
                and artifact.success is not False
                and artifact.object_id not in used_artifact_ids
            ]
            if matches:
                used_artifact_ids.add(matches[0].object_id)
                matches = matches[:1]
            matrix.append(
                {
                    "requirement_id": requirement_id,
                    "name": requirement.name,
                    "mandatory": requirement.mandatory,
                    "evidence_ids": [artifact.object_id for artifact in matches],
                    "covered": bool(matches),
                }
            )
            if requirement.mandatory and not matches:
                missing.append(requirement_id)
        return {
            "subject_id": subject_id,
            "requirements": matrix,
            "missing_mandatory": missing,
            "coverage": 1.0 if not requirements else sum(item["covered"] for item in matrix) / len(matrix),
            "artifact_reuse_forbidden": True,
        }

    def uniqueness(self, subject_id: str) -> Dict[str, Any]:
        artifacts = self.artifacts(subject_id)
        by_hash: Dict[str, list[str]] = {}
        by_group: Dict[str, list[str]] = {}
        for artifact in artifacts:
            by_hash.setdefault(artifact.sha256, []).append(artifact.object_id)
            by_group.setdefault(artifact.independence_group, []).append(artifact.object_id)
        duplicates = {key: value for key, value in by_hash.items() if len(value) > 1}
        dependent_groups = {key: value for key, value in by_group.items() if len(value) > 1}
        return {
            "subject_id": subject_id,
            "duplicate_content": duplicates,
            "dependent_groups": dependent_groups,
            "unique": not duplicates and not dependent_groups,
            "independent": not dependent_groups,
        }

    def conflicts(self, subject_id: str) -> list[Dict[str, Any]]:
        artifacts = self.artifacts(subject_id)
        conflicts: list[Dict[str, Any]] = []
        for index, left in enumerate(artifacts):
            for right in artifacts[index + 1 :]:
                same_claim = bool(set(left.claim_ids).intersection(right.claim_ids))
                same_requirement = bool(set(left.requirement_ids).intersection(right.requirement_ids))
                opposite = {left.success, right.success} == {True, False}
                if opposite and (same_claim or same_requirement) and left.simulated == right.simulated:
                    conflicts.append(
                        {
                            "left": left.object_id,
                            "right": right.object_id,
                            "reason": "opposite evidence outcomes for the same claim or requirement",
                        }
                    )
        return conflicts

    def confidence(self, subject_id: str, policy: str = "egcf-default-v1") -> ConfidenceAssessment:
        artifacts = self.artifacts(subject_id)
        coverage = self.coverage(subject_id)
        conflicts = self.conflicts(subject_id)
        uniqueness = self.uniqueness(subject_id)
        relevant = [artifact for artifact in artifacts if artifact.subject_id == subject_id]
        groups = {artifact.independence_group for artifact in relevant}
        dimensions = {
            "coverage": coverage["coverage"],
            "relevance": 1.0 if not artifacts else len(relevant) / len(artifacts),
            "oracle_strength": 0.0 if not artifacts else sum(bool(item.oracle) for item in artifacts) / len(artifacts),
            "source_authority": 0.0 if not artifacts else sum(
                1.0 if item.producer.startswith(("deterministic", "human")) else 0.5
                for item in artifacts
            ) / len(artifacts),
            "reproducibility": 0.0 if not artifacts else sum(
                bool(item.environment) and bool(item.source_snapshot_hash) for item in artifacts
            ) / len(artifacts),
            "independence": 0.0 if not artifacts else len(groups) / len(artifacts),
            "freshness": 0.0 if not artifacts else sum(bool(item.created_at) for item in artifacts) / len(artifacts),
            "counterexample_coverage": 1.0 if any(item.category == "counterexample" for item in artifacts) else 0.0,
            "conflict_resistance": 1.0 if not conflicts else max(0.0, 1.0 - len(conflicts) / max(1, len(artifacts))),
        }
        blocking_gaps = list(coverage["missing_mandatory"])
        if uniqueness["duplicate_content"]:
            blocking_gaps.append("duplicate evidence content")
        if uniqueness["dependent_groups"]:
            blocking_gaps.append("evidence independence groups are reused")
        known_unknowns = sorted(
            {limitation for artifact in artifacts for limitation in artifact.limitations}
        )
        average = sum(dimensions.values()) / len(dimensions)
        if blocking_gaps or conflicts:
            conclusion = "BLOCKED"
        elif average >= 0.85:
            conclusion = "HIGH"
        elif average >= 0.6:
            conclusion = "MEDIUM"
        else:
            conclusion = "LOW"
        assessment = ConfidenceAssessment(
            subject_id=subject_id,
            policy=policy,
            dimensions=dimensions,
            blocking_gaps=blocking_gaps,
            conflicts=[item["reason"] for item in conflicts],
            known_unknowns=known_unknowns,
            conclusion=conclusion,
            evidence_ids=[artifact.object_id for artifact in artifacts],
            created_at=utc_now(),
        )
        self.store.register(assessment)
        return assessment

    def graph(self, subject_id: str) -> Dict[str, Any]:
        requirements = self.requirements(subject_id)
        artifacts = self.artifacts(subject_id)
        return {
            "nodes": [
                *[
                    {"id": requirement_id, "type": "requirement", "label": requirement.name}
                    for requirement_id, requirement in requirements
                ],
                *[
                    {"id": artifact.object_id, "type": "evidence", "label": artifact.category}
                    for artifact in artifacts
                ],
            ],
            "edges": [
                {"from": artifact.object_id, "to": requirement_id, "relation": "supports"}
                for artifact in artifacts
                for requirement_id in artifact.requirement_ids
            ],
        }
