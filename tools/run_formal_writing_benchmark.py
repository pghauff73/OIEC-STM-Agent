from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ourd.formal_writing import FormalWritingService, compile_formal_writing_request
from ourd.persistence import atomic_write_text
from ourd.writing_engine.signatures import signature


DEFAULT_TASKS = REPOSITORY_ROOT / "benchmarks" / "formal_writing" / "tasks.jsonl"


def load_tasks(path: Path) -> tuple[dict[str, Any], ...]:
    tasks = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not payload.get("task_id"):
            raise ValueError(f"benchmark task line {line_number} has no task_id")
        tasks.append(payload)
    return tuple(tasks)


def run_benchmark(tasks_path: Path = DEFAULT_TASKS) -> dict[str, Any]:
    task_results = []
    for task in load_tasks(tasks_path):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_paths = []
            for source in task.get("sources", ()):
                source_path = workspace / str(source["path"])
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(str(source["text"]), encoding="utf-8")
                source_paths.append(source_path.relative_to(workspace).as_posix())
            request = compile_formal_writing_request(
                operation=str(task["operation"]),
                objective=str(task["objective"]),
                profile=str(task.get("profile", "general")),
                source_paths=tuple(source_paths),
            )
            result = FormalWritingService(workspace).execute(request, persist=False)
            if result.qualified_document is None:
                raise AssertionError(f"{task['task_id']} produced no qualified-document artifact")
            audit = result.qualified_document.audit
            issue_codes = set(audit.graph_issue_codes)
            required_issue_codes = set(task.get("required_issue_codes", ()))
            passed = (
                audit.status == task["expected_status"]
                and audit.evidence_coverage_bp >= int(task.get("minimum_evidence_coverage_bp", 0))
                and required_issue_codes <= issue_codes
            )
            task_results.append(
                {
                    "task_id": task["task_id"],
                    "passed": passed,
                    "expected_status": task["expected_status"],
                    "observed_status": audit.status,
                    "evidence_coverage_bp": audit.evidence_coverage_bp,
                    "claim_support_rate_bp": audit.claim_support_rate_bp,
                    "semantic_consistency_bp": audit.semantic_consistency_bp,
                    "argument_connectivity_bp": audit.argument_connectivity_bp,
                    "counterargument_coverage_bp": audit.counterargument_coverage_bp,
                    "qualification_adequacy_bp": audit.qualification_adequacy_bp,
                    "citation_traceability_bp": audit.citation_traceability_bp,
                    "graph_issue_codes": list(audit.graph_issue_codes),
                    "audit_id": audit.audit_id,
                }
            )
    report = {
        "schema_version": 1,
        "track": "OIEC-Bench/formal-writing",
        "task_count": len(task_results),
        "passed_count": sum(item["passed"] for item in task_results),
        "failed_count": sum(not item["passed"] for item in task_results),
        "tasks": task_results,
    }
    report["signature"] = signature(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic OIEC-Bench formal-writing track")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_benchmark(args.tasks)
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if args.report is not None:
        atomic_write_text(args.report, rendered + "\n")
    print(rendered)
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_TASKS", "build_parser", "load_tasks", "main", "run_benchmark"]
