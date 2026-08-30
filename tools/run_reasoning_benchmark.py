#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import (
    BENCHMARK_SYSTEM_IDS,
    FixtureBenchmarkExecutor,
    benchmark_json,
    build_source_manifest,
    load_benchmark_tasks,
    load_benchmark_run,
    load_fixture_observations,
    repository_git_state,
    run_benchmark,
    verify_benchmark_checksum,
    write_benchmark_run,
)


DEFAULT_BENCHMARK_ROOT = ROOT / "benchmarks" / "reasoning"
DEFAULT_SOURCE_PATHS = (
    "pyproject.toml",
    "ourd/agent.py",
    "ourd/oiec.py",
    "ourd/providers/base.py",
    "ourd/providers/openai_responses.py",
    "ourd/reasoning/models.py",
    "ourd/reasoning/topology.py",
    "ourd/reasoning/generator.py",
    "ourd/reasoning/verifier.py",
    "ourd/reasoning/falsifier.py",
    "ourd/reasoning/scoring.py",
    "ourd/reasoning/search.py",
    "ourd/reasoning/budget.py",
    "ourd/reasoning/kernel.py",
    "ourd/reasoning/benchmark.py",
    "tools/run_reasoning_benchmark.py",
    "benchmarks/reasoning/README.md",
    "benchmarks/reasoning/schema.json",
    "benchmarks/reasoning/tasks/development-v1.jsonl",
    "benchmarks/reasoning/fixtures/development-v1.outputs.json",
)


def project_version(root: Path) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def build_fixture_baseline(
    *,
    root: Path,
    benchmark_root: Path,
    generated_on: str,
):
    tasks = load_benchmark_tasks(benchmark_root / "tasks")
    observations = load_fixture_observations(
        benchmark_root / "fixtures" / "development-v1.outputs.json",
        tasks,
    )
    executors = tuple(
        FixtureBenchmarkExecutor(system_id, observations[system_id])
        for system_id in BENCHMARK_SYSTEM_IDS
    )
    git_head, worktree_dirty = repository_git_state(root)
    source_files = build_source_manifest(root, DEFAULT_SOURCE_PATHS)
    return run_benchmark(
        tasks=tasks,
        executors=executors,
        generated_on=generated_on,
        package_version=project_version(root),
        git_head=git_head,
        worktree_dirty=worktree_dirty,
        source_files=source_files,
    )


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Generate or verify the deterministic OIEC-SR SR-0 baseline."
    )
    value.add_argument("--root", type=Path, default=ROOT)
    value.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    value.add_argument("--date", required=True, help="Fixed YYYY-MM-DD result date")
    value.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_BENCHMARK_ROOT / "baseline-v1.json",
    )
    value.add_argument(
        "--check",
        action="store_true",
        help="Verify the recorded artifact's internal signature and pinned checksum.",
    )
    value.add_argument(
        "--check-current-source",
        action="store_true",
        help="Also require byte-identical regeneration from the current source tree.",
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    benchmark_root = args.benchmark_root.resolve()
    output = args.output.resolve()
    try:
        if args.check:
            if not output.is_file():
                raise PolicyError(f"benchmark baseline is missing: {output}")
            recorded = load_benchmark_run(output)
            checksum_path = output.with_suffix(".sha256")
            checksum = verify_benchmark_checksum(output, checksum_path)
            if args.check_current_source:
                current = build_fixture_baseline(
                    root=root,
                    benchmark_root=benchmark_root,
                    generated_on=args.date,
                )
                if output.read_text(encoding="utf-8") != benchmark_json(current):
                    raise PolicyError(
                        "recorded baseline is internally valid but source drift prevents current regeneration"
                    )
            print(
                f"verified {output}: signature={recorded.signature} sha256={checksum}"
            )
            return 0
        run = build_fixture_baseline(
            root=root,
            benchmark_root=benchmark_root,
            generated_on=args.date,
        )
        write_benchmark_run(output, run)
        print(
            f"wrote {output}: tasks={run.task_count} results={len(run.results)} "
            f"signature={run.signature}"
        )
        return 0
    except (OSError, ValueError, KeyError, PolicyError) as exc:
        print(f"reasoning benchmark failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
