from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ourd.providers.qwen38 import QWEN38_DIRECT_MODEL_ID


QWEN38_FAST_PRODUCT_ALIAS = "qwen3.8:27B-Fast"


class QwenBootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class QwenBootstrapResult:
    requested_model: str
    resolved_model: str
    model_digest: str
    model_size: int
    ollama_version: str
    service_started: bool
    warmed: bool
    resident: bool
    size_vram: int
    log_path: str
    product_alias: str = QWEN38_FAST_PRODUCT_ALIAS
    authoritative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_qwen_model(value: str) -> str:
    model = value.strip()
    if model.casefold() == QWEN38_FAST_PRODUCT_ALIAS.casefold():
        return QWEN38_DIRECT_MODEL_ID
    return model


def ensure_qwen38_fast(
    *,
    requested_model: str = QWEN38_FAST_PRODUCT_ALIAS,
    runner_path: str = "",
    model_path: str = "",
    expected_model_sha256: str = "",
    warm: bool = True,
    **deprecated_service_arguments: Any,
) -> QwenBootstrapResult:
    del deprecated_service_arguments
    resolved_model = canonical_qwen_model(requested_model)
    if resolved_model != QWEN38_DIRECT_MODEL_ID:
        raise QwenBootstrapError(
            "automatic direct Qwen profile requires the exact product alias"
        )
    if runner_path:
        runner = Path(runner_path).expanduser().resolve()
        if not runner.is_file():
            raise QwenBootstrapError(f"direct Qwen runner is missing: {runner}")
    model_size = 0
    observed_digest = ""
    if model_path:
        model = Path(model_path).expanduser().resolve()
        if not model.is_file():
            raise QwenBootstrapError(f"direct Qwen GGUF is missing: {model}")
        observed_digest = sha256_file(model)
        model_size = model.stat().st_size
        expected = expected_model_sha256.strip().lower()
        if expected and observed_digest != expected:
            raise QwenBootstrapError(
                f"direct Qwen GGUF digest mismatch: expected {expected}, observed {observed_digest}"
            )
    return QwenBootstrapResult(
        requested_model=requested_model,
        resolved_model=resolved_model,
        model_digest=observed_digest or expected_model_sha256,
        model_size=model_size,
        ollama_version="not_applicable",
        service_started=False,
        warmed=False,
        resident=bool(runner_path and model_path),
        size_vram=0,
        log_path="",
        authoritative=False,
    )


__all__ = [
    "QWEN38_DIRECT_MODEL_ID",
    "QWEN38_FAST_PRODUCT_ALIAS",
    "QwenBootstrapError",
    "QwenBootstrapResult",
    "canonical_qwen_model",
    "ensure_qwen38_fast",
    "sha256_file",
]
