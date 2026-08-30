from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from .egcf.brain_feed import BrainFeedProcessor
from .egcf.errors import EGCFError
from .egcf.repository_brain_feed import (
    LANGUAGE_EXTENSIONS,
    RepositoryScanPolicy,
    chunk_repository_plan,
    plan_as_manifests,
    scan_repository,
)
from .egcf.store import EGCFStore


PROGRAM = "oiec-stm-agent brain repo"


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Statically digest arbitrary repository code into SAA brain-feed evidence and candidates. "
            "The scanner never imports, executes, builds, or tests source code and never directly admits canonical algorithms."
        ),
    )
    parser.add_argument("source", nargs="?", type=Path, help="Source repository/directory to scan")
    parser.add_argument("--repo", default=".", help="OIEC workspace that receives brain-feed state")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON")
    parser.add_argument("--scan-only", action="store_true", help="Create a deterministic plan without changing brain state")
    parser.add_argument("--strict", action="store_true", help="Return non-zero for quarantine or material scan incompleteness")
    parser.add_argument("--verbose", action="store_true", help="Show batch and scanner details")
    parser.add_argument("--emit-manifests", type=Path, help="Write generated feed manifests to this directory")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB", help="Only include matching repository paths; repeat as needed")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="Exclude matching repository paths; repeat as needed")
    parser.add_argument("--language", action="append", default=[], help="Only scan selected language; repeat as needed")
    parser.add_argument("--max-files", type=_positive_int, default=1024)
    parser.add_argument("--max-total-bytes", type=_positive_int, default=64 * 1024 * 1024)
    parser.add_argument("--max-file-bytes", type=_positive_int, default=2 * 1024 * 1024)
    parser.add_argument("--max-symbols", type=int, default=8192)
    parser.add_argument("--max-items-per-batch", type=_positive_int, default=4096)
    parser.add_argument("--no-tests", action="store_true", help="Do not emit test experiment candidates")
    parser.add_argument("--no-docs", action="store_true", help="Do not include documentation-only files")
    parser.add_argument("--no-unknown-text", action="store_true", help="Ignore text files whose language is not recognized")
    parser.add_argument("--no-invariants", action="store_true", help="Do not extract Python assert statements as invariant candidates")
    parser.add_argument("--list-languages", action="store_true", help="List recognized code languages and exit")
    return parser


def _policy(args: argparse.Namespace) -> RepositoryScanPolicy:
    return RepositoryScanPolicy(
        max_files=args.max_files,
        max_total_bytes=args.max_total_bytes,
        max_file_bytes=args.max_file_bytes,
        max_symbols=args.max_symbols,
        max_items_per_batch=args.max_items_per_batch,
        include_tests=not args.no_tests,
        include_docs=not args.no_docs,
        include_unknown_text=not args.no_unknown_text,
        include_invariants=not args.no_invariants,
        include_globs=tuple(args.include),
        exclude_globs=tuple(args.exclude),
        languages=tuple(args.language),
    ).canonical()


def _write_manifests(directory: Path, manifests: Sequence[dict[str, Any]]) -> list[str]:
    root = directory.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for index, manifest in enumerate(manifests, start=1):
        path = root / f"repo-feed-{index:04d}.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(str(path))
    summary_path = root / "repo-feed-index.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_count": len(manifests),
                "manifests": paths,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    paths.append(str(summary_path))
    return paths


def _material_scan_warnings(skipped: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    prefixes = (
        "PYTHON_PARSE_ERROR:",
        "FILE_COUNT_LIMIT",
        "TOTAL_BYTE_LIMIT",
        "SYMBOL_COUNT_LIMIT",
        "READ_FAILED:",
        "STAT_FAILED:",
    )
    return [item for item in skipped if str(item.get("reason", "")).startswith(prefixes)]


def _human_summary(result: dict[str, Any], *, verbose: bool) -> None:
    scan = result["scan"]
    print(f"SAA repository brain feed: {scan['repository_name']}")
    print(f"  source: {scan['source_root']}")
    print(f"  repository signature: {scan['repository_signature']}")
    if scan.get("git_commit"):
        print(f"  git commit: {scan['git_commit']}")
    print(f"  files scanned: {scan['file_count']}")
    print(f"  symbols extracted: {scan['symbol_count']}")
    print(f"  source bytes inspected: {scan['total_bytes']}")
    print(f"  feed items generated: {scan['item_count']}")
    print(f"  batches: {result['batch_count']}")
    print(f"  admitted/routed: {result['admitted_count']}")
    print(f"  staged for qualification: {result['staged_count']}")
    print(f"  quarantined: {result['quarantined_count']}")
    print(f"  duplicates: {result['duplicate_count']}")
    print("  canonical algorithm admissions: 0")
    print("  safety: static read-only scan; repository code was not imported or executed.")
    print("  rule: extracted algorithms/tests/invariants remain candidates until normal SAA qualification.")
    if result.get("scan_only"):
        print("  brain state mutated: no (scan-only)")
    if result.get("manifest_paths"):
        print(f"  emitted manifests: {len(result['manifest_paths']) - 1}")
    if verbose:
        print("\nLanguages")
        for language, count in sorted(scan["language_counts"].items()):
            print(f"  {language}: {count}")
        if scan.get("skipped"):
            print("\nSkipped/warnings")
            for item in scan["skipped"][:100]:
                print(f"  {item['path']}: {item['reason']}")
            if len(scan["skipped"]) > 100:
                print(f"  ... {len(scan['skipped']) - 100} more")
        if result.get("batches"):
            print("\nBatch receipts")
            for batch in result["batches"]:
                receipt = batch["receipt"]
                print(
                    f"  {receipt['batch_id']}: admitted={receipt['admitted_count']} "
                    f"staged={receipt['staged_count']} quarantined={receipt['quarantined_count']} "
                    f"duplicates={receipt['duplicate_count']}"
                )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.list_languages:
            for language, extensions in sorted(LANGUAGE_EXTENSIONS.items()):
                print(f"{language}: {', '.join(extensions)}")
            return 0
        if args.source is None:
            parser.error("source repository is required unless --list-languages is used")

        plan = scan_repository(args.source, _policy(args))
        manifests = plan_as_manifests(plan)
        manifest_paths: list[str] = []
        if args.emit_manifests:
            manifest_paths = _write_manifests(args.emit_manifests, manifests)

        scan_summary = plan.to_summary_dict()
        material_warnings = _material_scan_warnings(list(plan.skipped))
        result: dict[str, Any] = {
            "scan": scan_summary,
            "scan_only": bool(args.scan_only),
            "batch_count": len(manifests),
            "batches": [],
            "admitted_count": 0,
            "staged_count": 0,
            "quarantined_count": 0,
            "duplicate_count": 0,
            "canonical_algorithm_admissions": 0,
            "material_scan_warnings": material_warnings,
            "manifest_paths": manifest_paths,
        }

        if not args.scan_only:
            batches = chunk_repository_plan(plan)
            workspace_root = Path(args.repo).expanduser().resolve()
            with EGCFStore(workspace_root) as egcf:
                processor = BrainFeedProcessor(egcf)
                for index, items in enumerate(batches, start=1):
                    batch_id = f"repo-{plan.repository_name}-{plan.repository_signature[:12]}-{index:04d}"
                    receipt, batch_ref = processor.process_batch(
                        items,
                        batch_id=batch_id,
                        source_signature=plan.repository_signature,
                        source_label=(
                            f"Static repository feed {plan.repository_name} [{index}/{len(batches)}]"
                        ),
                        strict=args.strict,
                    )
                    payload = receipt.to_dict()
                    result["batches"].append({"batch_ref": batch_ref, "receipt": payload})
                    result["admitted_count"] += receipt.admitted_count
                    result["staged_count"] += receipt.staged_count
                    result["quarantined_count"] += receipt.quarantined_count
                    result["duplicate_count"] += receipt.duplicate_count

        if args.json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _human_summary(result, verbose=args.verbose)

        strict_failure = bool(
            args.strict
            and (
                result["quarantined_count"]
                or result["material_scan_warnings"]
            )
        )
        return 2 if strict_failure else 0
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
