from __future__ import annotations

import textwrap
from typing import Iterable


WRITE_COMMAND_CAPABILITIES = (
    "python.unittest",
    "python.py_compile",
    "ctest.run",
    "cmake.build",
    "compiler.syntax_check",
)


def writing_task_prompt(task: str, allowed_paths: Iterable[str]) -> str:
    """Augment a user task with non-authoritative writing-mode guidance.

    The returned text changes model guidance only. It does not grant authority;
    the exact-snapshot AuthorityManifest and normal OIEC/EON gates remain the
    source of mutation permission.
    """

    scope = ", ".join(sorted({str(path) for path in allowed_paths if str(path)}))
    return textwrap.dedent(
        f"""
        HUMAN-GRANTED BOUNDED WRITING MODE
        Writable scope: {scope or '(none)'}

        Treat writing as an OIEC engineering task, whether the requested output
        is prose, Markdown, documentation, source code, configuration, or tests.

        For prose and documents:
        - identify purpose, audience, factual/evidence constraints, structure,
          tone, and length as separate dimensions;
        - inspect relevant repository sources before making factual claims;
        - write natural, coherent human-readable prose rather than template-like
          filler;
        - preserve citations, technical terminology, and user-provided facts;
        - distinguish evidence-backed statements from hypotheses or proposals.

        For code:
        - inspect the existing implementation and local conventions first;
        - keep the change minimal and preserve unrelated behaviour;
        - use only tests and command capabilities explicitly granted by authority.

        When the task asks to create or edit a workspace file, do not merely
        return a draft in chat. Use the existing governed mutation lifecycle:
        establish governance -> prepare candidate transaction -> bind an EON
        action -> gather evidence -> pass the deterministic gate -> apply the
        exact candidate -> verify/finalize when required. Never bypass that path.

        USER TASK:
        {task.strip()}
        """
    ).strip()
