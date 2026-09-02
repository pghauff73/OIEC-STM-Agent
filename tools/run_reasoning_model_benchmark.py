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
from ourd.providers import ProviderConfig, create_provider
from ourd.reasoning.ablation import REQUIRED_ABLATIONS, standard_ablation_configurations
from ourd.reasoning.benchmark import (
    benchmark_json,
    build_source_manifest,
    load_benchmark_tasks,
    repository_git_state,
    run_benchmark,
    select_benchmark_tasks,
)
from ourd.reasoning.model_benchmark import (
    MODEL_EXECUTION_MODE,
    MODEL_HELD_OUT_QUALIFICATION_STATUS,
    MODEL_QUALIFICATION_STATUS,
    close_model_benchmark_executors,
    make_model_benchmark_executors,
)
from ourd.reasoning.models import stable_hash


DEFAULT_BENCHMARK_ROOT = ROOT / "benchmarks" / "reasoning"


def default_source_paths(root: Path) -> tuple[str, ...]:
    paths = {
        "README.md",
        "pyproject.toml",
        "tools/build_reasoning_qualification_tasks.py",
        "tools/build_reasoning_ablation_manifest.py",
        "tools/build_reasoning_ablation_tasks.py",
        "tools/qualify_reasoning_runs.py",
        "tools/run_reasoning_benchmark.py",
        "tools/merge_reasoning_benchmark_shards.py",
        "tools/run_reasoning_qualification_shards.py",
        "tools/run_reasoning_model_benchmark.py",
        "benchmarks/reasoning/README.md",
        "benchmarks/reasoning/schema.json",
    }
    for directory in ("ourd", "ourd/providers", "ourd/reasoning"):
        paths.update(
            path.relative_to(root).as_posix()
            for path in (root / directory).glob("*.py")
            if path.is_file()
        )
    for directory in (
        "benchmarks/reasoning/models",
        "benchmarks/reasoning/tasks",
        "grammars/providers",
        "native/oiec_llama_runner",
        "schemas/providers",
    ):
        paths.update(
            path.relative_to(root).as_posix()
            for path in (root / directory).rglob("*")
            if path.is_file()
        )
    return tuple(sorted(paths))


DEFAULT_SOURCE_PATHS = default_source_paths(ROOT)


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
    value.add_argument(
        "--provider",
        choices=("llama_cpp_process",),
        default="llama_cpp_process",
    )
    value.add_argument("--base-url", default="")
    value.add_argument("--api-key", default="")
    value.add_argument("--reasoning-effort", default="")
    value.add_argument(
        "--json-object-output",
        action="store_true",
        help="Deprecated compatibility flag; direct process output is grammar-first JSON.",
    )
    value.add_argument("--response-temperature-bp", type=int, default=-1)
    value.add_argument("--response-top-p-bp", type=int, default=-1)
    value.add_argument("--response-seed", type=int, default=-1)
    value.add_argument("--context-budget-tokens", type=int, default=2000)
    value.add_argument("--max-output-tokens", type=int, default=2048)
    value.add_argument("--timeout-seconds", type=float, default=600.0)
    value.add_argument("--max-reasoning-samples", type=int, default=16)
    value.add_argument(
        "--task-file",
        type=Path,
        default=Path("tasks/development-v1.jsonl"),
        help="Task file relative to --benchmark-root, or an absolute path.",
    )
    value.add_argument(
        "--task-start",
        type=int,
        default=0,
        help="Zero-based first task index for a deterministic resumable shard.",
    )
    value.add_argument(
        "--task-count",
        type=int,
        help="Number of contiguous tasks in this shard; omitted means all remaining tasks.",
    )
    value.add_argument("--ablation", choices=REQUIRED_ABLATIONS, default="full_sr")
    value.add_argument(
        "--qualification-status",
        choices=(MODEL_QUALIFICATION_STATUS, MODEL_HELD_OUT_QUALIFICATION_STATUS),
        default=MODEL_QUALIFICATION_STATUS,
        help=(
            "Label provider-bound output as development plumbing or as a held-out "
            "qualification candidate. Neither status grants performance authority."
        ),
    )
    value.add_argument("--runner-path", default="")
    value.add_argument("--model-path", default="")
    value.add_argument("--expected-model-sha256", default="")
    value.add_argument("--llama-cpp-root", default="")
    value.add_argument("--llama-cpp-build-dir", default="")
    value.add_argument("--llama-grammar-dir", default="")
    value.add_argument("--llama-context", type=int, default=8192)
    value.add_argument("--llama-gpu-layers", type=int, default=-1)
    value.add_argument("--llama-threads", type=int, default=0)
    value.add_argument("--llama-seed", type=int, default=1234)
    value.add_argument("--llama-temperature-bp", type=int, default=1000)
    value.add_argument("--llama-top-p-bp", type=int, default=9500)
    value.add_argument("--llama-top-k", type=int, default=40)
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
            provider_kind=args.provider,
            base_url=args.base_url,
            api_key=args.api_key,
            reasoning_effort=args.reasoning_effort,
            json_object_output=args.json_object_output,
            response_temperature_bp=args.response_temperature_bp,
            response_top_p_bp=args.response_top_p_bp,
            response_seed=args.response_seed,
            max_output_tokens=args.max_output_tokens,
            context_budget_tokens=args.context_budget_tokens,
            timeout_seconds=args.timeout_seconds,
            max_transport_retries=0,
            max_reasoning_samples=args.max_reasoning_samples,
            runner_path=args.runner_path,
            model_path=args.model_path,
            expected_model_sha256=args.expected_model_sha256,
            llama_cpp_root=args.llama_cpp_root,
            llama_cpp_build_dir=args.llama_cpp_build_dir,
            llama_grammar_dir=args.llama_grammar_dir,
            llama_context_tokens=args.llama_context,
            llama_gpu_layers=args.llama_gpu_layers,
            llama_threads=args.llama_threads,
            llama_seed=args.llama_seed,
            llama_temperature_bp=args.llama_temperature_bp,
            llama_top_p_bp=args.llama_top_p_bp,
            llama_top_k=args.llama_top_k,
        )

        def provider_factory():
            return create_provider(config)

        ablation = next(
            item
            for item in standard_ablation_configurations()
            if item.ablation_id == args.ablation
        )

        git_head, worktree_dirty = repository_git_state(root)
        source_files = build_source_manifest(root, DEFAULT_SOURCE_PATHS)
        source_snapshot_hash = stable_hash(
            [{"path": item.path, "sha256": item.sha256} for item in source_files]
        )
        executors = make_model_benchmark_executors(
            provider_factory=provider_factory,
            source_snapshot_hash=source_snapshot_hash,
            ablation=ablation,
        )
        try:
            if args.preflight_only:
                for executor in executors:
                    identity = executor.identity_descriptor()
                    binding = identity["provider_binding"]
                    print(
                        f"{executor.system_id}: {binding['provider']} {binding['model']} "
                        f"digest={binding['model_digest']} profile={binding['signature']}"
                    )
                return 0
            task_file = args.task_file
            if not task_file.is_absolute():
                task_file = benchmark_root / task_file
            all_tasks = load_benchmark_tasks(task_file)
            tasks = select_benchmark_tasks(
                all_tasks,
                start=args.task_start,
                count=args.task_count,
            )
            run = run_benchmark(
                tasks=tasks,
                executors=executors,
                generated_on=args.date,
                package_version=project_version(root),
                git_head=git_head,
                worktree_dirty=worktree_dirty,
                source_files=source_files,
                execution_mode=MODEL_EXECUTION_MODE,
                qualification_status=args.qualification_status,
            )
        finally:
            close_model_benchmark_executors(executors)
        _write_new(output, benchmark_json(run))
        print(
            f"wrote {output}: task_start={args.task_start} tasks={run.task_count} "
            f"results={len(run.results)} "
            f"signature={run.signature}"
        )
        return 0
    except (OSError, ValueError, KeyError, PolicyError, ProviderError) as exc:
        print(f"model reasoning benchmark failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
