from __future__ import annotations

import hashlib
import json
import os
import select
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

from ..context_budget import effective_input_budget, estimate_tokens
from ..errors import ContextBudgetError, ProviderError
from .base import ProviderConfig
from .local_model import (
    LocalModelCompletionOptions,
    LocalModelDescriptor,
    LocalModelMetrics,
    LocalModelRequest,
    LocalModelResult,
    LocalModelStatus,
)
PROTOCOL_VERSION = 1
FINAL_EVENT_TYPES = {"result", "error", "cancelled"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(path: Path, *, base: Path | None = None) -> Dict[str, Any]:
    resolved = path.resolve()
    display = str(resolved)
    if base is not None:
        try:
            display = str(resolved.relative_to(base.resolve()))
        except ValueError:
            pass
    return {
        "path": display,
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _git_source_identity(root: Path) -> Dict[str, Any]:
    if not root.is_dir():
        raise ProviderError(f"llama.cpp source root is missing: {root}")
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status_lines = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProviderError(f"cannot identify llama.cpp source tree: {root}") from exc
    canonical_status = tuple(sorted(status_lines))
    return {
        "root": str(root.resolve()),
        "commit": commit,
        "dirty": bool(canonical_status),
        "status_sha256": hashlib.sha256(
            canonical_json(canonical_status).encode("utf-8")
        ).hexdigest(),
    }


def _build_identity(build_root: Path) -> Dict[str, Any]:
    binary_dir = build_root.resolve() / "bin"
    if not binary_dir.is_dir():
        raise ProviderError(f"llama.cpp build binary directory is missing: {binary_dir}")
    resolved_libraries: Dict[str, Path] = {}
    for pattern in ("libllama.so*", "libggml*.so*"):
        for candidate in binary_dir.glob(pattern):
            if candidate.is_file():
                resolved_libraries[str(candidate.resolve())] = candidate.resolve()
    if not resolved_libraries:
        raise ProviderError(f"llama.cpp shared libraries are missing: {binary_dir}")
    libraries = tuple(
        _file_identity(path, base=build_root)
        for path in sorted(resolved_libraries.values(), key=lambda item: str(item))
    )
    cache = build_root.resolve() / "CMakeCache.txt"
    payload: Dict[str, Any] = {
        "root": str(build_root.resolve()),
        "libraries": libraries,
    }
    if cache.is_file():
        payload["cmake_cache"] = _file_identity(cache, base=build_root)
    payload["signature"] = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return payload


def _stable_runner_descriptor(value: Mapping[str, Any]) -> Dict[str, Any]:
    descriptor = dict(value)
    backend_devices = descriptor.get("backend_devices")
    if isinstance(backend_devices, (list, tuple)):
        stable_devices = []
        for raw_device in backend_devices:
            if not isinstance(raw_device, Mapping):
                raise ProviderError("runner backend device descriptor must be an object")
            device = dict(raw_device)
            device.pop("memory_free", None)
            stable_devices.append(device)
        descriptor["backend_devices"] = stable_devices
    return descriptor


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "arguments") -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise ProviderError(f"{path} must be an object")
        properties = schema.get("properties", {})
        required = schema.get("required", ())
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ProviderError(f"{path} schema is malformed")
        missing = [name for name in required if name not in value]
        if missing:
            raise ProviderError(f"{path} is missing required fields: {missing!r}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ProviderError(f"{path} has unknown fields: {unknown!r}")
        for name, item in value.items():
            child = properties.get(name)
            if isinstance(child, dict):
                _validate_schema(item, child, f"{path}.{name}")
        return
    if schema_type == "array":
        if not isinstance(value, list):
            raise ProviderError(f"{path} must be an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")
        return
    expected = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }.get(schema_type)
    if expected is not None and (not isinstance(value, expected) or schema_type == "integer" and isinstance(value, bool)):
        raise ProviderError(f"{path} must be {schema_type}")
    if "enum" in schema and value not in schema["enum"]:
        raise ProviderError(f"{path} is outside the allowed enum")


class LlamaCppProcessProvider:
    reasoning_role_batch_size = 2

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._sequence = 0
        self._stderr_lines: deque[str] = deque(maxlen=512)
        self._stderr_thread: threading.Thread | None = None
        self._active_request_id: str | None = None
        self._cancelled_request_id: str | None = None
        self._last_completion_request_sent = False

    @property
    def last_completion_request_sent(self) -> bool:
        return self._last_completion_request_sent

    def _start_stderr_drain(self, process: subprocess.Popen[str]) -> None:
        self._stderr_lines.clear()

        def drain() -> None:
            stream = process.stderr
            if stream is None:
                return
            try:
                for line in stream:
                    self._stderr_lines.append(line.rstrip("\n"))
            except (OSError, ValueError):
                return

        thread = threading.Thread(
            target=drain,
            name="oiec-llama-stderr",
            daemon=True,
        )
        self._stderr_thread = thread
        thread.start()

    def _stderr_diagnostic(self) -> str:
        return "\n".join(self._stderr_lines)[-65536:].strip()

    def _dispose_process(
        self,
        process: subprocess.Popen[str],
        *,
        terminate: bool = False,
    ) -> None:
        if terminate and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        thread = self._stderr_thread
        if thread is not None:
            thread.join(timeout=1.0)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._stderr_thread = None
        if self._process is process:
            self._process = None

    def close(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            if process is None:
                return
            try:
                if process.poll() is None:
                    self._write_line(process, {"op": "shutdown", "request_id": "shutdown"})
                    process.wait(timeout=2.0)
            except (OSError, subprocess.SubprocessError):
                self._dispose_process(process, terminate=True)
                return
            self._dispose_process(process)

    def __enter__(self) -> "LlamaCppProcessProvider":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _runner_command(self) -> list[str]:
        if not self.config.runner_path:
            raise ProviderError("llama.cpp process provider requires runner_path")
        if not self.config.model_path:
            raise ProviderError("llama.cpp process provider requires model_path")
        grammar_dir = self.config.llama_grammar_dir or str(
            Path(__file__).resolve().parents[2] / "grammars" / "providers"
        )
        return [
            self.config.runner_path,
            "--model",
            self.config.model_path,
            "--context",
            str(max(256, int(self.config.llama_context_tokens))),
            "--gpu-layers",
            str(int(self.config.llama_gpu_layers)),
            "--threads",
            str(max(0, int(self.config.llama_threads))),
            "--grammar-dir",
            grammar_dir,
        ]

    def _ensure_process(self) -> subprocess.Popen[str]:
        process = self._process
        if process is not None and process.poll() is None:
            return process
        environment = dict(os.environ)
        if self.config.llama_cpp_build_dir:
            library_dir = str(Path(self.config.llama_cpp_build_dir).resolve() / "bin")
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(
                value for value in (library_dir, environment.get("LD_LIBRARY_PATH", "")) if value
            )
        try:
            process = subprocess.Popen(
                self._runner_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=environment,
            )
        except OSError as exc:
            raise ProviderError(f"cannot launch llama.cpp runner: {exc}") from exc
        if process.stdin is None or process.stdout is None:
            process.kill()
            raise ProviderError("llama.cpp runner pipes are unavailable")
        self._process = process
        self._start_stderr_drain(process)
        return process

    @staticmethod
    def _write_line(process: subprocess.Popen[str], payload: Mapping[str, Any]) -> None:
        if process.stdin is None:
            raise ProviderError("llama.cpp runner stdin is unavailable")
        process.stdin.write(canonical_json(payload) + "\n")
        process.stdin.flush()

    def _next_request_id(self, operation: str, material: Mapping[str, Any]) -> str:
        self._sequence += 1
        digest = hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()[:20]
        return f"{operation}-{self._sequence}-{digest}"

    def _request(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        stream_callback: Callable[[str], bool] | None = None,
    ) -> Dict[str, Any]:
        with self._lock:
            process = self._ensure_process()
            request_id = self._next_request_id(operation, payload)
            self._active_request_id = request_id
            try:
                request = {
                    "protocol_version": PROTOCOL_VERSION,
                    "op": operation,
                    "request_id": request_id,
                    **dict(payload),
                }
                self._write_line(process, request)
                if operation == "complete":
                    self._last_completion_request_sent = True
                deadline = time.monotonic() + max(1.0, float(self.config.timeout_seconds))
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._dispose_process(process, terminate=True)
                        diagnostic = self._stderr_diagnostic()
                        raise ProviderError(
                            "llama.cpp runner deadline exceeded"
                            + (f": {diagnostic}" if diagnostic else "")
                        )
                    if process.stdout is None:
                        raise ProviderError("llama.cpp runner stdout is unavailable")
                    ready, _, _ = select.select([process.stdout], [], [], remaining)
                    if not ready:
                        continue
                    line = process.stdout.readline()
                    if not line:
                        cancelled = self._cancelled_request_id == request_id
                        try:
                            process.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            self._dispose_process(process, terminate=True)
                        else:
                            self._dispose_process(process)
                        if cancelled:
                            self._cancelled_request_id = None
                            raise ProviderError("llama.cpp request cancelled")
                        diagnostic = self._stderr_diagnostic()
                        raise ProviderError(
                            "llama.cpp runner exited before a result"
                            + (f": {diagnostic}" if diagnostic else "")
                        )
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ProviderError(f"llama.cpp runner returned invalid JSON: {exc}") from exc
                    if not isinstance(event, dict):
                        raise ProviderError("llama.cpp runner event must be an object")
                    if event.get("request_id") != request_id:
                        raise ProviderError("llama.cpp runner response identity mismatch")
                    if event.get("type") == "stream":
                        if stream_callback is not None:
                            chunk = event.get("text", "")
                            if not isinstance(chunk, str):
                                raise ProviderError("llama.cpp stream event text must be a string")
                            try:
                                keep_streaming = bool(stream_callback(chunk))
                            except Exception as exc:
                                self._dispose_process(process, terminate=True)
                                raise ProviderError(
                                    f"llama.cpp stream callback failed: {exc}"
                                ) from exc
                            if not keep_streaming:
                                self._cancelled_request_id = request_id
                                self._dispose_process(process, terminate=True)
                                self._cancelled_request_id = None
                                return {
                                    "protocol_version": PROTOCOL_VERSION,
                                    "type": "cancelled",
                                    "request_id": request_id,
                                    "status": "cancelled",
                                    "diagnostic": "stream callback requested cancellation",
                                    "metrics": {
                                        "attempts_used": 1,
                                        "cancelled": True,
                                        "no_first_token": False,
                                    },
                                }
                        continue
                    if event.get("type") not in FINAL_EVENT_TYPES:
                        raise ProviderError("llama.cpp runner returned an unknown event type")
                    return event
            finally:
                if self._active_request_id == request_id:
                    self._active_request_id = None

    def preflight(self) -> Dict[str, Any]:
        model_path = Path(self.config.model_path).expanduser().resolve()
        if not model_path.is_file():
            raise ProviderError(f"GGUF model is missing: {model_path}")
        observed_digest = sha256_file(model_path)
        expected = self.config.expected_model_sha256.strip().lower()
        if expected and observed_digest != expected:
            raise ProviderError(
                f"GGUF digest mismatch: expected {expected}, observed {observed_digest}"
            )
        if not self.config.llama_cpp_root:
            raise ProviderError("llama.cpp process provider requires llama_cpp_root")
        if not self.config.llama_cpp_build_dir:
            raise ProviderError("llama.cpp process provider requires llama_cpp_build_dir")
        source_identity = _git_source_identity(
            Path(self.config.llama_cpp_root).expanduser().resolve()
        )
        build_identity = _build_identity(
            Path(self.config.llama_cpp_build_dir).expanduser().resolve()
        )
        runner_identity = _file_identity(
            Path(self.config.runner_path).expanduser().resolve()
        )
        grammar_dir = Path(
            self.config.llama_grammar_dir
            or Path(__file__).resolve().parents[2] / "grammars" / "providers"
        ).expanduser().resolve()
        grammar_identity = tuple(
            _file_identity(grammar_dir / f"{name}.gbnf", base=grammar_dir)
            for name in (
                "oiec_compact_tool_response",
                "oiec_reasoning_response",
                "oiec_tool_response",
            )
        )
        event = self._request("describe", {})
        if event.get("status") != "ok" or not isinstance(event.get("descriptor"), dict):
            raise ProviderError(str(event.get("diagnostic") or "runner describe failed"))
        descriptor = _stable_runner_descriptor(event["descriptor"])
        descriptor.update(
            {
                "status": "ready",
                "provider": "llama_cpp_process",
                "model": self.config.model,
                "model_path": str(model_path),
                "model_digest": observed_digest,
                "model_file_size": model_path.stat().st_size,
                "max_transport_retries": 0,
                "max_reasoning_samples": self.config.max_reasoning_samples,
                "context_budget_tokens": self.config.context_budget_tokens,
                "runtime_context_tokens": (
                    self.config.runtime_context_tokens or self.config.llama_context_tokens
                ),
                "context_safety_margin_tokens": self.config.context_safety_margin_tokens,
                "max_output_tokens": self.config.max_output_tokens,
                "protocol_version": PROTOCOL_VERSION,
                "supports_cancellation": True,
                "supports_deadline": True,
                "supports_json_grammar": True,
                "runner_identity": runner_identity,
                "llama_cpp_source": source_identity,
                "llama_cpp_build": build_identity,
                "grammar_identity": grammar_identity,
                "sampling_contract": {
                    "seed": int(self.config.llama_seed),
                    "temperature_bp": int(self.config.llama_temperature_bp),
                    "top_p_bp": int(self.config.llama_top_p_bp),
                    "top_k": int(self.config.llama_top_k),
                    "context_tokens": int(self.config.llama_context_tokens),
                    "gpu_layers": int(self.config.llama_gpu_layers),
                    "threads": int(self.config.llama_threads),
                    "max_output_tokens": int(self.config.max_output_tokens),
                },
            }
        )
        descriptor["identity_signature"] = hashlib.sha256(
            canonical_json(descriptor).encode("utf-8")
        ).hexdigest()
        return descriptor

    def descriptor(self) -> LocalModelDescriptor:
        return LocalModelDescriptor.from_mapping(self.preflight())

    def complete_local(self, request: LocalModelRequest) -> LocalModelResult:
        options = request.options
        if options.max_attempts != 1:
            raise ProviderError("OIEC local-model calls permit exactly one attempt")
        if options.json_schema:
            return LocalModelResult(
                status=LocalModelStatus.UNSUPPORTED_CONTRACT,
                diagnostic="native runner does not accept arbitrary JSON schemas",
            )
        if not options.grammar_first:
            return LocalModelResult(
                status=LocalModelStatus.UNSUPPORTED_CONTRACT,
                diagnostic="native runner requires grammar-first sampling",
            )
        estimated = estimate_tokens(request.prompt)
        effective_budget = effective_input_budget(
            configured_input_budget_tokens=self.config.context_budget_tokens,
            runtime_context_tokens=(
                self.config.runtime_context_tokens or self.config.llama_context_tokens
            ),
            reserved_output_tokens=options.max_tokens,
            safety_margin_tokens=self.config.context_safety_margin_tokens,
        )
        if estimated > effective_budget:
            raise ContextBudgetError(
                "provider input exceeds configured context budget: "
                f"estimated {estimated}, budget {effective_budget}"
            )
        event = self._request(
            "complete",
            {
                "prompt": request.prompt,
                "context_tokens": max(256, int(self.config.llama_context_tokens)),
                "max_output_tokens": max(1, int(options.max_tokens)),
                "deadline_ms": max(1, int(options.max_elapsed_ms)),
                "seed": int(options.seed),
                "temperature": max(0, int(options.temperature_bp)) / 10_000.0,
                "top_p": max(0, int(options.top_p_bp)) / 10_000.0,
                "top_k": max(1, int(options.top_k)),
                "grammar": options.grammar,
                "use_chat_template": bool(options.use_chat_template),
            },
            stream_callback=request.stream_callback,
        )
        status = LocalModelStatus.parse(event.get("status", "provider_error"))
        metrics_payload = event.get("metrics")
        if metrics_payload is not None and not isinstance(metrics_payload, dict):
            raise ProviderError("llama.cpp completion metrics must be an object")
        try:
            metrics = LocalModelMetrics.from_mapping(metrics_payload)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc
        response = event.get("response")
        text = event.get("text", "")
        if not isinstance(text, str):
            raise ProviderError("llama.cpp completion text must be a string")
        if response is not None and not isinstance(response, dict):
            return LocalModelResult(
                status=LocalModelStatus.INVALID_OUTPUT,
                raw_output=text,
                diagnostic="llama.cpp completion response must be an object",
                metrics=metrics,
                request_id=str(event.get("request_id", "")),
            )
        if response is None and text and request.require_json_object:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                response = parsed
        if status is LocalModelStatus.OK and request.require_json_object and not isinstance(response, dict):
            status = LocalModelStatus.INVALID_OUTPUT
        raw_output = text or (canonical_json(response) if isinstance(response, dict) else "")
        return LocalModelResult(
            status=status,
            text=text or raw_output,
            raw_output=raw_output,
            diagnostic=str(event.get("diagnostic", "")),
            metrics=metrics,
            request_id=str(event.get("request_id", "")),
            response=response,
        )

    def _prompt(
        self,
        *,
        instructions: str,
        input_items: Sequence[Any],
        tools: Sequence[Mapping[str, Any]],
    ) -> str:
        contract = {
            "message": {"type": "message", "content": "concise response"},
            "function_call": {
                "type": "function_call",
                "name": "one declared tool name",
                "arguments": {"declared": "arguments"},
                "call_id": "stable-call-id",
            },
        }
        return canonical_json(
            {
                "system": (
                    "Return exactly one JSON object and no markdown. Do not expose private "
                    "chain-of-thought. Select only a declared tool and only when needed."
                ),
                "instructions": instructions,
                "input": list(input_items),
                "tools": list(tools),
                "response_contract": contract,
            }
        )

    @staticmethod
    def _validated_output(payload: Mapping[str, Any], tools: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        output_type = str(payload.get("type", ""))
        if output_type == "message":
            content = payload.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("llama.cpp message content must be non-empty")
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": content.strip()}],
                    }
                ],
                "output_text": content.strip(),
            }
        if output_type != "function_call":
            raise ProviderError("llama.cpp output type must be message or function_call")
        name = payload.get("name")
        arguments = payload.get("arguments")
        call_id = payload.get("call_id")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ProviderError("llama.cpp function call is malformed")
        declared = {str(tool.get("name", "")): tool for tool in tools}
        tool = declared.get(name)
        if tool is None:
            raise ProviderError(f"llama.cpp selected undeclared tool: {name!r}")
        parameters = tool.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ProviderError(f"declared tool schema is malformed: {name!r}")
        _validate_schema(arguments, parameters)
        if not isinstance(call_id, str) or not call_id:
            call_id = f"call-{hashlib.sha256(canonical_json([name, arguments]).encode()).hexdigest()[:16]}"
        return {
            "output": [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": canonical_json(arguments),
                    "call_id": call_id,
                }
            ],
            "output_text": "",
        }

    def create_response(
        self,
        *,
        instructions: str,
        input_items: List[Any],
        tools: List[Dict[str, Any]],
    ) -> Any:
        return self.create_reasoning_response(
            instructions=instructions,
            input_items=input_items,
            tools=tools,
            max_output_tokens=max(1, int(self.config.max_output_tokens)),
        )

    def create_reasoning_response(
        self,
        *,
        instructions: str,
        input_items: List[Any],
        tools: List[Dict[str, Any]],
        max_output_tokens: int,
    ) -> Any:
        self._last_completion_request_sent = False
        output_limit = max(1, int(max_output_tokens))
        estimated = estimate_tokens(
            {"instructions": instructions, "input": input_items, "tools": tools}
        )
        effective_budget = effective_input_budget(
            configured_input_budget_tokens=self.config.context_budget_tokens,
            runtime_context_tokens=(
                self.config.runtime_context_tokens or self.config.llama_context_tokens
            ),
            reserved_output_tokens=output_limit,
            safety_margin_tokens=self.config.context_safety_margin_tokens,
        )
        if estimated > effective_budget:
            raise ContextBudgetError(
                "provider input exceeds configured context budget: "
                f"estimated {estimated}, budget {effective_budget}"
            )
        prompt = self._prompt(instructions=instructions, input_items=input_items, tools=tools)
        tool_names = {str(tool.get("name", "")) for tool in tools}
        if tool_names & {
            "submit_oiec_reasoning_batch",
            "submit_oiec_reasoning_object",
        }:
            grammar_name = "oiec_compact_tool_response"
        else:
            grammar_name = "oiec_tool_response" if tools else "oiec_reasoning_response"
        result = self.complete_local(
            LocalModelRequest(
                prompt=prompt,
                options=LocalModelCompletionOptions(
                    max_tokens=output_limit,
                    max_attempts=1,
                    temperature_bp=int(self.config.llama_temperature_bp),
                    top_p_bp=int(self.config.llama_top_p_bp),
                    top_k=int(self.config.llama_top_k),
                    seed=int(self.config.llama_seed),
                    max_elapsed_ms=max(1, int(float(self.config.timeout_seconds) * 1000)),
                    grammar=grammar_name,
                    use_chat_template=True,
                ),
                require_json_object=True,
            )
        )
        if not result.ok:
            generated_text = result.raw_output
            generated_detail = ""
            if generated_text:
                generated_detail = f"; generated={generated_text[:512]!r}"
            raise ProviderError(
                f"llama.cpp completion failed: {result.status.value}: "
                f"{result.diagnostic}{generated_detail}"
            )
        generated = result.response
        if not isinstance(generated, dict):
            text = result.text
            if not text:
                raise ProviderError("llama.cpp completion omitted structured output")
            try:
                generated = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProviderError(f"llama.cpp completion returned invalid JSON: {exc}") from exc
        response = self._validated_output(generated, tools)
        metrics = result.metrics.to_dict()
        input_tokens = result.metrics.prompt_tokens
        output_tokens = result.metrics.output_tokens
        if input_tokens < 1 or output_tokens < 1:
            raise ProviderError("llama.cpp completion omitted positive token usage")
        response["usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        response["temperature"] = (
            max(0, int(self.config.llama_temperature_bp)) / 10_000.0
        )
        response["top_p"] = max(0, int(self.config.llama_top_p_bp)) / 10_000.0
        response["provider_metadata"] = {
            "provider": "llama_cpp_process",
            "request_id": result.request_id,
            "metrics": metrics,
        }
        return response

    def create_responses(
        self,
        *,
        requests: List[Mapping[str, Any]],
        max_responses: int,
    ) -> List[Any]:
        hard_cap = min(
            max(1, int(max_responses)),
            max(1, int(self.config.max_reasoning_samples)),
        )
        if not requests:
            raise ProviderError("multi-response request must be non-empty")
        if len(requests) > hard_cap:
            raise ProviderError(
                f"multi-response request exceeds configured sample cap: {len(requests)} > {hard_cap}"
            )
        responses = []
        for request in requests:
            try:
                requested_output = request.get("max_output_tokens")
                if requested_output is None:
                    responses.append(
                        self.create_response(
                            instructions=str(request.get("instructions", "")),
                            input_items=list(request.get("input_items", [])),
                            tools=list(request.get("tools", [])),
                        )
                    )
                else:
                    responses.append(
                        self.create_reasoning_response(
                            instructions=str(request.get("instructions", "")),
                            input_items=list(request.get("input_items", [])),
                            tools=list(request.get("tools", [])),
                            max_output_tokens=max(1, int(requested_output)),
                        )
                    )
            except (ContextBudgetError, ProviderError) as exc:
                responses.append(
                    {"type": "reasoning_error", "error": f"{type(exc).__name__}: {exc}"}
                )
        return responses

    def reset_context(self) -> None:
        event = self._request("reset_context", {})
        if event.get("status") != "ok":
            raise ProviderError("llama.cpp runner context reset failed")

    def cancel(self, request_id: str = "") -> None:
        process = self._process
        active_request_id = self._active_request_id
        if process is None or process.poll() is not None or active_request_id is None:
            return
        if request_id and request_id != active_request_id:
            raise ProviderError("llama.cpp cancellation target does not match active request")
        self._cancelled_request_id = active_request_id
        process.terminate()
