from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class ExecutorAdapter(ABC):
    name = "executor"
    version = "1"

    def capability_contract(
        self,
        *,
        input_schema: Dict[str, Any],
        side_effects: list[str],
        idempotency: str,
        data_boundary: str,
        rollback: str,
    ) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "input_schema": input_schema,
            "side_effects": side_effects,
            "idempotency": idempotency,
            "data_boundary": data_boundary,
            "rollback": rollback,
        }

    @abstractmethod
    def describe_capabilities(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
