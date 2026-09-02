from __future__ import annotations

from pathlib import Path

from .base import ProviderConfig


QWEN38_DIRECT_MODEL_ID = "qwen3.8-27b-direct"
QWEN38_Q2_K_MODEL_PATH = str(
    Path(__file__).resolve().parents[2].parent / "Neuro-llama" / "Qwen3.8-27B-Q2_K.gguf"
)
QWEN38_Q2_K_SHA256 = "028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9"


def qwen38_direct_config(
    *,
    runner_path: str,
    llama_cpp_root: str,
    llama_cpp_build_dir: str,
    model_path: str = QWEN38_Q2_K_MODEL_PATH,
    llama_grammar_dir: str = "",
    context_tokens: int = 8192,
    max_output_tokens: int = 2048,
    context_budget_tokens: int = 6000,
    timeout_seconds: float = 600.0,
    gpu_layers: int = -1,
    threads: int = 0,
    seed: int = 1234,
    temperature_bp: int = 1000,
    top_p_bp: int = 9500,
    top_k: int = 40,
) -> ProviderConfig:
    return ProviderConfig(
        model=QWEN38_DIRECT_MODEL_ID,
        provider_kind="llama_cpp_process",
        max_output_tokens=max_output_tokens,
        context_budget_tokens=context_budget_tokens,
        runtime_context_tokens=context_tokens,
        timeout_seconds=timeout_seconds,
        max_transport_retries=0,
        runner_path=runner_path,
        model_path=model_path,
        expected_model_sha256=QWEN38_Q2_K_SHA256,
        llama_cpp_root=llama_cpp_root,
        llama_cpp_build_dir=llama_cpp_build_dir,
        llama_grammar_dir=llama_grammar_dir,
        llama_context_tokens=context_tokens,
        llama_gpu_layers=gpu_layers,
        llama_threads=threads,
        llama_seed=seed,
        llama_temperature_bp=temperature_bp,
        llama_top_p_bp=top_p_bp,
        llama_top_k=top_k,
    )


__all__ = [
    "QWEN38_DIRECT_MODEL_ID",
    "QWEN38_Q2_K_MODEL_PATH",
    "QWEN38_Q2_K_SHA256",
    "qwen38_direct_config",
]
