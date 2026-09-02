from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Protocol


@dataclass
class ProviderConfig:
    model: str
    provider_kind: str = "llama_cpp_process"
    base_url: str = ""
    api_key: str = ""
    reasoning_effort: str = ""
    json_object_output: bool = False
    response_temperature_bp: int = -1
    response_top_p_bp: int = -1
    response_seed: int = -1
    max_output_tokens: int = 2048
    context_budget_tokens: int = 6000
    runtime_context_tokens: int = 0
    context_safety_margin_tokens: int = 512
    timeout_seconds: float = 600.0
    max_transport_retries: int = 0
    max_reasoning_samples: int = 16
    visual_asset_root: str = ""
    runner_path: str = ""
    model_path: str = ""
    expected_model_sha256: str = ""
    llama_cpp_root: str = ""
    llama_cpp_build_dir: str = ""
    llama_grammar_dir: str = ""
    llama_context_tokens: int = 8192
    llama_gpu_layers: int = -1
    llama_threads: int = 0
    llama_seed: int = 1234
    llama_temperature_bp: int = 1000
    llama_top_p_bp: int = 9500
    llama_top_k: int = 40


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
