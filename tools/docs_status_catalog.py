"""Source-derived machine-status catalog with deterministic beginner decoding."""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{2,}")
STATUS_FIELDS = {
    "status",
    "state",
    "result",
    "decision",
    "outcome",
    "classification",
    "verdict",
    "reason",
    "resolution",
    "next_action",
}


@dataclass(frozen=True)
class StatusRecord:
    status: str
    plain_language_meaning: str
    category: str
    trigger: str
    what_happens_next: str
    user_action: str
    source_paths: tuple[str, ...]
    related_concepts: tuple[str, ...]
    authorship: str


EXPLICIT = {
    "QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND": StatusRecord(
        "QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND",
        "OIEC found both a qualified mathematical algorithm and a qualified reasoning procedure for the current context.",
        "Qualified Retrieval",
        "Context-qualified retrieval returns the required algorithm and reasoning pair.",
        "Reuse the qualified pair instead of generating replacements.",
        "Inspect the qualification and source bindings before continuing.",
        ("ourd/egcf/algebra/unified_retrieval.py",),
        ("SAA", "Evidence", "Algorithm Store"),
        "authored",
    ),
    "SEMANTIC_MISREPRESENTATION": StatusRecord(
        "SEMANTIC_MISREPRESENTATION",
        "The declared representation does not preserve the meaning required by the problem.",
        "Representation Failure",
        "Semantic analysis finds that a coordinate, dimension, or unit combines or changes meanings incorrectly.",
        "Canonical admission and dependent action remain blocked.",
        "Resolve the representation and produce new semantic evidence.",
        ("ourd/egcf/algebra/semantic_units.py", "ourd/egcf/algebra/semantic.py"),
        ("OURD", "IURM", "CFEL"),
        "authored",
    ),
    "NON_REPRESENTATIVE_COUPLED": StatusRecord(
        "NON_REPRESENTATIVE_COUPLED",
        "The proposed inputs remain coupled and do not form independent representative dimensions.",
        "Representation Failure",
        "Representative-input analysis detects unresolved coupling.",
        "The candidate cannot enter the canonical store as an independent representation.",
        "Decouple, re-parameterize, or explicitly preserve the limitation.",
        ("ourd/egcf/algebra/representative.py", "ourd/egcf/algebra/semantic.py"),
        ("IURM", "SAA", "Evidence Gate"),
        "authored",
    ),
    "CANDIDATE_IMPROVEMENT_QUALIFIED": StatusRecord(
        "CANDIDATE_IMPROVEMENT_QUALIFIED",
        "A candidate improved the declared objective without violating the tested regression constraints.",
        "Qualified Improvement",
        "Candidate-versus-baseline evidence satisfies the improvement contract.",
        "The candidate becomes eligible for governed promotion, not automatically promoted.",
        "Review evidence, scope, regressions, and promotion authority.",
        ("ourd/egcf/algebra/algorithm_experiment.py", "ourd/egcf/algebra/experiment_aggregation.py"),
        ("IURM", "IEPS", "SAA"),
        "authored",
    ),
    "CLOSED_LOOP_IMPROVEMENT_VERIFIED": StatusRecord(
        "CLOSED_LOOP_IMPROVEMENT_VERIFIED",
        "A promoted improvement was retrieved again under the intended context, closing the improvement loop.",
        "Closed-Loop Verification",
        "Promotion and context-qualified re-retrieval both succeed with preserved lineage.",
        "The verified improvement may be reused within its qualification boundary.",
        "Inspect the lineage and keep claims within the tested context.",
        ("ourd/egcf/improvement_store.py", "ourd/egcf/algebra/intelligence_loop.py"),
        ("SAA", "CFEL", "Evidence"),
        "authored",
    ),
}


def _status_sources() -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    for path in sorted((ROOT / "ourd").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            values: list[str] = []
            if isinstance(node, ast.keyword) and node.arg in STATUS_FIELDS:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    values.append(node.value.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in STATUS_FIELDS
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        values.append(value.value)
            elif isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                mentions_status = any(
                    (isinstance(item, ast.Name) and item.id in STATUS_FIELDS)
                    or (isinstance(item, ast.Attribute) and item.attr in STATUS_FIELDS)
                    for item in operands
                )
                if mentions_status:
                    values.extend(
                        item.value
                        for item in operands
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    )
            for value in values:
                if STATUS_PATTERN.fullmatch(value) and "_" in value:
                    sources.setdefault(value, set()).add(relative)
    for status, record in EXPLICIT.items():
        sources.setdefault(status, set()).update(record.source_paths)
    return sources


def _category(status: str) -> str:
    if any(part in status for part in ("FAIL", "REJECT", "BLOCK", "REFUS", "INVALID", "COLLISION", "REGRESSION")):
        return "Failure or Refusal"
    if any(part in status for part in ("QUALIFIED", "VERIFIED", "PASSED", "ADMITTED", "APPROVED", "FOUND")):
        return "Qualified or Verified"
    if any(part in status for part in ("PENDING", "AWAITING", "UNRESOLVED", "UNKNOWN", "REVIEW")):
        return "Pending or Unresolved"
    return "Runtime State"


def _generic_record(status: str, sources: tuple[str, ...]) -> StatusRecord:
    words = status.replace("_", " ").lower()
    category = _category(status)
    if category == "Failure or Refusal":
        next_step = "The dependent operation remains blocked or records a failed result."
        user_action = "Inspect the named source record, violated constraint, and required evidence before retrying."
    elif category == "Qualified or Verified":
        next_step = "The result may advance only through the next declared governance gate."
        user_action = "Review scope, evidence, and source binding before relying on the result."
    elif category == "Pending or Unresolved":
        next_step = "The system preserves the unresolved state instead of guessing."
        user_action = "Provide the missing evidence, clarification, approval, or source state."
    else:
        next_step = "The runtime records this state for the owning workflow to interpret."
        user_action = "Follow the linked source and related concept before taking action."
    return StatusRecord(
        status,
        f"The runtime reported {words}.",
        category,
        f"A source-owned status field or comparison emitted {status}.",
        next_step,
        user_action,
        sources,
        ("Evidence", "CFEL"),
        "source-derived",
    )


def discover_statuses() -> tuple[StatusRecord, ...]:
    records = []
    for status, paths in sorted(_status_sources().items()):
        records.append(EXPLICIT.get(status) or _generic_record(status, tuple(sorted(paths))))
    return tuple(records)


def validate_statuses(records: Iterable[StatusRecord]) -> None:
    seen: set[str] = set()
    for record in records:
        if record.status in seen:
            raise ValueError(f"duplicate status record: {record.status}")
        seen.add(record.status)
        if not record.source_paths:
            raise ValueError(f"status lacks source evidence: {record.status}")
        for source in record.source_paths:
            if not (ROOT / source).is_file():
                raise ValueError(f"status source does not exist: {source}")


def records_for_manifest(records: Iterable[StatusRecord]) -> list[dict[str, object]]:
    return [asdict(record) for record in records]
