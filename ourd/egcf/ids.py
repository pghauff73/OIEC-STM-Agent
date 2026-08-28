from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def typed_id(object_type: str, payload: Any) -> str:
    normalized = object_type.strip().lower().replace("_", "-")
    if not normalized or ":" in normalized:
        raise ValueError(f"invalid object type: {object_type!r}")
    return f"{normalized}:sha256:{sha256_json({'object_type': normalized, 'payload': payload})}"


def parse_typed_id(object_id: str) -> tuple[str, str]:
    parts = object_id.split(":")
    if len(parts) != 3 or parts[1] != "sha256" or len(parts[2]) != 64:
        raise ValueError(f"invalid typed object ID: {object_id!r}")
    return parts[0], parts[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
