from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

from ourd.errors import ContextBudgetError, ProviderError
from ourd.providers import (
    LocalModelCompletionOptions,
    LocalModelRequest,
    LocalModelStatus,
    ProviderConfig,
    QWEN38_DIRECT_MODEL_ID,
    QWEN38_Q2_K_SHA256,
    create_provider,
    qwen38_direct_config,
)
from ourd.providers.llama_cpp_process import LlamaCppProcessProvider, sha256_file
from ourd.reasoning.generator import reasoning_object_tool


FAKE_RUNNER = r'''#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--model")
parser.add_argument("--context")
parser.add_argument("--gpu-layers")
parser.add_argument("--threads")
parser.add_argument("--grammar-dir")
args = parser.parse_args()
counter = pathlib.Path(args.model + ".attempts")

if pathlib.Path(args.model).name.startswith("oom"):
    print("ggml_cuda_compute_forward: NV_ERR_NO_MEMORY", file=sys.stderr, flush=True)
    raise SystemExit(1)

if pathlib.Path(args.model).name.startswith("noisy"):
    for _ in range(512):
        print("llama.cpp diagnostic " + ("x" * 1024), file=sys.stderr, flush=True)

for line in sys.stdin:
    request = json.loads(line)
    request_id = request["request_id"]
    operation = request["op"]
    response = {
        "protocol_version": 1,
        "type": "result",
        "request_id": request_id,
        "status": "ok",
    }
    if operation == "describe":
        response["descriptor"] = {
            "runner": "fake-oiec-llama-runner",
            "model_architecture": "qwen3.8",
            "parameter_count": 27000000000,
            "quantization": "Q2_K",
            "context_tokens": int(args.context),
            "gpu_layers": int(args.gpu_layers),
            "supports_grammar": True,
            "supports_chat_template": True,
            "supports_streaming": True,
            "supports_deadline": True,
            "fresh_context_per_completion": True,
            "backend_devices": [
                {
                    "index": 0,
                    "name": "fake-gpu",
                    "device_id": "GPU-stable",
                    "memory_free": os.getpid(),
                    "memory_total": 16000000000,
                }
            ],
        }
    elif operation == "complete":
        attempts = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(attempts))
        prompt = request["prompt"]
        if "STREAM_CANCEL" in prompt:
            print(json.dumps({
                "protocol_version": 1,
                "type": "stream",
                "request_id": request_id,
                "status": "ok",
                "text": "{",
            }), flush=True)
            time.sleep(10)
        if "SLOW" in prompt:
            time.sleep(10)
        if "FORCE_ERROR" in prompt:
            response["status"] = "invalid_output"
            response["diagnostic"] = "forced failure"
            response["text"] = "{\"partial\""
        elif "UNKNOWN_TOOL" in prompt:
            response["response"] = {
                "type": "function_call",
                "name": "not_declared",
                "arguments": {},
            }
        elif "submit_oiec_reasoning_object" in prompt:
            if request["grammar"] != "oiec_compact_tool_response":
                response["status"] = "invalid_output"
                response["diagnostic"] = "structured reasoning used the wrong grammar"
                response["text"] = ""
            else:
                response["response"] = {
                    "type": "function_call",
                    "name": "submit_oiec_reasoning_object",
                    "arguments": {"answer": "no"},
                    "call_id": "call-reasoning",
                }
        elif "CALL_TOOL" in prompt:
            response["response"] = {
                "type": "function_call",
                "name": "read_file",
                "arguments": {"path": "README.md"},
                "call_id": "call-1",
            }
        else:
            response["response"] = {"type": "message", "content": "Qwen3.8 response"}
        response["metrics"] = {"prompt_tokens": 10, "output_tokens": 4, "total_ms": 5}
    elif operation == "shutdown":
        print(json.dumps(response), flush=True)
        break
    print(json.dumps(response), flush=True)
'''


class LlamaCppProcessProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.model = self.root / "qwen3.8.gguf"
        self.model.write_bytes(b"fake-qwen3.8-gguf")
        self.runner = self.root / "fake_runner.py"
        self.runner.write_text(textwrap.dedent(FAKE_RUNNER), encoding="utf-8")
        self.runner.chmod(0o755)
        self.llama_root = self.root / "llama.cpp"
        self.llama_root.mkdir()
        (self.llama_root / "README.md").write_text("fake llama.cpp source", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.llama_root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.llama_root), "config", "user.email", "tests@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.llama_root), "config", "user.name", "OIEC Tests"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.llama_root), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(self.llama_root), "commit", "-q", "-m", "fixture"],
            check=True,
        )
        self.llama_build = self.root / "llama-build"
        (self.llama_build / "bin").mkdir(parents=True)
        (self.llama_build / "bin" / "libllama.so.0").write_bytes(b"fake-libllama")
        (self.llama_build / "bin" / "libggml.so.0").write_bytes(b"fake-libggml")
        (self.llama_build / "CMakeCache.txt").write_text("FAKE=ON\n", encoding="utf-8")
        self.config = ProviderConfig(
            model="qwen3.8-27b-direct",
            provider_kind="llama_cpp_process",
            runner_path=str(self.runner),
            model_path=str(self.model),
            expected_model_sha256=sha256_file(self.model),
            llama_cpp_root=str(self.llama_root),
            llama_cpp_build_dir=str(self.llama_build),
            llama_grammar_dir=str(Path(__file__).resolve().parents[2] / "grammars" / "providers"),
            max_transport_retries=0,
            max_reasoning_samples=4,
            context_budget_tokens=4096,
            llama_context_tokens=4096,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_factory_selects_direct_process_provider(self) -> None:
        provider = create_provider(self.config)
        self.assertIsInstance(provider, LlamaCppProcessProvider)
        provider.close()

    def test_preflight_binds_exact_model_digest_and_descriptor(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            report = provider.preflight()
        self.assertEqual("ready", report["status"])
        self.assertEqual(self.config.expected_model_sha256, report["model_digest"])
        self.assertEqual("qwen3.8", report["model_architecture"])
        self.assertEqual(0, report["max_transport_retries"])
        self.assertTrue(report["identity_signature"])
        self.assertEqual(2, len(report["llama_cpp_build"]["libraries"]))
        self.assertFalse(report["llama_cpp_source"]["dirty"])
        self.assertNotIn("memory_free", report["backend_devices"][0])

    def test_preflight_identity_ignores_ephemeral_backend_free_memory(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            first = provider.preflight()
        with LlamaCppProcessProvider(self.config) as provider:
            second = provider.preflight()
        self.assertEqual(first["identity_signature"], second["identity_signature"])

    def test_verbose_runner_stderr_cannot_deadlock_preflight(self) -> None:
        noisy_model = self.root / "noisy-qwen3.8.gguf"
        noisy_model.write_bytes(b"fake-noisy-qwen3.8-gguf")
        self.config.model_path = str(noisy_model)
        self.config.expected_model_sha256 = sha256_file(noisy_model)
        self.config.timeout_seconds = 5.0
        with LlamaCppProcessProvider(self.config) as provider:
            report = provider.preflight()
        self.assertEqual("ready", report["status"])

    def test_cancellation_terminates_active_process_and_allows_restart(self) -> None:
        provider = LlamaCppProcessProvider(self.config)
        errors = []

        def complete() -> None:
            try:
                provider.create_response(
                    instructions="SLOW",
                    input_items=[{"role": "user", "content": "wait"}],
                    tools=[],
                )
            except ProviderError as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=complete)
        worker.start()
        attempts = Path(str(self.model) + ".attempts")
        deadline = time.monotonic() + 3.0
        while not attempts.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(attempts.exists())
        provider.cancel()
        worker.join(timeout=3.0)
        self.assertFalse(worker.is_alive())
        self.assertEqual(["llama.cpp request cancelled"], errors)
        self.assertEqual("ready", provider.preflight()["status"])
        provider.close()

    def test_deadline_terminates_runner_without_retry(self) -> None:
        self.config.timeout_seconds = 0.01
        with LlamaCppProcessProvider(self.config) as provider:
            with self.assertRaisesRegex(ProviderError, "deadline exceeded"):
                provider.create_response(
                    instructions="SLOW",
                    input_items=[{"role": "user", "content": "wait"}],
                    tools=[],
                )
        attempts = Path(str(self.model) + ".attempts")
        self.assertEqual("1", attempts.read_text(encoding="utf-8"))

    def test_oom_diagnostic_fails_closed(self) -> None:
        oom_model = self.root / "oom-qwen3.8.gguf"
        oom_model.write_bytes(b"fake-oom-qwen3.8-gguf")
        self.config.model_path = str(oom_model)
        self.config.expected_model_sha256 = sha256_file(oom_model)
        with LlamaCppProcessProvider(self.config) as provider:
            with self.assertRaisesRegex(ProviderError, "NV_ERR_NO_MEMORY"):
                provider.preflight()

    def test_digest_mismatch_fails_before_runner_authority(self) -> None:
        self.config.expected_model_sha256 = "0" * 64
        with LlamaCppProcessProvider(self.config) as provider:
            with self.assertRaisesRegex(ProviderError, "digest mismatch"):
                provider.preflight()
            self.assertFalse(provider.last_completion_request_sent)

    def test_context_budget_failure_occurs_before_completion_request(self) -> None:
        self.config.context_budget_tokens = 1
        with LlamaCppProcessProvider(self.config) as provider:
            with self.assertRaises(ContextBudgetError):
                provider.create_response(
                    instructions="Answer",
                    input_items=[{"role": "user", "content": "hello"}],
                    tools=[],
                )
            self.assertFalse(provider.last_completion_request_sent)

    def test_message_is_responses_compatible(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            response = provider.create_response(
                instructions="Answer",
                input_items=[{"role": "user", "content": "hello"}],
                tools=[],
            )
        self.assertEqual("Qwen3.8 response", response["output_text"])
        self.assertEqual("message", response["output"][0]["type"])
        self.assertEqual(
            {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            response["usage"],
        )
        self.assertEqual(0.1, response["temperature"])
        self.assertEqual(0.95, response["top_p"])
        self.assertEqual(5, response["provider_metadata"]["metrics"]["total_ms"])

    def test_neuro_compatible_descriptor_is_typed_and_process_cancelled(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            descriptor = provider.descriptor()
        self.assertEqual("llama_cpp_process", descriptor.provider_id)
        self.assertEqual("qwen3.8-27b-direct", descriptor.model_id)
        self.assertTrue(descriptor.supports_json_grammar)
        self.assertTrue(descriptor.supports_chat_template)
        self.assertTrue(descriptor.supports_cancellation)
        self.assertTrue(descriptor.supports_deadline)

    def test_typed_local_completion_preserves_status_metrics_and_output(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            result = provider.complete_local(
                LocalModelRequest(
                    prompt="return a message",
                    options=LocalModelCompletionOptions(),
                )
            )
        self.assertTrue(result.ok)
        self.assertEqual(LocalModelStatus.OK, result.status)
        self.assertEqual(10, result.metrics.prompt_tokens)
        self.assertEqual(4, result.metrics.output_tokens)
        self.assertEqual("message", result.response["type"])

    def test_typed_local_failure_is_returned_without_hidden_retry(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            result = provider.complete_local(
                LocalModelRequest(
                    prompt="FORCE_ERROR",
                    options=LocalModelCompletionOptions(),
                )
            )
        self.assertEqual(LocalModelStatus.INVALID_OUTPUT, result.status)
        self.assertIn("forced failure", result.diagnostic)
        attempts = Path(str(self.model) + ".attempts")
        self.assertEqual("1", attempts.read_text(encoding="utf-8"))

    def test_stream_callback_can_cancel_and_provider_restarts(self) -> None:
        chunks = []
        with LlamaCppProcessProvider(self.config) as provider:
            cancelled = provider.complete_local(
                LocalModelRequest(
                    prompt="STREAM_CANCEL",
                    options=LocalModelCompletionOptions(),
                    stream_callback=lambda chunk: (chunks.append(chunk), False)[1],
                )
            )
            recovered = provider.complete_local(
                LocalModelRequest(
                    prompt="return a message",
                    options=LocalModelCompletionOptions(),
                )
            )
        self.assertEqual(["{"], chunks)
        self.assertEqual(LocalModelStatus.CANCELLED, cancelled.status)
        self.assertTrue(cancelled.metrics.cancelled)
        self.assertTrue(recovered.ok)

    def test_qwen38_profile_binds_exact_digest_and_zero_retries(self) -> None:
        config = qwen38_direct_config(
            runner_path=str(self.runner),
            model_path=str(self.model),
            llama_cpp_root=str(self.llama_root),
            llama_cpp_build_dir=str(self.llama_build),
        )
        self.assertEqual(QWEN38_DIRECT_MODEL_ID, config.model)
        self.assertEqual(QWEN38_Q2_K_SHA256, config.expected_model_sha256)
        self.assertEqual(0, config.max_transport_retries)

    def test_local_model_contract_forbids_internal_retry(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one attempt"):
            LocalModelCompletionOptions(max_attempts=2)

    def test_tool_call_is_schema_validated(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            }
        ]
        with LlamaCppProcessProvider(self.config) as provider:
            response = provider.create_response(
                instructions="CALL_TOOL",
                input_items=[{"role": "user", "content": "read it"}],
                tools=tools,
            )
        call = response["output"][0]
        self.assertEqual("function_call", call["type"])
        self.assertEqual({"path": "README.md"}, json.loads(call["arguments"]))

    def test_reasoning_object_tool_uses_compact_function_call_grammar(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            response = provider.create_response(
                instructions="Submit the structured reasoning answer.",
                input_items=[{"role": "user", "content": "answer no"}],
                tools=[
                    reasoning_object_tool(
                        ("answer",),
                        required_keys=("answer",),
                    )
                ],
            )
        call = response["output"][0]
        self.assertEqual("function_call", call["type"])
        self.assertEqual("submit_oiec_reasoning_object", call["name"])
        self.assertEqual({"answer": "no"}, json.loads(call["arguments"]))

    def test_undeclared_tool_fails_closed(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            with self.assertRaisesRegex(ProviderError, "undeclared tool"):
                provider.create_response(
                    instructions="UNKNOWN_TOOL",
                    input_items=[{"role": "user", "content": "unsafe"}],
                    tools=[],
                )

    def test_provider_error_is_not_retried(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            with self.assertRaisesRegex(ProviderError, "forced failure.*partial"):
                provider.create_response(
                    instructions="FORCE_ERROR",
                    input_items=[{"role": "user", "content": "fail"}],
                    tools=[],
                )
            self.assertTrue(provider.last_completion_request_sent)
        attempts = Path(str(self.model) + ".attempts")
        self.assertEqual("1", attempts.read_text(encoding="utf-8"))

    def test_multi_response_is_ordered_and_bounded(self) -> None:
        with LlamaCppProcessProvider(self.config) as provider:
            responses = provider.create_responses(
                requests=[
                    {"instructions": "first", "input_items": [], "tools": []},
                    {"instructions": "FORCE_ERROR", "input_items": [], "tools": []},
                ],
                max_responses=4,
            )
        self.assertEqual("Qwen3.8 response", responses[0]["output_text"])
        self.assertEqual("reasoning_error", responses[1]["type"])

    def test_protocol_schemas_and_grammars_are_packaged_sources(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        for relative in (
            "schemas/providers/llama_cpp_request.schema.json",
            "schemas/providers/llama_cpp_response.schema.json",
        ):
            payload = json.loads((repository / relative).read_text(encoding="utf-8"))
            self.assertEqual("object", payload["type"])
        for relative in (
            "grammars/providers/oiec_reasoning_response.gbnf",
            "grammars/providers/oiec_tool_response.gbnf",
            "grammars/providers/oiec_compact_tool_response.gbnf",
        ):
            text = (repository / relative).read_text(encoding="utf-8")
            self.assertIn("root ::=", text)
        compact = (
            repository / "grammars/providers/oiec_compact_tool_response.gbnf"
        ).read_text(encoding="utf-8")
        self.assertTrue(compact.startswith("root ::= function-call\n"))
        self.assertNotIn("message ::=", compact)


if __name__ == "__main__":
    unittest.main()
