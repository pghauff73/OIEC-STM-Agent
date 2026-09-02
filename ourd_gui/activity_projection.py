from __future__ import annotations

from typing import Any, Mapping, Sequence

from .events import AgentEvent


ActivityProjection = tuple[str, str]

MAX_ACTIVITY_DETAIL_CHARACTERS = 220
MAX_ACTIVITY_VALUE_CHARACTERS = 96

_TOOL_ARGUMENT_KEYS = (
    "path",
    "target",
    "query",
    "pattern",
    "command",
    "operation",
    "kind",
    "format",
    "action_id",
    "transaction_id",
    "plan_id",
    "evidence_id",
    "hypothesis_id",
    "relation",
    "start_line",
    "end_line",
    "max_depth",
)

_TOOL_RESULT_KEYS = (
    "path",
    "target",
    "status",
    "count",
    "match_count",
    "file_count",
    "returncode",
    "action_id",
    "transaction_id",
    "evidence_id",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bounded_text(value: Any, *, limit: int = MAX_ACTIVITY_VALUE_CHARACTERS) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _display_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Mapping):
        return f"{len(value)} fields"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        if not items:
            return "none"
        preview = ", ".join(_bounded_text(item, limit=36) for item in items[:2])
        if len(items) > 2:
            preview += f", +{len(items) - 2} more"
        return preview
    text = _bounded_text(value)
    if key.endswith("_id") and len(text) > 16:
        return text[:12] + "…"
    return text


def _selected_fields(
    payload: Mapping[str, Any],
    keys: Sequence[str],
    *,
    limit: int = 3,
) -> str:
    fields = []
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, Mapping) and not value:
            continue
        if (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray))
            and not value
        ):
            continue
        fields.append(f"{key.replace('_', ' ')}={_display_value(key, value)}")
        if len(fields) >= limit:
            break
    return " · ".join(fields)


def _finish(label: str, detail: str) -> ActivityProjection:
    return label, _bounded_text(detail, limit=MAX_ACTIVITY_DETAIL_CHARACTERS)


def _run_started(payload: Mapping[str, Any]) -> ActivityProjection:
    provider = _mapping(payload.get("provider"))
    model = provider.get("model") or provider.get("resolved_model") or payload.get("model")
    details = []
    if model:
        details.append(f"model={_display_value('model', model)}")
    history_count = _integer(payload.get("history_message_count", 0))
    if history_count:
        details.append(f"{history_count} prior messages")
    return _finish("Started", " · ".join(details) or "Agent run started")


def _model_request(payload: Mapping[str, Any]) -> ActivityProjection:
    step = payload.get("step")
    details = [f"Step {step}" if step not in {None, ""} else "Model request"]
    model = payload.get("model")
    if model:
        details.append(_display_value("model", model))
    input_count = _integer(payload.get("input_item_count", 0))
    if input_count:
        details.append(f"{input_count} input items")
    reductions = _integer(payload.get("context_reduction_count", 0))
    if reductions:
        details.append(f"{reductions} context reductions")
    return _finish("Thinking", " · ".join(details))


def _tool_call(payload: Mapping[str, Any]) -> ActivityProjection:
    name = _bounded_text(payload.get("name", "tool"), limit=64)
    arguments = _mapping(payload.get("args"))
    details = _selected_fields(arguments, _TOOL_ARGUMENT_KEYS)
    if not details and arguments:
        details = f"{len(arguments)} parameters"
    return _finish("Tool", f"{name} · {details}" if details else name)


def _tool_result(payload: Mapping[str, Any]) -> ActivityProjection:
    name = _bounded_text(payload.get("name", "tool"), limit=64)
    result = _mapping(payload.get("result"))
    error = result.get("error")
    failed = result.get("ok") is False or error not in {None, ""}
    if failed:
        detail = f"{name} · Failed"
        error_code = result.get("error_code")
        if error_code:
            detail += f" · {_bounded_text(error_code, limit=64)}"
        if error:
            detail += f": {_bounded_text(error, limit=120)}"
        return _finish("Result", detail)
    fields = _selected_fields(result, _TOOL_RESULT_KEYS, limit=2)
    detail = f"{name} · Complete"
    if fields:
        detail += f" · {fields}"
    return _finish("Result", detail)


def _context_recovery(payload: Mapping[str, Any]) -> ActivityProjection:
    verdict = str(payload.get("verdict", "FIT"))
    overage = _integer(payload.get("overage_tokens", 0))
    if verdict != "FIT" or overage:
        return _finish("Context", f"Budget blocked · {overage} tokens over limit")
    reductions = []
    removed = _integer(payload.get("removed_history_item_count", 0))
    compacted = _integer(payload.get("compacted_tool_output_count", 0))
    dropped = _integer(payload.get("dropped_tool_exchange_count", 0))
    if removed:
        reductions.append(f"removed {removed} history items")
    if compacted:
        reductions.append(f"compacted {compacted} tool outputs")
    if dropped:
        reductions.append(f"dropped {dropped} tool exchanges")
    if not reductions:
        step_count = len(payload.get("reduction_steps", ()) or ())
        reductions.append(f"applied {step_count} reductions")
    return _finish("Context", " · ".join(reductions))


def _provider_recovery(payload: Mapping[str, Any]) -> ActivityProjection:
    kind = _bounded_text(payload.get("kind", "provider recovery"), limit=100)
    detail = kind.replace("_", " ").title()
    retries = _integer(payload.get("retry_count", 0))
    if retries:
        detail += f" · {retries} {'retry' if retries == 1 else 'retries'}"
    tool_name = payload.get("tool_name")
    if tool_name:
        detail += f" · tool={_display_value('tool_name', tool_name)}"
    return _finish("Recovery", detail)


def _action_proposed(payload: Mapping[str, Any]) -> ActivityProjection:
    summary = payload.get("summary") or payload.get("operation") or "Governed action proposed"
    targets = payload.get("targets") or ()
    target_text = _display_value("targets", targets) if targets else ""
    risk = payload.get("effective_risk") or payload.get("model_risk")
    details = [_bounded_text(summary, limit=130)]
    if target_text:
        details.append(target_text)
    if risk:
        details.append(f"risk={_display_value('risk', risk)}")
    return _finish("Plan", " · ".join(details))


def _gate_decision(payload: Mapping[str, Any]) -> ActivityProjection:
    verdict = payload.get("verdict") or payload.get("proposed_verdict") or "DECIDED"
    reason = payload.get("reason")
    detail = _bounded_text(verdict, limit=64)
    if reason:
        detail += f" · {_bounded_text(reason, limit=145)}"
    return _finish("Gate", detail)


def _approval(payload: Mapping[str, Any]) -> ActivityProjection:
    approved = payload.get("approved", True)
    detail = "Recorded" if approved else "Rejected"
    approver = payload.get("approver")
    if approver:
        detail += f" · approver={_display_value('approver', approver)}"
    return _finish("Approval", detail)


def _transaction(trace_type: str, payload: Mapping[str, Any]) -> ActivityProjection:
    state = {
        "transaction_prepared": "Prepared",
        "transaction_applied": "Applied",
        "transaction_verified": "Verified",
        "transaction_discarded": "Discarded",
        "transaction_rolled_back": "Rolled back",
    }[trace_type]
    targets = payload.get("targets") or ()
    target_text = _display_value("targets", targets) if targets else ""
    detail = state
    if target_text:
        detail += f" · {target_text}"
    return _finish("Transaction", detail)


def _cycle_stop(payload: Mapping[str, Any]) -> ActivityProjection:
    kind = payload.get("cycle_kind") or "Agent loop stopped"
    reason = payload.get("reason")
    detail = _bounded_text(kind, limit=80).replace("_", " ")
    if reason:
        detail += f" · {_bounded_text(reason, limit=135)}"
    return _finish("Stopped", detail)


def _final(payload: Mapping[str, Any]) -> ActivityProjection:
    detail = "Response ready"
    if payload.get("terminal_synthesis_fallback"):
        detail += " · deterministic fallback used"
    return _finish("Finished", detail)


def _corpus_manifest(payload: Mapping[str, Any]) -> ActivityProjection:
    count = _integer(payload.get("file_count", 0))
    root = _bounded_text(payload.get("root_path", "."), limit=80)
    return _finish("Sources", f"Indexed {count} documents · {root}")


def _corpus_read(payload: Mapping[str, Any]) -> ActivityProjection:
    path = _bounded_text(payload.get("path", "document"), limit=110)
    state = "fully read" if payload.get("coverage_complete") else "reading"
    return _finish("Sources", f"{state.title()} · {path}")


def _document_summary(payload: Mapping[str, Any]) -> ActivityProjection:
    path = _bounded_text(payload.get("path", "document"), limit=110)
    return _finish("Summary", f"Recorded source-bound summary · {path}")


def _corpus_report(payload: Mapping[str, Any]) -> ActivityProjection:
    status = _bounded_text(payload.get("coverage_status", "PARTIAL"), limit=32)
    expected = len(payload.get("expected_paths", ()) or ())
    summarized = len(payload.get("summarized_paths", ()) or ())
    return _finish("Summary", f"{status} · {summarized}/{expected} documents")


def _formal_writing(payload: Mapping[str, Any]) -> ActivityProjection:
    operation = _bounded_text(payload.get("operation", "formal writing"), limit=48)
    sources = _integer(payload.get("source_count", 0))
    references = _integer(payload.get("reference_count", 0))
    details = [operation.replace("_", " ").title(), f"{sources} sources", f"{references} references"]
    if payload.get("has_draft"):
        details.append("draft ready")
    integrity = payload.get("integrity_passed")
    if integrity is not None:
        details.append("integrity passed" if integrity else "review required")
    return _finish("Writing", " · ".join(details))


def project_agent_activity(event: AgentEvent) -> ActivityProjection | None:
    envelope = _mapping(event.payload)
    trace_type = str(envelope.get("trace_type", event.event_type.value))
    payload = _mapping(envelope.get("trace_payload", envelope))

    if trace_type == "run_started":
        return _run_started(payload)
    if trace_type == "model_request":
        return _model_request(payload)
    if trace_type == "tool_call":
        return _tool_call(payload)
    if trace_type == "tool_result":
        return _tool_result(payload)
    if trace_type == "corpus_manifest_created":
        return _corpus_manifest(payload)
    if trace_type == "corpus_read_progress":
        return _corpus_read(payload)
    if trace_type == "document_summary_recorded":
        return _document_summary(payload)
    if trace_type == "corpus_summary_report":
        return _corpus_report(payload)
    if trace_type == "formal_writing_completed":
        return _formal_writing(payload)
    if trace_type == "context_budget_recovery":
        return _context_recovery(payload)
    if trace_type == "provider_response_recovery":
        return _provider_recovery(payload)
    if trace_type == "eon_action_proposed":
        return _action_proposed(payload)
    if trace_type == "gate_decision":
        return _gate_decision(payload)
    if trace_type in {"human_approval", "external_human_approval"}:
        return _approval(payload)
    if trace_type in {
        "transaction_prepared",
        "transaction_applied",
        "transaction_verified",
        "transaction_discarded",
        "transaction_rolled_back",
    }:
        return _transaction(trace_type, payload)
    if trace_type == "cycle_stop":
        return _cycle_stop(payload)
    if trace_type == "final":
        return _final(payload)
    return None
