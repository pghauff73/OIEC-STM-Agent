from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Protocol


@dataclass
class ProviderConfig:
    model: str
    base_url: str = ""
    api_key: str = ""
    reasoning_effort: str = ""
    max_output_tokens: int = 2048
    context_budget_tokens: int = 6000
    timeout_seconds: float = 600.0
    max_transport_retries: int = 0
    visual_asset_root: str = ""
    max_reasoning_samples: int = 16


class ModelProvider(Protocol):
    config: ProviderConfig

    def preflight(self) -> Dict[str, Any]:
        ...

    def create_response(
        self,
        *,
        instructions: str,
        input_items: List[Any],
        tools: List[Dict[str, Any]],
    ) -> Any:
        ...

    def create_responses(
        self,
        *,
        requests: List[Mapping[str, Any]],
        max_responses: int,
    ) -> List[Any]:
        ...
