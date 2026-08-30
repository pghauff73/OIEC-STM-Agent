from __future__ import annotations

import sys
from typing import Optional, Sequence


HELP = """usage: oiec-stm-agent brain <command> [options]

SAA brain ingestion and inspection commands.

commands:
  feed         Process JSON brain-feed manifests/items/directories
  validate     Validate a JSON brain-feed dependency graph without mutation
  status       Inspect recorded brain-feed batches and dispositions
  quarantine   List brain-feed items rejected from routing
  example      Generate an example JSON brain-feed manifest
  repo         Statically digest arbitrary repository code into brain-feed batches
  feed-repo    Alias for repo

Repository digestion is static and read-only. Source code is never imported,
executed, built, or tested by the scanner. Extracted algorithms, tests and
invariants remain candidates until normal SAA qualification.
"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0
    if arguments[0] in {"repo", "feed-repo"}:
        from .repo_brain_cli import main as repository_main

        return repository_main(arguments[1:])

    from .brain_cli import main as batch_main

    return batch_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
