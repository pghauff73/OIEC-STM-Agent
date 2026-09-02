#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import BenchmarkTask, load_benchmark_tasks
from ourd.reasoning.models import stable_hash
from ourd.reasoning.qualification import REQUIRED_QUALIFICATION_CATEGORIES


ABLATION_CORPUS_ID = "qualification-ablation-v1"
ABLATION_CLASS_COUNT = 10
DEFAULT_PARENT = ROOT / "benchmarks/reasoning/tasks/qualification-v2.jsonl"
DEFAULT_OUTPUT = ROOT / "benchmarks/reasoning/tasks/qualification-ablation-v1.jsonl"
DEFAULT_MANIFEST = (
    ROOT / "benchmarks/reasoning/tasks/qualification-ablation-v1.manifest.json"
)


def select_ablation_tasks(
    tasks: tuple[BenchmarkTask, ...],
    *,
    class_count: int = ABLATION_CLASS_COUNT,
) -> tuple[BenchmarkTask, ...]:
    if class_count < 1:
        raise PolicyError("ablation class count must be positive")
    selected = []
    for category in REQUIRED_QUALIFICATION_CATEGORIES:
        candidates = [task for task in tasks if task.category == category]
        if len(candidates) < class_count:
            raise PolicyError(f"ablation parent corpus has too few {category} tasks")
        if len(candidates) % class_count:
            raise PolicyError(f"ablation parent corpus cannot form {category} blocks")
        block_count = len(candidates) // class_count
        block_index = int(
            stable_hash(
                {
                    "corpus_id": ABLATION_CORPUS_ID,
                    "category": category,
                    "class_count": class_count,
                }
            ),
            16,
        ) % block_count
        start = block_index * class_count
        selected.extend(candidates[start : start + class_count])
    selected_ids = {task.problem_id for task in selected}
    return tuple(
        task for task in tasks if task.problem_id in selected_ids
    )


def parent_shards(
    parent_tasks: tuple[BenchmarkTask, ...],
    selected_tasks: tuple[BenchmarkTask, ...],
) -> tuple[dict[str, int | str], ...]:
    index_by_id = {task.problem_id: index for index, task in enumerate(parent_tasks)}
    shards = []
    for category in REQUIRED_QUALIFICATION_CATEGORIES:
        selected = [task for task in selected_tasks if task.category == category]
        indexes = [index_by_id[task.problem_id] for task in selected]
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            raise PolicyError(f"ablation {category} selection is not one parent shard")
        shards.append(
            {
                "category": category,
                "start": indexes[0],
                "count": len(indexes),
                "shard_index": indexes[0] // len(indexes),
            }
        )
    return tuple(shards)


def render_tasks(tasks: tuple[BenchmarkTask, ...]) -> str:
    rows = []
    for task in tasks:
        payload = asdict(task)
        payload.pop("signature", None)
        rows.append(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        )
    return "".join(rows)


def build_manifest(
    *,
    parent: Path,
    output: Path,
    tasks: tuple[BenchmarkTask, ...],
    content: str,
) -> dict:
    parent_tasks = load_benchmark_tasks(parent)
    counts = Counter(task.category for task in tasks)
    return {
        "schema_version": 1,
        "qualification_status": "held_out_ablation_frozen_before_live_scoring",
        "corpus_id": ABLATION_CORPUS_ID,
        "task_file": output.relative_to(ROOT).as_posix()
        if output.is_relative_to(ROOT)
        else str(output),
        "task_file_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "task_count": len(tasks),
        "class_count": ABLATION_CLASS_COUNT,
        "classes": list(REQUIRED_QUALIFICATION_CATEGORIES),
        "class_counts": dict(sorted(counts.items())),
        "parent_task_file": parent.relative_to(ROOT).as_posix()
        if parent.is_relative_to(ROOT)
        else str(parent),
        "parent_task_file_sha256": hashlib.sha256(parent.read_bytes()).hexdigest(),
        "parent_task_count": len(parent_tasks),
        "parent_shards": list(parent_shards(parent_tasks, tasks)),
        "selection_rule": (
            "per category, choose one parent-order block of class_count tasks using "
            "SHA-256({corpus_id,category,class_count}) modulo available blocks; "
            "preserve parent order"
        ),
        "performance_claim_allowed": False,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Build the frozen deterministic held-out SR ablation corpus."
    )
    value.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    value.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    value.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        parent = args.parent.resolve()
        output = args.output.resolve()
        manifest_path = args.manifest.resolve()
        tasks = select_ablation_tasks(load_benchmark_tasks(parent))
        content = render_tasks(tasks)
        manifest = build_manifest(
            parent=parent,
            output=output,
            tasks=tasks,
            content=content,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {len(tasks)} ablation tasks: {manifest['task_file_sha256']}")
        return 0
    except (OSError, ValueError, KeyError, PolicyError) as exc:
        print(f"ablation task build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
