from __future__ import annotations

import textwrap
from typing import Iterable

from .formal_writing import WRITING_PROFILES, profile_dimensions, research_backed_profile


WRITE_COMMAND_CAPABILITIES = (
    "python.unittest",
    "python.py_compile",
    "ctest.run",
    "cmake.build",
    "compiler.syntax_check",
)


def writing_task_prompt(
    task: str,
    allowed_paths: Iterable[str],
    profile: str = "general",
) -> str:
    """Augment a user task with non-authoritative governed writing guidance.

    The returned text changes model guidance only. It does not grant authority;
    the exact-snapshot AuthorityManifest and normal OIEC/EON gates remain the
    source of mutation permission.
    """

    if profile not in WRITING_PROFILES:
        raise ValueError(f"unsupported writing profile: {profile!r}")

    scope = ", ".join(sorted({str(path) for path in allowed_paths if str(path)}))
    dimensions = ", ".join(profile_dimensions(profile))
    formal_rules = research_backed_profile(profile)

    return textwrap.dedent(
        f"""
        HUMAN-GRANTED BOUNDED WRITING MODE
        Writable scope: {scope or '(none)'}
        Writing profile: {profile}
        Writing dimensions: {dimensions}

        Treat writing as an OIEC engineering task, whether the requested output
        is prose, Markdown, documentation, source code, configuration, or tests.

        CORE WRITING WORKFLOW
        1. Analyse the task and any assessment/rubric constraints before drafting.
        2. Establish purpose, audience, central claim/thesis, evidence boundary,
           structure, tone, length and citation requirements as explicit dimensions.
        3. Inspect relevant repository or supplied sources before factual claims.
        4. For academic arguments, construct the claim/evidence/reasoning topology
           before prose so unsupported claims and circular reasoning can be found.
        5. Draft for logical continuity and human readability rather than template
           completion. Each paragraph must have a purpose in the argument.
        6. Critique the draft against evidence, counterarguments, limitations,
           assignment requirements and the selected profile, then revise.
        7. Never invent references, quotations, statistics, results, DOIs, page
           numbers or evidence. Mark unresolved evidence explicitly.

        RESEARCH-BACKED PROFILE RULES
        {formal_rules}

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
