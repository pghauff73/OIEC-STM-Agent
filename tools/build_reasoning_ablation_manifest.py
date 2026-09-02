#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError
from ourd.reasoning.ablation import (
    REQUIRED_ABLATIONS,
    ablation_pipeline,
    standard_ablation_configurations,
)
from ourd.reasoning.benchmark import (
    BENCHMARK_SYSTEM_IDS,
    load_benchmark_run,
    verify_benchmark_checksum,
)
from ourd.reasoning.models import stable_hash


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Build a signed manifest of checksum-verified SR ablation runs."
    )
    value.add_argument(
        "--run",
        action="append",
        default=[],
        metavar="ABLATION_ID=BENCHMARK.json",
        help="Bind one benchmark artifact to its persisted SR ablation ID.",
    )
    value.add_argument("--output", required=True, type=Path)
    return value


def _write_new(path: Path, content: str) -> None:
    checksum_path = path.with_suffix(".sha256")
    if path.exists() or checksum_path.exists():
        raise PolicyError(f"ablation manifest artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with checksum_path.open("x", encoding="utf-8") as handle:
            handle.write(f"{checksum}  {path.name}\n")
    except (FileExistsError, OSError) as exc:
        if path.exists() and not checksum_path.exists():
            path.unlink()
        raise PolicyError(f"cannot create ablation manifest: {path}") from exc


def build_manifest(*, bindings: list[str], output: Path) -> dict:
    configurations = {
        item.ablation_id: item for item in standard_ablation_configurations()
    }
    grouped: dict[str, list[dict[str, str]]] = {}
    for binding in bindings:
        ablation_id, separator, raw_path = binding.partition("=")
        if not separator or ablation_id not in REQUIRED_ABLATIONS or not raw_path:
            raise PolicyError(f"invalid ablation run binding: {binding!r}")
        run_path = Path(raw_path).resolve()
        checksum = verify_benchmark_checksum(
            run_path,
            run_path.with_suffix(".sha256"),
        )
        run = load_benchmark_run(run_path)
        sr_pipeline = run.systems[BENCHMARK_SYSTEM_IDS.index("oiec_sr")]["pipeline"]
        if sr_pipeline != ablation_pipeline(configurations[ablation_id]):
            raise PolicyError(f"ablation run pipeline mismatch: {ablation_id}")
        relative = Path(os.path.relpath(run_path, output.parent.resolve())).as_posix()
        grouped.setdefault(ablation_id, []).append(
            {
                "benchmark_signature": run.signature,
                "path": relative,
                "sha256": checksum,
            }
        )
    runs = {
        ablation_id: sorted(entries, key=lambda item: item["path"])
        for ablation_id, entries in sorted(grouped.items())
    }
    material = {"schema_version": 1, "runs": runs}
    return {**material, "signature": stable_hash(material)}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = args.output.resolve()
        payload = build_manifest(bindings=args.run, output=output)
        _write_new(
            output,
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        print(payload["signature"])
        return 0
    except (OSError, ValueError, KeyError, PolicyError) as exc:
        print(f"ablation manifest build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
