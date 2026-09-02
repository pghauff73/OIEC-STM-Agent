"""Canonical command, alias, recipe, and provider records for documentation."""

from __future__ import annotations

import contextlib
import io
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CLIProgram:
    program_id: str
    command: str
    entry_point: str
    purpose: str
    alias_of: str


@dataclass(frozen=True)
class CommandRecipe:
    command_id: str
    title: str
    program_id: str
    argv: tuple[str, ...]
    purpose: str
    explanation: tuple[tuple[str, str], ...]
    expected_mode: str

    @property
    def command(self) -> str:
        return shlex.join(self.argv)


@dataclass(frozen=True)
class RejectedRecipe:
    command_id: str
    argv: tuple[str, ...]
    reason_fragment: str


@dataclass(frozen=True)
class ProviderRecipe:
    provider_id: str
    title: str
    description: str
    command_id: str
    stores_secret: bool


PROGRAMS = (
    CLIProgram("agent", "oiec-stm-agent", "ourd.entrypoint:main", "Start the bounded agent CLI.", ""),
    CLIProgram("agent-icpi", "oiec-stm-sr-agent-icpi", "ourd_gui.app:main", "Start the OIEC-STM-SR AgentICPI workbench.", "gui"),
    CLIProgram("agent-icpi-alias", "oiec-stm-sr-AgentICPI", "ourd_gui.app:main", "Case-preserving alias of the AgentICPI workbench.", "agent-icpi"),
    CLIProgram("agent-alias", "ourd-agent", "ourd.entrypoint:main", "Alias of the main agent CLI.", "agent"),
    CLIProgram("egcf", "egcf", "ourd.egcf.cli:main", "Compile and run evidence-governed semantic commands.", ""),
    CLIProgram("gui", "oiec-stm-gui", "ourd_gui.app:main", "Start the graphical engineering workbench.", ""),
    CLIProgram("gui-alias", "ourd-gui", "ourd_gui.app:main", "Alias of the graphical workbench entry point.", "gui"),
    CLIProgram("formal-write", "oiec-stm-formal-write", "ourd.formal_writing_cli:main", "Run the deterministic formal-writing CLI.", "agent"),
    CLIProgram("formal-writing-gui", "oiec-stm-formal-writing-gui", "ourd_gui.formal_writing_gui:main", "Start the standalone formal-writing GUI.", "gui"),
)


RECIPES = (
    CommandRecipe("install-editable", "Install the current checkout", "agent", ("python3", "-m", "pip", "install", "-e", "."), "Install the merged project command entry points from the checkout.", (("python3 -m pip", "run pip with this Python interpreter"), ("install -e .", "install the checkout in editable mode")), "installation"),
    CommandRecipe("show-help", "Show agent help", "agent", ("oiec-stm-agent", "--help"), "List the current parser options without starting a run.", (("oiec-stm-agent", "start the agent command"), ("--help", "show parser-owned help")), "read-only"),
    CommandRecipe("agent-read-repo", "Start a read-only session", "agent", ("oiec-stm-agent", "."), "Start an interactive read-only session in the current directory.", (("oiec-stm-agent", "start the agent"), (".", "use the current directory as the workspace")), "read-only"),
    CommandRecipe("agent-one-shot", "Explain this repository", "agent", ("oiec-stm-agent", ".", "--task", "Explain this repository"), "Run one bounded read-only task and exit.", (("--task", "supply one task instead of opening the interactive prompt"),), "read-only"),
    CommandRecipe("agent-write-docs", "Improve documentation in a bounded path", "agent", ("oiec-stm-agent", ".", "--write", "--write-path", "docs/**", "--task", "Improve the introduction"), "Grant a temporary bounded writing session limited to docs/**.", (("--write", "request bounded writing mode"), ("--write-path docs/**", "limit proposed writes to documentation paths"), ("--task", "run one exact writing objective")), "bounded-write"),
    CommandRecipe("provider-llama-cpp", "Use direct llama.cpp", "agent", ("oiec-stm-agent", ".", "--provider", "llama_cpp_process", "--model", "qwen3.8-27b-direct", "--model-path", "../Neuro-llama/Qwen3.8-27B-Q2_K.gguf", "--llama-cpp-root", "../Neuro-llama/llama.cpp", "--preflight"), "Check the direct llama.cpp process provider without starting a model webserver.", (("--provider llama_cpp_process", "select the direct local process provider"), ("--model-path", "bind the exact model file"), ("--llama-cpp-root", "bind the local llama.cpp checkout"), ("--preflight", "check readiness before a task")), "read-only"),
    CommandRecipe("egcf-capability-list", "List EGCF capabilities", "egcf", ("egcf", "capability", "list", "--repo", "."), "Inspect available capability definitions.", (("capability", "select the capability namespace"), ("list", "select the list verb"), ("--repo .", "use the current workspace")), "read-only"),
    CommandRecipe("egcf-dry-run", "Dry-run a parser fix", "egcf", ("egcf", "run", "fix", "parser", "regression", "--repo", ".", "--input", '{"target":"src/parser.py"}', "--dry-run", "--why"), "Compile and explain a proposed operation without executing it.", (("run fix parser regression", "state the objective"), ("--input", "supply typed JSON inputs"), ("--dry-run", "prevent execution"), ("--why", "explain compilation decisions")), "simulation"),
    CommandRecipe("egcf-workflow", "Inspect a strict workflow", "egcf", ("egcf", "run", "fix", "parser", "regression", "--repo", ".", "--input", '{"target":"src/parser.py"}', "--dry-run", "--why", "--graph", "--strict", "--risk", "L1", "--rollback", "exact"), "Show graph, strict validation, risk, and rollback for a dry-run objective.", (("--graph", "render the compiled plan graph"), ("--strict", "reject unresolved compilation details"), ("--risk L1", "declare bounded low-risk mutation intent"), ("--rollback exact", "require an exact rollback strategy")), "simulation"),
    CommandRecipe("gui-first-launch", "Open the workbench", "gui", ("oiec-stm-gui", "--repo", "."), "Open the GUI for the current repository.", (("oiec-stm-gui", "start the workbench"), ("--repo .", "open the current repository")), "read-only"),
)


REJECTED_RECIPES = (
    RejectedRecipe("write-without-path", ("oiec-stm-agent", ".", "--write"), "--write requires at least one explicit --write-path"),
    RejectedRecipe("write-with-yolo", ("oiec-stm-agent", ".", "--write", "--write-path", "docs/**", "--yolo"), "bounded --write mode never grants --yolo"),
    RejectedRecipe("write-with-authority", ("oiec-stm-agent", ".", "--write", "--write-path", "docs/**", "--authority", "authority.json"), "--write and --authority are mutually exclusive"),
)


PROVIDERS = (
    ProviderRecipe("llama_cpp_process", "Direct llama.cpp process", "Run the local model file through the native llama.cpp process boundary; no model webserver endpoint is required.", "provider-llama-cpp", False),
)


COMMAND_BUILDER_SCHEMA = {
    "program": ("agent", "egcf", "gui", "formal-write", "agent-icpi"),
    "workspace": ".",
    "target": "src/parser.py",
    "risk": ("L0", "L1", "L2"),
    "explain": True,
    "graph": False,
    "strict": False,
    "simulate": True,
}


def _entry_points_from_pyproject() -> dict[str, str]:
    entries: dict[str, str] = {}
    in_scripts = False
    for raw_line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and line.startswith("["):
            break
        if in_scripts and "=" in line:
            name, value = line.split("=", 1)
            entries[name.strip()] = value.strip().strip('"')
    return entries


def validate_programs() -> None:
    actual = _entry_points_from_pyproject()
    expected = {program.command: program.entry_point for program in PROGRAMS}
    if actual != expected:
        raise ValueError(f"CLI entry-point drift: expected {expected!r}, observed {actual!r}")


def _parse_recipe(recipe: CommandRecipe) -> None:
    if recipe.command_id.startswith("install-"):
        return
    argv = list(recipe.argv[1:])
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if recipe.program_id == "agent":
                from ourd.cli import _validate_write_args, build_parser

                parser = build_parser()
                args = parser.parse_args(argv)
                _validate_write_args(parser, args)
            elif recipe.program_id == "egcf":
                from ourd.egcf.cli import build_parser

                build_parser().parse_args(argv)
            elif recipe.program_id == "gui":
                from ourd_gui.app import build_parser

                build_parser().parse_args(argv)
    except SystemExit as exc:
        if exc.code != 0:
            raise


def validate_recipes() -> None:
    validate_programs()
    for recipe in RECIPES:
        _parse_recipe(recipe)


def records_for_manifest(records: Iterable[object]) -> list[dict[str, object]]:
    return [asdict(record) for record in records]
