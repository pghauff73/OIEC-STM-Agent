from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.egcf.external_algorithms import (
    register_babcs_algorithm,
    registration_json,
    render_babcs_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Store an exact BAB-CS source bundle as a reference algorithm and analyse it."
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--babcs-root", type=Path, default=Path("../BAB-CS"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--run-focused-tests", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registration = register_babcs_algorithm(
        args.workspace.resolve(),
        args.babcs_root.resolve(),
        run_focused_tests=args.run_focused_tests,
    )
    if args.report is not None:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_babcs_report(registration).rstrip() + "\n", encoding="utf-8")
    receipt = registration_json(registration).rstrip() + "\n"
    if args.receipt is not None:
        receipt_path = args.receipt.resolve()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(receipt, encoding="utf-8")
    print(receipt, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
