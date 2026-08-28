from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from ..errors import ContextBudgetError, ProviderError
from .base import ProviderConfig


def estimate_tokens(value: Any) -> int:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, (len(encoded) + 3) // 4)


class OpenAIResponsesProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.client = None
        if self.is_local_ollama:
            return
        if not config.api_key:
            raise ProviderError("OPENAI_API_KEY or OURD_API_KEY is required")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(
                "missing dependency: install the project or run `pip install openai`"
            ) from exc
        kwargs: Dict[str, Any] = {
            "api_key": config.api_key or ("ollama" if self.is_local_ollama else None),
            "timeout": config.timeout_seconds,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)

    @property
    def is_local_ollama(self) -> bool:
        base = self.config.base_url.lower()
        return "127.0.0.1:11434" in base or "localhost:11434" in base

    def preflight(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "provider": "openai_responses",
            "model": self.config.model,
            "base_url": self.config.base_url or "default",
            "endpoint_type": "ollama_local" if self.is_local_ollama else "openai_responses",
            "context_budget_tokens": self.config.context_budget_tokens,
            "max_output_tokens": self.config.max_output_tokens,
            "reasoning_effort": self.config.reasoning_effort or "provider_default",
            "max_transport_retries": self.config.max_transport_retries,
        }
        if not self.is_local_ollama:
            result["status"] = "configuration_only"
            return result
        host = self.config.base_url.rsplit("/v1", 1)[0]
        request = urllib.request.Request(
            f"{host}/api/show",
            data=json.dumps({"model": self.config.model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = self._urlopen_json(
            request,
            timeout=min(20.0, self.config.timeout_seconds),
            context="Ollama model preflight",
        )
        if not isinstance(payload, dict):
            raise ProviderError("Ollama model preflight returned a non-object response")
        result.update(
            {
                "status": "ready",
                "model_family": payload.get("details", {}).get("family", ""),
                "parameter_size": payload.get("details", {}).get("parameter_size", ""),
                "quantization_level": payload.get("details", {}).get("quantization_level", ""),
                "model_info": payload.get("model_info", {}),
            }
        )
        tags_request = urllib.request.Request(f"{host}/api/tags", method="GET")
        try:
            tags = self._urlopen_json(
                tags_request,
                timeout=min(20.0, self.config.timeout_seconds),
                context="Ollama tag inventory",
            )
        except ProviderError:
            tags = {}
        for model in tags.get("models", []):
            if model.get("name") in {self.config.model, f"{self.config.model}:latest"}:
                result["model_digest"] = model.get("digest", "")
                result["model_size"] = model.get("size", 0)
                break
        return result

    def create_response(
        self,
        *,
        instructions: str,
        input_items: List[Any],
        tools: List[Dict[str, Any]],
    ) -> Any:
        estimated = estimate_tokens(
            {"instructions": instructions, "input": input_items, "tools": tools}
        )
        if estimated > self.config.context_budget_tokens:
            raise ContextBudgetError(
                "provider input exceeds configured context budget: "
                f"estimated {estimated}, budget {self.config.context_budget_tokens}"
            )
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "max_output_tokens": self.config.max_output_tokens,
        }
        if self.config.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.config.reasoning_effort}
        if self.is_local_ollama:
            return self._create_local_response(kwargs)
        try:
            assert self.client is not None
            return self.client.responses.create(**kwargs)
        except Exception as exc:
            raise ProviderError(f"model response failed: {exc}") from exc

    def _create_local_response(self, body: Dict[str, Any]) -> Dict[str, Any]:
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/responses",
            data=json.dumps(body, ensure_ascii=False, default=self._json_default).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key or 'ollama'}",
            },
            method="POST",
        )
        payload = self._urlopen_json(
            request,
            timeout=self.config.timeout_seconds,
            context="Ollama Responses",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("output"), list):
            raise ProviderError("Ollama Responses returned an incompatible response object")
        return payload

    def _urlopen_json(
        self,
        request: urllib.request.Request,
        *,
        timeout: float,
        context: str,
    ) -> Any:
        retries = max(0, min(int(self.config.max_transport_retries), 5))
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ProviderError(f"{context} returned invalid JSON: {exc}") from exc
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise ProviderError(f"{context} failed: HTTP {exc.code}: {detail}") from exc
            except OSError as exc:
                if attempt >= retries:
                    raise ProviderError(f"cannot reach {context}: {exc}") from exc
        raise ProviderError(f"cannot reach {context}")

    @staticmethod
    def _json_default(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(exclude_none=True)
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "__dict__"):
            return value.__dict__
        return str(value)
