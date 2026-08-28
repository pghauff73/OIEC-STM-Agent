from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, TYPE_CHECKING

from .errors import PolicyError
from .models import AuthorityManifest, EONAction, RISK_ORDER, max_risk
from .workspace import Workspace

if TYPE_CHECKING:
    from .models import BoundaryState, DimensionBudget


@dataclass(frozen=True)
class CommandDecision:
    argv: List[str]
    capability: str
    minimum_risk: str
    referenced_paths: List[str] = field(default_factory=list)


class PolicyEngine:
    MUTATION_OPERATIONS = {
        "write_file",
        "replace_text",
        "apply_transaction",
        "run_command",
    }

    STRUCTURAL_TERMS = {
        "dependency",
        "package",
        "architecture",
        "schema",
        "migration",
        "build system",
        "configuration",
        "refactor",
        "rename",
        "delete",
        "remove",
    }

    def minimum_risk(
        self,
        operation: str,
        summary: str,
        targets: Sequence[str],
        command_capabilities: Sequence[str],
    ) -> str:
        normalized = operation.strip().lower()
        if normalized in {"read", "list_files", "read_file", "search_text", "git_status", "git_diff"}:
            return "L0"
        risk = "L1" if normalized in self.MUTATION_OPERATIONS else "L1"
        combined = f"{summary} {operation} {' '.join(targets)}".lower()
        if len(set(targets)) > 3 or any(term in combined for term in self.STRUCTURAL_TERMS):
            risk = "L2"
        if any(capability in {"cmake.build", "package.install"} for capability in command_capabilities):
            risk = "L2"
        return risk

    def effective_risk(
        self,
        model_risk: str,
        operation: str,
        summary: str,
        targets: Sequence[str],
        command_capabilities: Sequence[str],
    ) -> str:
        if model_risk not in RISK_ORDER:
            raise PolicyError("risk must be L0, L1, or L2")
        return max_risk(
            model_risk,
            self.minimum_risk(operation, summary, targets, command_capabilities),
        )

    @staticmethod
    def require_oiec_boundary_target(
        workspace: Workspace,
        boundary: "BoundaryState",
        target: str,
    ) -> str:
        from .oiec import require_boundary_target

        return require_boundary_target(workspace, boundary, target)

    @staticmethod
    def require_oiec_dimension_action(
        budget: "DimensionBudget",
        varied_dimensions: Sequence[str],
    ) -> None:
        from .oiec import require_dimension_action

        require_dimension_action(budget, varied_dimensions)

    def require_mutation_authority(self, authority: AuthorityManifest) -> None:
        if authority.read_only:
            raise PolicyError("current authority is read-only")

    def require_action_available(self, action: EONAction) -> None:
        if action.use_count >= action.use_limit:
            raise PolicyError("EON action use limit is exhausted")

    def require_auto_or_interactive_permission(
        self,
        authority: AuthorityManifest,
        effective_risk: str,
        *,
        yolo: bool,
    ) -> str:
        if effective_risk == "L0":
            return "automatic"
        if (
            effective_risk == "L1"
            and authority.allow_l1_auto_apply
            and RISK_ORDER[authority.max_automatic_risk] >= RISK_ORDER["L1"]
        ):
            return "automatic"
        if effective_risk == "L2" and not authority.allow_interactive_l2:
            raise PolicyError("authority does not permit interactive L2 application")
        if yolo:
            if not authority.allow_yolo:
                raise PolicyError("--yolo is not authorized by the authority manifest")
            return "preauthorized"
        return "interactive"

    def parse_command(self, command: str) -> List[str]:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise PolicyError(f"invalid command syntax: {exc}") from exc
        if not argv:
            raise PolicyError("empty command")
        if Path(argv[0]).is_absolute() or "=" in argv[0]:
            raise PolicyError("absolute executables and environment assignments are not allowed")
        shell_tokens = {";", "&&", "||", "|", ">", ">>", "<", "2>", "2>>"}
        if any(argument in shell_tokens for argument in argv):
            raise PolicyError("shell chaining and redirection tokens are not allowed")
        return argv

    def classify_command(self, command: str, workspace: Workspace) -> CommandDecision:
        argv = self.parse_command(command)
        executable = Path(argv[0]).name

        if executable == "git" and argv[1:] in (["status", "--short"], ["status"]):
            return CommandDecision(argv, "git.status", "L0")
        if executable == "git" and argv[1:] in (["diff"], ["diff", "--", "."]):
            return CommandDecision(argv, "git.diff", "L0")

        if executable in {"python", "python3"} and len(argv) >= 3 and argv[1:3] == ["-m", "unittest"]:
            paths = self._validate_python_test_args(argv[3:], workspace)
            return CommandDecision(argv, "python.unittest", "L1", paths)
        if executable in {"python", "python3"} and len(argv) >= 3 and argv[1:3] == ["-m", "py_compile"]:
            if len(argv) == 3:
                raise PolicyError("py_compile requires at least one workspace file")
            paths = []
            for argument in argv[3:]:
                if argument.startswith("-"):
                    raise PolicyError(f"unsupported py_compile option: {argument}")
                paths.append(workspace.canonical(argument))
            return CommandDecision(argv, "python.py_compile", "L1", paths)
        if executable == "ctest":
            paths = self._validate_ctest_args(argv[1:], workspace)
            return CommandDecision(argv, "ctest.run", "L1", paths)
        if executable == "cmake" and len(argv) >= 3 and argv[1] == "--build":
            paths = [workspace.canonical(argv[2])]
            self._validate_cmake_build_args(argv[3:])
            return CommandDecision(argv, "cmake.build", "L2", paths)
        if executable in {"gcc", "g++", "clang", "clang++"} and "-fsyntax-only" in argv[1:]:
            paths = self._validate_compiler_args(argv[1:], workspace)
            return CommandDecision(argv, "compiler.syntax_check", "L1", paths)

        raise PolicyError(
            "command is not represented by an approved capability; use a built-in "
            "read tool or extend the deterministic command policy"
        )

    def require_command_authority(
        self,
        decision: CommandDecision,
        authority: AuthorityManifest,
    ) -> None:
        capabilities = (
            authority.read_capabilities
            if decision.minimum_risk == "L0"
            else authority.command_capabilities
        )
        if decision.capability not in capabilities:
            raise PolicyError(
                f"command capability {decision.capability!r} is not authorized"
            )

    @staticmethod
    def require_command_scope(
        decision: CommandDecision,
        authority: AuthorityManifest,
        workspace: Workspace,
    ) -> None:
        for path in decision.referenced_paths:
            workspace.require_scope(path, authority.allowed_paths, authority.forbidden_paths)

    @staticmethod
    def _validate_python_test_args(arguments: Sequence[str], workspace: Workspace) -> List[str]:
        allowed_flags = {"discover", "-v", "--verbose", "-q", "--quiet", "-f", "--failfast", "-b", "--buffer"}
        options_with_path = {"-s", "--start-directory", "-t", "--top-level-directory", "-p", "--pattern"}
        index = 0
        paths: List[str] = []
        while index < len(arguments):
            argument = arguments[index]
            if argument in allowed_flags:
                index += 1
                continue
            if argument in options_with_path:
                if index + 1 >= len(arguments):
                    raise PolicyError(f"missing value for unittest option {argument}")
                value = arguments[index + 1]
                if argument not in {"-p", "--pattern"}:
                    paths.append(workspace.canonical(value))
                index += 2
                continue
            if argument.startswith("-"):
                raise PolicyError(f"unsupported unittest option: {argument}")
            if "/" in argument or argument.endswith(".py") or argument.startswith("."):
                paths.append(workspace.canonical(argument))
            elif argument not in {"discover"}:
                module_path = argument.replace(".", "/") + ".py"
                if workspace.resolve(module_path).exists():
                    paths.append(workspace.canonical(module_path))
            index += 1
        return list(dict.fromkeys(paths))

    @staticmethod
    def _validate_ctest_args(arguments: Sequence[str], workspace: Workspace) -> List[str]:
        standalone = {"-N", "-V", "-VV", "--output-on-failure", "--stop-on-failure"}
        valued = {"-R", "-E", "-j", "--parallel", "--timeout", "--repeat"}
        path_valued = {"--test-dir"}
        paths: List[str] = []
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument.startswith("@") or argument == "--":
                raise PolicyError("response files and native argument forwarding are not allowed")
            if argument in standalone:
                index += 1
                continue
            if argument in valued | path_valued:
                if index + 1 >= len(arguments):
                    raise PolicyError(f"missing value for ctest option {argument}")
                if argument in path_valued:
                    paths.append(workspace.canonical(arguments[index + 1]))
                index += 2
                continue
            raise PolicyError(f"unsupported ctest option: {argument}")
        return paths

    @staticmethod
    def _validate_cmake_build_args(arguments: Sequence[str]) -> None:
        standalone = {"--clean-first", "--verbose"}
        valued = {"--parallel", "-j", "--target", "-t", "--config"}
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument.startswith("@") or argument == "--":
                raise PolicyError("response files and native build arguments are not allowed")
            if argument in standalone:
                index += 1
                continue
            if argument in valued:
                if index + 1 >= len(arguments):
                    raise PolicyError(f"missing value for cmake build option {argument}")
                index += 2
                continue
            raise PolicyError(f"unsupported cmake build option: {argument}")

    @staticmethod
    def _validate_compiler_args(arguments: Sequence[str], workspace: Workspace) -> List[str]:
        paths: List[str] = []
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument.startswith("@"):
                raise PolicyError("response files are not allowed")
            if argument == "-fsyntax-only" or argument.startswith(("-D", "-U", "-std=", "-W")):
                index += 1
                continue
            if argument in {"-I", "-isystem", "-include"}:
                if index + 1 >= len(arguments):
                    raise PolicyError(f"missing value for compiler option {argument}")
                paths.append(workspace.canonical(arguments[index + 1]))
                index += 2
                continue
            if argument.startswith("-I") and len(argument) > 2:
                paths.append(workspace.canonical(argument[2:]))
                index += 1
                continue
            if argument == "-x":
                if index + 1 >= len(arguments):
                    raise PolicyError("missing language for compiler -x")
                index += 2
                continue
            if argument.startswith("-"):
                raise PolicyError(f"unsupported compiler option: {argument}")
            paths.append(workspace.canonical(argument))
            index += 1
        return list(dict.fromkeys(paths))
