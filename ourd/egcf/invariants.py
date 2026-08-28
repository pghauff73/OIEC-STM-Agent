from __future__ import annotations

from typing import Any, Dict, Iterable

from .errors import EGCFError
from .ids import utc_now
from .models import InvariantRecord
from .store import EGCFStore


def _normalize_statement(statement: str) -> str:
    return " ".join(statement.lower().strip().rstrip(".").split())


def _opposites(left: str, right: str) -> bool:
    normalized_left = _normalize_statement(left)
    normalized_right = _normalize_statement(right)
    return normalized_left == f"not {normalized_right}" or normalized_right == f"not {normalized_left}"


def _scope_overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    left_scope = set(left)
    right_scope = set(right)
    return bool(left_scope.intersection(right_scope)) or "**" in left_scope or "**" in right_scope


class InvariantManager:
    def __init__(self, store: EGCFStore):
        self.store = store

    def discover(self, statements: Iterable[str], scope: Iterable[str], source: str) -> list[str]:
        identifiers = []
        for statement in dict.fromkeys(item.strip() for item in statements if item.strip()):
            record = InvariantRecord(
                name="-".join(_normalize_statement(statement).split()[:8]) or "unnamed",
                statement=statement,
                scope=list(scope),
                status="DISCOVERED_CANDIDATE",
                validator={"kind": "unvalidated", "source": source},
                evidence_ids=[],
                falsifier=f"Find a case in scope where: not ({statement})",
                counterexamples=[],
                authority="proposal-only",
                created_at=utc_now(),
            )
            identifiers.append(self.store.register(record))
        return identifiers

    def register(
        self,
        *,
        name: str,
        statement: str,
        scope: Iterable[str],
        validator: Dict[str, Any],
        evidence_ids: Iterable[str],
        falsifier: str,
        authority: str,
        counterexamples: Iterable[str] = (),
    ) -> str:
        evidence = list(dict.fromkeys(evidence_ids))
        if not authority or not validator or not evidence or not falsifier:
            raise EGCFError("registered invariant requires authority, validator, evidence, and falsifier")
        record = InvariantRecord(
            name=name,
            statement=statement,
            scope=list(scope),
            status="REGISTERED",
            validator=validator,
            evidence_ids=evidence,
            falsifier=falsifier,
            counterexamples=list(counterexamples),
            authority=authority,
            created_at=utc_now(),
        )
        return self.store.register(record)

    def records(self, active_only: bool = False) -> list[InvariantRecord]:
        records = [record for record in self.store.find("invariant") if isinstance(record, InvariantRecord)]
        if not active_only:
            return records
        active = set(self.store.active_ids("invariant"))
        return [record for record in records if record.object_id in active and record.status == "REGISTERED"]

    def validate(self, invariant_id: str, success: bool, evidence_ids: Iterable[str]) -> str:
        invariant = self.store.get(invariant_id)
        if not isinstance(invariant, InvariantRecord):
            raise EGCFError(f"not an invariant: {invariant_id}")
        record = InvariantRecord(
            **{
                **invariant.to_dict(),
                "status": "VALIDATED" if success else "CONFLICTED",
                "evidence_ids": list(dict.fromkeys([*invariant.evidence_ids, *evidence_ids])),
                "created_at": utc_now(),
                "supersedes": invariant_id,
            }
        )
        new_id = self.store.register(record)
        self.store.supersede(invariant_id, new_id, "invariant validation result", "deterministic validator")
        return new_id

    def conflicts(self) -> list[Dict[str, Any]]:
        records = self.records(active_only=True)
        conflicts: list[Dict[str, Any]] = []
        for index, left in enumerate(records):
            for right in records[index + 1 :]:
                same_name_different = left.name == right.name and _normalize_statement(left.statement) != _normalize_statement(right.statement)
                if _scope_overlap(left.scope, right.scope) and (same_name_different or _opposites(left.statement, right.statement)):
                    conflicts.append(
                        {
                            "left": left.object_id,
                            "right": right.object_id,
                            "reason": "active invariant statements conflict in overlapping scope",
                        }
                    )
        return conflicts

    def supersede(self, old_id: str, new_record: InvariantRecord, reason: str, authority: str) -> str:
        if not authority:
            raise EGCFError("invariant supersedence requires authority")
        new_record.supersedes = old_id
        new_id = self.store.register(new_record)
        self.store.supersede(old_id, new_id, reason, authority)
        return new_id
