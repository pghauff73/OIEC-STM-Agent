from __future__ import annotations

import itertools
from typing import Any, Dict, Iterable

from .errors import EGCFError


class ExperimentDesigner:
    MAX_COMBINATIONS = 10000

    @staticmethod
    def _validate(parameters: Dict[str, list[Any]]) -> None:
        if not parameters:
            raise EGCFError("experiment parameters cannot be empty")
        if len(parameters) > 10:
            raise EGCFError("at most 10 experiment dimensions are supported")
        for name, values in parameters.items():
            if not name or not values:
                raise EGCFError("experiment dimensions require names and values")
            if len(values) > 20:
                raise EGCFError(f"dimension {name} exceeds 20 values")

    def factorial(self, parameters: Dict[str, list[Any]]) -> list[Dict[str, Any]]:
        self._validate(parameters)
        names = list(parameters)
        count = 1
        for values in parameters.values():
            count *= len(values)
        if count > self.MAX_COMBINATIONS:
            raise EGCFError(f"factorial design exceeds {self.MAX_COMBINATIONS} combinations")
        return [dict(zip(names, values)) for values in itertools.product(*(parameters[name] for name in names))]

    def ofat(self, baseline: Dict[str, Any], parameters: Dict[str, list[Any]]) -> list[Dict[str, Any]]:
        self._validate(parameters)
        rows = [dict(baseline)]
        for name, values in parameters.items():
            for value in values:
                if baseline.get(name) == value:
                    continue
                row = dict(baseline)
                row[name] = value
                rows.append(row)
        return rows

    def covering(self, parameters: Dict[str, list[Any]], strength: int = 2) -> list[Dict[str, Any]]:
        self._validate(parameters)
        if strength != 2:
            raise EGCFError("v1 covering arrays support pairwise strength=2")
        rows = self.factorial(parameters)
        names = list(parameters)
        required_pairs = {
            (left, row[left], right, row[right])
            for row in rows
            for left_index, left in enumerate(names)
            for right in names[left_index + 1 :]
        }
        selected: list[Dict[str, Any]] = []
        remaining = list(rows)
        while required_pairs:
            best_row = max(
                remaining,
                key=lambda row: sum(
                    (left, row[left], right, row[right]) in required_pairs
                    for left_index, left in enumerate(names)
                    for right in names[left_index + 1 :]
                ),
            )
            selected.append(best_row)
            remaining.remove(best_row)
            for left_index, left in enumerate(names):
                for right in names[left_index + 1 :]:
                    required_pairs.discard((left, best_row[left], right, best_row[right]))
        return selected

    @staticmethod
    def analyse(results: Iterable[Dict[str, Any]], outcome: str) -> Dict[str, Any]:
        rows = list(results)
        values = [row[outcome] for row in rows if isinstance(row.get(outcome), (int, float))]
        if not values:
            return {"count": len(rows), "numeric_count": 0, "outcome": outcome}
        return {
            "count": len(rows),
            "numeric_count": len(values),
            "outcome": outcome,
            "minimum": min(values),
            "maximum": max(values),
            "mean": sum(values) / len(values),
        }
