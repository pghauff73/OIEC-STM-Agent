from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol


LocalModelStreamCallback = Callable[[str], bool]


class LocalModelStatus(str, Enum):
    OK = "ok"
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CONTEXT_OVERFLOW = "context_overflow"
    UNSUPPORTED_CONTRACT = "unsupported_contract"
    INVALID_OUTPUT = "invalid_output"
    PROVIDER_ERROR = "provider_error"

    @classmethod
    def parse(cls, value: Any) -> "LocalModelStatus":
        try:
            return cls(str(value))
        except ValueError:
            return cls.PROVIDER_ERROR


@dataclass(frozen=True)
class LocalModelCompletionOptions:
    max_tokens: int = 2048
    max_attempts: int = 1
    temperature_bp: int = 1000
    top_p_bp: int = 9500
    top_k: int = 40
    seed: int = 1234
    max_elapsed_ms: int = 600_000
    prompt_chunk_tokens: int = 512
    n_threads: int = 0
    n_threads_batch: int = 0
    response_prefix: str = ""
    grammar: str = "oiec_reasoning_response"
    json_schema: str = ""
    grammar_first: bool = True
    use_chat_template: bool = True

    def __post_init__(self) -> None:
        if int(self.max_tokens) < 1:
            raise ValueError("local-model max_tokens must be positive")
        if int(self.max_attempts) != 1:
            raise ValueError("OIEC local-model calls permit exactly one attempt")
        if not 0 <= int(self.temperature_bp) <= 20_000:
            raise ValueError("local-model temperature must be 0..20000 basis points")
        if not 0 <= int(self.top_p_bp) <= 10_000:
            raise ValueError("local-model top_p must be 0..10000 basis points")
        if int(self.top_k) < 1:
            raise ValueError("local-model top_k must be positive")
        if int(self.max_elapsed_ms) < 1:
            raise ValueError("local-model deadline must be positive")
        if int(self.prompt_chunk_tokens) < 1:
            raise ValueError("local-model prompt chunk size must be positive")


@dataclass(frozen=True)
class LocalModelMetrics:
    attempts_used: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    tokenize_ms: int = 0
    context_reset_ms: int = 0
    prompt_decode_ms: int = 0
    decode_ms: int = 0
    first_token_ms: int = -1
    total_ms: int = 0
    timed_out: bool = False
    cancelled: bool = False
    no_first_token: bool = False
    timed_out_stage: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "LocalModelMetrics":
        values = dict(payload or {})
        integer_fields = {
            "attempts_used": 1,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "tokenize_ms": 0,
            "context_reset_ms": 0,
            "prompt_decode_ms": 0,
            "decode_ms": 0,
            "first_token_ms": -1,
            "total_ms": 0,
        }
        normalized = {}
        for name, default in integer_fields.items():
            try:
                normalized[name] = int(values.get(name, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid local-model metric: {name}") from exc
        for name in (
            "attempts_used",
            "prompt_tokens",
            "output_tokens",
            "tokenize_ms",
            "context_reset_ms",
            "prompt_decode_ms",
            "decode_ms",
            "total_ms",
        ):
            if normalized[name] < 0:
                raise ValueError(f"local-model metric cannot be negative: {name}")
        if normalized["first_token_ms"] < -1:
            raise ValueError("local-model first_token_ms cannot be less than -1")
        return cls(
            **normalized,
            timed_out=bool(values.get("timed_out", False)),
            cancelled=bool(values.get("cancelled", False)),
            no_first_token=bool(values.get("no_first_token", False)),
            timed_out_stage=str(values.get("timed_out_stage", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts_used": self.attempts_used,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "tokenize_ms": self.tokenize_ms,
            "context_reset_ms": self.context_reset_ms,
            "prompt_decode_ms": self.prompt_decode_ms,
            "decode_ms": self.decode_ms,
            "first_token_ms": self.first_token_ms,
            "total_ms": self.total_ms,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "no_first_token": self.no_first_token,
            "timed_out_stage": self.timed_out_stage,
        }


@dataclass(frozen=True)
class LocalModelDescriptor:
    provider_id: str
    model_path: str
    context_tokens: int
    supports_json_grammar: bool = False
    supports_chat_template: bool = False
    supports_gpu_offload: bool = False
    requested_gpu_layers: int = 0
    accelerator_device: str = ""
    model_id: str = ""
    model_digest: str = ""
    provider_version: str = ""
    backend_build_id: str = ""
    supports_json_schema: bool = False
    supports_cancellation: bool = False
    supports_deadline: bool = False
    supports_streaming: bool = False
    identity_signature: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LocalModelDescriptor":
        values = dict(payload)
        backend_devices = values.get("backend_devices")
        accelerator_device = ""
        if isinstance(backend_devices, list):
            accelerator_device = ", ".join(str(item) for item in backend_devices if item)
        return cls(
            provider_id=str(values.get("provider", values.get("runner", ""))),
            model_path=str(values.get("model_path", "")),
            context_tokens=int(values.get("context_tokens", 0)),
            supports_json_grammar=bool(
                values.get("supports_json_grammar", values.get("supports_grammar", False))
            ),
            supports_chat_template=bool(values.get("supports_chat_template", False)),
            supports_gpu_offload=bool(
                values.get("supports_gpu_offload", int(values.get("gpu_layers", 0)) != 0)
            ),
            requested_gpu_layers=int(values.get("gpu_layers", 0)),
            accelerator_device=str(values.get("accelerator_device", accelerator_device)),
            model_id=str(values.get("model", values.get("model_name", ""))),
            model_digest=str(values.get("model_digest", "")),
            provider_version=str(values.get("runner_version", values.get("protocol_version", ""))),
            backend_build_id=str(values.get("identity_signature", "")),
            supports_json_schema=bool(values.get("supports_json_schema", False)),
            supports_cancellation=bool(
                values.get("supports_cancellation", values.get("supports_cancel_operation", False))
            ),
            supports_deadline=bool(values.get("supports_deadline", False)),
            supports_streaming=bool(values.get("supports_streaming", False)),
            identity_signature=str(values.get("identity_signature", "")),
            metadata=values,
        )


@dataclass(frozen=True)
class LocalModelRequest:
    prompt: str
    options: LocalModelCompletionOptions = field(default_factory=LocalModelCompletionOptions)
    require_json_object: bool = True
    stream_callback: LocalModelStreamCallback | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            raise ValueError("local-model prompt must be non-empty")


@dataclass(frozen=True)
class LocalModelResult:
    status: LocalModelStatus = LocalModelStatus.PROVIDER_ERROR
    text: str = ""
    raw_output: str = ""
    diagnostic: str = ""
    metrics: LocalModelMetrics = field(default_factory=LocalModelMetrics)
    request_id: str = ""
    response: Mapping[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status is LocalModelStatus.OK


class LocalModelAdapter(Protocol):
    def descriptor(self) -> LocalModelDescriptor:
        ...

    def complete_local(self, request: LocalModelRequest) -> LocalModelResult:
        ...

    def cancel(self, request_id: str = "") -> None:
        ...


__all__ = [
    "LocalModelAdapter",
    "LocalModelCompletionOptions",
    "LocalModelDescriptor",
    "LocalModelMetrics",
    "LocalModelRequest",
    "LocalModelResult",
    "LocalModelStatus",
    "LocalModelStreamCallback",
]
