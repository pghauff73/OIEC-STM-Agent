from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .egcf.algebra.brain_feed import MAX_BRAIN_FEED_ITEMS, BrainFeedItem, make_brain_feed_item
from .egcf.brain_feed import BrainFeedProcessor
from .egcf.brain_feed_store import BrainFeedStore
from .egcf.errors import EGCFError
from .egcf.ids import sha256_json
from .egcf.store import EGCFStore


PROGRAM = "oiec-stm-agent brain"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Repository/workspace root")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Batch-feed evidence and candidate knowledge into the SAA brain. "
            "Raw algorithm/reasoning candidates are staged for qualification and are never directly made canonical."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    feed = sub.add_parser("feed", help="Process a JSON manifest, JSON item, JSON array, or directory of JSON feed files")
    _add_common(feed)
    feed.add_argument("source", type=Path, help="Feed manifest/file or directory")
    feed.add_argument("--recursive", action="store_true", help="Recursively read *.json when source is a directory")
    feed.add_argument("--strict", action="store_true", help="Return non-zero when any item is quarantined")
    feed.add_argument("--batch-id", default="", help="Override the manifest/implicit batch identifier")
    feed.add_argument("--source-label", default="", help="Human label for this feed source")
    feed.add_argument("--max-items", type=int, default=MAX_BRAIN_FEED_ITEMS, help="Hard item limit for this invocation")
    feed.add_argument("--verbose", action="store_true", help="Print every item disposition")

    validate = sub.add_parser("validate", help="Validate batch structure and dependency graph without changing brain state")
    validate.add_argument("source", type=Path)
    validate.add_argument("--recursive", action="store_true")
    validate.add_argument("--max-items", type=int, default=MAX_BRAIN_FEED_ITEMS)
    validate.add_argument("--json", action="store_true", dest="json_output")

    status = sub.add_parser("status", help="Inspect recorded brain-feed batches and item dispositions")
    _add_common(status)
    status.add_argument("--items", action="store_true", help="Include item dispositions")
    status.add_argument("--status", default="", help="Filter item dispositions by exact status")

    quarantine = sub.add_parser("quarantine", help="List items that were rejected from routing")
    _add_common(quarantine)

    example = sub.add_parser("example", help="Write or print an example batch manifest")
    example.add_argument("--output", type=Path, help="Write example JSON to this file")

    return parser


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EGCFError(f"cannot read brain-feed JSON {path}: {exc}") from exc


def _raw_items_from_document(document: Any, *, source_path: str) -> tuple[list[Mapping[str, Any]], str, str]:
    batch_id = ""
    source_label = ""
    if isinstance(document, Mapping):
        if "items" in document:
            version = int(document.get("schema_version", 1))
            if version != 1:
                raise EGCFError(f"unsupported brain-feed manifest schema_version: {version}")
            raw_items = document.get("items")
            if not isinstance(raw_items, list):
                raise EGCFError("brain-feed manifest items must be an array")
            batch_id = str(document.get("batch_id", "")).strip()
            source_label = str(document.get("source_label", document.get("description", ""))).strip()
            return list(raw_items), batch_id, source_label
        if "kind" in document:
            return [document], "", ""
        raise EGCFError(f"brain-feed JSON object in {source_path} must contain 'items' or 'kind'")
    if isinstance(document, list):
        return list(document), "", ""
    raise EGCFError(f"brain-feed JSON in {source_path} must be an object or array")


def _load_source(path: Path, *, recursive: bool) -> tuple[list[BrainFeedItem], str, str, str]:
    source = path.expanduser().resolve()
    if not source.exists():
        raise EGCFError(f"brain-feed source does not exist: {source}")
    files: list[Path]
    if source.is_dir():
        files = sorted(source.rglob("*.json") if recursive else source.glob("*.json"))
        if not files:
            raise EGCFError(f"brain-feed directory contains no JSON files: {source}")
    else:
        files = [source]

    all_items: list[BrainFeedItem] = []
    declared_batch_ids: list[str] = []
    source_labels: list[str] = []
    source_material: list[dict[str, Any]] = []
    for file_path in files:
        document = _read_json(file_path)
        source_material.append({"path": str(file_path.relative_to(source) if source.is_dir() else file_path.name), "document": document})
        raw_items, declared_batch_id, label = _raw_items_from_document(document, source_path=str(file_path))
        if declared_batch_id:
            declared_batch_ids.append(declared_batch_id)
        if label:
            source_labels.append(label)
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                raise EGCFError(f"brain-feed item in {file_path} must be a JSON object")
            item_id = str(raw.get("id", raw.get("item_id", ""))).strip()
            kind = str(raw.get("kind", "")).strip()
            if "payload" in raw:
                payload = raw["payload"]
            else:
                payload = {
                    str(key): value
                    for key, value in raw.items()
                    if key not in {"id", "item_id", "kind", "depends_on", "evidence_from"}
                }
            all_items.append(
                make_brain_feed_item(
                    item_id=item_id,
                    kind=kind,
                    payload=payload,
                    depends_on=raw.get("depends_on", ()),
                    evidence_from=raw.get("evidence_from", ()),
                    source_path=str(file_path),
                )
            )
    source_signature = sha256_json({"brain_feed_source": source_material})
    if len(set(declared_batch_ids)) > 1:
        batch_id = f"{source.name}-{source_signature[:12]}"
    elif declared_batch_ids:
        batch_id = declared_batch_ids[0]
    else:
        batch_id = f"{source.stem or source.name}-{source_signature[:12]}"
    source_label = source_labels[0] if len(set(source_labels)) == 1 and source_labels else str(source)
    return all_items, batch_id, source_label, source_signature


def _validate_graph(items: Sequence[BrainFeedItem], max_items: int) -> dict[str, Any]:
    if max_items < 1 or max_items > MAX_BRAIN_FEED_ITEMS:
        raise EGCFError(f"--max-items must be in 1..{MAX_BRAIN_FEED_ITEMS}")
    if len(items) > max_items:
        raise EGCFError(f"brain-feed contains {len(items)} items, exceeding --max-items={max_items}")
    by_id: dict[str, BrainFeedItem] = {}
    errors: list[str] = []
    for item in items:
        if item.item_id in by_id:
            errors.append(f"DUPLICATE_ITEM_ID:{item.item_id}")
        by_id[item.item_id] = item
    for item in items:
        for ref in (*item.depends_on, *item.evidence_from):
            if ref not in by_id:
                errors.append(f"MISSING_REFERENCE:{item.item_id}->{ref}")
    pending = {item.item_id: set(item.depends_on) | set(item.evidence_from) for item in items}
    completed: set[str] = set()
    while pending:
        ready = [item_id for item_id, refs in pending.items() if refs.issubset(completed)]
        if not ready:
            unresolved = ",".join(sorted(pending))
            errors.append(f"CYCLIC_OR_UNRESOLVED_DEPENDENCY:{unresolved}")
            break
        for item_id in ready:
            completed.add(item_id)
            pending.pop(item_id)
    return {
        "valid": not errors,
        "item_count": len(items),
        "kinds": {kind: sum(item.kind == kind for item in items) for kind in sorted({item.kind for item in items})},
        "errors": sorted(set(errors)),
    }


def _example_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "batch_id": "thermal-lab-001",
        "source_label": "Example thermal-control knowledge episode",
        "items": [
            {
                "id": "coolant-temp-run-01",
                "kind": "MEASUREMENT",
                "payload": {
                    "subject_id": "thermal-control",
                    "category": "measurement",
                    "producer": "deterministic-calibrated-sensor",
                    "method": "calibrated-temperature-measurement",
                    "target": "coolant temperature",
                    "oracle": "calibrated thermocouple",
                    "independence_group": "thermal-run-01",
                    "environment": {"engine_speed_rpm": 2500},
                    "content": {"value": "83.2", "unit": "degC", "uncertainty": "+/-0.3 degC"},
                    "success": True,
                    "simulated": False,
                },
            },
            {
                "id": "coolant-temperature-meaning",
                "kind": "SEMANTIC_CONCEPT",
                "evidence_from": ["coolant-temp-run-01"],
                "payload": {
                    "name": "coolant temperature",
                    "meaning": "thermodynamic temperature of engine coolant at the declared sensor location",
                    "domain": "automotive thermal control",
                    "quantity_kind": "temperature",
                    "aliases": ["engine coolant temperature"],
                    "physical_dimension": [0, 0, 0, 0, 1, 0, 0],
                    "canonical_unit": "degC",
                    "semantic_status": "SEMANTICALLY_RESOLVED",
                },
            },
            {
                "id": "thermal-threshold-candidate",
                "kind": "ALGORITHM_CANDIDATE",
                "depends_on": ["coolant-temperature-meaning"],
                "evidence_from": ["coolant-temp-run-01"],
                "payload": {
                    "name": "thermal threshold detector",
                    "inputs": ["coolant temperature"],
                    "outputs": ["overheat flag"],
                    "procedure": "compare representative coolant temperature with a qualified threshold",
                    "meanings": {"input": "coolant temperature", "output": "overheat state"},
                },
            },
            {
                "id": "sensor-drift-failure",
                "kind": "FAILURE",
                "evidence_from": ["coolant-temp-run-01"],
                "payload": {
                    "source_kind": "thermal experiment",
                    "component": "coolant temperature sensor",
                    "failure_class": "EVIDENCE_FAILURE",
                    "mechanism": "calibration drift contradicted the expected measurement tolerance",
                    "semantic_roles": ["temperature observation"],
                    "violated_invariants": ["measurement remains within calibration tolerance"],
                },
            },
        ],
    }


def _print_receipt(result: Mapping[str, Any], *, verbose: bool) -> None:
    receipt = result["receipt"]
    print(f"SAA brain-feed batch: {receipt['batch_id']}")
    print(f"  status: {receipt['status']}")
    print(f"  items: {receipt['item_count']}")
    print(f"  admitted/routed: {receipt['admitted_count']}")
    print(f"  staged for qualification: {receipt['staged_count']}")
    print(f"  quarantined: {receipt['quarantined_count']}")
    print(f"  duplicates: {receipt['duplicate_count']}")
    print("  canonical algorithm admissions: 0")
    print("  rule: algorithm/reasoning candidates are staged; batch feeding cannot bypass SAA qualification.")
    print(f"  batch ref: {result['batch_ref']}")
    if verbose:
        print("\nItem dispositions")
        for item in receipt["dispositions"]:
            targets = ", ".join(item["target_refs"]) or "none"
            print(f"  {item['item_id']} [{item['kind']}] -> {item['status']} via {item['route']}")
            print(f"    targets: {targets}")
            if item["reasons"]:
                print("    reasons: " + "; ".join(item["reasons"]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            payload = _example_manifest()
            text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf-8")
                print(args.output)
            else:
                print(text, end="")
            return 0

        if args.command == "validate":
            items, batch_id, source_label, source_signature = _load_source(args.source, recursive=args.recursive)
            validation = _validate_graph(items, args.max_items)
            result = {
                "batch_id": batch_id,
                "source_label": source_label,
                "source_signature": source_signature,
                **validation,
                "state_mutated": False,
            }
            if args.json_output:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"Brain-feed validation: {'valid' if validation['valid'] else 'invalid'}")
                print(f"  items: {validation['item_count']}")
                for error in validation["errors"]:
                    print(f"  error: {error}")
                print("  state mutated: no")
            return 0 if validation["valid"] else 2

        root = Path(args.repo)
        with EGCFStore(root) as egcf:
            store = BrainFeedStore(egcf)
            if args.command == "feed":
                items, implicit_batch_id, implicit_label, source_signature = _load_source(
                    args.source,
                    recursive=args.recursive,
                )
                validation = _validate_graph(items, args.max_items)
                if not validation["valid"]:
                    raise EGCFError("brain-feed dependency graph is invalid: " + "; ".join(validation["errors"]))
                processor = BrainFeedProcessor(egcf)
                receipt, batch_ref = processor.process_batch(
                    items,
                    batch_id=args.batch_id or implicit_batch_id,
                    source_signature=source_signature,
                    source_label=args.source_label or implicit_label,
                    strict=args.strict,
                )
                result = {"batch_ref": batch_ref, "receipt": receipt.to_dict()}
                if args.json_output:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    _print_receipt(result, verbose=args.verbose)
                return 2 if args.strict and receipt.quarantined_count else 0

            if args.command == "status":
                batches = store.batches()
                result: dict[str, Any] = {"batches": batches}
                if args.items or args.status:
                    result["dispositions"] = store.dispositions(status=args.status or None)
                if args.json_output:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    if not batches:
                        print("No brain-feed batches recorded.")
                    else:
                        print("Recorded SAA brain-feed batches")
                        for batch in batches:
                            payload = batch["payload"]
                            print(
                                f"  {batch['batch_ref']} | {payload['batch_id']} | {payload['status']} | "
                                f"items={payload['item_count']} admitted={payload['admitted_count']} "
                                f"staged={payload['staged_count']} quarantine={payload['quarantined_count']}"
                            )
                    if args.items or args.status:
                        for row in result.get("dispositions", []):
                            payload = row["payload"]
                            print(f"  item {payload['item_id']} -> {payload['status']} ({payload['route']})")
                return 0

            if args.command == "quarantine":
                records = store.quarantined()
                if args.json_output:
                    print(json.dumps(records, indent=2, ensure_ascii=False))
                elif not records:
                    print("Brain-feed quarantine is empty.")
                else:
                    print("Brain-feed quarantine")
                    for row in records:
                        payload = row["payload"]
                        print(f"  {payload['item_id']} [{payload['kind']}] : {'; '.join(payload['reasons'])}")
                return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
        return 2
    parser.error("unknown brain command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
