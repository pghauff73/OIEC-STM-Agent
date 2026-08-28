from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Mapping


QUANTIZATION_PATTERN = re.compile(r"(?i)(?:^|[-_:])(q\d(?:_[a-z0-9]+)*)")


@dataclass(frozen=True)
class ModelBackendInfo:
    provider: str
    backend: str
    model: str
    base_url: str
    quantization: str
    context_tokens: int
    latency: str
    memory: str
    device_residency: str
    health: str
    provenance: str
    authoritative: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def model_backend_info(
    *,
    model: str,
    base_url: str,
    context_tokens: int,
    environment: Mapping[str, str] | None = None,
) -> ModelBackendInfo:
    env = environment or os.environ
    lowered = base_url.casefold()
    if "11434" in lowered or "ollama" in lowered:
        backend = "Local Ollama / OpenAI-compatible"
    elif base_url:
        backend = "OpenAI-compatible endpoint"
    else:
        backend = "OpenAI Responses"
    match = QUANTIZATION_PATTERN.search(model)
    quantization = env.get("OURD_MODEL_QUANTIZATION", "") or (
        match.group(1).upper() if match else "unknown"
    )
    return ModelBackendInfo(
        provider="openai_responses",
        backend=backend,
        model=model,
        base_url=base_url or "provider default",
        quantization=quantization,
        context_tokens=max(1, int(context_tokens)),
        latency=env.get("OURD_MODEL_LATENCY", "not measured"),
        memory=env.get("OURD_MODEL_MEMORY", "not measured"),
        device_residency=env.get("OURD_MODEL_DEVICE", "not measured"),
        health="not checked",
        provenance="CLI arguments and process environment",
        authoritative=False,
    )
