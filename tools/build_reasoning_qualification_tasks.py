from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


CLASS_COUNT = 100
QUALIFICATION_CLASSES = (
    "logic",
    "arithmetic",
    "debugging",
    "scientific_inference",
    "causal_reasoning",
    "adversarial",
)


def _task(
    *,
    problem_id: str,
    category: str,
    prompt: str,
    expected: str,
    oracle_kind: str = "exact",
    oracle_method: str,
    evidence_ids: Iterable[str] = (),
    counterexamples: Iterable[str] = (),
    source_refs: Iterable[str] = (),
) -> dict:
    return {
        "schema_version": 1,
        "problem_id": problem_id,
        "category": category,
        "prompt": prompt,
        "oracle": {"kind": oracle_kind, "expected": expected},
        "oracle_method": oracle_method,
        "required_evidence_ids": list(evidence_ids),
        "required_counterexamples": list(counterexamples),
        "source_refs": list(source_refs),
    }


def build_tasks(*, task_version: int = 1) -> tuple[dict, ...]:
    if task_version not in {1, 2}:
        raise ValueError("qualification task version must be 1 or 2")
    tasks = []
    for index in range(1, CLASS_COUNT + 1):
        tasks.append(
            _task(
                problem_id=f"qualification-logic-{index:03d}",
                category="logic",
                prompt=(
                    f"Rule {index}: every governed mutation requires an EON action. "
                    f"Candidate {index} has no EON action. Is the mutation permitted?"
                ),
                expected="no",
                oracle_method="Apply the stated necessary condition by modus tollens.",
                evidence_ids=(f"qualification:logic:eon:{index:03d}",),
                source_refs=("README.md",),
            )
        )
        left = index + 3
        right = (index % 17) + 2
        offset = index % 11
        tasks.append(
            _task(
                problem_id=f"qualification-mathematics-{index:03d}",
                category="arithmetic",
                prompt=f"Compute ({left} multiplied by {right}) plus {offset}.",
                expected=str(left * right + offset),
                oracle_method="Exact bounded integer arithmetic.",
                source_refs=("benchmark:integer-oracle",),
            )
        )
        earliest = ("tokenizer", "loader", "schema validator", "path normalizer")[index % 4]
        later = ("parser", "planner", "executor", "renderer")[index % 4]
        tasks.append(
            _task(
                problem_id=f"qualification-debugging-{index:03d}",
                category="debugging",
                prompt=(
                    f"Trace {index}: the {earliest} emits malformed input before the "
                    f"{later} begins. Which named layer is the earliest supported fault location?"
                ),
                expected=earliest,
                oracle_kind="exact" if task_version == 1 else "component_label",
                oracle_method="Select the earliest component named by the causal trace.",
                evidence_ids=(f"qualification:debug:trace:{index:03d}",),
                source_refs=("benchmark:debug-trace",),
            )
        )
        variable = ("temperature", "pressure", "voltage", "humidity")[index % 4]
        tasks.append(
            _task(
                problem_id=f"qualification-science-{index:03d}",
                category="scientific_inference",
                prompt=(
                    f"Experiment {index}: hypothesis A predicts no {variable} effect. "
                    f"Hypothesis B predicts a reproducible {variable}-linked effect. "
                    f"The measured response changes reproducibly with {variable}. "
                    "Which hypothesis is better supported?"
                ),
                expected="hypothesis b" if task_version == 1 else "b",
                oracle_kind="exact" if task_version == 1 else "hypothesis_label",
                oracle_method="Compare the observed dependency with both explicit predictions.",
                evidence_ids=(f"qualification:science:observation:{index:03d}",),
                counterexamples=("measurement error could imitate the observed effect",),
                source_refs=("benchmark:prediction-oracle",),
            )
        )
        tasks.append(
            _task(
                problem_id=f"qualification-causal-{index:03d}",
                category="causal_reasoning",
                prompt=(
                    f"Study {index}: X and Y are correlated, but Z is a measured common "
                    "cause of both. No intervention on X was performed. Is an intervention "
                    "effect of X on Y established?"
                ),
                expected="no",
                oracle_method="Distinguish association from intervention and account for confounding.",
                evidence_ids=(f"qualification:causal:confounder:{index:03d}",),
                counterexamples=("the observed association may be explained by z",),
                source_refs=("benchmark:causal-oracle",),
            )
        )
        tasks.append(
            _task(
                problem_id=f"qualification-adversarial-{index:03d}",
                category="adversarial",
                prompt=(
                    f"Claim {index} sounds plausible and has an old screenshot, but its current "
                    "source hash and reproducible test are missing. Is the current release claim proven?"
                ),
                expected="no",
                oracle_method="Reject plausibility and stale evidence as proof of a current claim.",
                evidence_ids=(
                    f"qualification:adversarial:stale:{index:03d}",
                    f"qualification:adversarial:missing-hash:{index:03d}",
                ),
                counterexamples=("plausibility is not current reproducible evidence",),
                source_refs=("README.md",),
            )
        )
    return tuple(sorted(tasks, key=lambda item: item["problem_id"]))


def render_tasks(tasks: Iterable[dict]) -> str:
    return "".join(
        json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for task in tasks
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-version", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    output = args.output or Path(
        f"benchmarks/reasoning/tasks/qualification-v{args.task_version}.jsonl"
    )
    manifest_path = args.manifest or Path(
        f"benchmarks/reasoning/tasks/qualification-v{args.task_version}.manifest.json"
    )
    tasks = build_tasks(task_version=args.task_version)
    content = render_tasks(tasks)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "qualification_status": "held_out_frozen_before_live_scoring",
        "task_file": output.as_posix(),
        "task_file_sha256": digest,
        "task_count": len(tasks),
        "class_count": CLASS_COUNT,
        "classes": list(QUALIFICATION_CLASSES),
        "performance_claim_allowed": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(tasks)} tasks: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
