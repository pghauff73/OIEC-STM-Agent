from __future__ import annotations

from typing import Any, Dict, Iterable

from .errors import EGCFError
from .ids import utc_now
from .models import DecisionRecord
from .store import EGCFStore


def _scope_overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    left_scope = set(left)
    right_scope = set(right)
    return bool(left_scope.intersection(right_scope)) or "**" in left_scope or "**" in right_scope


class DecisionManager:
    def __init__(self, store: EGCFStore):
        self.store = store

    def create(
        self,
        *,
        question: str,
        alternatives: Iterable[str],
        choice: str,
        rationale: str,
        evidence_ids: Iterable[str],
        constraints: Iterable[str],
        owner: str,
        scope: Iterable[str],
        activate: bool = False,
        authority: str = "",
    ) -> str:
        if activate:
            raise EGCFError(
                "direct decision activation is forbidden; use an approved supersedence operation"
            )
        record = DecisionRecord(
            question=question,
            alternatives=list(alternatives),
            choice=choice,
            rationale=rationale,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            constraints=list(constraints),
            owner=owner,
            scope=list(scope),
            status="ACTIVE" if activate else "PROPOSED",
            created_at=utc_now(),
        )
        return self.store.register(record)

    def records(self, active_only: bool = False) -> list[DecisionRecord]:
        records = [record for record in self.store.find("decision") if isinstance(record, DecisionRecord)]
        if not active_only:
            return records
        active = set(self.store.active_ids("decision"))
        return [record for record in records if record.object_id in active and record.status == "ACTIVE"]

    def query(self, text: str = "", scope: Iterable[str] = ()) -> list[Dict[str, Any]]:
        requested_scope = list(scope)
        return [
            {"object_id": record.object_id, **record.to_dict()}
            for record in self.records()
            if (not text or text.lower() in f"{record.question} {record.choice} {record.rationale}".lower())
            and (not requested_scope or _scope_overlap(record.scope, requested_scope))
        ]

    def conflicts(self) -> list[Dict[str, Any]]:
        records = self.records(active_only=True)
        conflicts: list[Dict[str, Any]] = []
        for index, left in enumerate(records):
            for right in records[index + 1 :]:
                if (
                    left.question.strip().lower() == right.question.strip().lower()
                    and left.choice.strip().lower() != right.choice.strip().lower()
                    and _scope_overlap(left.scope, right.scope)
                ):
                    conflicts.append(
                        {
                            "left": left.object_id,
                            "right": right.object_id,
                            "reason": "active decisions choose different alternatives for the same question",
                        }
                    )
        return conflicts

    def supersede(
        self,
        old_id: str,
        *,
        choice: str,
        rationale: str,
        evidence_ids: Iterable[str],
        authority: str,
    ) -> str:
        if not authority:
            raise EGCFError("decision supersedence requires authority")
        old = self.store.get(old_id)
        if not isinstance(old, DecisionRecord):
            raise EGCFError(f"not a decision: {old_id}")
        record = DecisionRecord(
            **{
                **old.to_dict(),
                "choice": choice,
                "rationale": rationale,
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "status": "ACTIVE",
                "created_at": utc_now(),
                "supersedes": old_id,
            }
        )
        new_id = self.store.register(record)
        self.store.supersede(old_id, new_id, "decision superseded", authority)
        return new_id
