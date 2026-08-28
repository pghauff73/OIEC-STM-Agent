from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, Optional

from ourd.authority import authority_payload, finalize_authority
from ourd.models import AuthorityManifest
from ourd.workspace import Workspace


class RepoFixture:
    def __init__(self):
        self.temporary = TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        (self.root / "README.md").write_text("# Example\n\nvalue = 1\n", encoding="utf-8")

    def close(self) -> None:
        self.temporary.cleanup()

    def write(self, path: str, content: str) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def authority(
        self,
        *,
        allowed_paths: Optional[Iterable[str]] = None,
        command_capabilities: Optional[Iterable[str]] = None,
        mandatory_tests: Optional[Iterable[str]] = None,
        mandatory_evidence: Optional[Iterable[str]] = None,
        allow_l1_auto_apply: bool = True,
        allow_interactive_l2: bool = True,
        allow_yolo: bool = False,
        max_retries_per_action: int = 1,
        max_automatic_risk: str = "L1",
        read_only: bool = False,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Path:
        workspace = Workspace(self.root)
        manifest = AuthorityManifest(
            task_id="test-task",
            goal="Exercise deterministic governance",
            source_snapshot_hash=workspace.snapshot_hash(),
            allowed_paths=list(allowed_paths or ["README.md", "src/**", "tests/**"]),
            forbidden_paths=[".ourd-agent/**", "secrets/**"],
            command_capabilities=list(command_capabilities or []),
            max_retries_per_action=max_retries_per_action,
            max_automatic_risk=max_automatic_risk,
            allow_l1_auto_apply=allow_l1_auto_apply,
            allow_interactive_l2=allow_interactive_l2,
            allow_yolo=allow_yolo,
            mandatory_tests=list(mandatory_tests or []),
            mandatory_evidence=list(mandatory_evidence or []),
            operator="unit-test",
            read_only=read_only,
        )
        for key, value in (overrides or {}).items():
            setattr(manifest, key, value)
        finalize_authority(manifest)
        path = self.base / "authority.json"
        path.write_text(json.dumps(authority_payload(manifest), indent=2), encoding="utf-8")
        return path


def governance_args(allowed_paths: Optional[list[str]] = None) -> Dict[str, Any]:
    return {
        "goal": "Make one bounded change",
        "constraints": ["preserve unrelated behavior"],
        "assumptions": [],
        "uncertainties": [],
        "objects": ["workspace", "candidate"],
        "relations": ["candidate modifies workspace"],
        "boundaries": ["authority scope"],
        "excluded_scope": [".ourd-agent/**"],
        "allowed_paths": allowed_paths or ["README.md"],
        "dimensions": ["policy correctness"],
        "invariants": ["unrelated files unchanged"],
    }
