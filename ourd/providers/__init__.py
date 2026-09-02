from .base import ModelProvider, ProviderConfig
from .llama_cpp_process import LlamaCppProcessProvider
from .local_model import (
    LocalModelAdapter,
    LocalModelCompletionOptions,
    LocalModelDescriptor,
    LocalModelMetrics,
    LocalModelRequest,
    LocalModelResult,
    LocalModelStatus,
)
from .qwen38 import (
    QWEN38_DIRECT_MODEL_ID,
    QWEN38_Q2_K_MODEL_PATH,
    QWEN38_Q2_K_SHA256,
    qwen38_direct_config,
)


def create_provider(config: ProviderConfig) -> ModelProvider:
    if config.provider_kind == "llama_cpp_process":
        return LlamaCppProcessProvider(config)
    raise ValueError(f"unsupported provider kind: {config.provider_kind}")


__all__ = [
    "LlamaCppProcessProvider",
    "LocalModelAdapter",
    "LocalModelCompletionOptions",
    "LocalModelDescriptor",
    "LocalModelMetrics",
    "LocalModelRequest",
    "LocalModelResult",
    "LocalModelStatus",
    "ModelProvider",
    "ProviderConfig",
    "QWEN38_DIRECT_MODEL_ID",
    "QWEN38_Q2_K_MODEL_PATH",
    "QWEN38_Q2_K_SHA256",
    "create_provider",
    "qwen38_direct_config",
]
