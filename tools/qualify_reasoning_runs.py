from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import PolicyError
from ourd.reasoning.benchmark import (
    load_benchmark_run,
    verify_benchmark_checksum,
)
from ourd.reasoning.models import stable_hash
from ourd.reasoning.qualification import qualify_reasoning_runs


def _load_ablation_runs(path: Path):
    verify_benchmark_checksum(path, path.with_suffix(".sha256"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "runs",
        "signature",
    }:
        raise PolicyError("ablation manifest fields are invalid")
    if int(payload["schema_version"]) != 1 or not isinstance(payload["runs"], dict):
        raise PolicyError("ablation manifest schema is invalid")
    material = {
        "schema_version": int(payload["schema_version"]),
        "runs": payload["runs"],
    }
    if str(payload["signature"]) != stable_hash(material):
        raise PolicyError("ablation manifest signature mismatch")
    resolved = {}
    for ablation_id, entries in payload["runs"].items():
        if not isinstance(entries, list):
            raise PolicyError("ablation manifest run entries must be arrays")
        runs = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "benchmark_signature",
                "path",
                "sha256",
            }:
                raise PolicyError("ablation manifest artifact entry is invalid")
            run_path = Path(str(entry["path"]))
            if not run_path.is_absolute():
                run_path = path.parent / run_path
            run_path = run_path.resolve()
            actual = verify_benchmark_checksum(
                run_path,
                run_path.with_suffix(".sha256"),
            )
            if actual != str(entry["sha256"]):
                raise PolicyError("ablation manifest artifact checksum mismatch")
            run = load_benchmark_run(run_path)
            if run.signature != str(entry["benchmark_signature"]):
                raise PolicyError("ablation manifest benchmark signature mismatch")
            runs.append(run)
        resolved[str(ablation_id)] = tuple(runs)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--ablations", required=True, type=Path)
    parser.add_argument(
        "--certificate-reproducibility-bp",
        type=int,
        help="Optional assertion checked against certificate signatures derived from the runs.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise PolicyError("qualification report path already exists")
    report = qualify_reasoning_runs(
        tuple(load_benchmark_run(path) for path in args.runs),
        ablation_runs=_load_ablation_runs(args.ablations.resolve()),
        certificate_reproducibility_assertion_bp=args.certificate_reproducibility_bp,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(report.signature)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
