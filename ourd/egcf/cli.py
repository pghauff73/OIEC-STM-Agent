from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .engine import EGCFEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="egcf",
        description="Evidence Governed Command Fabric v1",
    )
    parser.add_argument("namespace", nargs="?", default="capability")
    parser.add_argument("verb", nargs="?", default="list")
    parser.add_argument("objective", nargs="*")
    parser.add_argument("--repo", default=".", help="Repository/workspace root")
    parser.add_argument("--authority", type=Path, help="External authority manifest")
    parser.add_argument(
        "--recovery-transaction",
        default="",
        help="Exact transaction ID authorized for restart-safe recovery",
    )
    parser.add_argument("--input", default="{}", help="JSON object containing command inputs")
    parser.add_argument("--input-file", type=Path, help="Read command input JSON from a file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--why", action="store_true")
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument(
        "--approval",
        choices=["automatic", "policy", "human", "quorum"],
        default="automatic",
    )
    parser.add_argument("--risk", choices=["L0", "L1", "L2"], default="L0")
    parser.add_argument(
        "--rollback",
        choices=["none", "best_effort", "compensating", "exact"],
        default="none",
    )
    parser.add_argument("--budget", default="")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--graph", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--replay", default="", metavar="PLAN_ID")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--human-confirmation", action="store_true")
    parser.add_argument("--rebuild-projection", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    return parser


def _load_inputs(args: argparse.Namespace) -> Dict[str, Any]:
    if args.input_file is not None:
        payload = json.loads(args.input_file.read_text(encoding="utf-8"))
    else:
        payload = json.loads(args.input)
    if not isinstance(payload, dict):
        raise ValueError("command input must be a JSON object")
    if args.human_confirmation:
        payload["human_confirmation"] = True
    return payload


def _modifiers(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "dry_run": args.dry_run,
        "why": args.why,
        "scope": args.scope or ["**"],
        "evidence": args.evidence,
        "approval": args.approval,
        "risk": args.risk,
        "rollback": args.rollback,
        "budget": args.budget,
        "timeout": args.timeout,
        "trace": args.trace,
        "json_output": args.json_output,
        "graph": args.graph,
        "record": args.record,
        "replay": args.replay,
        "strict": args.strict,
        "simulate": args.simulate,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with EGCFEngine(
            Path(args.repo),
            authority_path=args.authority,
            recovery_transaction_id=args.recovery_transaction,
        ) as engine:
            if args.snapshot:
                result: Any = {"source_snapshot_hash": engine.workspace.snapshot_hash()}
            elif args.rebuild_projection:
                engine.store.rebuild_projection()
                result = {"ok": True, "projection": str(engine.store.projection_path), "rebuilt": True}
            elif args.replay:
                result = engine.replay(args.replay, _modifiers(args))
            elif args.namespace == "run":
                objective = " ".join([args.verb, *args.objective]).strip()
                result = engine.run_objective(
                    objective,
                    inputs=_load_inputs(args),
                    modifiers=_modifiers(args),
                )
            else:
                if args.objective:
                    parser.error("extra positional arguments are supported only by 'egcf run'")
                result = engine.invoke(
                    f"{args.namespace}.{args.verb}",
                    _load_inputs(args),
                    _modifiers(args),
                )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
