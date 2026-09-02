from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..persistence import atomic_write_text
from . import nonlinear_store as _implementation
from .errors import EGCFError
from .ids import canonical_json


def _immutable_payload_write(path: Path, envelope: dict[str, Any]) -> bool:
    """Ignore non-identity creation timestamps when re-admitting the same immutable object."""
    serialized = json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read immutable nonlinear store object {path}: {exc}") from exc
        existing_identity = dict(existing)
        incoming_identity = dict(envelope)
        existing_identity.pop("created_at", None)
        incoming_identity.pop("created_at", None)
        if canonical_json(existing_identity) != canonical_json(incoming_identity):
            raise EGCFError(f"immutable nonlinear object collision at {path}")
        return False
    atomic_write_text(path, serialized)
    return True


_implementation._write_immutable = _immutable_payload_write
NonlinearCanonicalStore = _implementation.NonlinearCanonicalStore
NONLINEAR_STORE_VERSION = _implementation.NONLINEAR_STORE_VERSION
NONLINEAR_STORE_SCHEMA_VERSION = _implementation.NONLINEAR_STORE_SCHEMA_VERSION

__all__ = [
    "NONLINEAR_STORE_SCHEMA_VERSION",
    "NONLINEAR_STORE_VERSION",
    "NonlinearCanonicalStore",
]
