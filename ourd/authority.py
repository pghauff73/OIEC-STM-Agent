from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .errors import PolicyError
from .models import AuthorityManifest, RISK_ORDER
from .workspace import Workspace


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def authority_payload(manifest: AuthorityManifest) -> Dict[str, Any]:
    payload = asdict(manifest)
    payload.pop("authority_hash", None)
    return payload


def finalize_authority(manifest: AuthorityManifest) -> AuthorityManifest:
    manifest.authority_hash = sha256_json(authority_payload(manifest))
    return manifest


def read_only_authority(workspace: Workspace) -> AuthorityManifest:
    return finalize_authority(
        AuthorityManifest(source_snapshot_hash=workspace.snapshot_hash(), read_only=True)
    )


def scoped_write_authority(
    workspace: Workspace,
    *,
    allowed_paths: Iterable[str],
    goal: str,
    operator: str = "cli-user",
    command_capabilities: Optional[Iterable[str]] = None,
    mandatory_tests: Optional[Iterable[str]] = None,
    allow_interactive_l2: bool = False,
    max_retries_per_action: int = 1,
) -> AuthorityManifest:
    """Create exact-snapshot mutation authority from explicit CLI user scope.

    This helper is intentionally conservative: L1 changes still require exact
    candidate approval, L2 is disabled unless the CLI user explicitly enables
    it, and --yolo is never granted. It does not broaden scope beyond the path
    patterns supplied by the human invocation.
    """

    normalized_paths = []
    for raw in allowed_paths:
        path = str(raw).strip()
        if not path:
            continue
        if Path(path).is_absolute() or "\x00" in path:
            raise PolicyError(f"invalid write path pattern: {path!r}")
        normalized_paths.append(path.replace("\\", "/"))
    normalized_paths = list(dict.fromkeys(normalized_paths))
    if not normalized_paths:
        raise PolicyError("bounded write authority requires at least one allowed path")

    capabilities = list(dict.fromkeys(str(value) for value in (command_capabilities or ()) if str(value)))
    tests = list(dict.fromkeys(str(value) for value in (mandatory_tests or ()) if str(value)))
    manifest = AuthorityManifest(
        task_id="cli-write",
        goal=goal.strip() or "Human-authorized bounded writing session",
        source_snapshot_hash=workspace.snapshot_hash(),
        allowed_paths=normalized_paths,
        forbidden_paths=[".ourd-agent/**"],
        command_capabilities=capabilities,
        semantic_capability_ceiling="C3",
        semantic_capabilities=["filesystem.write"],
        max_retries_per_action=max(0, min(int(max_retries_per_action), 10)),
        max_automatic_risk="L0",
        allow_l1_auto_apply=False,
        allow_interactive_l2=bool(allow_interactive_l2),
        allow_yolo=False,
        mandatory_tests=tests,
        mandatory_evidence=[],
        operator=operator.strip() or "cli-user",
        read_only=False,
    )
    validate_authority(manifest, workspace)
    return finalize_authority(manifest)


def save_authority(path: Path, manifest: AuthorityManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = authority_payload(finalize_authority(manifest))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_authority(
    path: Path,
    workspace: Workspace,
    *,
    allow_snapshot_mismatch: bool = False,
) -> AuthorityManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot load authority manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PolicyError("authority manifest must be a JSON object")
    try:
        manifest = AuthorityManifest(**payload)
    except TypeError as exc:
        raise PolicyError(f"invalid authority manifest fields: {exc}") from exc
    validate_authority(
        manifest,
        workspace,
        check_snapshot=not allow_snapshot_mismatch,
    )
    return finalize_authority(manifest)


def validate_authority(
    manifest: AuthorityManifest,
    workspace: Workspace,
    *,
    check_snapshot: bool = True,
) -> None:
    if manifest.schema_version != 1:
        raise PolicyError(f"unsupported authority schema: {manifest.schema_version}")
    if manifest.max_automatic_risk not in RISK_ORDER:
        raise PolicyError("max_automatic_risk must be L0, L1, or L2")
    if manifest.semantic_capability_ceiling not in {"C0", "C1", "C2", "C3", "C4", "C5"}:
        raise PolicyError("semantic_capability_ceiling must be C0, C1, C2, C3, C4, or C5")
    if not 0 <= manifest.max_retries_per_action <= 10:
        raise PolicyError("max_retries_per_action must be between 0 and 10")
    if not manifest.task_id.strip() or not manifest.goal.strip():
        raise PolicyError("authority task_id and goal are required")
    if not manifest.allowed_paths:
        raise PolicyError("authority allowed_paths cannot be empty")
    for path_pattern in [*manifest.allowed_paths, *manifest.forbidden_paths]:
        if Path(path_pattern).is_absolute() or "\x00" in path_pattern:
            raise PolicyError(f"invalid authority path pattern: {path_pattern!r}")
    if manifest.expires_at:
        try:
            expiry = datetime.fromisoformat(manifest.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PolicyError("authority expires_at must be ISO-8601") from exc
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise PolicyError("authority manifest has expired")
    current_snapshot = workspace.snapshot_hash()
    if (
        check_snapshot
        and manifest.source_snapshot_hash
        and manifest.source_snapshot_hash != current_snapshot
    ):
        raise PolicyError(
            "authority source snapshot mismatch: "
            f"expected {manifest.source_snapshot_hash}, observed {current_snapshot}"
        )
    if not manifest.read_only and not manifest.source_snapshot_hash:
        raise PolicyError("mutation authority requires source_snapshot_hash")
    if manifest.read_only and (
        manifest.allow_l1_auto_apply
        or manifest.allow_interactive_l2
        or manifest.allow_yolo
        or manifest.command_capabilities
    ):
        raise PolicyError("read-only authority cannot grant mutation capabilities")
    if manifest.read_only and manifest.semantic_capability_ceiling in {"C3", "C4", "C5"}:
        raise PolicyError("read-only authority cannot grant C3-C5 semantic capabilities")


def save_authority_example(path: Path, workspace: Workspace) -> None:
    manifest = AuthorityManifest(
        task_id="replace-me",
        goal="Describe the exact authorized engineering task",
        source_snapshot_hash=workspace.snapshot_hash(),
        allowed_paths=["README.md", "ourd/**", "tests/**", "pyproject.toml"],
        forbidden_paths=[".ourd-agent/**"],
        command_capabilities=["python.unittest", "python.py_compile"],
        semantic_capability_ceiling="C3",
        semantic_capabilities=[
            "simulation.run",
            "filesystem.write",
            "process.execute",
            "workflow.execute",
            "governance.write",
            "registry.admin",
        ],
        max_retries_per_action=1,
        max_automatic_risk="L1",
        allow_l1_auto_apply=False,
        allow_interactive_l2=True,
        allow_yolo=False,
        mandatory_tests=["python3 -m unittest discover -s tests -v"],
        mandatory_evidence=["unrelated files unchanged", "authorized scope preserved"],
        operator="replace-me",
        read_only=False,
    )
    save_authority(path, manifest)
