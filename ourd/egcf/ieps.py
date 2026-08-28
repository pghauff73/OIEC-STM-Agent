from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

from .evidence import EvidenceManager
from .ids import utc_now
from .models import EvidenceRequirement


class IEPS:
    def __init__(self, evidence: EvidenceManager):
        self.evidence = evidence

    def qualify(self, subject_id: str) -> Dict[str, Any]:
        coverage = self.evidence.coverage(subject_id)
        confidence = self.evidence.confidence(subject_id)
        conflicts = self.evidence.conflicts(subject_id)
        qualified = not coverage["missing_mandatory"] and not conflicts and confidence.conclusion != "BLOCKED"
        return {
            "subject_id": subject_id,
            "qualified": qualified,
            "coverage": coverage,
            "confidence_id": confidence.object_id,
            "confidence": confidence.to_dict(),
            "conflicts": conflicts,
            "evaluated_at": utc_now(),
        }

    def coverage(self, subject_id: str) -> Dict[str, Any]:
        return self.evidence.coverage(subject_id)

    def oracle(
        self,
        subject_id: str,
        name: str,
        category: str,
        oracle: str,
        *,
        mandatory: bool = True,
        freshness_seconds: int = 0,
        independence_group: str = "",
    ) -> str:
        requirement = EvidenceRequirement(
            subject_id=subject_id,
            name=name,
            category=category,
            oracle=oracle,
            freshness_seconds=freshness_seconds,
            independence_group=independence_group or name,
            mandatory=mandatory,
        )
        return self.evidence.add_requirement(requirement)

    @staticmethod
    def counterexamples(candidates: Iterable[Any], predicate_results: Iterable[bool]) -> Dict[str, Any]:
        pairs = list(zip(candidates, predicate_results))
        failures = [candidate for candidate, result in pairs if not result]
        return {
            "tested": len(pairs),
            "counterexamples": failures,
            "found": bool(failures),
        }

    def uniqueness(self, subject_id: str) -> Dict[str, Any]:
        return self.evidence.uniqueness(subject_id)

    @staticmethod
    def mutation(mutations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        items = list(mutations)
        detected = [item for item in items if item.get("detected")]
        survivors = [item for item in items if not item.get("detected")]
        return {
            "total": len(items),
            "detected": len(detected),
            "survivors": survivors,
            "mutation_score": 1.0 if not items else len(detected) / len(items),
        }

    @staticmethod
    def shrink(sequence: Sequence[Any], required_items: Iterable[Any]) -> Dict[str, Any]:
        required = list(required_items)
        minimized = [item for item in sequence if item in required]
        missing = [item for item in required if item not in minimized]
        return {
            "original_size": len(sequence),
            "minimized": minimized,
            "missing_required": missing,
            "preserved": not missing,
        }

    def gate(self, subject_id: str) -> Dict[str, Any]:
        qualification = self.qualify(subject_id)
        return {
            "subject_id": subject_id,
            "verdict": "APPROVE" if qualification["qualified"] else "REFUSE",
            "qualification": qualification,
            "reason": "all mandatory evidence gates passed"
            if qualification["qualified"]
            else "mandatory evidence, conflict, or confidence gate failed",
        }
