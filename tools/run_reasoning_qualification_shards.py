#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import (
    BENCHMARK_SYSTEM_IDS,
    HELD_OUT_MODEL_QUALIFICATION_STATUS,
    benchmark_json,
    build_source_manifest,
    load_benchmark_run,
    load_benchmark_tasks,
    merge_benchmark_runs,
    repository_git_state,
    verify_benchmark_checksum,
)
from ourd.reasoning.models import stable_hash
from tools.run_reasoning_model_benchmark import (
    DEFAULT_BENCHMARK_ROOT,
    DEFAULT_SOURCE_PATHS,
    parser as model_benchmark_parser,
)


CONTROLLED_BENCHMARK_FLAGS = {
    "--root",
    "--benchmark-root",
    "--task-file",
    "--task-start",
    "--task-count",
    "--qualification-status",
    "--output",
    "--preflight-only",
}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "Run or resume checksum-bound held-out model qualification shards, "
            "then merge only exact complete coverage."
        )
    )
    value.add_argument("--root", type=Path, default=ROOT)
    value.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    value.add_argument(
        "--task-file",
        type=Path,
        default=Path("tasks/qualification-v2.jsonl"),
    )
    value.add_argument("--run-dir", required=True, type=Path)
    value.add_argument("--shard-size", type=int, default=10)
    value.add_argument(
        "--max-new-shards",
        type=int,
        help="Execute at most this many missing shards before a clean resumable stop.",
    )
    value.add_argument("--merged-name", default="merged.json")
    value.add_argument(
        "--benchmark-runner",
        type=Path,
        default=ROOT / "tools" / "run_reasoning_model_benchmark.py",
    )
    value.add_argument(
        "benchmark_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded after -- to run_reasoning_model_benchmark.py.",
    )
    return value


def build_shard_specs(task_count: int, shard_size: int) -> tuple[dict[str, Any], ...]:
    if task_count < 1 or shard_size < 1:
        raise PolicyError("qualification task count and shard size must be positive")
    return tuple(
        {
            "index": index,
            "start": start,
            "count": min(shard_size, task_count - start),
            "path": f"shards/shard-{index:03d}.json",
        }
        for index, start in enumerate(range(0, task_count, shard_size))
    )


def normalized_benchmark_args(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(values[1:] if values and values[0] == "--" else values)
    if not result:
        raise PolicyError("qualification controller requires forwarded benchmark arguments")
    for value in result:
        flag = value.split("=", 1)[0]
        if flag in CONTROLLED_BENCHMARK_FLAGS:
            raise PolicyError(f"qualification controller owns benchmark flag: {flag}")
        if flag == "--api-key":
            raise PolicyError("qualification controller does not persist API credentials")
    return result


def _write_new(path: Path, content: str) -> str:
    checksum_path = path.with_suffix(".sha256")
    if path.exists() or checksum_path.exists():
        raise PolicyError(f"qualification artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        with checksum_path.open("x", encoding="utf-8") as handle:
            handle.write(f"{checksum}  {path.name}\n")
    except (FileExistsError, OSError) as exc:
        if path.exists() and not checksum_path.exists():
            path.unlink()
        raise PolicyError(f"cannot create qualification artifact: {path}") from exc
    return checksum


def _task_ids(run) -> tuple[str, ...]:
    values = tuple(
        result.problem_id for result in run.results if result.system_id == "base"
    )
    if len(values) != run.task_count:
        raise PolicyError("qualification shard task identity is incomplete")
    return values


def _run_identity(run) -> str:
    return stable_hash(
        [
            {key: value for key, value in descriptor.items() if key != "telemetry"}
            for descriptor in run.systems
        ]
    )


def validate_shard_run(
    *,
    path: Path,
    spec: Mapping[str, Any],
    tasks: Sequence[Any],
    source_manifest_hash: str,
    generated_on: str,
    expected_identity: str = "",
):
    checksum_path = path.with_suffix(".sha256")
    if path.exists() != checksum_path.exists():
        raise PolicyError(f"qualification shard is incomplete: {path}")
    verify_benchmark_checksum(path, checksum_path)
    run = load_benchmark_run(path)
    start = int(spec["start"])
    count = int(spec["count"])
    expected_tasks = tuple(task.problem_id for task in tasks[start : start + count])
    if run.task_count != count or _task_ids(run) != expected_tasks:
        raise PolicyError(f"qualification shard task range mismatch: {path}")
    if run.generated_on != generated_on:
        raise PolicyError(f"qualification shard date mismatch: {path}")
    if run.execution_mode != "provider_bound":
        raise PolicyError(f"qualification shard is not provider-bound: {path}")
    if run.qualification_status != HELD_OUT_MODEL_QUALIFICATION_STATUS:
        raise PolicyError(f"qualification shard is not held-out evidence: {path}")
    if run.source_manifest_hash != source_manifest_hash:
        raise PolicyError(f"qualification shard source drift detected: {path}")
    if any(
        int(descriptor["telemetry"]["provider_failures"]) != 0
        for descriptor in run.systems
    ):
        raise PolicyError(f"qualification shard contains provider failures: {path}")
    identity = _run_identity(run)
    if expected_identity and identity != expected_identity:
        raise PolicyError(f"qualification shard provider/runtime drift detected: {path}")
    return run, identity


def controller_manifest(
    *,
    root: Path,
    benchmark_root: Path,
    task_file: Path,
    run_dir: Path,
    shard_size: int,
    merged_name: str,
    benchmark_runner: Path,
    benchmark_args: Sequence[str],
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    if Path(merged_name).name != merged_name or not merged_name.endswith(".json"):
        raise PolicyError("merged benchmark name must be one JSON filename")
    tasks = load_benchmark_tasks(task_file)
    source_files = build_source_manifest(root, DEFAULT_SOURCE_PATHS)
    source_manifest_hash = stable_hash(
        [asdict(item) for item in source_files]
    )
    git_head, worktree_dirty = repository_git_state(root)
    parsed = model_benchmark_parser().parse_args(
        [
            *benchmark_args,
            "--root",
            str(root),
            "--benchmark-root",
            str(benchmark_root),
            "--task-file",
            str(task_file),
            "--task-start",
            "0",
            "--task-count",
            "1",
            "--qualification-status",
            HELD_OUT_MODEL_QUALIFICATION_STATUS,
            "--output",
            str(run_dir / ".controller-validation-unused.json"),
        ]
    )
    specs = build_shard_specs(len(tasks), shard_size)
    material = {
        "schema_version": 1,
        "generated_on": parsed.date,
        "git_head": git_head,
        "worktree_dirty": worktree_dirty,
        "source_manifest_hash": source_manifest_hash,
        "source_files": [asdict(item) for item in source_files],
        "task_file": task_file.relative_to(root).as_posix()
        if task_file.is_relative_to(root)
        else str(task_file),
        "task_file_sha256": hashlib.sha256(task_file.read_bytes()).hexdigest(),
        "task_signatures": [task.signature for task in tasks],
        "task_count": len(tasks),
        "shard_size": shard_size,
        "shards": list(specs),
        "merged_name": merged_name,
        "benchmark_runner_sha256": hashlib.sha256(benchmark_runner.read_bytes()).hexdigest(),
        "benchmark_args": list(benchmark_args),
        "qualification_status": HELD_OUT_MODEL_QUALIFICATION_STATUS,
    }
    return {**material, "signature": stable_hash(material)}, tasks


def _load_or_create_manifest(path: Path, expected: Mapping[str, Any]) -> None:
    checksum_path = path.with_suffix(".sha256")
    if path.exists() or checksum_path.exists():
        if not path.exists() or not checksum_path.exists():
            raise PolicyError("qualification controller manifest is incomplete")
        verify_benchmark_checksum(path, checksum_path)
        actual = json.loads(path.read_text(encoding="utf-8"))
        if actual != expected:
            raise PolicyError("qualification controller manifest drift detected")
        return
    _write_new(
        path,
        json.dumps(expected, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _next_log_path(log_dir: Path, index: int) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while True:
        candidate = log_dir / f"shard-{index:03d}-attempt-{attempt:03d}.log"
        if not candidate.exists():
            return candidate
        attempt += 1


def _run_shard(
    *,
    benchmark_runner: Path,
    benchmark_args: Sequence[str],
    root: Path,
    benchmark_root: Path,
    task_file: Path,
    run_dir: Path,
    spec: Mapping[str, Any],
) -> None:
    output = run_dir / str(spec["path"])
    log_path = _next_log_path(run_dir / "logs", int(spec["index"]))
    command = [
        sys.executable,
        str(benchmark_runner),
        *benchmark_args,
        "--root",
        str(root),
        "--benchmark-root",
        str(benchmark_root),
        "--task-file",
        str(task_file),
        "--task-start",
        str(spec["start"]),
        "--task-count",
        str(spec["count"]),
        "--qualification-status",
        HELD_OUT_MODEL_QUALIFICATION_STATUS,
        "--output",
        str(output),
    ]
    print(
        f"running shard {int(spec['index']) + 1}: "
        f"tasks {spec['start']}..{int(spec['start']) + int(spec['count']) - 1}"
    )
    with log_path.open("x", encoding="utf-8") as handle:
        handle.write(f"command={shlex.join(command)}\n")
        handle.flush()
        completed = subprocess.run(
            command,
            cwd=root,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        handle.write(f"exit_code={completed.returncode}\n")
    if completed.returncode != 0:
        raise PolicyError(f"qualification shard failed; inspect {log_path}")


def _write_completion(
    *,
    path: Path,
    manifest: Mapping[str, Any],
    shard_paths: Sequence[Path],
    merged_path: Path,
    merged,
) -> None:
    material = {
        "schema_version": 1,
        "controller_manifest_signature": manifest["signature"],
        "source_manifest_hash": manifest["source_manifest_hash"],
        "shard_sha256": [
            {
                "path": shard.relative_to(path.parent).as_posix(),
                "sha256": hashlib.sha256(shard.read_bytes()).hexdigest(),
            }
            for shard in shard_paths
        ],
        "merged_path": merged_path.relative_to(path.parent).as_posix(),
        "merged_sha256": hashlib.sha256(merged_path.read_bytes()).hexdigest(),
        "merged_benchmark_signature": merged.signature,
    }
    payload = {**material, "signature": stable_hash(material)}
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists() or path.with_suffix(".sha256").exists():
        verify_benchmark_checksum(path, path.with_suffix(".sha256"))
        if path.read_text(encoding="utf-8") != content:
            raise PolicyError("qualification completion artifact drift detected")
        return
    _write_new(path, content)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = args.root.resolve()
        benchmark_root = args.benchmark_root.resolve()
        task_file = args.task_file
        if not task_file.is_absolute():
            task_file = benchmark_root / task_file
        task_file = task_file.resolve()
        run_dir = args.run_dir.resolve()
        benchmark_runner = args.benchmark_runner.resolve()
        benchmark_args = normalized_benchmark_args(args.benchmark_args)
        if args.max_new_shards is not None and args.max_new_shards < 1:
            raise PolicyError("max-new-shards must be positive")
        manifest, tasks = controller_manifest(
            root=root,
            benchmark_root=benchmark_root,
            task_file=task_file,
            run_dir=run_dir,
            shard_size=args.shard_size,
            merged_name=args.merged_name,
            benchmark_runner=benchmark_runner,
            benchmark_args=benchmark_args,
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        _load_or_create_manifest(run_dir / "controller-manifest.json", manifest)

        expected_identity = ""
        completed_runs = {}
        missing_specs = []
        for spec in manifest["shards"]:
            shard_path = run_dir / str(spec["path"])
            if not shard_path.exists() and not shard_path.with_suffix(".sha256").exists():
                missing_specs.append(spec)
                continue
            run, identity = validate_shard_run(
                path=shard_path,
                spec=spec,
                tasks=tasks,
                source_manifest_hash=str(manifest["source_manifest_hash"]),
                generated_on=str(manifest["generated_on"]),
                expected_identity=expected_identity,
            )
            expected_identity = expected_identity or identity
            completed_runs[int(spec["index"])] = run

        limit = args.max_new_shards
        for offset, spec in enumerate(missing_specs):
            if limit is not None and offset >= limit:
                break
            _run_shard(
                benchmark_runner=benchmark_runner,
                benchmark_args=benchmark_args,
                root=root,
                benchmark_root=benchmark_root,
                task_file=task_file,
                run_dir=run_dir,
                spec=spec,
            )
            shard_path = run_dir / str(spec["path"])
            run, identity = validate_shard_run(
                path=shard_path,
                spec=spec,
                tasks=tasks,
                source_manifest_hash=str(manifest["source_manifest_hash"]),
                generated_on=str(manifest["generated_on"]),
                expected_identity=expected_identity,
            )
            expected_identity = expected_identity or identity
            completed_runs[int(spec["index"])] = run

        if len(completed_runs) != len(manifest["shards"]):
            print(
                f"qualification pending: completed={len(completed_runs)} "
                f"total={len(manifest['shards'])}"
            )
            return 0

        ordered_runs = tuple(completed_runs[index] for index in range(len(completed_runs)))
        merged = merge_benchmark_runs(shards=ordered_runs, tasks=tasks)
        merged_path = run_dir / str(manifest["merged_name"])
        merged_content = benchmark_json(merged)
        if merged_path.exists() or merged_path.with_suffix(".sha256").exists():
            verify_benchmark_checksum(merged_path, merged_path.with_suffix(".sha256"))
            if merged_path.read_text(encoding="utf-8") != merged_content:
                raise PolicyError("qualification merged artifact drift detected")
        else:
            _write_new(merged_path, merged_content)
        shard_paths = tuple(
            run_dir / str(spec["path"]) for spec in manifest["shards"]
        )
        _write_completion(
            path=run_dir / "completion.json",
            manifest=manifest,
            shard_paths=shard_paths,
            merged_path=merged_path,
            merged=merged,
        )
        print(
            f"qualification complete: tasks={merged.task_count} "
            f"signature={merged.signature}"
        )
        return 0
    except (OSError, ValueError, KeyError, PolicyError) as exc:
        print(f"qualification shard controller failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
