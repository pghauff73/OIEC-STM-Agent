from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .errors import EGCFError
from .ids import canonical_json
from .knowledge_governance_store import KnowledgeGovernanceStore as _BaseKnowledgeGovernanceStore, _ref


class KnowledgeGovernanceStore(_BaseKnowledgeGovernanceStore):
    """Grounded facade with idempotent immutable-object reuse."""

    def _write(self, root: Path, kind: str, signature: str, payload: Mapping[str, Any]) -> tuple[str, Path, str]:
        object_ref = _ref(kind, signature)
        path = self._path(root, object_ref, kind)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EGCFError(f"cannot read existing knowledge-governance object {object_ref}: {exc}") from exc
            if existing.get("object_id") != object_ref or canonical_json(existing.get("payload", {})) != canonical_json(dict(payload)):
                raise EGCFError(f"immutable knowledge-governance collision at {path}")
            return object_ref, path, str(existing.get("created_at", ""))
        return super()._write(root, kind, signature, payload)
