#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError, ProviderError
from ourd.providers import OpenAIResponsesProvider, ProviderConfig
from ourd.reasoning.benchmark import (
    benchmark_json,
    build_source_manifest,
    load_benchmark_tasks,
    repository_git_state,
    run_benchmark,
)
from ourd.reasoning.model_benchmark import (
    MODEL_EXECUTION_MODE,
    MODEL_QUALIFICATION_STATUS,
    make_model_benchmark_executors,
)
from ourd.reasoning.models import stable_hash


DEFAULT_BENCHMARK_ROOT = ROOT / "benchmarks" / "reasoning"
DEFAULT_SOURCE_PATHS = (
    "pyproject.toml",
    "ourd/agent.py",
    "ourd/cfel.py",
    "ourd/models.py",
    "ourd/oiec.py",
    "ourd/persistence.py",
    "ourd/providers/base.py",
    "ourd/providers/openai_responses.py",
    "ourd/reasoning/models.py",
    "ourd/reasoning/topology.py",
    "ourd/reasoning/generator.py",
    "ourd/reasoning/hypotheses.py",
    "ourd/reasoning/verifier.py",
    "ourd/reasoning/falsifier.py",
    "ourd/reasoning/scoring.py",
    "ourd/reasoning/search.py",
    "ourd/reasoning/budget.py",
    "ourd/reasoning/kernel.py",
    "ourd/reasoning/benchmark.py",
    "ourd/reasoning/model_benchmark.py",
    "tools/run_reasoning_benchmark.py",
    "tools/run_reasoning_model_benchmark.py",
    "benchmarks/reasoning/README.md",
    "benchmarks/reasoning/schema.json",
    "benchmarks/reasoning/tasks/development-v1.jsonl",
    "benchmarks/reasoning/models/qwen3.8-27b-benchmark-4k.Modelfile",
)


def project_version(root: Path) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Run a source-, provider-, model-, and hardware-bound OIEC-SR benchmark."
    )
    value.add_argument("--root", type=Path, default=ROOT)
    value.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    value.add_argument("--date", required=True, help="Fixed YYYY-MM-DD result date")
    value.add_argument("--model", default="qwen2.5:14b")
    value.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    value.add_argument("--api-key", default="")
    value.add_argument("--reasoning-effort", default="")
    value.add_argument("--context-budget-tokens", type=int, default=2000)
    value.add_argument("--max-output-tokens", type=int, default=2048)
    value.add_argument("--timeout-seconds", type=float, default=600.0)
    value.add_argument("--max-reasoning-samples", type=int, default=16)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate exact provider and model identity without executing tasks.",
    )
    return value


def _write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path = path.with_suffix(".sha256")
    if path.exists() or checksum_path.exists():
        raise PolicyError(f"model benchmark artifact already exists: {path}")
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with checksum_path.open("x", encoding="utf-8") as handle:
            handle.write(f"{checksum}  {path.name}\n")
    except (FileExistsError, OSError) as exc:
        if path.exists() and not checksum_path.exists():
            path.unlink()
        raise PolicyError(f"cannot create model benchmark artifact: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    benchmark_root = args.benchmark_root.resolve()
    output = args.output.resolve()
    deterministic_baseline = (benchmark_root / "baseline-v1.json").resolve()
    try:
        if output == deterministic_baseline:
            raise PolicyError("model benchmark must not overwrite baseline-v1.json")
        config = ProviderConfig(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
            context_budget_tokens=args.context_budget_tokens,
            timeout_seconds=args.timeout_seconds,
            max_transport_retries=0,
            max_reasoning_samples=args.max_reasoning_samples,
        )

        def provider_factory():
            return OpenAIResponsesProvider(config)

        git_head, worktree_dirty = repository_git_state(root)
        source_files = build_source_manifest(root, DEFAULT_SOURCE_PATHS)
        source_snapshot_hash = stable_hash(
            [{"path": item.path, "sha256": item.sha256} for item in source_files]
        )
        executors = make_model_benchmark_executors(
            provider_factory=provider_factory,
            source_snapshot_hash=source_snapshot_hash,
        )
        if args.preflight_only:
            for executor in executors:
                identity = executor.identity_descriptor()
                binding = identity["provider_binding"]
                print(
                    f"{executor.system_id}: {binding['provider']} {binding['model']} "
                    f"digest={binding['model_digest']} profile={binding['signature']}"
                )
            return 0
        tasks = load_benchmark_tasks(benchmark_root / "tasks")
        run = run_benchmark(
            tasks=tasks,
            executors=executors,
            generated_on=args.date,
            package_version=project_version(root),
            git_head=git_head,
            worktree_dirty=worktree_dirty,
            source_files=source_files,
            execution_mode=MODEL_EXECUTION_MODE,
            qualification_status=MODEL_QUALIFICATION_STATUS,
        )
        _write_new(output, benchmark_json(run))
        print(
            f"wrote {output}: tasks={run.task_count} results={len(run.results)} "
            f"signature={run.signature}"
        )
        return 0
    except (OSError, ValueError, KeyError, PolicyError, ProviderError) as exc:
        print(f"model reasoning benchmark failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
