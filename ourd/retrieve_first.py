from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from .egcf.algebra.unified_retrieval import (
    UnifiedProblemRequirements,
    UnifiedRetrievalDecision,
    retrieve_unified_solution,
)
from .egcf.errors import EGCFError
from .egcf.ids import sha256_json


RETRIEVE_FIRST_VERSION = "saa-retrieve-first-policy-v1"


@dataclass(frozen=True)
class RetrieveFirstReceipt:
    schema_version: int
    policy_version: str
    status: str
    retrieval_attempted: bool
    required_search_completed: bool
    new_algorithm_generation_allowed: bool
    adaptation_allowed: bool
    generation_scope: Tuple[str, ...]
    selected_mathematical_algorithm_id: str | None
    selected_reasoning_id: str | None
    retrieval_decision_signature: str
    guidance: Tuple[str, ...]
    receipt_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "status": self.status,
            "retrieval_attempted": self.retrieval_attempted,
            "required_search_completed": self.required_search_completed,
            "new_algorithm_generation_allowed": self.new_algorithm_generation_allowed,
            "adaptation_allowed": self.adaptation_allowed,
            "generation_scope": list(self.generation_scope),
            "selected_mathematical_algorithm_id": self.selected_mathematical_algorithm_id,
            "selected_reasoning_id": self.selected_reasoning_id,
            "retrieval_decision_signature": self.retrieval_decision_signature,
            "guidance": list(self.guidance),
            "receipt_signature": self.receipt_signature,
        }


class RetrieveFirstController:
    """SAA-10.1 deterministic retrieve-before-generate policy controller."""

    def __init__(
        self,
        *,
        canonical_algorithm_store: Any | None,
        reasoning_store: Any | None,
        ontology: Any | None = None,
    ) -> None:
        self.canonical_algorithm_store = canonical_algorithm_store
        self.reasoning_store = reasoning_store
        self.ontology = ontology

    def evaluate(self, requirements: UnifiedProblemRequirements) -> RetrieveFirstReceipt:
        task = requirements.canonical()
        infrastructure_missing: list[str] = []
        if task.require_mathematical_algorithm and self.canonical_algorithm_store is None:
            infrastructure_missing.append("MATHEMATICAL_ALGORITHM_STORE")
        if task.require_reasoning_algorithm and self.reasoning_store is None:
            infrastructure_missing.append("REASONING_ALGORITHM_STORE")
        if infrastructure_missing:
            payload = {
                "version": RETRIEVE_FIRST_VERSION,
                "problem": task.to_dict(),
                "status": "RETRIEVAL_INFRASTRUCTURE_MISSING",
                "missing": infrastructure_missing,
            }
            return RetrieveFirstReceipt(
                schema_version=1,
                policy_version=RETRIEVE_FIRST_VERSION,
                status="RETRIEVAL_INFRASTRUCTURE_MISSING",
                retrieval_attempted=False,
                required_search_completed=False,
                new_algorithm_generation_allowed=False,
                adaptation_allowed=False,
                generation_scope=(),
                selected_mathematical_algorithm_id=None,
                selected_reasoning_id=None,
                retrieval_decision_signature="",
                guidance=(
                    "Required canonical stores are unavailable. Do not claim that novelty search has been completed.",
                ),
                receipt_signature=sha256_json(payload),
            )

        decision = retrieve_unified_solution(
            self.canonical_algorithm_store,
            self.reasoning_store,
            task,
            ontology=self.ontology,
        )
        missing = decision.missing_components
        if decision.required_components_satisfied:
            status = "REUSE_QUALIFIED_KNOWN_SOLUTION"
            generation_allowed = False
            adaptation_allowed = False
            guidance = (
                "Reuse the selected qualified canonical algorithms; do not invent a replacement algorithm without new contrary evidence or changed requirements.",
            )
        elif decision.selected_mathematical_algorithm_id or decision.selected_reasoning_id:
            status = "ADAPT_OR_FILL_CONFIRMED_GAP"
            generation_allowed = True
            adaptation_allowed = True
            guidance = (
                "Reuse the qualified component that fits and generate or adapt only the explicitly missing component(s).",
                "Any adapted or newly composed algorithm remains unqualified until it passes the applicable evidence gates.",
            )
        else:
            status = "NOVEL_GENERATION_ALLOWED_AFTER_QUALIFIED_SEARCH"
            generation_allowed = True
            adaptation_allowed = True
            guidance = (
                "Qualified canonical stores were searched and no eligible known solution was found for the required components.",
                "Novel generation is allowed only inside the confirmed missing scope and must be qualified before canonical reuse.",
            )
        payload = {
            "version": RETRIEVE_FIRST_VERSION,
            "problem_signature": decision.problem_signature,
            "retrieval_decision_signature": decision.decision_signature,
            "status": status,
            "generation_allowed": generation_allowed,
            "adaptation_allowed": adaptation_allowed,
            "generation_scope": list(missing),
            "selected_mathematical_algorithm_id": decision.selected_mathematical_algorithm_id,
            "selected_reasoning_id": decision.selected_reasoning_id,
        }
        return RetrieveFirstReceipt(
            schema_version=1,
            policy_version=RETRIEVE_FIRST_VERSION,
            status=status,
            retrieval_attempted=True,
            required_search_completed=True,
            new_algorithm_generation_allowed=generation_allowed,
            adaptation_allowed=adaptation_allowed,
            generation_scope=tuple(missing),
            selected_mathematical_algorithm_id=decision.selected_mathematical_algorithm_id,
            selected_reasoning_id=decision.selected_reasoning_id,
            retrieval_decision_signature=decision.decision_signature,
            guidance=guidance,
            receipt_signature=sha256_json(payload),
        )
