from __future__ import annotations

import sys
from typing import Optional, Sequence


HELP = """usage: oiec-stm-agent brain <command> [options]

Batch-feed evidence and candidate knowledge into the SAA brain, inspect that
staging state, or statically digest arbitrary repository code into new feed
candidates.

commands:
  feed         Process JSON brain-feed manifests/items/directories
  feed repo    Statically digest arbitrary repository code into brain-feed batches
  validate     Validate a JSON brain-feed dependency graph without mutation
  status       Inspect recorded brain-feed batches and dispositions
  quarantine   List brain-feed items rejected from routing
  example      Generate an example JSON brain-feed manifest
  repo         Alias for feed repo
  feed-repo    Alias for feed repo

Repository digestion is static and read-only. Source code is never imported,
executed, built, or tested by the scanner. Extracted algorithms, tests and
invariants remain candidates until normal SAA qualification.
"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(HELP)
        return 0
    if arguments[0] in {"-h", "--help", "help"}:
        print(HELP)
        raise SystemExit(0)
    if arguments[:2] == ["feed", "repo"]:
        from .repo_brain_cli import main as repository_main

        return repository_main(
            arguments[2:],
            prog="oiec-stm-agent brain feed repo",
        )
    if arguments[0] in {"repo", "feed-repo"}:
        from .repo_brain_cli import main as repository_main

        return repository_main(
            arguments[1:],
            prog=f"oiec-stm-agent brain {arguments[0]}",
        )

    from .brain_cli import main as batch_main

    return batch_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
