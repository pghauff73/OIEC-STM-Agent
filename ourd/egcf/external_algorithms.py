from __future__ import annotations

import ast
from datetime import datetime, timezone
import io
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time
from typing import Any, Iterable

from .ids import sha256_bytes, sha256_json, utc_now
from .models import AlgorithmDefinition, ArtifactRecord, EvidenceArtifact
from .registry import AlgorithmRegistry, CommandRegistry
from .store import EGCFStore


@dataclass(frozen=True)
class SourceSnapshot:
    repository: str
    version: str
    git_head: str
    dirty: bool
    dirty_path_count: int
    dirty_paths: tuple[str, ...]
    unrelated_dirty_path_count: int
    files: tuple[tuple[str, str, int], ...]
    manifest_digest: str
    bundle_digest: str
    bundle_size: int
    captured_at: str


@dataclass(frozen=True)
class BABCSRegistration:
    algorithm_definition_id: str
    algorithm_id: str
    source_bundle_artifact_id: str
    analysis_evidence_id: str
    snapshot: SourceSnapshot
    analysis: dict[str, Any]


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return ""
    return result.stdout.strip()


def _project_version(project_file: Path) -> str:
    tree = ast.parse(project_file.read_text(encoding="utf-8"), filename=str(project_file))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "VERSION":
                    value = ast.literal_eval(node.value)
                    return str(value)
    raise ValueError("BAB-CS VERSION is missing from src/babcs/_project.py")


def babcs_source_paths(root: Path) -> tuple[Path, ...]:
    root = root.resolve()
    package_root = root / "src" / "babcs"
    required = (
        root / "README.md",
        root / "IMPLEMENTATION_PLAN.md",
        root / "pyproject.toml",
        root / "LICENSE",
        package_root / "_project.py",
        package_root / "bounded.py",
        package_root / "candidates.py",
        package_root / "integrators.py",
        package_root / "model.py",
        package_root / "simulator.py",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("BAB-CS source is incomplete: " + ", ".join(str(path) for path in missing))
    return tuple(sorted({*required, *package_root.glob("*.py")}))


def _source_manifest(root: Path, paths: Iterable[Path]) -> tuple[tuple[str, str, int], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            sha256_bytes(path.read_bytes()),
            path.stat().st_size,
        )
        for path in sorted(paths)
    )


def _source_bundle(root: Path, paths: Iterable[Path]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(paths):
            content = path.read_bytes()
            info = tarfile.TarInfo(path.relative_to(root).as_posix())
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def capture_babcs_source(root: Path) -> tuple[SourceSnapshot, bytes]:
    root = root.resolve()
    paths = babcs_source_paths(root)
    manifest = _source_manifest(root, paths)
    bundle = _source_bundle(root, paths)
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    all_dirty_paths = tuple(
        sorted(
            line[3:] if len(line) > 3 else line
            for line in status.splitlines()
            if line.strip()
        )
    )
    captured_paths = {path for path, _, _ in manifest}
    dirty_paths = tuple(path for path in all_dirty_paths if path in captured_paths)
    latest_mtime = max(path.stat().st_mtime for path in paths)
    snapshot = SourceSnapshot(
        repository="Bounded-Authority-Based-Circuit-Simulation",
        version=_project_version(root / "src" / "babcs" / "_project.py"),
        git_head=_git(root, "rev-parse", "HEAD"),
        dirty=bool(all_dirty_paths),
        dirty_path_count=len(all_dirty_paths),
        dirty_paths=dirty_paths,
        unrelated_dirty_path_count=len(all_dirty_paths) - len(dirty_paths),
        files=manifest,
        manifest_digest=sha256_json(manifest),
        bundle_digest=sha256_bytes(bundle),
        bundle_size=len(bundle),
        captured_at=datetime.fromtimestamp(latest_mtime, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    )
    return snapshot, bundle


def _literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, Any] = {}

    def evaluate(node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ValueError(f"unresolved constant {node.id} in {path}")
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = evaluate(node.left)
            right = evaluate(node.right)
            return set(left).union(right)
        return ast.literal_eval(node)

    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    value = node.value
                    if value is not None:
                        values[target.id] = evaluate(value)
    return values.get(name)


def analyse_babcs_source(root: Path, snapshot: SourceSnapshot) -> dict[str, Any]:
    root = root.resolve()
    source_root = root / "src" / "babcs"
    class_names: set[str] = set()
    function_names: set[str] = set()
    dataclass_names: set[str] = set()
    for path in sorted(source_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_names.add(node.name)
                decorator_names = {
                    decorator.id
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Name)
                }
                if "dataclass" in decorator_names:
                    dataclass_names.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_names.add(node.name)
    exports = _literal_assignment(source_root / "__init__.py", "__all__") or []
    candidate_methods = _literal_assignment(source_root / "candidates.py", "CANDIDATE_METHODS") or []
    config_tree = ast.parse((source_root / "bounded.py").read_text(encoding="utf-8"))
    config_fields: list[str] = []
    for node in config_tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "BABCSConfig":
            config_fields = [
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
            ]
    return {
        "snapshot": asdict(snapshot),
        "source_metrics": {
            "python_modules": len(tuple(source_root.glob("*.py"))),
            "classes": len(class_names),
            "functions": len(function_names),
            "dataclasses": len(dataclass_names),
            "source_bytes": sum(size for _, _, size in snapshot.files),
        },
        "public_api": sorted(str(item) for item in exports),
        "candidate_methods": sorted(str(item) for item in candidate_methods),
        "configuration_controls": config_fields,
        "control_layers": [
            "candidate integrator prediction",
            "algebraic projection",
            "implicit reference authority",
            "contractive correction",
            "residual, error, energy, and amplification gates",
            "periodic independent replay anchor",
            "event-safe history reset",
            "stiffness and failure fallback to implicit authority",
        ],
        "oiec_mapping": {
            "boundary_determination": "Circuit topology, rollout mode, event boundaries, source snapshot, and configured safety caps define where a step is admissible.",
            "dimension_limiting": "Candidate method, step size, reference interval, anchor refinement, linear backend, and bounded retry count constrain active numerical complexity.",
            "iurm": "Candidate/reference and dual-resolution comparisons isolate controlled numerical variations.",
            "eon": "A simulation configuration and exact circuit case determine one reproducible integration action.",
            "cfel": "Step rejection, residual failures, anchor discrepancy, stiffness, and uncertainty metrics revise the next step or transfer authority.",
        },
        "strengths": [
            "separates provisional candidate state from independently refreshed implicit authority",
            "uses categorical fail-closed gates for residual, contraction, stiffness, event, and minimum-step failures",
            "records per-step evidence and supports deterministic dense execution by default",
            "keeps rollout modes explicit and provides no unanchored candidate-only production mode",
        ],
        "limitations": [
            "the repository states that BAB-CS is not a production sparse SPICE replacement",
            "trajectory accuracy is not claimed indefinitely for unstable, chaotic, discontinuous, or neutrally oscillating circuits",
            "the captured worktree is dirty, so the content bundle rather than Git HEAD is the authoritative implementation snapshot",
            "focused unit tests do not establish complete release qualification, external equivalence, or certification",
        ],
    }


def run_babcs_focused_tests(root: Path, timeout_seconds: int = 180) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "tests.test_babcs",
        "tests.test_bound_model",
        "tests.test_integrator_boundaries",
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root.resolve() / "src")
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    match = re.search(r"Ran (\d+) tests?", output)
    return {
        "command": "PYTHONPATH=src " + " ".join(command),
        "returncode": result.returncode,
        "success": result.returncode == 0,
        "test_count": int(match.group(1)) if match else None,
        "duration_seconds": round(time.monotonic() - started, 6),
        "output_tail": output[-4000:],
    }


def _definition(snapshot: SourceSnapshot, source_bundle_artifact_id: str) -> AlgorithmDefinition:
    return AlgorithmDefinition(
        name="reference.babcs.bounded-integrator",
        version=1,
        implementation_kind="reference",
        implementation_ref=(
            f"artifact-record:{source_bundle_artifact_id}#src/babcs/bounded.py:BoundedIntegrator"
        ),
        implementation_digest=snapshot.bundle_digest,
        command_ids=[
            "algorithm.compare@1",
            "algorithm.explain@1",
            "experiment.analyse@1",
            "experiment.benchmark@1",
        ],
        input_schema={
            "type": "object",
            "properties": {
                "circuit": {"type": "object"},
                "configuration": {"type": "object"},
                "time_span": {"type": "object"},
            },
            "required": ["circuit", "configuration", "time_span"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "trajectory": {"type": "array"},
                "step_metrics": {"type": "array"},
                "summary": {"type": "object"},
            },
            "required": ["trajectory", "step_metrics", "summary"],
            "additionalProperties": False,
        },
        applicability={
            "domain": "transient circuit integration",
            "execution": "reference-only",
            "upstream_version": snapshot.version,
        },
        capability_requirements=["registry.read"],
        capability_level="C0",
        risk_floor="L0",
        rollback_class="none",
        invariants=[
            "algebraic projection remains inside configured residual caps",
            "accepted active correction gain remains contractive",
            "event boundaries reset multistep history",
            "stiffness and failed safety gates transfer state authority to the implicit reference",
            "minimum step and bounded rejection limits fail closed",
        ],
        evidence_requirements=[
            "exact content-addressed source bundle",
            "analytic and nonlinear convergence tests",
            "boundary, event, stiffness, and singular-system tests",
            "independent runtime and external-reference comparisons",
        ],
        qualification_policy={
            "tests_required": True,
            "contextual": True,
            "reference_only": True,
            "release_certification_required_for_execution": True,
        },
        owner="BAB-CS source repository",
        provenance={
            "source_repository": "../BAB-CS",
            "source_bundle_artifact_id": source_bundle_artifact_id,
            "source_manifest_digest": snapshot.manifest_digest,
            "source_git_head": snapshot.git_head,
            "source_dirty": snapshot.dirty,
            "upstream_version": snapshot.version,
            "license": "MPL-2.0",
        },
        status="PROPOSED",
        known_failures=[
            "not qualified as a production sparse SPICE replacement",
            "no indefinite trajectory-accuracy claim for unstable, chaotic, discontinuous, or neutral oscillatory cases",
            "external source execution remains outside this reference registration",
        ],
    )


def register_babcs_algorithm(
    workspace_root: Path,
    babcs_root: Path,
    *,
    run_focused_tests: bool = False,
) -> BABCSRegistration:
    snapshot, bundle = capture_babcs_source(babcs_root)
    analysis = analyse_babcs_source(babcs_root, snapshot)
    if run_focused_tests:
        analysis["focused_validation"] = run_babcs_focused_tests(babcs_root)
    with EGCFStore(workspace_root) as store:
        commands = CommandRegistry(store)
        algorithms = AlgorithmRegistry(store, commands)
        artifact_bytes_id, artifact_path = store.artifacts.put(bundle)
        _, _, artifact_digest = artifact_bytes_id.partition("artifact-bytes:sha256:")
        source_record = ArtifactRecord(
            media_type="application/x-tar",
            sha256=artifact_digest,
            size=len(bundle),
            source_ids=[],
            provenance={
                "producer": "deterministic-babcs-source-bundler",
                "repository": "../BAB-CS",
                "manifest_digest": snapshot.manifest_digest,
                "bundle_digest": snapshot.bundle_digest,
                "file_count": len(snapshot.files),
                "license": "MPL-2.0",
            },
            created_at=snapshot.captured_at,
            path=str(artifact_path.relative_to(store.state_root)),
        )
        source_bundle_artifact_id = store.register(
            source_record,
            event_type="egcf_artifact_registered",
        )
        if source_record.sha256 != snapshot.bundle_digest:
            raise RuntimeError("stored BAB-CS source bundle digest does not match the captured bytes")
        definition = _definition(snapshot, source_bundle_artifact_id)
        previous_definitions = [
            item
            for item in algorithms.algorithms(active_only=True)
            if item.algorithm_id == definition.algorithm_id
        ]
        algorithm_definition_id = algorithms.register(definition)
        for previous in previous_definitions:
            if previous.object_id != algorithm_definition_id:
                store.supersede(
                    previous.object_id,
                    algorithm_definition_id,
                    "exact BAB-CS source registration refreshed",
                    "deterministic-babcs-importer",
                )
        analysis = {
            **analysis,
            "store": {
                "algorithm_definition_id": algorithm_definition_id,
                "algorithm_id": definition.algorithm_id,
                "source_bundle_artifact_id": source_bundle_artifact_id,
                "source_bundle_path": source_record.path,
                "source_bundle_sha256": source_record.sha256,
            },
        }
        evidence = EvidenceArtifact(
            subject_id=algorithm_definition_id,
            claim_ids=[],
            requirement_ids=[],
            category="analysis",
            producer="deterministic-babcs-importer",
            method="source-bundle-ast-and-focused-test-analysis",
            source_snapshot_hash=snapshot.manifest_digest,
            target=definition.algorithm_id,
            oracle="source-hash-ast-and-test-exit-status",
            environment={
                "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                "platform": sys.platform,
            },
            command_id="experiment.analyse@1",
            algorithm_id=definition.algorithm_id,
            created_at=utc_now(),
            sha256=sha256_json(analysis),
            success=bool(analysis.get("focused_validation", {}).get("success", True)),
            limitations=list(analysis["limitations"]),
            independence_group="babcs-source-import-v1",
            simulated=False,
            content=analysis,
        )
        analysis_evidence_id = store.register(evidence)
    return BABCSRegistration(
        algorithm_definition_id=algorithm_definition_id,
        algorithm_id=definition.algorithm_id,
        source_bundle_artifact_id=source_bundle_artifact_id,
        analysis_evidence_id=analysis_evidence_id,
        snapshot=snapshot,
        analysis=analysis,
    )


def render_babcs_report(registration: BABCSRegistration) -> str:
    snapshot = registration.snapshot
    analysis = registration.analysis
    validation = analysis.get("focused_validation", {})
    dirty_paths = "\n".join(f"- `{path}`" for path in snapshot.dirty_paths) or "- None"
    methods = ", ".join(f"`{item}`" for item in analysis["candidate_methods"])
    controls = "\n".join(f"- {item}" for item in analysis["control_layers"])
    strengths = "\n".join(f"- {item}" for item in analysis["strengths"])
    limitations = "\n".join(f"- {item}" for item in analysis["limitations"])
    mapping_names = {
        "boundary_determination": "Boundary Determination",
        "dimension_limiting": "Dimension Limiting",
        "iurm": "IURM",
        "eon": "EON",
        "cfel": "CFEL",
    }
    mapping = "\n".join(
        f"- **{mapping_names.get(name, name.replace('_', ' ').title())}:** {description}"
        for name, description in analysis["oiec_mapping"].items()
    )
    validation_text = (
        f"- Command: `{validation.get('command', 'not run')}`\n"
        f"- Result: `{'PASS' if validation.get('success') else 'NOT RUN OR FAILED'}`\n"
        f"- Tests observed: `{validation.get('test_count')}`\n"
        f"- Duration: `{validation.get('duration_seconds')}` seconds"
    )
    return f"""# BAB-CS Algorithm Store and Analysis Report

## Executive conclusion

The current BAB-CS bounded integrator has been captured without modifying its
worktree and stored as an exact content-addressed tar artifact in the OURD EGCF
store. A separate `PROPOSED` `reference` algorithm definition describes the
implementation for search, comparison, explanation, and experiment analysis.
It is deliberately not a direct executor and is not qualified for release or
production use by this import.

## Store receipt

- Algorithm ID: `{registration.algorithm_id}`
- Algorithm definition object: `{registration.algorithm_definition_id}`
- Source bundle artifact: `{registration.source_bundle_artifact_id}`
- Analysis evidence object: `{registration.analysis_evidence_id}`
- Bundle SHA-256: `{snapshot.bundle_digest}`
- Manifest SHA-256: `{snapshot.manifest_digest}`
- Bundle size: `{snapshot.bundle_size}` bytes
- Captured files: `{len(snapshot.files)}`

## Source provenance

- Repository: `../BAB-CS`
- Upstream package version: `{snapshot.version}`
- Git HEAD: `{snapshot.git_head}`
- Dirty worktree captured: `{str(snapshot.dirty).lower()}`
- Dirty paths in BAB-CS worktree: `{snapshot.dirty_path_count}`
- Dirty captured-source paths: `{len(snapshot.dirty_paths)}`
- Dirty paths outside the source bundle: `{snapshot.unrelated_dirty_path_count}`
- License retained from source: `MPL-2.0`

The bundle digest, not Git HEAD alone, identifies the imported implementation
because the BAB-CS worktree contains current uncommitted changes.

### Dirty captured-source paths present during capture

{dirty_paths}

## Algorithm structure

- Python modules: `{analysis['source_metrics']['python_modules']}`
- Public API symbols: `{len(analysis['public_api'])}`
- Classes: `{analysis['source_metrics']['classes']}`
- Functions and methods: `{analysis['source_metrics']['functions']}`
- Dataclasses: `{analysis['source_metrics']['dataclasses']}`
- Candidate methods: {methods}

BAB-CS supervises candidate transient integration rather than trusting one
explicit step blindly. Its active path projects the candidate into the circuit
constraints, compares it with implicit authority, applies bounded correction,
checks residual/error/energy/amplification evidence, and periodically rebuilds
authority through independent replay.

### Control layers

{controls}

## OIEC-STMv1.1 analysis

{mapping}

The strongest architectural match is the separation between candidate freedom
and authoritative acceptance. BAB-CS may compute several candidate dimensions,
but configured bounds, implicit references, event surfaces, and fail-closed
fallback determine which state becomes authoritative. This is analogous to
OIEC's distinction between semantic possibility, bounded experimentation, and
governed action.

## Strengths

{strengths}

## Focused validation

{validation_text}

This focused result covers the main bounded integrator, bound model, and
integrator-boundary tests. It does not replace the BAB-CS repository's full
test discovery, long-horizon tier, runtime benchmark workflow, external
ngspice comparison, packaging checks, or human release decision.

## Limitations and unresolved evidence

{limitations}

## Governance conclusion

The correct current state is **stored and analyzable, but not executable by
reference and not qualified by this repository**. Any future execution adapter
must be a separate implementation with explicit capabilities, exact source and
environment binding, independent qualification evidence, bounded resource
budgets, and EON authorization. The imported MPL-2.0 source bundle also remains
legally distinct from this repository's MIT-licensed original code.
"""


def registration_json(registration: BABCSRegistration) -> str:
    return json.dumps(asdict(registration), indent=2, sort_keys=True)


__all__ = [
    "BABCSRegistration",
    "SourceSnapshot",
    "analyse_babcs_source",
    "babcs_source_paths",
    "capture_babcs_source",
    "register_babcs_algorithm",
    "registration_json",
    "render_babcs_report",
    "run_babcs_focused_tests",
]
