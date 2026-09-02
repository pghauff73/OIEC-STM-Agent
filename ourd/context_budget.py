from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence, Tuple


FIT = "FIT"
INSUFFICIENT_CONTEXT_BUDGET = "INSUFFICIENT_CONTEXT_BUDGET"
CONTEXT_BUDGET_VERDICTS = {FIT, INSUFFICIENT_CONTEXT_BUDGET}
DROP_OLDEST_UNPINNED_TURN = "DROP_OLDEST_UNPINNED_TURN"
COMPACT_COMPLETED_TOOL_OUTPUT = "COMPACT_COMPLETED_TOOL_OUTPUT"
DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE = "DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE"
CONTEXT_REDUCTION_KINDS = {
    DROP_OLDEST_UNPINNED_TURN,
    COMPACT_COMPLETED_TOOL_OUTPUT,
    DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE,
}
MAX_COMPACTED_TOOL_OUTPUT_CHARS = 1_600
MAX_TOOL_OUTPUT_EXCERPT_CHARS = 1_000
MINIMAL_TOOL_OUTPUT_EXCERPT_CHARS = 160


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def estimate_tokens(value: Any) -> int:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, (len(encoded) + 3) // 4)


def _serialized_character_count(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def effective_input_budget(
    *,
    configured_input_budget_tokens: int,
    runtime_context_tokens: int = 0,
    reserved_output_tokens: int = 0,
    safety_margin_tokens: int = 0,
) -> int:
    configured = max(0, int(configured_input_budget_tokens))
    runtime = max(0, int(runtime_context_tokens))
    if runtime == 0:
        return configured
    runtime_available = max(
        0,
        runtime
        - max(0, int(reserved_output_tokens))
        - max(0, int(safety_margin_tokens)),
    )
    return min(configured, runtime_available)


@dataclass(frozen=True)
class ContextReductionStep:
    schema_version: int = 1
    kind: str = DROP_OLDEST_UNPINNED_TURN
    affected_item_count: int = 0
    original_item_signatures: Tuple[str, ...] = ()
    replacement_item_signatures: Tuple[str, ...] = ()
    tokens_before: int = 0
    tokens_after: int = 0
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context reduction step schema_version must be 1")
        if self.kind not in CONTEXT_REDUCTION_KINDS:
            raise ValueError(f"unsupported context reduction kind: {self.kind}")
        affected_count = int(self.affected_item_count)
        before = int(self.tokens_before)
        after = int(self.tokens_after)
        if affected_count < 1:
            raise ValueError("context reduction must affect at least one item")
        if affected_count != len(self.original_item_signatures):
            raise ValueError("context reduction original signature count mismatch")
        if self.kind in {
            DROP_OLDEST_UNPINNED_TURN,
            DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE,
        } and self.replacement_item_signatures:
            raise ValueError("dropped context items cannot have replacement signatures")
        if self.kind == COMPACT_COMPLETED_TOOL_OUTPUT and (
            affected_count != len(self.replacement_item_signatures)
        ):
            raise ValueError("context compaction replacement signature count mismatch")
        if before < 0 or after < 0 or after > before:
            raise ValueError("context reduction token counts are invalid")
        material = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "affected_item_count": affected_count,
            "original_item_signatures": tuple(self.original_item_signatures),
            "replacement_item_signatures": tuple(self.replacement_item_signatures),
            "tokens_before": before,
            "tokens_after": after,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context reduction step signature mismatch")
        object.__setattr__(self, "affected_item_count", affected_count)
        object.__setattr__(self, "tokens_before", before)
        object.__setattr__(self, "tokens_after", after)
        object.__setattr__(self, "signature", expected)


@dataclass(frozen=True)
class ContextBudgetReport:
    schema_version: int = 1
    verdict: str = FIT
    configured_input_budget_tokens: int = 0
    effective_input_budget_tokens: int = 0
    runtime_context_tokens: int = 0
    reserved_output_tokens: int = 0
    safety_margin_tokens: int = 0
    estimated_input_tokens: int = 0
    overage_tokens: int = 0
    instructions_tokens: int = 0
    tools_tokens: int = 0
    history_tokens: int = 0
    active_input_tokens: int = 0
    history_item_count: int = 0
    active_input_item_count: int = 0
    removed_history_item_count: int = 0
    compacted_tool_output_count: int = 0
    dropped_tool_exchange_count: int = 0
    request_signature: str = ""
    history_signature: str = ""
    active_input_signature: str = ""
    reduction_steps: Tuple[ContextReductionStep, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context budget report schema_version must be 1")
        if self.verdict not in CONTEXT_BUDGET_VERDICTS:
            raise ValueError(f"invalid context budget verdict: {self.verdict}")
        numeric_fields = (
            "configured_input_budget_tokens",
            "effective_input_budget_tokens",
            "runtime_context_tokens",
            "reserved_output_tokens",
            "safety_margin_tokens",
            "estimated_input_tokens",
            "overage_tokens",
            "instructions_tokens",
            "tools_tokens",
            "history_tokens",
            "active_input_tokens",
            "history_item_count",
            "active_input_item_count",
            "removed_history_item_count",
            "compacted_tool_output_count",
            "dropped_tool_exchange_count",
        )
        for name in numeric_fields:
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
            object.__setattr__(self, name, value)
        expected_overage = max(
            0,
            self.estimated_input_tokens - self.effective_input_budget_tokens,
        )
        if self.overage_tokens != expected_overage:
            raise ValueError("context budget overage mismatch")
        expected_verdict = FIT if expected_overage == 0 else INSUFFICIENT_CONTEXT_BUDGET
        if self.verdict != expected_verdict:
            raise ValueError("context budget verdict does not match the overage")
        material = {
            "schema_version": self.schema_version,
            "verdict": self.verdict,
            "configured_input_budget_tokens": self.configured_input_budget_tokens,
            "effective_input_budget_tokens": self.effective_input_budget_tokens,
            "runtime_context_tokens": self.runtime_context_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "estimated_input_tokens": self.estimated_input_tokens,
            "overage_tokens": self.overage_tokens,
            "instructions_tokens": self.instructions_tokens,
            "tools_tokens": self.tools_tokens,
            "history_tokens": self.history_tokens,
            "active_input_tokens": self.active_input_tokens,
            "history_item_count": self.history_item_count,
            "active_input_item_count": self.active_input_item_count,
            "removed_history_item_count": self.removed_history_item_count,
            "compacted_tool_output_count": self.compacted_tool_output_count,
            "dropped_tool_exchange_count": self.dropped_tool_exchange_count,
            "request_signature": self.request_signature,
            "history_signature": self.history_signature,
            "active_input_signature": self.active_input_signature,
            "reduction_step_signatures": tuple(
                item.signature for item in self.reduction_steps
            ),
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context budget report signature mismatch")
        object.__setattr__(self, "signature", expected)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextRecoveryResult:
    input_items: Tuple[Any, ...]
    history_item_count: int
    report: ContextBudgetReport


def _oldest_history_turn_size(history: Sequence[Any]) -> int:
    if not history:
        return 0
    first = history[0]
    first_role = str(first.get("role", "")) if isinstance(first, Mapping) else ""
    if first_role != "user" or len(history) == 1:
        return 1
    second = history[1]
    second_role = str(second.get("role", "")) if isinstance(second, Mapping) else ""
    return 2 if second_role == "assistant" else 1


def _bounded_excerpt(value: str, limit: int = MAX_TOOL_OUTPUT_EXCERPT_CHARS) -> str:
    bounded = max(1, int(limit))
    if len(value) <= bounded:
        return value
    marker = "\n... OIEC CONTEXT PROJECTION OMITTED ...\n"
    available = max(2, bounded - len(marker))
    head = (available * 3) // 5
    tail = available - head
    return value[:head] + marker + value[-tail:]


def _evidence_ids(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    found = []
    direct = value.get("evidence_id")
    if isinstance(direct, str) and direct:
        found.append(direct)
    multiple = value.get("evidence_ids")
    if isinstance(multiple, Sequence) and not isinstance(multiple, (str, bytes)):
        found.extend(str(item) for item in multiple if str(item))
    return tuple(sorted(set(found)))


def markdown_semantic_outline(content: str, limit: int = 1_600) -> str:
    kept: list[str] = []
    body_lines_after_heading = 0
    for raw_line in content.splitlines():
        match = re.match(r"^\s*\d+\s+\|\s?(.*)$", raw_line)
        line = (match.group(1) if match else raw_line).strip()
        if not line:
            continue
        if line.startswith("#"):
            kept.append(line)
            body_lines_after_heading = 0
            continue
        if body_lines_after_heading < 2:
            kept.append(line)
            body_lines_after_heading += 1
            continue
        if line.casefold().startswith(
            ("status:", "limitation:", "limitations:", "warning:", "invariant:")
        ):
            kept.append(line)
    return _bounded_excerpt("\n".join(kept), limit)


def _semantic_artifacts(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    preserved: dict[str, Any] = {}
    summary = value.get("summary")
    if isinstance(summary, Mapping):
        preserved_summary: dict[str, Any] = {}
        for key in (
            "summary_id",
            "manifest_id",
            "path",
            "content_sha256",
            "source_snapshot_hash",
            "summary_sha256",
            "source_read_evidence_ids",
            "coverage_signature",
            "coverage_complete",
            "model_identity",
            "prompt_signature",
            "epistemic_status",
            "signature",
        ):
            item = summary.get(key)
            if item is not None and item != "":
                preserved_summary[key] = item
        preserved["document_summary"] = preserved_summary
        if isinstance(summary.get("summary_text"), str):
            preserved["document_summary"]["summary_text"] = _bounded_excerpt(
                summary["summary_text"], 4_000
            )
    report = value.get("report")
    if isinstance(report, Mapping):
        preserved["corpus_coverage"] = dict(report)
    coverage = value.get("coverage")
    if isinstance(coverage, Mapping):
        preserved["document_coverage"] = dict(coverage)
    content = value.get("content")
    path = value.get("path")
    if isinstance(content, str) and isinstance(path, str) and content:
        preserved["document_outline"] = {
            "path": path,
            "start_line": int(value.get("start_line", 0) or 0),
            "end_line": int(value.get("end_line", 0) or 0),
            "content_character_count": len(content),
            "outline": markdown_semantic_outline(content),
        }
    formal_result = value.get("formal_writing_result")
    if isinstance(formal_result, Mapping):
        request = formal_result.get("request") if isinstance(formal_result.get("request"), Mapping) else {}
        plan = formal_result.get("plan") if isinstance(formal_result.get("plan"), Mapping) else {}
        draft = formal_result.get("draft") if isinstance(formal_result.get("draft"), Mapping) else {}
        report = formal_result.get("integrity_report") if isinstance(formal_result.get("integrity_report"), Mapping) else {}
        preserved["formal_writing"] = {
            "request_id": request.get("request_id", ""),
            "operation": request.get("operation", ""),
            "request_signature": request.get("request_signature", ""),
            "plan_id": plan.get("plan_id", ""),
            "plan_signature": plan.get("signature", ""),
            "draft_id": draft.get("draft_id", ""),
            "draft_text": _bounded_excerpt(str(draft.get("text", "")), 6_000),
            "integrity_report": dict(report),
            "source_count": len(formal_result.get("sources", ()) or ()),
            "reference_count": len(formal_result.get("references", ()) or ()),
        }
    return preserved


def _compact_tool_output_item(
    item: Any,
    *,
    excerpt_chars: int,
    force: bool,
) -> Any | None:
    if not isinstance(item, Mapping) or item.get("type") != "function_call_output":
        return None
    output = item.get("output")
    if not isinstance(output, str):
        return None
    try:
        decoded = json.loads(output)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, Mapping) and decoded.get("context_budget_compacted") is True:
        projection = dict(decoded)
        current_excerpt = str(projection.get("excerpt", ""))
        projection["excerpt"] = _bounded_excerpt(current_excerpt, excerpt_chars)
        projection["projection_level"] = (
            "minimal"
            if excerpt_chars <= MINIMAL_TOOL_OUTPUT_EXCERPT_CHARS
            else "bounded"
        )
        replacement = dict(item)
        replacement["output"] = canonical_json(projection)
        if _serialized_character_count(replacement) >= _serialized_character_count(item):
            return None
        return replacement
    if not force and len(output) <= MAX_COMPACTED_TOOL_OUTPUT_CHARS:
        return None
    preserved: dict[str, Any] = {}
    if isinstance(decoded, Mapping):
        for key in (
            "ok",
            "returncode",
            "capability",
            "collision_id",
            "truncated",
            "total_file_count",
            "returned_file_count",
        ):
            value = decoded.get(key)
            if isinstance(value, (bool, int, float, str)):
                preserved[key] = value
    projection = {
        "context_budget_compacted": True,
        "projection_kind": "completed_tool_output",
        "projection_level": (
            "minimal"
            if excerpt_chars <= MINIMAL_TOOL_OUTPUT_EXCERPT_CHARS
            else "bounded"
        ),
        "original_output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "original_output_character_count": len(output),
        "evidence_ids": _evidence_ids(decoded),
        "full_result_persisted_as_evidence": bool(_evidence_ids(decoded)),
        "preserved_fields": preserved,
        "semantic_artifacts": _semantic_artifacts(decoded),
        "excerpt": _bounded_excerpt(output, excerpt_chars),
    }
    replacement = dict(item)
    replacement["output"] = canonical_json(projection)
    if _serialized_character_count(replacement) >= _serialized_character_count(item):
        return None
    return replacement


def _oldest_evidence_tool_exchange(
    items: Sequence[Any],
    *,
    start_index: int,
    retain_newest: int,
) -> Tuple[int, int] | None:
    outputs: dict[str, int] = {}
    evidence_bound_outputs: set[str] = set()
    for index in range(start_index, len(items)):
        item = items[index]
        if not isinstance(item, Mapping) or item.get("type") != "function_call_output":
            continue
        call_id = str(item.get("call_id", ""))
        output = item.get("output")
        if not call_id or not isinstance(output, str):
            continue
        try:
            decoded = json.loads(output)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, Mapping) and (
            decoded.get("context_preserve") is True
            or isinstance(decoded.get("summary"), Mapping)
            or isinstance(decoded.get("report"), Mapping)
        ):
            continue
        if not _evidence_ids(decoded):
            continue
        outputs[call_id] = index
        evidence_bound_outputs.add(call_id)

    candidates: list[Tuple[int, int]] = []
    for index in range(start_index, len(items)):
        item = items[index]
        if not isinstance(item, Mapping) or item.get("type") != "function_call":
            continue
        call_id = str(item.get("call_id", ""))
        if call_id in evidence_bound_outputs:
            candidates.append((index, outputs[call_id]))
    keep = max(0, int(retain_newest))
    if len(candidates) <= keep:
        return None
    return candidates[0]


def _build_report(
    *,
    instructions: str,
    input_items: Sequence[Any],
    tools: Sequence[Mapping[str, Any]],
    history_item_count: int,
    configured_input_budget_tokens: int,
    runtime_context_tokens: int,
    reserved_output_tokens: int,
    safety_margin_tokens: int,
    removed_history_item_count: int,
    reduction_steps: Sequence[ContextReductionStep],
) -> ContextBudgetReport:
    history = tuple(input_items[:history_item_count])
    active_input = tuple(input_items[history_item_count:])
    request = {
        "instructions": instructions,
        "input": list(input_items),
        "tools": list(tools),
    }
    estimated = estimate_tokens(request)
    effective = effective_input_budget(
        configured_input_budget_tokens=configured_input_budget_tokens,
        runtime_context_tokens=runtime_context_tokens,
        reserved_output_tokens=reserved_output_tokens,
        safety_margin_tokens=safety_margin_tokens,
    )
    overage = max(0, estimated - effective)
    return ContextBudgetReport(
        verdict=FIT if overage == 0 else INSUFFICIENT_CONTEXT_BUDGET,
        configured_input_budget_tokens=max(0, int(configured_input_budget_tokens)),
        effective_input_budget_tokens=effective,
        runtime_context_tokens=max(0, int(runtime_context_tokens)),
        reserved_output_tokens=max(0, int(reserved_output_tokens)),
        safety_margin_tokens=max(0, int(safety_margin_tokens)),
        estimated_input_tokens=estimated,
        overage_tokens=overage,
        instructions_tokens=estimate_tokens(instructions),
        tools_tokens=estimate_tokens(list(tools)) if tools else 0,
        history_tokens=estimate_tokens(list(history)) if history else 0,
        active_input_tokens=estimate_tokens(list(active_input)) if active_input else 0,
        history_item_count=len(history),
        active_input_item_count=len(active_input),
        removed_history_item_count=max(0, int(removed_history_item_count)),
        compacted_tool_output_count=sum(
            item.affected_item_count
            for item in reduction_steps
            if item.kind == COMPACT_COMPLETED_TOOL_OUTPUT
        ),
        dropped_tool_exchange_count=sum(
            1
            for item in reduction_steps
            if item.kind == DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE
        ),
        request_signature=stable_hash(request),
        history_signature=stable_hash(history),
        active_input_signature=stable_hash(active_input),
        reduction_steps=tuple(reduction_steps),
    )


def recover_context_request(
    *,
    instructions: str,
    input_items: Sequence[Any],
    tools: Sequence[Mapping[str, Any]],
    history_item_count: int,
    configured_input_budget_tokens: int,
    runtime_context_tokens: int = 0,
    reserved_output_tokens: int = 0,
    safety_margin_tokens: int = 0,
) -> ContextRecoveryResult:
    items = list(input_items)
    initial_history_count = int(history_item_count)
    if not 0 <= initial_history_count <= len(items):
        raise ValueError("history_item_count must identify a leading input projection")
    current_history_count = initial_history_count
    steps: list[ContextReductionStep] = []
    report = _build_report(
        instructions=instructions,
        input_items=items,
        tools=tools,
        history_item_count=current_history_count,
        configured_input_budget_tokens=configured_input_budget_tokens,
        runtime_context_tokens=runtime_context_tokens,
        reserved_output_tokens=reserved_output_tokens,
        safety_margin_tokens=safety_margin_tokens,
        removed_history_item_count=0,
        reduction_steps=steps,
    )
    while report.verdict != FIT and current_history_count > 0:
        turn_size = _oldest_history_turn_size(items[:current_history_count])
        removed = tuple(items[:turn_size])
        tokens_before = report.estimated_input_tokens
        del items[:turn_size]
        current_history_count -= turn_size
        provisional = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
        steps.append(
            ContextReductionStep(
                kind=DROP_OLDEST_UNPINNED_TURN,
                affected_item_count=turn_size,
                original_item_signatures=tuple(stable_hash(item) for item in removed),
                tokens_before=tokens_before,
                tokens_after=provisional.estimated_input_tokens,
            )
        )
        report = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
    while report.verdict != FIT:
        candidate_index = -1
        replacement = None
        for index in range(current_history_count, len(items)):
            replacement = _compact_tool_output_item(
                items[index],
                excerpt_chars=MAX_TOOL_OUTPUT_EXCERPT_CHARS,
                force=False,
            )
            if replacement is not None:
                candidate_index = index
                break
        if candidate_index < 0 or replacement is None:
            break
        original = items[candidate_index]
        tokens_before = report.estimated_input_tokens
        items[candidate_index] = replacement
        provisional = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
        steps.append(
            ContextReductionStep(
                kind=COMPACT_COMPLETED_TOOL_OUTPUT,
                affected_item_count=1,
                original_item_signatures=(stable_hash(original),),
                replacement_item_signatures=(stable_hash(replacement),),
                tokens_before=tokens_before,
                tokens_after=provisional.estimated_input_tokens,
            )
        )
        report = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
    while report.verdict != FIT:
        candidate_index = -1
        replacement = None
        for index in range(current_history_count, len(items)):
            replacement = _compact_tool_output_item(
                items[index],
                excerpt_chars=MINIMAL_TOOL_OUTPUT_EXCERPT_CHARS,
                force=True,
            )
            if replacement is not None:
                candidate_index = index
                break
        if candidate_index < 0 or replacement is None:
            break
        original = items[candidate_index]
        tokens_before = report.estimated_input_tokens
        items[candidate_index] = replacement
        provisional = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
        steps.append(
            ContextReductionStep(
                kind=COMPACT_COMPLETED_TOOL_OUTPUT,
                affected_item_count=1,
                original_item_signatures=(stable_hash(original),),
                replacement_item_signatures=(stable_hash(replacement),),
                tokens_before=tokens_before,
                tokens_after=provisional.estimated_input_tokens,
            )
        )
        report = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
    while report.verdict != FIT:
        candidate = _oldest_evidence_tool_exchange(
            items,
            start_index=current_history_count,
            retain_newest=2,
        )
        if candidate is None:
            candidate = _oldest_evidence_tool_exchange(
                items,
                start_index=current_history_count,
                retain_newest=0,
            )
        if candidate is None:
            break
        indices = tuple(sorted(set(candidate)))
        removed = tuple(items[index] for index in indices)
        tokens_before = report.estimated_input_tokens
        for index in reversed(indices):
            del items[index]
        provisional = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
        steps.append(
            ContextReductionStep(
                kind=DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE,
                affected_item_count=len(removed),
                original_item_signatures=tuple(stable_hash(item) for item in removed),
                tokens_before=tokens_before,
                tokens_after=provisional.estimated_input_tokens,
            )
        )
        report = _build_report(
            instructions=instructions,
            input_items=items,
            tools=tools,
            history_item_count=current_history_count,
            configured_input_budget_tokens=configured_input_budget_tokens,
            runtime_context_tokens=runtime_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            removed_history_item_count=initial_history_count - current_history_count,
            reduction_steps=steps,
        )
    return ContextRecoveryResult(
        input_items=tuple(items),
        history_item_count=current_history_count,
        report=report,
    )


def format_context_budget_error(report: ContextBudgetReport) -> str:
    runtime = (
        str(report.runtime_context_tokens)
        if report.runtime_context_tokens
        else "unknown"
    )
    return (
        f"{INSUFFICIENT_CONTEXT_BUDGET}: estimated_input="
        f"{report.estimated_input_tokens}, effective_input_budget="
        f"{report.effective_input_budget_tokens}, overage={report.overage_tokens}; "
        f"configured_input={report.configured_input_budget_tokens}, runtime_context="
        f"{runtime}, reserved_output={report.reserved_output_tokens}, safety_margin="
        f"{report.safety_margin_tokens}; instructions={report.instructions_tokens}, "
        f"tools={report.tools_tokens}, history={report.history_tokens}, active_input="
        f"{report.active_input_tokens}, compacted_tool_outputs="
        f"{report.compacted_tool_output_count}, dropped_tool_exchanges="
        f"{report.dropped_tool_exchange_count}; report_signature={report.signature}"
    )


__all__ = [
    "CONTEXT_BUDGET_VERDICTS",
    "COMPACT_COMPLETED_TOOL_OUTPUT",
    "ContextBudgetReport",
    "ContextRecoveryResult",
    "ContextReductionStep",
    "FIT",
    "DROP_OLDEST_UNPINNED_TURN",
    "DROP_OLDEST_EVIDENCE_TOOL_EXCHANGE",
    "INSUFFICIENT_CONTEXT_BUDGET",
    "canonical_json",
    "effective_input_budget",
    "estimate_tokens",
    "format_context_budget_error",
    "markdown_semantic_outline",
    "recover_context_request",
    "stable_hash",
]
