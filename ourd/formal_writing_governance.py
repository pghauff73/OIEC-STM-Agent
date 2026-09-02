from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .agent import OURDAgent


def prepare_governed_formal_write(
    workspace: Path,
    authority_path: Path,
    request_signature: str,
    confirmed_request_signature: str,
    objective: str,
    output_paths: Sequence[str],
    draft_text: str,
) -> dict[str, Any]:
    if not request_signature or confirmed_request_signature != request_signature:
        raise ValueError("governed formal write requires the exact request signature")
    normalized_outputs = tuple(dict.fromkeys(str(path).strip() for path in output_paths if str(path).strip()))
    if not normalized_outputs:
        raise ValueError("governed formal write requires at least one output path")
    if not draft_text.strip():
        raise ValueError("governed formal write requires a non-empty draft candidate")
    with OURDAgent(workspace, authority_path=authority_path, super_reasoning_enabled=False) as agent:
        agent.establish_governance(
            goal=objective,
            constraints=["apply only the exact source-grounded draft candidate"],
            assumptions=[],
            uncertainties=["human approval and final verification remain pending"],
            objects=list(normalized_outputs),
            relations=["draft candidate is bound to the confirmed formal-writing request"],
            boundaries=["formal-writing output paths only"],
            excluded_scope=[".ourd-agent/**"],
            allowed_paths=list(normalized_outputs),
            dimensions=["formal prose", "reference integrity", "citation rendering"],
            invariants=[
                "request signature remains exact",
                "source hashes remain current",
                "unrelated workspace files remain unchanged",
            ],
        )
        changes = [
            {"type": "write", "path": output_path, "content": draft_text}
            for output_path in normalized_outputs
        ]
        transaction = agent.prepare_transaction(changes)
        action = agent.propose_eon_action(
            summary=f"Prepare formal-writing output for request {request_signature}",
            operation="apply_transaction",
            targets=list(normalized_outputs),
            preconditions=["exact confirmed request signature", "current source hashes"],
            postconditions=["output bytes equal the prepared draft candidate"],
            preserve=["all non-target workspace files"],
            evidence=["reference integrity report", "writing certificate"],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=[],
            commands=[],
            required_tests=[],
            expires_at="",
            use_limit=1,
            varied_dimensions=["formal prose"],
        )
        return {
            "transaction": transaction,
            "eon_action": action["eon_action"],
            "status": "PREPARED_PENDING_EVIDENCE_AND_HUMAN_APPROVAL",
        }


__all__ = ["prepare_governed_formal_write"]
