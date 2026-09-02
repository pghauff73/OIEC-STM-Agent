from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ourd.models import RuntimeState


REASONING_EXPORT_SCHEMA_VERSION = 1


def reasoning_projection(state: RuntimeState) -> dict[str, Any]:
    candidates = state.reasoning_candidates
    metrics = {} if candidates is None else {
        item.path_id: asdict(item) for item in candidates.metrics
    }
    verifier = {} if candidates is None else {
        item.path_id: asdict(item) for item in candidates.verifier_reports
    }
    falsifier = {} if candidates is None else {
        item.path_id: asdict(item) for item in candidates.falsifier_reports
    }
    paths = []
    if candidates is not None:
        for path in candidates.paths:
            paths.append(
                {
                    "path_id": path.path_id,
                    "strategy": path.perspective,
                    "hypothesis_ids": list(path.hypothesis_ids),
                    "conclusion": path.conclusion,
                    "structure_signature": path.structure_signature,
                    "diversity_bp": path.diversity_bp,
                    "steps": [asdict(step) for step in path.steps],
                    "metrics": metrics.get(path.path_id),
                    "verifier": verifier.get(path.path_id),
                    "falsifier": falsifier.get(path.path_id),
                }
            )
    return {
        "schema_version": REASONING_EXPORT_SCHEMA_VERSION,
        "authoritative": False,
        "export_kind": "oiec-sr-read-only-observability",
        "notice": (
            "This projection cannot grant authority, approve evidence, mutate the "
            "repository, or certify an EON action."
        ),
        "runtime_schema_version": state.schema_version,
        "problem": asdict(state.reasoning_problem) if state.reasoning_problem else None,
        "budget": asdict(state.reasoning_budget) if state.reasoning_budget else None,
        "hypothesis_state": (
            asdict(state.reasoning_hypothesis_state)
            if state.reasoning_hypothesis_state
            else None
        ),
        "paths": paths,
        "selected_path_id": candidates.selected_path_id if candidates else "",
        "surviving_path_ids": list(candidates.surviving_path_ids) if candidates else [],
        "score_config_id": candidates.score_config_id if candidates else "",
        "score_config_hash": candidates.score_config_hash if candidates else "",
        "diversity_config_hash": candidates.diversity_config_hash if candidates else "",
        "synthesis": asdict(state.last_synthesis) if state.last_synthesis else None,
        "contradictions": [asdict(item) for item in state.reasoning_contradictions],
        "context": asdict(state.reasoning_context) if state.reasoning_context else None,
        "next_operation": (
            asdict(state.next_reasoning_operation)
            if state.next_reasoning_operation
            else None
        ),
        "certificate": (
            asdict(state.last_reasoning_certificate)
            if state.last_reasoning_certificate
            else None
        ),
        "limits": {
            "path_count": len(paths),
            "hypothesis_count": (
                len(state.reasoning_hypothesis_state.hypotheses)
                if state.reasoning_hypothesis_state
                else 0
            ),
            "contradiction_count": len(state.reasoning_contradictions),
            "context_item_limit": (
                state.reasoning_context.max_items if state.reasoning_context else 0
            ),
        },
    }


def load_reasoning_projection(repository_root: Path) -> dict[str, Any]:
    state_path = repository_root / ".ourd-agent" / "state.json"
    if not state_path.exists():
        return reasoning_projection(RuntimeState())
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return reasoning_projection(RuntimeState.from_dict(payload))


def reasoning_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def reasoning_markdown(payload: dict[str, Any]) -> str:
    certificate = payload.get("certificate") or {}
    synthesis = payload.get("synthesis") or {}
    lines = [
        "# OIEC-SR Reasoning Export",
        "",
        "**Authority:** non-authoritative read-only GUI projection  ",
        f"**Problem hash:** `{certificate.get('problem_hash', '')}`  ",
        f"**Decision:** `{certificate.get('decision', 'UNAVAILABLE')}`  ",
        f"**Terminal state:** `{certificate.get('terminal_state', 'UNAVAILABLE')}`  ",
        f"**Certificate:** `{certificate.get('signature', '')}`",
        "",
        "## Synthesis",
        "",
        synthesis.get("merged_conclusion", "No synthesis is available."),
        "",
        f"- Verified: `{bool(synthesis.get('verified', False))}`",
        f"- Winner: `{synthesis.get('winning_path_id', '')}`",
        f"- Sources: `{', '.join(synthesis.get('source_path_ids', []))}`",
        "",
        "## Candidates",
        "",
    ]
    for path in payload.get("paths", []):
        metrics = path.get("metrics") or {}
        verifier = path.get("verifier") or {}
        falsifier = path.get("falsifier") or {}
        lines.extend(
            [
                f"### `{path.get('path_id', '')}`",
                "",
                f"- Strategy: `{path.get('strategy', '')}`",
                f"- Score: `{metrics.get('total_score_bp', 0)}`",
                f"- Weakest verifier step: `{verifier.get('weakest_step_bp', 0)}`",
                f"- Falsifier survival: `{falsifier.get('survival_bp', 0)}`",
                f"- Conclusion: {path.get('conclusion', '')}",
                "",
            ]
        )
    lines.extend(["## Contradictions", ""])
    for record in payload.get("contradictions", []) or [{}]:
        if not record:
            lines.append("- None")
            continue
        lines.append(
            f"- `{record.get('contradiction_id', '')}` "
            f"{record.get('conflict_type', '')} severity="
            f"`{record.get('severity_bp', 0)}` status="
            f"`{record.get('resolution_status', '')}`"
        )
    lines.extend(
        [
            "",
            "## Notice",
            "",
            str(payload.get("notice", "")),
        ]
    )
    return "\n".join(lines) + "\n"


def write_reasoning_export(
    repository_root: Path,
    payload: dict[str, Any],
    format_name: str,
) -> Path:
    certificate = payload.get("certificate") or {}
    identity = str(certificate.get("signature", "unavailable"))[:16] or "unavailable"
    export_dir = repository_root / ".ourd-agent" / "gui"
    export_dir.mkdir(parents=True, exist_ok=True)
    if format_name == "json":
        path = export_dir / f"reasoning-{identity}.json"
        content = reasoning_json(payload)
    elif format_name == "markdown":
        path = export_dir / f"reasoning-{identity}.md"
        content = reasoning_markdown(payload)
    else:
        raise ValueError("reasoning export format must be json or markdown")
    path.write_text(content, encoding="utf-8")
    return path


__all__ = [
    "load_reasoning_projection",
    "reasoning_json",
    "reasoning_markdown",
    "reasoning_projection",
    "write_reasoning_export",
]
