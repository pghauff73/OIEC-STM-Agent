#!/usr/bin/env python3
"""Canonical launcher for the OIEC-STM-SR-AgentICPI workbench."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from ourd_gui.app import main as app_main
from ourd_gui.supervisor import read_supervisor_status, run_supervisor


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    supervisor_parser = argparse.ArgumentParser(add_help=False)
    supervisor_parser.add_argument("--supervisor-mode", action="store_true")
    supervisor_parser.add_argument("--supervisor-status", action="store_true")
    supervisor_parser.add_argument("--supervisor-heartbeat-stale-seconds", type=float, default=5.0)
    supervisor_parser.add_argument("--supervisor-max-restarts", type=int, default=2)
    supervisor_parser.add_argument("--supervisor-poll-seconds", type=float, default=1.0)
    supervisor_parser.add_argument("--supervisor-debug-stdout", action="store_true")
    supervisor_args, child_arguments = supervisor_parser.parse_known_args(arguments)
    if supervisor_args.supervisor_status:
        repository_root = Path(".")
        for index, argument in enumerate(child_arguments):
            if argument == "--repo" and index + 1 < len(child_arguments):
                repository_root = Path(child_arguments[index + 1])
                break
            if argument.startswith("--repo="):
                repository_root = Path(argument.partition("=")[2])
                break
        print(
            json.dumps(
                read_supervisor_status(
                    repository_root,
                    heartbeat_stale_seconds=supervisor_args.supervisor_heartbeat_stale_seconds,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not supervisor_args.supervisor_mode:
        return app_main(arguments)
    return run_supervisor(
        child_arguments,
        launcher_path=Path(__file__),
        max_restarts=supervisor_args.supervisor_max_restarts,
        poll_seconds=supervisor_args.supervisor_poll_seconds,
        debug_stdout=supervisor_args.supervisor_debug_stdout,
    )


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
