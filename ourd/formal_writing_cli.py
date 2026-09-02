from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from .formal_writing import WRITING_PROFILES
from .formal_writing_governance import prepare_governed_formal_write
from .persistence import atomic_write_text
from .writing_engine import FormalWritingService, compile_formal_writing_request


COMMANDS = (
    "plan",
    "research",
    "argue",
    "audit",
    "explain",
    "export",
    "inspect",
    "locate",
    "explain-reference",
    "source-map",
    "argument-map",
    "outline",
    "draft",
    "revise",
    "validate",
    "write",
    "references",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oiec-stm-formal-write",
        description="Source-grounded, page-aware formal writing engine",
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--rubric", action="append", default=[])
    parser.add_argument("--draft", action="append", default=[])
    parser.add_argument("--plan", default="", help="Persisted document plan ID")
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--profile", choices=WRITING_PROFILES, default="general")
    parser.add_argument("--genre", default="essay")
    parser.add_argument("--audience", default="general")
    parser.add_argument("--discipline", default="general")
    parser.add_argument("--word-target", "--words", dest="word_target", type=int, default=0)
    parser.add_argument("--citation-style", default="author-date")
    parser.add_argument("--locale", default="en")
    parser.add_argument("--task", default="")
    parser.add_argument(
        "--network-policy",
        choices=("offline", "metadata-only", "explicit-retrieval"),
        default="offline",
    )
    parser.add_argument("--require-page-accuracy", action="store_true")
    parser.add_argument("--allow-ocr", action="store_true")
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--why", action="store_true", help="Include audit rationale and graph issues")
    parser.add_argument(
        "--require-qualified",
        action="store_true",
        help="Fail unless the deterministic writing audit is QUALIFIED_FORMAL_DOCUMENT",
    )
    parser.add_argument("--authority", type=Path)
    parser.add_argument(
        "--confirm-request-signature",
        default="",
        help="Exact request signature required before preparing a governed write candidate",
    )
    return parser


def _result_projection(result: Any) -> dict[str, Any]:
    return asdict(result)


def _persisted_results(workspace: Path) -> tuple[dict[str, Any], ...]:
    root = workspace / ".ourd-agent" / "writing" / "results"
    results = []
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload["_path"] = str(path)
        results.append(payload)
    return tuple(results)


def _find_persisted_result(workspace: Path, identifier: str) -> dict[str, Any] | None:
    for payload in _persisted_results(workspace):
        candidates = {
            str((payload.get("request") or {}).get("request_id", "")),
            str((payload.get("plan") or {}).get("plan_id", "")),
            str((payload.get("draft") or {}).get("draft_id", "")),
            str(
                (((payload.get("qualified_document") or {}).get("plan") or {}).get("document_plan_id", ""))
            ),
            str(
                (((payload.get("qualified_document") or {}).get("audit") or {}).get("audit_id", ""))
            ),
        }
        if identifier in candidates:
            return payload
    return None


def _prior_request_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    request = payload.get("request") or {}
    return {
        "objective": str(request.get("objective", "")),
        "profile": str(request.get("profile", "general")),
        "genre": str(request.get("genre", "essay")),
        "audience": str(request.get("audience", "general")),
        "discipline": str(request.get("discipline", "general")),
        "word_target": int(request.get("word_target", 0)),
        "citation_style": str(request.get("citation_style", "author-date")),
        "locale": str(request.get("locale", "en")),
        "network_policy": str(request.get("network_policy", "offline")),
        "source_document_ids": tuple(
            str(source.get("source_document_id", ""))
            for source in payload.get("sources", ()) or ()
            if source.get("source_document_id")
        ),
    }


def _prepare_governed_write(
    workspace: Path,
    authority_path: Path,
    request_signature: str,
    objective: str,
    output_paths: Sequence[str],
    draft_text: str,
) -> dict[str, Any]:
    return prepare_governed_formal_write(
        workspace,
        authority_path,
        request_signature,
        request_signature,
        objective,
        output_paths,
        draft_text,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = args.workspace.resolve()
    prior_payload = _find_persisted_result(workspace, args.plan) if args.plan else None
    draft_identifier = next((item for item in args.draft if item.startswith("draft:")), "")
    if draft_identifier:
        prior_payload = _find_persisted_result(workspace, draft_identifier)
        if prior_payload is None:
            raise SystemExit(f"unknown persisted draft ID: {draft_identifier}")
    if args.plan and prior_payload is None:
        raise SystemExit(f"unknown persisted plan ID: {args.plan}")
    if args.command in {"audit", "validate"} and draft_identifier and prior_payload is not None:
        qualified = prior_payload.get("qualified_document") or {}
        audit = qualified.get("audit") or {}
        projection = {
            "draft_id": draft_identifier,
            "audit": audit,
            "status": audit.get("status", "EVIDENCE_INSUFFICIENT"),
        }
        if args.why:
            graph = (qualified.get("plan") or {}).get("graph") or {}
            projection["graph_issues"] = graph.get("issues", ())
            projection["limitations"] = audit.get("limitations", ())
            projection["performed_checks"] = audit.get("performed_checks", ())
        rendered = json.dumps(projection, indent=2, sort_keys=True, ensure_ascii=False)
        if args.report:
            atomic_write_text(args.report, rendered + "\n")
        print(rendered)
        if args.require_qualified and audit.get("status") != "QUALIFIED_FORMAL_DOCUMENT":
            return 2
        return 0
    defaults = _prior_request_defaults(prior_payload) if prior_payload is not None else {}
    objective = args.task or str(defaults.get("objective", ""))
    if not objective:
        raise SystemExit("formal writing requires --task unless --plan or a persisted --draft ID supplies it")
    draft_paths = tuple(item for item in args.draft if not item.startswith("draft:"))
    persisted_prior_draft_text = ""
    if draft_identifier and args.command == "revise":
        draft_file = workspace / ".ourd-agent" / "writing" / "drafts" / f"{draft_identifier.replace(':', '-')}.md"
        if not draft_file.exists():
            raise SystemExit(f"persisted draft artifact is missing: {draft_file}")
        persisted_prior_draft_text = draft_file.read_text(encoding="utf-8")
    request = compile_formal_writing_request(
        operation=args.command,
        objective=objective,
        profile=str(defaults.get("profile", args.profile)) if prior_payload is not None else args.profile,
        genre=str(defaults.get("genre", args.genre)) if prior_payload is not None else args.genre,
        audience=str(defaults.get("audience", args.audience)) if prior_payload is not None else args.audience,
        discipline=str(defaults.get("discipline", args.discipline)) if prior_payload is not None else args.discipline,
        word_target=args.word_target or int(defaults.get("word_target", 0)),
        source_document_ids=tuple(defaults.get("source_document_ids", ())),
        source_paths=tuple(args.source),
        rubric_paths=tuple(args.rubric),
        draft_paths=draft_paths,
        output_paths=tuple(args.output),
        citation_style=str(defaults.get("citation_style", args.citation_style)) if prior_payload is not None else args.citation_style,
        locale=str(defaults.get("locale", args.locale)) if prior_payload is not None else args.locale,
        network_policy=str(defaults.get("network_policy", args.network_policy)) if prior_payload is not None else args.network_policy,
        constraints=tuple(args.constraint),
        requested_outputs=(args.command,),
        authority_binding=str(args.authority or ""),
    )
    result = FormalWritingService(workspace).execute(
        request,
        allow_ocr=args.allow_ocr,
        ocr_language=args.ocr_language,
        prior_draft_text=persisted_prior_draft_text,
    )
    if args.require_page_accuracy:
        non_paginated = [source.workspace_relative_path for source in result.sources if source.page_count == 0]
        if non_paginated:
            raise SystemExit(
                "page accuracy was required, but these reflowable sources have no stable pages: "
                + ", ".join(non_paginated)
            )
    projection = _result_projection(result)
    if args.command == "write":
        if result.draft is None:
            raise SystemExit("write operation did not produce a draft candidate")
        if not args.output:
            raise SystemExit("write requires at least one --output path")
        if args.authority is None:
            raise SystemExit("write requires an exact-snapshot --authority manifest")
        if args.confirm_request_signature != request.request_signature:
            raise SystemExit(
                "write requires --confirm-request-signature equal to "
                + request.request_signature
            )
        projection["governed_write"] = prepare_governed_formal_write(
            workspace,
            args.authority,
            request.request_signature,
            args.confirm_request_signature,
            request.objective,
            args.output,
            result.draft.text,
        )
    if args.why and result.qualified_document is not None:
        projection["why"] = {
            "selected_reasoning_path": result.qualified_document.plan.selected_path_id,
            "graph_issues": [asdict(issue) for issue in result.qualified_document.plan.graph.issues],
            "performed_checks": result.qualified_document.audit.performed_checks,
            "limitations": result.qualified_document.audit.limitations,
        }
    rendered = json.dumps(projection, indent=2, sort_keys=True, ensure_ascii=False)
    if args.report:
        atomic_write_text(args.report, rendered + "\n")
    if args.json or args.command != "draft" or result.draft is None:
        print(rendered)
    else:
        print(result.draft.text)
    if args.require_qualified:
        audit = result.qualified_document.audit if result.qualified_document is not None else None
        if audit is None or audit.status != "QUALIFIED_FORMAL_DOCUMENT":
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["COMMANDS", "build_parser", "main"]
