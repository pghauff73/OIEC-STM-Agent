from __future__ import annotations

from typing import Iterable, Mapping

from .models import InteractionRoute, TurnExecutionPolicy


MODE_TOOL_GROUPS = {
    "INSPECT": ("repository_discovery", "workspace_read"),
    "SUMMARIZE": ("repository_discovery", "workspace_read", "corpus_read"),
    "EXPLAIN": ("repository_discovery", "workspace_read"),
    "REASON": (
        "repository_discovery",
        "workspace_read",
        "hypothesis_control",
        "governance_proposal",
        "certified_reasoning",
    ),
    "COMPARE": (
        "repository_discovery",
        "workspace_read",
        "hypothesis_control",
        "governance_proposal",
        "certified_reasoning",
    ),
    "PLAN": (
        "repository_discovery",
        "workspace_read",
        "hypothesis_control",
        "governance_proposal",
        "certified_reasoning",
    ),
    "PROPOSE": (
        "repository_discovery",
        "workspace_read",
        "hypothesis_control",
        "governance_proposal",
        "certified_reasoning",
        "candidate_preparation",
        "eon_proposal",
        "evidence_gate",
    ),
    "WRITE": (
        "repository_discovery",
        "workspace_read",
        "hypothesis_control",
        "governance_proposal",
        "certified_reasoning",
        "candidate_preparation",
        "eon_proposal",
        "evidence_gate",
        "transaction_apply",
        "verification",
    ),
    "TEST": (
        "repository_discovery",
        "workspace_read",
        "governance_proposal",
        "evidence_gate",
        "verification",
    ),
    "EXECUTE": (
        "repository_discovery",
        "workspace_read",
        "governance_proposal",
        "eon_proposal",
        "evidence_gate",
        "transaction_apply",
        "verification",
    ),
    "RECOVER": (
        "repository_discovery",
        "workspace_read",
        "governance_proposal",
        "transaction_apply",
        "verification",
    ),
    "EXPORT": ("repository_discovery", "workspace_read"),
}


def compile_turn_execution_policy(
    route: InteractionRoute,
    *,
    source_snapshot_hash: str,
    context_envelope_signature: str = "",
    corpus_request: Mapping[str, str] | Iterable[tuple[str, str]] = (),
) -> TurnExecutionPolicy:
    if route.kind != "INTENT" or route.intent is None:
        raise ValueError("turn execution policies require a natural-language intent route")
    pairs = tuple(corpus_request.items()) if isinstance(corpus_request, Mapping) else tuple(corpus_request)
    mode = route.intent.mode
    if route.intent.formal_writing is not None:
        operation = route.intent.formal_writing.operation
        if operation in {"WRITE", "REVISE"}:
            groups = (
                "repository_discovery",
                "workspace_read",
                "governance_proposal",
                "candidate_preparation",
                "eon_proposal",
                "evidence_gate",
                "transaction_apply",
                "verification",
            )
        else:
            groups = ("repository_discovery", "workspace_read")
    else:
        groups = MODE_TOOL_GROUPS[mode]
    return TurnExecutionPolicy(
        route_id=route.route_id,
        route_signature=route.signature,
        source_snapshot_hash=source_snapshot_hash,
        intent_mode=mode,
        route_target=route.target,
        target_paths=route.intent.target_paths,
        allowed_tool_groups=groups,
        requires_reasoning_certificate="certified_reasoning" in groups,
        allows_candidate_preparation="candidate_preparation" in groups,
        allows_action_tools="transaction_apply" in groups,
        corpus_request=pairs,
        context_envelope_signature=context_envelope_signature,
    )


__all__ = ["MODE_TOOL_GROUPS", "compile_turn_execution_policy"]
