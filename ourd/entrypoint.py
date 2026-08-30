from __future__ import annotations

import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "brain":
        from .brain_dispatch import main as brain_main

        return brain_main(arguments[1:])

    from .cli import main as agent_main

    return agent_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
