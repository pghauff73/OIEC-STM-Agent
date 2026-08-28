from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Sequence

from .agent import OURDAgent
from .authority import save_authority_example
from .providers import ProviderConfig
from .workspace import Workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oiec-stm-agent",
        description="OIEC-STM bounded HRT/OURD/IURM/EON/CFEL coding agent",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repository/workspace root")
    parser.add_argument("--task", help="Run one task and exit")
    parser.add_argument("--authority", type=Path, help="Human-authored authority manifest")
    parser.add_argument(
        "--recovery-transaction",
        default="",
        help="Exact transaction ID authorized for restart-safe recovery",
    )
    parser.add_argument(
        "--write-authority-example",
        type=Path,
        help="Write a mutation-authority example bound to the current source snapshot",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OURD_MODEL", "gpt-5.6"),
        help="Responses API model name",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OURD_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
        help="OpenAI-compatible base URL, including /v1 for Ollama",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OURD_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        help="Provider API key; local Ollama accepts an ignored placeholder",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.getenv("OURD_REASONING_EFFORT", ""),
        choices=["", "none", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=int(os.getenv("OURD_MAX_OUTPUT_TOKENS", "2048")),
    )
    parser.add_argument(
        "--context-budget",
        type=int,
        default=int(os.getenv("OURD_CONTEXT_BUDGET", "6000")),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("OURD_TIMEOUT_SECONDS", "600")),
    )
    parser.add_argument(
        "--transport-retries",
        type=int,
        default=int(os.getenv("OURD_TRANSPORT_RETRIES", "0")),
        help="Bounded provider transport retries; defaults to zero",
    )
    parser.add_argument("--preflight", action="store_true", help="Check provider/model readiness")
    parser.add_argument("--snapshot", action="store_true", help="Print the current workspace snapshot hash")
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Skip interactive L2 prompt only when the authority manifest explicitly permits it",
    )
    parser.add_argument("--max-steps", type=int, default=80)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.repo)
    workspace = Workspace(root)
    if args.snapshot:
        print(workspace.snapshot_hash())
        return 0
    if args.write_authority_example is not None:
        save_authority_example(args.write_authority_example, workspace)
        print(args.write_authority_example)
        return 0
    config = ProviderConfig(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        reasoning_effort=args.reasoning_effort,
        max_output_tokens=max(1, args.max_output_tokens),
        context_budget_tokens=max(256, args.context_budget),
        timeout_seconds=max(1.0, args.timeout_seconds),
        max_transport_retries=max(0, min(args.transport_retries, 5)),
    )
    with OURDAgent(
        root,
        model=args.model,
        yolo=args.yolo,
        max_steps=max(1, args.max_steps),
        authority_path=args.authority,
        recovery_transaction_id=args.recovery_transaction,
        provider_config=config,
    ) as agent:
        if args.preflight:
            print(json.dumps(agent.provider_preflight(), indent=2, default=str))
            if not args.task:
                return 0
        if args.task:
            print(agent.run_task(args.task))
            return 0
        print(
            f"OIEC-STM-Agent | repo={agent.ws.root} | model={agent.model} | "
            f"authority={agent.state.authority.task_id}\n"
            "Enter a coding task. Ctrl-D / Ctrl-C exits."
        )
        while True:
            try:
                task = input("\noiec-stm> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not task:
                continue
            if task in {"/exit", "/quit"}:
                return 0
            if task == "/new":
                agent.clear_chat_history()
                print("Started a new chat context.")
                continue
            if task == "/help":
                print("Commands: /new clears chat context, /exit exits. Other input runs a governed agent turn.")
                continue
            try:
                print(agent.run_chat_turn(task))
            except Exception as exc:
                print(f"agent error: {exc}", file=os.sys.stderr)
