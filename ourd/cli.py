from __future__ import annotations

import argparse
import getpass
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .production_agent import ProductionOURDAgent as OURDAgent
from .authority import save_authority, save_authority_example, scoped_write_authority
from .formal_writing import (
    FormalWritingService,
    WRITING_PROFILES,
    compile_formal_writing_request,
)
from .errors import PolicyError
from .interaction import (
    InteractionSessionSnapshot,
    PinnedContextSet,
    build_context_envelope,
    build_interaction_confirmation,
    build_interaction_confirmation_receipt,
    build_pinned_context_envelope,
    compare_context_envelopes,
    dispatch_interaction,
    interaction_confirmation_receipt_audit_metadata,
    pinned_context_freshness,
    render_context_delta,
    require_fresh_pinned_context,
    require_interaction_confirmation_receipt,
    route_interaction,
)
from .providers import (
    ProviderConfig,
    QWEN38_Q2_K_MODEL_PATH,
    QWEN38_Q2_K_SHA256,
)
from .reasoning import SuperReasoningKernel
from .workspace import Workspace
from .writing import WRITE_COMMAND_CAPABILITIES, writing_task_prompt


MAX_LOOP_ITERATIONS = 32
LOOP_COMPLETE_SENTINEL = "ICPI_LOOP_COMPLETE"
LOOP_USAGE = "usage: /loop COUNT TASK"


@dataclass(frozen=True)
class LoopCommand:
    iterations: int
    task: str

    def prompt(self, index: int) -> str:
        expanded_task = self.task.replace("{index}", str(index)).replace(
            "{count}", str(self.iterations)
        )
        return (
            f"ICPI bounded CLI loop iteration {index} of {self.iterations}. "
            "Normal authority, evidence, OIEC progress, and cycle controls remain active. "
            f"If the overall loop objective is complete, respond exactly {LOOP_COMPLETE_SENTINEL}.\n\n"
            f"{expanded_task}"
        )


@dataclass(frozen=True)
class LoopResult:
    requested_iterations: int
    completed_iterations: int
    stop_reason: str


def parse_loop_command(text: str) -> Optional[LoopCommand]:
    parts = text.strip().split(maxsplit=2)
    if not parts or parts[0].casefold() != "/loop":
        return None
    if len(parts) != 3 or not parts[2].strip():
        raise ValueError(LOOP_USAGE)
    try:
        iterations = int(parts[1])
    except ValueError as exc:
        raise ValueError("loop count must be an integer") from exc
    if not 1 <= iterations <= MAX_LOOP_ITERATIONS:
        raise ValueError(
            f"loop count must be between 1 and {MAX_LOOP_ITERATIONS}"
        )
    return LoopCommand(iterations=iterations, task=parts[2].strip())


def run_loop_command(
    agent: Any,
    command: LoopCommand,
    bounded_task: Callable[[str], str],
    emit: Callable[[str], None] = print,
) -> LoopResult:
    for index in range(1, command.iterations + 1):
        emit(f"[loop {index}/{command.iterations}]")
        response = agent.run_chat_turn(bounded_task(command.prompt(index)))
        if response.strip() == LOOP_COMPLETE_SENTINEL:
            emit(f"[loop completed at {index}/{command.iterations}]")
            return LoopResult(
                requested_iterations=command.iterations,
                completed_iterations=index,
                stop_reason="completion_sentinel",
            )
        emit(response)
    return LoopResult(
        requested_iterations=command.iterations,
        completed_iterations=command.iterations,
        stop_reason="iteration_limit",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oiec-stm-agent",
        description="OIEC-STM bounded reasoning, writing, and coding agent",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repository/workspace root")
    parser.add_argument("--task", help="Run one task and exit")
    parser.add_argument("--authority", type=Path, help="Human-authored authority manifest")
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Enable a human-granted bounded writing session. Requires at least one "
            "--write-path and keeps exact-candidate approval enabled."
        ),
    )
    parser.add_argument(
        "--writing-profile",
        default="general",
        choices=WRITING_PROFILES,
        help=(
            "Formal writing profile for --write mode: general, scientific-essay, "
            "or argumentative-essay."
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="PATH",
        help="Formal-writing source path; repeatable and valid only with --write",
    )
    parser.add_argument(
        "--rubric",
        action="append",
        default=[],
        metavar="PATH",
        help="Formal-writing rubric path; repeatable and valid only with --write",
    )
    parser.add_argument(
        "--draft",
        action="append",
        default=[],
        metavar="PATH",
        help="Prior draft path for source-grounded revision; valid only with --write",
    )
    parser.add_argument("--genre", default="essay")
    parser.add_argument("--audience", default="general")
    parser.add_argument("--discipline", default="general")
    parser.add_argument("--word-target", type=int, default=0)
    parser.add_argument("--citation-style", default="author-date")
    parser.add_argument(
        "--network-policy",
        choices=("offline", "metadata-only", "explicit-retrieval"),
        default="offline",
    )
    parser.add_argument("--require-page-accuracy", action="store_true")
    parser.add_argument("--allow-ocr", action="store_true")
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument(
        "--write-path",
        action="append",
        default=[],
        metavar="PATH_OR_PATTERN",
        help="Writable path/pattern for --write mode; repeat to grant multiple paths",
    )
    parser.add_argument(
        "--write-command-capability",
        action="append",
        default=[],
        choices=WRITE_COMMAND_CAPABILITIES,
        help="Optional deterministic command capability granted to the writing session",
    )
    parser.add_argument(
        "--write-test",
        action="append",
        default=[],
        metavar="COMMAND",
        help="Mandatory verification command for --write mode; repeat as needed",
    )
    parser.add_argument(
        "--write-allow-l2",
        action="store_true",
        help="Allow interactive L2 candidates in --write mode; never makes them automatic",
    )
    parser.add_argument(
        "--write-retries",
        type=int,
        default=1,
        help="Maximum retries per governed action in --write mode (0-10)",
    )
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
        "--provider",
        default=os.getenv("OURD_PROVIDER", "llama_cpp_process"),
        choices=["llama_cpp_process"],
        help="Direct local model provider boundary",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OURD_MODEL", "qwen3.8-27b-direct"),
        help="Direct local model name shown in traces and reports",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OURD_BASE_URL", ""),
        help="Deprecated compatibility field; llama_cpp_process does not use HTTP",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OURD_API_KEY", ""),
        help="Deprecated compatibility field; llama_cpp_process does not use API keys",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.getenv("OURD_REASONING_EFFORT", ""),
        choices=["", "none", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument(
        "--json-object-output",
        action="store_true",
        default=os.getenv("OURD_JSON_OBJECT_OUTPUT", "").strip().lower()
        in {"1", "true", "yes", "on"},
        help="Deprecated compatibility flag; direct process output is grammar-first JSON",
    )
    parser.add_argument(
        "--response-temperature-bp",
        type=int,
        default=int(os.getenv("OURD_RESPONSE_TEMPERATURE_BP", "-1")),
        help="Deprecated compatibility temperature field; use --llama-temperature-bp",
    )
    parser.add_argument(
        "--response-top-p-bp",
        type=int,
        default=int(os.getenv("OURD_RESPONSE_TOP_P_BP", "-1")),
        help="Deprecated compatibility top-p field; use --llama-top-p-bp",
    )
    parser.add_argument(
        "--response-seed",
        type=int,
        default=int(os.getenv("OURD_RESPONSE_SEED", "-1")),
        help="Deprecated compatibility seed field; use --llama-seed",
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
        "--runtime-context-tokens",
        type=int,
        default=int(os.getenv("OURD_RUNTIME_CONTEXT", "0")),
        help="Known provider runtime context; zero disables the combined runtime bound",
    )
    parser.add_argument(
        "--context-safety-margin",
        type=int,
        default=int(os.getenv("OURD_CONTEXT_SAFETY_MARGIN", "512")),
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
    parser.add_argument(
        "--max-reasoning-samples",
        type=int,
        default=int(os.getenv("OURD_MAX_REASONING_SAMPLES", "16")),
        help="Hard cap for one OIEC-SR multi-response episode",
    )
    parser.add_argument(
        "--disable-super-reasoning",
        action="store_true",
        help="Remove OIEC-SR from the session tool surface.",
    )
    parser.add_argument(
        "--sr-max-candidates",
        type=int,
        default=int(os.getenv("OIEC_SR_MAX_CANDIDATES", "16")),
    )
    parser.add_argument(
        "--sr-max-provider-calls",
        type=int,
        default=int(os.getenv("OIEC_SR_MAX_PROVIDER_CALLS", "64")),
    )
    parser.add_argument(
        "--sr-minimum-voi-bp",
        type=int,
        default=int(os.getenv("OIEC_SR_MINIMUM_VOI_BP", "100")),
    )
    parser.add_argument(
        "--runner-path",
        default=os.getenv("OURD_LLAMA_RUNNER", ""),
        help="Native oiec-llama-runner executable for llama_cpp_process",
    )
    parser.add_argument(
        "--model-path",
        default=os.getenv("OURD_LLAMA_MODEL_PATH", QWEN38_Q2_K_MODEL_PATH),
        help="Exact local GGUF path for llama_cpp_process",
    )
    parser.add_argument(
        "--expected-model-sha256",
        default=os.getenv("OURD_LLAMA_MODEL_SHA256", QWEN38_Q2_K_SHA256),
        help="Required GGUF SHA-256 for llama_cpp_process preflight",
    )
    parser.add_argument(
        "--llama-cpp-root",
        default=os.getenv("OURD_LLAMA_CPP_ROOT", ""),
    )
    parser.add_argument(
        "--llama-cpp-build-dir",
        default=os.getenv("OURD_LLAMA_CPP_BUILD_DIR", ""),
    )
    parser.add_argument(
        "--llama-grammar-dir",
        default=os.getenv("OURD_LLAMA_GRAMMAR_DIR", ""),
    )
    parser.add_argument(
        "--llama-context",
        type=int,
        default=int(os.getenv("OURD_LLAMA_CONTEXT", "8192")),
    )
    parser.add_argument(
        "--llama-gpu-layers",
        type=int,
        default=int(os.getenv("OURD_LLAMA_GPU_LAYERS", "-1")),
    )
    parser.add_argument(
        "--llama-threads",
        type=int,
        default=int(os.getenv("OURD_LLAMA_THREADS", "0")),
    )
    parser.add_argument(
        "--llama-seed",
        type=int,
        default=int(os.getenv("OURD_LLAMA_SEED", "1234")),
    )
    parser.add_argument(
        "--llama-temperature-bp",
        type=int,
        default=int(os.getenv("OURD_LLAMA_TEMPERATURE_BP", "1000")),
    )
    parser.add_argument(
        "--llama-top-p-bp",
        type=int,
        default=int(os.getenv("OURD_LLAMA_TOP_P_BP", "9500")),
    )
    parser.add_argument(
        "--llama-top-k",
        type=int,
        default=int(os.getenv("OURD_LLAMA_TOP_K", "40")),
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


def _validate_write_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    formal_options_used = bool(
        args.source
        or args.rubric
        or args.draft
        or args.genre != "essay"
        or args.audience != "general"
        or args.discipline != "general"
        or args.word_target
        or args.citation_style != "author-date"
        or args.network_policy != "offline"
        or args.require_page_accuracy
        or args.allow_ocr
        or args.ocr_language != "eng"
    )
    write_options_used = bool(
        args.write_path
        or args.write_command_capability
        or args.write_test
        or args.write_allow_l2
        or args.write_retries != 1
        or args.writing_profile != "general"
        or formal_options_used
    )
    if write_options_used and not args.write:
        parser.error("--writing-profile/--write-path/--write-test/--write-* options require --write")
    if not args.write:
        return
    if args.authority is not None:
        parser.error("--write and --authority are mutually exclusive")
    if not args.write_path:
        parser.error("--write requires at least one explicit --write-path")
    if formal_options_used and not args.source:
        parser.error("formal-writing options require at least one --source")
    if len(args.draft) > 1:
        parser.error("formal-writing revision accepts exactly one --draft path")
    if args.yolo:
        parser.error(
            "bounded --write mode never grants --yolo; use a reviewed authority manifest instead"
        )
    if not 0 <= args.write_retries <= 10:
        parser.error("--write-retries must be between 0 and 10")


def _compile_formal_write_request(
    args: argparse.Namespace,
    objective: str,
    *,
    authority_binding: str = "",
):
    if not args.source:
        return None
    return compile_formal_writing_request(
        operation="revise" if args.draft else "write",
        objective=objective,
        profile=args.writing_profile,
        genre=args.genre,
        audience=args.audience,
        discipline=args.discipline,
        word_target=args.word_target,
        source_paths=tuple(args.source),
        rubric_paths=tuple(args.rubric),
        draft_paths=tuple(args.draft),
        output_paths=tuple(args.write_path),
        citation_style=args.citation_style,
        network_policy=args.network_policy,
        requested_outputs=("write",),
        authority_binding=authority_binding,
    )


def _formal_writing_task_prompt(
    args: argparse.Namespace,
    workspace: Workspace,
    objective: str,
    *,
    authority_binding: str,
) -> str:
    request = _compile_formal_write_request(
        args,
        objective,
        authority_binding=authority_binding,
    )
    if request is None:
        return writing_task_prompt(objective, args.write_path, profile=args.writing_profile)
    result = FormalWritingService(workspace).execute(
        request,
        allow_ocr=args.allow_ocr,
        ocr_language=args.ocr_language,
    )
    if args.require_page_accuracy:
        non_paginated = [
            source.workspace_relative_path
            for source in result.sources
            if source.page_count == 0
        ]
        if non_paginated:
            raise PolicyError(
                "page accuracy was required, but these sources have no stable pages: "
                + ", ".join(non_paginated)
            )
    if result.draft is None or result.integrity_report is None:
        raise PolicyError("formal-writing request did not produce a verifiable draft candidate")
    if not result.integrity_report.passed:
        raise PolicyError(
            "formal-writing candidate failed reference integrity: "
            + result.integrity_report.report_id
        )
    return (
        writing_task_prompt(objective, args.write_path, profile=args.writing_profile)
        + "\n\nFORMAL WRITING ENGINE CANDIDATE\n"
        + f"Request signature: {request.request_signature}\n"
        + f"Draft signature: {result.draft.signature}\n"
        + f"Reference integrity report: {result.integrity_report.report_id}\n"
        + "Prepare the exact candidate below for the governed transaction. Do not invent, "
        + "remove, or alter references without producing a new formal-writing request and audit.\n\n"
        + result.draft.text
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_args = tuple(argv) if argv is not None else tuple(os.sys.argv[1:])
    if raw_args and raw_args[0] == "improvement":
        from .improvement_cli import main as improvement_main

        return improvement_main(raw_args[1:])
    if len(raw_args) >= 2 and raw_args[0] == "write":
        from .formal_writing_cli import COMMANDS, main as formal_writing_main

        if raw_args[1] in COMMANDS:
            return formal_writing_main(raw_args[1:])
    parser = build_parser()
    args = parser.parse_args(raw_args)
    _validate_write_args(parser, args)
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
        provider_kind=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        reasoning_effort=args.reasoning_effort,
        json_object_output=args.json_object_output,
        response_temperature_bp=args.response_temperature_bp,
        response_top_p_bp=args.response_top_p_bp,
        response_seed=args.response_seed,
        max_output_tokens=max(1, args.max_output_tokens),
        context_budget_tokens=max(256, args.context_budget),
        runtime_context_tokens=max(0, args.runtime_context_tokens),
        context_safety_margin_tokens=max(0, args.context_safety_margin),
        timeout_seconds=max(1.0, args.timeout_seconds),
        max_transport_retries=max(0, min(args.transport_retries, 5)),
        max_reasoning_samples=max(1, min(args.max_reasoning_samples, 64)),
        runner_path=args.runner_path,
        model_path=args.model_path,
        expected_model_sha256=args.expected_model_sha256,
        llama_cpp_root=args.llama_cpp_root,
        llama_cpp_build_dir=args.llama_cpp_build_dir,
        llama_grammar_dir=args.llama_grammar_dir,
        llama_context_tokens=max(256, args.llama_context),
        llama_gpu_layers=args.llama_gpu_layers,
        llama_threads=max(0, args.llama_threads),
        llama_seed=args.llama_seed,
        llama_temperature_bp=args.llama_temperature_bp,
        llama_top_p_bp=args.llama_top_p_bp,
        llama_top_k=args.llama_top_k,
    )
    super_reasoning = SuperReasoningKernel(
        max_candidates=max(1, min(args.sr_max_candidates, 16)),
        max_provider_calls=max(4, min(args.sr_max_provider_calls, 256)),
        minimum_voi_bp=max(0, min(args.sr_minimum_voi_bp, 10_000)),
    )

    temporary_authority: Optional[tempfile.TemporaryDirectory[str]] = None
    authority_path = args.authority
    if args.write:
        manifest = scoped_write_authority(
            workspace,
            allowed_paths=args.write_path,
            goal=args.task or "Interactive bounded writing session",
            operator=getpass.getuser() or "cli-user",
            command_capabilities=args.write_command_capability,
            mandatory_tests=args.write_test,
            allow_interactive_l2=args.write_allow_l2,
            max_retries_per_action=args.write_retries,
        )
        temporary_authority = tempfile.TemporaryDirectory(prefix="oiec-write-authority-")
        authority_path = Path(temporary_authority.name) / "authority.json"
        save_authority(authority_path, manifest)

    authority_binding = manifest.authority_hash if args.write else ""

    def bounded_task(text: str) -> str:
        if not args.write:
            return text
        return _formal_writing_task_prompt(
            args,
            workspace,
            text,
            authority_binding=authority_binding,
        )

    try:
        with OURDAgent(
            root,
            model=args.model,
            yolo=args.yolo,
            max_steps=max(1, args.max_steps),
            authority_path=authority_path,
            recovery_transaction_id=args.recovery_transaction,
            provider_config=config,
            super_reasoning_kernel=super_reasoning,
            super_reasoning_enabled=not args.disable_super_reasoning,
        ) as agent:
            if args.preflight:
                print(json.dumps(agent.provider_preflight(), indent=2, default=str))
                if not args.task:
                    return 0
            if args.task:
                print(agent.run_task(bounded_task(args.task)))
                return 0
            mode = "write" if args.write else "read-only"
            profile = args.writing_profile if args.write else "none"
            print(
                f"OIEC-STM-Agent | repo={agent.ws.root} | model={agent.model} | "
                f"authority={agent.state.authority.task_id} | mode={mode} | "
                f"writing-profile={profile}\n"
                "Enter a reasoning, writing, or coding task. Ctrl-D / Ctrl-C exits."
            )
            pinned_context = PinnedContextSet()
            pinned_context_envelope = None
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
                if task == "/help":
                    print(
                        "Commands:\n"
                        "  /new                 Clear chat context and pinned paths.\n"
                        "  /context             Show active pinned context state.\n"
                        "  /context add PATH    Pin source context for later tasks.\n"
                        "  /context clear       Clear pinned source context.\n"
                        f"  /loop COUNT TASK     Run TASK 1-{MAX_LOOP_ITERATIONS} times; "
                        "supports {index} and {count}.\n"
                        "  /exit, /quit         Exit the session.\n"
                        f"A loop stops early only when the model responds exactly "
                        f"{LOOP_COMPLETE_SENTINEL}. Every iteration remains governed."
                    )
                    continue
                try:
                    loop_command = parse_loop_command(task)
                except ValueError as exc:
                    print(f"loop error: {exc}", file=os.sys.stderr)
                    continue
                if loop_command is not None:
                    try:
                        run_loop_command(agent, loop_command, bounded_task)
                    except Exception as exc:
                        print(f"agent error: {exc}", file=os.sys.stderr)
                    continue
                try:
                    source_snapshot = agent.ws.snapshot_hash()
                    if not task.startswith("/"):
                        require_fresh_pinned_context(
                            pinned_context,
                            pinned_context_envelope,
                            current_source_snapshot_hash=source_snapshot,
                        )
                    routed_task = pinned_context.apply_to(task, agent.ws)
                    route = route_interaction(
                        routed_task,
                        agent.ws,
                        known_evidence_ids=tuple(agent.state.evidence_registry),
                    )
                    freshness = pinned_context_freshness(
                        pinned_context,
                        pinned_context_envelope,
                        current_source_snapshot_hash=source_snapshot,
                    )
                    directive = dispatch_interaction(
                        route,
                        InteractionSessionSnapshot(
                            repository_root=str(agent.ws.root),
                            source_snapshot=source_snapshot,
                            provider=config.provider_kind,
                            model=agent.model,
                            authority_task_id=agent.state.authority.task_id,
                            mode=mode,
                            context_message_count=len(agent._chat_history),
                            pinned_context_count=len(pinned_context.paths),
                            pinned_context_signature=pinned_context.signature,
                            pinned_context_envelope_id=(
                                pinned_context_envelope.envelope_id
                                if pinned_context_envelope is not None
                                else ""
                            ),
                            pinned_context_source_snapshot=(
                                pinned_context_envelope.source_snapshot_hash
                                if pinned_context_envelope is not None
                                else ""
                            ),
                            pinned_context_freshness=freshness,
                            active_operation=False,
                        ),
                    )
                except (PolicyError, ValueError) as exc:
                    print(f"ICPI blocked: {exc}", file=os.sys.stderr)
                    continue
                if directive.action == "EXIT":
                    return 0
                if directive.action == "NEW_CONTEXT":
                    agent.clear_chat_history()
                    pinned_context = pinned_context.clear()
                    pinned_context_envelope = None
                    print("Started a new chat context and cleared pinned paths.")
                    continue
                if directive.action == "ATTACH_CONTEXT":
                    assert route.command is not None
                    try:
                        require_fresh_pinned_context(
                            pinned_context,
                            pinned_context_envelope,
                            current_source_snapshot_hash=source_snapshot,
                        )
                        updated_context = pinned_context.add(
                            agent.ws,
                            route.command.arguments,
                        )
                        updated_envelope = build_pinned_context_envelope(
                            updated_context,
                            agent.ws,
                            source_snapshot_hash=source_snapshot,
                            known_evidence_ids=tuple(agent.state.evidence_registry),
                        )
                    except (PolicyError, ValueError) as exc:
                        print(f"ICPI blocked: {exc}", file=os.sys.stderr)
                        continue
                    pinned_context = updated_context
                    pinned_context_envelope = updated_envelope
                    print(
                        f"Pinned {len(pinned_context.paths)} path(s); "
                        f"signature={pinned_context.signature}"
                    )
                    continue
                if directive.action == "DETACH_CONTEXT":
                    assert route.command is not None
                    try:
                        options = dict(route.command.options)
                        if options.get("all", "false").casefold() in {
                            "1",
                            "true",
                            "yes",
                            "on",
                        }:
                            updated_context = pinned_context.clear()
                        else:
                            updated_context = pinned_context.remove(
                                agent.ws,
                                route.command.arguments,
                            )
                        if updated_context.paths:
                            require_fresh_pinned_context(
                                pinned_context,
                                pinned_context_envelope,
                                current_source_snapshot_hash=source_snapshot,
                            )
                        updated_envelope = build_pinned_context_envelope(
                            updated_context,
                            agent.ws,
                            source_snapshot_hash=source_snapshot,
                            known_evidence_ids=tuple(agent.state.evidence_registry),
                        )
                    except (PolicyError, ValueError) as exc:
                        print(f"ICPI blocked: {exc}", file=os.sys.stderr)
                        continue
                    pinned_context = updated_context
                    pinned_context_envelope = updated_envelope
                    print(
                        f"Pinned {len(pinned_context.paths)} path(s); "
                        f"signature={pinned_context.signature}"
                    )
                    continue
                if route.command is not None and route.command.name == "context":
                    if not pinned_context.paths:
                        print("No pinned context paths are active.")
                        continue
                    try:
                        observed_envelope = build_pinned_context_envelope(
                            pinned_context,
                            agent.ws,
                            source_snapshot_hash=source_snapshot,
                            known_evidence_ids=tuple(agent.state.evidence_registry),
                        )
                    except (PolicyError, ValueError) as exc:
                        print(f"ICPI blocked: {exc}", file=os.sys.stderr)
                        continue
                    assert observed_envelope is not None
                    baseline_envelope = pinned_context_envelope or observed_envelope
                    refresh_applied = directive.action == "REFRESH_CONTEXT"
                    delta = compare_context_envelopes(
                        baseline_envelope,
                        observed_envelope,
                        refresh_applied=refresh_applied,
                    )
                    if refresh_applied:
                        pinned_context_envelope = observed_envelope
                    print(render_context_delta(delta))
                    continue
                if directive.action == "PROVIDER_PREFLIGHT":
                    print(json.dumps(agent.provider_preflight(), indent=2, default=str))
                    continue
                if directive.action == "STOP":
                    print("No asynchronous operation is active in this synchronous CLI session.")
                    continue
                if directive.action != "RUN_AGENT":
                    print(directive.message)
                    continue
                try:
                    envelope = build_context_envelope(
                        route,
                        agent.ws,
                        source_snapshot_hash=source_snapshot,
                        known_evidence_ids=tuple(agent.state.evidence_registry),
                    )
                    if directive.requires_confirmation:
                        confirmation = build_interaction_confirmation(
                            directive,
                            context_envelope=envelope,
                            pinned_context=pinned_context,
                            pinned_context_envelope=pinned_context_envelope,
                        )
                        print(confirmation.render_text())
                        try:
                            answer = input(
                                "Confirm this exact context-bound request? [y/N] "
                            ).strip().casefold()
                        except (EOFError, KeyboardInterrupt):
                            print()
                            answer = ""
                        receipt = build_interaction_confirmation_receipt(
                            confirmation,
                            accepted=answer in {"y", "yes"},
                        )
                        agent.trace(
                            "icpi_confirmation_receipt",
                            interaction_confirmation_receipt_audit_metadata(receipt),
                        )
                        if receipt.decision != "ACCEPTED":
                            print(
                                "ICPI interpretation cancelled; no model turn was started. "
                                f"receipt={receipt.receipt_id}"
                            )
                            continue
                        require_interaction_confirmation_receipt(
                            confirmation,
                            receipt,
                            current_source_snapshot_hash=agent.ws.snapshot_hash(),
                            context_envelope=envelope,
                            pinned_context=pinned_context,
                            pinned_context_envelope=pinned_context_envelope,
                        )
                        print(f"Accepted confirmation receipt: {receipt.receipt_id}")
                    print(agent.run_chat_turn(bounded_task(envelope.model_input)))
                except Exception as exc:
                    print(f"agent error: {exc}", file=os.sys.stderr)
    finally:
        if temporary_authority is not None:
            temporary_authority.cleanup()
