from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .egcf.algebra.improvement_scheduling import (
    OPPORTUNITY_KINDS,
    ImprovementOpportunity,
    ImprovementSchedulingPolicy,
    make_improvement_opportunity,
    schedule_improvements,
)
from .egcf.errors import EGCFError
from .egcf.knowledge_governance_store import KnowledgeGovernanceStore
from .egcf.store import EGCFStore


PROGRAM = "oiec-stm-agent improvement"


def _bp(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer basis-point value") from exc
    if parsed < 0 or parsed > 10000:
        raise argparse.ArgumentTypeError("must be in 0..10000 basis points")
    return parsed


def _cost_budget(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer basis-point cost budget") from exc
    if parsed < 0 or parsed > 160000:
        raise argparse.ArgumentTypeError("must be in 0..160000 basis-point cost units")
    return parsed


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Repository/workspace root")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Operate SAA-12.4 evidence-grounded improvement scheduling. "
            "Scheduling ranks investigations; it never grants mutation authority."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Register one evidence-grounded improvement opportunity")
    _add_common(add)
    add.add_argument("--input-file", type=Path, help="Read the opportunity fields from a JSON object")
    add.add_argument("--id", dest="opportunity_id", help="Stable human-facing opportunity identifier")
    add.add_argument("--kind", choices=sorted(OPPORTUNITY_KINDS), help="Opportunity kind")
    add.add_argument("--source-signature", help="SHA-256 signature of the source failure/gap/signal")
    add.add_argument("--objective", help="Investigation objective")
    add.add_argument("--evidence-value-bp", type=_bp, help="Evidence value, 0..10000 basis points")
    add.add_argument("--impact-bp", type=_bp, help="Expected impact, 0..10000 basis points")
    add.add_argument("--uncertainty-reduction-bp", type=_bp, help="Expected uncertainty reduction, 0..10000 basis points")
    add.add_argument("--cost-bp", type=_bp, help="Estimated investigation cost, 0..10000 basis points")
    add.add_argument("--risk-bp", type=_bp, help="Investigation risk, 0..10000 basis points")
    add.add_argument("--evidence", action="append", default=[], metavar="EVIDENCE_ID", help="Grounded EvidenceArtifact ID; repeat as needed")
    add.add_argument("--blocked-reason", action="append", default=[], help="Known blocker; repeat as needed")

    list_parser = sub.add_parser("list", help="List registered improvement opportunities")
    _add_common(list_parser)
    list_parser.add_argument("--kind", choices=sorted(OPPORTUNITY_KINDS), help="Filter by opportunity kind")
    list_parser.add_argument("--eligible-only", action="store_true", help="Show only opportunities without hard blockers")

    schedule = sub.add_parser("schedule", help="Rank and select bounded improvement investigations")
    _add_common(schedule)
    schedule.add_argument("--kind", action="append", choices=sorted(OPPORTUNITY_KINDS), default=[], help="Only schedule these kinds; repeat as needed")
    schedule.add_argument("--eligible-only", action="store_true", help="Exclude blocked opportunities before scheduling")
    schedule.add_argument("--max-selected", type=int, default=4, help="Maximum selected investigations, 1..16")
    schedule.add_argument("--cost-budget-bp", type=_cost_budget, default=20000, help="Total scheduling cost budget, 0..160000")
    schedule.add_argument("--max-risk-bp", type=_bp, default=6000, help="Maximum permitted investigation risk")
    schedule.add_argument("--min-priority-bp", type=_bp, default=1000, help="Minimum priority for selection")
    schedule.add_argument("--record", action="store_true", help="Persist the immutable schedule artifact after calculating it")
    schedule.add_argument("--explain", action="store_true", help="Include a human explanation of selected and deferred opportunities")

    history = sub.add_parser("history", help="List previously recorded improvement schedules")
    _add_common(history)

    return parser


def _load_input_file(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EGCFError(f"cannot read opportunity input file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EGCFError("improvement opportunity input file must contain a JSON object")
    return payload


def _add_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_file is not None:
        payload = dict(_load_input_file(args.input_file))
        if args.evidence:
            payload["evidence_ids"] = list(args.evidence)
        if args.blocked_reason:
            payload["blocked_reasons"] = list(args.blocked_reason)
        return payload
    required = {
        "opportunity_id": args.opportunity_id,
        "kind": args.kind,
        "source_signature": args.source_signature,
        "objective": args.objective,
        "evidence_value_bp": args.evidence_value_bp,
        "expected_impact_bp": args.impact_bp,
        "uncertainty_reduction_bp": args.uncertainty_reduction_bp,
        "cost_bp": args.cost_bp,
        "risk_bp": args.risk_bp,
    }
    missing = [name for name, value in required.items() if value is None or value == ""]
    if missing:
        raise EGCFError("improvement add is missing required fields: " + ", ".join(missing))
    required["evidence_ids"] = list(args.evidence)
    required["blocked_reasons"] = list(args.blocked_reason)
    return required


def _make_opportunity(store: EGCFStore, payload: Mapping[str, Any]) -> ImprovementOpportunity:
    return make_improvement_opportunity(
        store,
        opportunity_id=str(payload.get("opportunity_id", payload.get("id", ""))),
        kind=str(payload.get("kind", "")),
        source_signature=str(payload.get("source_signature", "")),
        objective=str(payload.get("objective", "")),
        evidence_value_bp=int(payload.get("evidence_value_bp")),
        expected_impact_bp=int(payload.get("expected_impact_bp", payload.get("impact_bp"))),
        uncertainty_reduction_bp=int(payload.get("uncertainty_reduction_bp")),
        cost_bp=int(payload.get("cost_bp")),
        risk_bp=int(payload.get("risk_bp")),
        evidence_ids=tuple(payload.get("evidence_ids", ())),
        blocked_reasons=tuple(payload.get("blocked_reasons", ())),
    )


def _percent(bp: int) -> str:
    return f"{bp / 100:.2f}%"


def _print_opportunities(records: Sequence[ImprovementOpportunity]) -> None:
    if not records:
        print("No improvement opportunities are registered.")
        return
    print("SAA-12.4 improvement opportunities")
    print("Scheduling authorizes investigation only; it never grants mutation authority.\n")
    for item in records:
        state = "eligible" if item.eligible else "blocked"
        print(
            f"{item.opportunity_id} | {item.kind} | priority {_percent(item.priority_bp)} | "
            f"cost {_percent(item.cost_bp)} | risk {_percent(item.risk_bp)} | {state}"
        )
        print(f"  {item.objective}")
        if item.blocked_reasons:
            print("  blockers: " + "; ".join(item.blocked_reasons))
        print(f"  signature: {item.opportunity_signature}")


def _explain_schedule(schedule: Any, by_signature: Mapping[str, ImprovementOpportunity]) -> list[str]:
    lines = [
        "SAA-12.4 schedules investigations, not mutations.",
        f"Status: {schedule.status}",
        f"Selected {len(schedule.selected)} investigation(s); allocated cost {_percent(schedule.total_allocated_cost_bp)}.",
    ]
    for entry in schedule.selected:
        item = by_signature.get(entry.opportunity_signature)
        objective = item.objective if item else entry.opportunity_id
        lines.append(
            f"SELECT #{entry.rank}: {entry.opportunity_id} at priority {_percent(entry.priority_bp)}; "
            f"cost {_percent(entry.allocated_cost_bp)}. Objective: {objective}"
        )
    for opportunity_id, reason in schedule.deferred:
        lines.append(f"DEFER: {opportunity_id} because {reason}.")
    return lines


def _schedule_to_dict(schedule: Any, *, recorded_ref: str = "", explanation: Sequence[str] = ()) -> dict[str, Any]:
    payload = schedule.to_dict()
    payload["recorded_schedule_ref"] = recorded_ref
    payload["authority_effect"] = "INVESTIGATION_PRIORITY_ONLY_NO_MUTATION_AUTHORITY"
    if explanation:
        payload["explanation"] = list(explanation)
    return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo)
        with EGCFStore(root) as egcf:
            governance = KnowledgeGovernanceStore(egcf)
            if args.command == "add":
                opportunity = _make_opportunity(egcf, _add_payload(args))
                ref = governance.register_opportunity(opportunity)
                result = {"opportunity_ref": ref, **opportunity.to_dict()}
                if args.json_output:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print(f"Registered improvement opportunity: {opportunity.opportunity_id}")
                    print(f"  kind: {opportunity.kind}")
                    print(f"  priority: {_percent(opportunity.priority_bp)}")
                    print(f"  eligible: {opportunity.eligible}")
                    print(f"  ref: {ref}")
                return 0

            if args.command == "list":
                records = governance.improvement_opportunities(
                    kind=args.kind,
                    eligible_only=args.eligible_only,
                )
                if args.json_output:
                    print(json.dumps([item.to_dict() for item in records], indent=2, ensure_ascii=False))
                else:
                    _print_opportunities(records)
                return 0

            if args.command == "schedule":
                kinds = set(args.kind)
                records = governance.improvement_opportunities(eligible_only=args.eligible_only)
                if kinds:
                    records = [item for item in records if item.kind in kinds]
                policy = ImprovementSchedulingPolicy(
                    max_selected=args.max_selected,
                    total_cost_budget_bp=args.cost_budget_bp,
                    maximum_risk_bp=args.max_risk_bp,
                    minimum_priority_bp=args.min_priority_bp,
                )
                schedule = schedule_improvements(records, policy)
                recorded_ref = governance.register_schedule(schedule) if args.record else ""
                by_signature = {item.opportunity_signature: item for item in records}
                explanation = _explain_schedule(schedule, by_signature) if args.explain else ()
                result = _schedule_to_dict(schedule, recorded_ref=recorded_ref, explanation=explanation)
                if args.json_output:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    for line in _explain_schedule(schedule, by_signature):
                        print(line)
                    if recorded_ref:
                        print(f"Recorded immutable schedule: {recorded_ref}")
                    else:
                        print("Preview only. Add --record to persist this schedule.")
                return 0

            if args.command == "history":
                records = governance.improvement_schedules()
                if args.json_output:
                    print(json.dumps(records, indent=2, ensure_ascii=False))
                elif not records:
                    print("No recorded improvement schedules.")
                else:
                    print("Recorded SAA-12.4 improvement schedules")
                    for record in records:
                        payload = record["payload"]
                        print(
                            f"{record['schedule_ref']} | {payload['status']} | "
                            f"selected={len(payload['selected'])} | cost={_percent(payload['total_allocated_cost_bp'])}"
                        )
                return 0
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2),
            file=sys.stderr,
        )
        return 2
    parser.error("unknown improvement command")
    return 2
