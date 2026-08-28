from __future__ import annotations

import base64
import json
import mimetypes
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from ..errors import ContextBudgetError, ProviderError
from .base import ProviderConfig


IMAGE_REFERENCE_RE = re.compile(r"@img:([0-9a-f]{12,64})\b", re.IGNORECASE)
MAX_PROVIDER_IMAGE_BYTES = 20 * 1024 * 1024


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
            "visual_asset_root": bool(self.config.visual_asset_root),
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
        expanded_input = self._expand_latest_image_references(input_items)
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "instructions": instructions,
            "input": expanded_input,
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

    def _expand_latest_image_references(self, input_items: List[Any]) -> List[Any]:
        """Attach explicitly referenced GUI images to the latest user text item only.

        The chat/event layer keeps the compact @img reference. Expansion happens
        only at the provider boundary so binary image data is never persisted in
        the ordinary transcript or OIEC event payloads.
        """

        root_text = self.config.visual_asset_root.strip()
        if not root_text:
            return input_items
        root = Path(root_text).expanduser().resolve()
        index_path = root / "index.json"
        if not index_path.is_file():
            return input_items
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return input_items
        if not isinstance(index, dict):
            return input_items
        expanded = list(input_items)
        for item_index in range(len(expanded) - 1, -1, -1):
            item = expanded[item_index]
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            text = item.get("content")
            if not isinstance(text, str):
                continue
            digests = IMAGE_REFERENCE_RE.findall(text)
            if not digests:
                return expanded
            references: list[str] = []
            for digest in digests:
                prefix = f"@img:{digest.lower()}"
                matches = [
                    reference
                    for reference in index
                    if isinstance(reference, str) and reference.lower().startswith(prefix)
                ]
                if len(matches) == 1 and matches[0] not in references:
                    references.append(matches[0])
            if not references:
                return expanded
            content: list[dict[str, str]] = [{"type": "input_text", "text": text}]
            for reference in references:
                metadata = index.get(reference)
                if not isinstance(metadata, dict) or metadata.get("kind") != "image":
                    continue
                stored = metadata.get("stored_path", "")
                if not isinstance(stored, str) or not stored:
                    continue
                candidate = (root.parent.parent / stored).resolve()
                try:
                    candidate.relative_to(root.parent.parent.resolve())
                except ValueError:
                    continue
                if not candidate.is_file():
                    continue
                size = candidate.stat().st_size
                if size <= 0 or size > MAX_PROVIDER_IMAGE_BYTES:
                    raise ProviderError(
                        f"referenced image {reference} exceeds provider image bound"
                    )
                media_type = str(metadata.get("media_type") or "")
                if not media_type.startswith("image/"):
                    media_type = mimetypes.guess_type(candidate.name)[0] or "image/png"
                encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{encoded}",
                    }
                )
            if len(content) > 1:
                expanded[item_index] = {**item, "content": content}
            return expanded
        return expanded

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
