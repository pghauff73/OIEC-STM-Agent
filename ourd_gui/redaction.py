from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from ourd.persistence import redact


REDACTED = "[REDACTED]"
MAX_DEPTH_MARKER = "[maximum depth exceeded]"
TRUNCATED_ITEMS_MARKER = "[additional items omitted]"

_SENSITIVE_KEYS = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "client-secret",
    "client_secret",
    "cookie",
    "credentials",
    "password",
    "passwd",
    "private-key",
    "private_key",
    "refresh-token",
    "refresh_token",
    "secret",
    "token",
}


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().casefold().replace(" ", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        ("_password", "_secret", "_token", "_api_key", "_private_key")
    )


def safe_projection(
    value: Any,
    *,
    max_depth: int = 12,
    max_items: int = 1_000,
    max_string_characters: int = 100_000,
    _depth: int = 0,
) -> Any:
    if _depth >= max_depth:
        return MAX_DEPTH_MARKER
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:max_items]:
            text_key = str(key)
            projected[text_key] = (
                REDACTED
                if _is_sensitive_key(text_key)
                else safe_projection(
                    item,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_string_characters=max_string_characters,
                    _depth=_depth + 1,
                )
            )
        if len(items) > max_items:
            projected[TRUNCATED_ITEMS_MARKER] = len(items) - max_items
        return projected
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        projected = [
            safe_projection(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_characters=max_string_characters,
                _depth=_depth + 1,
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            projected.append({TRUNCATED_ITEMS_MARKER: len(items) - max_items})
        return projected
    if isinstance(value, str):
        redacted = str(redact(value))
        if len(redacted) <= max_string_characters:
            return redacted
        return redacted[:max_string_characters] + "[truncated]"
    if isinstance(value, (bytes, bytearray)):
        return f"[{type(value).__name__} {len(value)} bytes]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)
