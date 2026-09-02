#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import (
    benchmark_json,
    load_benchmark_run,
    load_benchmark_tasks,
    merge_benchmark_runs,
)


DEFAULT_BENCHMARK_ROOT = ROOT / "benchmarks" / "reasoning"


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Merge complete ordered OIEC-SR benchmark shards without rerunning tasks."
    )
    value.add_argument("shards", nargs="+", type=Path)
    value.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    value.add_argument(
        "--task-file",
        type=Path,
        default=Path("tasks/qualification-v2.jsonl"),
        help="Complete task file relative to --benchmark-root, or an absolute path.",
    )
    value.add_argument("--output", required=True, type=Path)
    return value


def _write_new(path: Path, content: str) -> None:
    checksum_path = path.with_suffix(".sha256")
    if path.exists() or checksum_path.exists():
        raise PolicyError(f"merged benchmark artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with checksum_path.open("x", encoding="utf-8") as handle:
            handle.write(f"{checksum}  {path.name}\n")
    except (FileExistsError, OSError) as exc:
        if path.exists() and not checksum_path.exists():
            path.unlink()
        raise PolicyError(f"cannot create merged benchmark artifact: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    benchmark_root = args.benchmark_root.resolve()
    task_file = args.task_file
    if not task_file.is_absolute():
        task_file = benchmark_root / task_file
    try:
        tasks = load_benchmark_tasks(task_file)
        shards = tuple(load_benchmark_run(path.resolve()) for path in args.shards)
        merged = merge_benchmark_runs(shards=shards, tasks=tasks)
        output = args.output.resolve()
        _write_new(output, benchmark_json(merged))
        print(
            f"wrote {output}: shards={len(shards)} tasks={merged.task_count} "
            f"signature={merged.signature}"
        )
        return 0
    except (OSError, ValueError, KeyError, PolicyError) as exc:
        print(f"benchmark shard merge failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
