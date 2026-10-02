"""Plan and describe `toffee <env> check` without running the tools.

The behavior is specified in specs/check.md.
"""

import os
import platform
import shlex
import shutil
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

OPTIONAL_CHECKS = ("tflint", "checkov")
CHECKOV_INSTALL_COMMANDS = (
    "uv tool install checkov",
    "pipx install checkov",
)
TFLINT_GO_INSTALL = "go install github.com/terraform-linters/tflint@latest"
_TFLINT_RELEASE = "https://github.com/terraform-linters/tflint/releases/latest/download"

# kind is "terraform", "tflint", or "checkov". name is the executable text.
MissingTool = Tuple[str, str]


class CheckUsage(ValueError):
    """Raised when check arguments are not valid."""


@dataclass(frozen=True)
class CheckStep:
    """One check invocation."""

    label: str
    argv: Tuple[str, ...]
    cwd: Optional[str]
    environment: Optional[str]


def parse_checks(args: Sequence[str]) -> List[str]:
    """Return scanners selected by --checks, in the order written."""
    selected: Optional[List[str]] = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--checks":
            if index + 1 >= len(args):
                raise CheckUsage(
                    "--checks requires a comma-separated list, for example "
                    "--checks tflint,checkov."
                )
            value = args[index + 1]
            index += 2
        elif arg.startswith("--checks="):
            value = arg[len("--checks=") :]
            index += 1
        else:
            following = args[index + 1] if index + 1 < len(args) else None
            raise _unknown_argument(arg, following)
        if selected is not None:
            raise CheckUsage("Pass --checks once.")
        selected = _parse_names(value)
    return selected or []


def requests_check_help(args: Sequence[str]) -> bool:
    """Return whether these arguments ask for check help."""
    return "help" in args


def _unknown_argument(arg: str, following: Optional[str]) -> CheckUsage:
    if arg == "--check" or arg.startswith("--check="):
        if arg.startswith("--check="):
            value = arg[len("--check=") :]
        elif following and not following.startswith("-"):
            value = following
        else:
            value = "tflint,checkov"
        return CheckUsage(f"Unknown option {arg!r}. Use --checks {value}.")
    if arg.startswith("-"):
        return CheckUsage(f"Unknown option {arg!r}. Options are --checks and --help.")
    return CheckUsage(f"Unknown argument {arg!r}. Options are --checks and --help.")


def _parse_names(value: str) -> List[str]:
    names = []
    for raw in value.split(","):
        name = raw.strip()
        if not name:
            raise CheckUsage("Empty check name in --checks.")
        if name in {"fmt", "validate"}:
            raise CheckUsage(
                "fmt and validate always run. --checks accepts tflint and checkov."
            )
        if name not in OPTIONAL_CHECKS:
            raise CheckUsage(
                f"Unknown check {name!r}. --checks accepts tflint and checkov. "
                "fmt and validate always run."
            )
        if name in names:
            raise CheckUsage(f"Repeated check {name!r}.")
        names.append(name)
    if not names:
        raise CheckUsage(
            "--checks requires a comma-separated list, for example "
            "--checks tflint,checkov."
        )
    return names


def find_executable(name: str) -> Optional[str]:
    """Resolve a bare PATH name or an explicit executable path."""
    if os.path.dirname(name):
        if os.path.isfile(name) and os.access(name, os.X_OK):
            return name
        return None
    return shutil.which(name)


def plan_steps(
    terraform: str,
    global_args: Sequence[str],
    env_names: Sequence[str],
    var_files: Sequence[str],
    selected: Sequence[str],
    root: str,
) -> List[CheckStep]:
    """Return the check steps for the selected environments and scanners."""
    single = len(env_names) == 1
    steps = [
        CheckStep(
            "fmt",
            (terraform, *global_args, "fmt", "-check", "-diff", "-recursive"),
            None,
            None,
        )
    ]
    for env_name in env_names:
        steps.append(
            CheckStep(
                "validate" if single else f"{env_name} validate",
                (terraform, *global_args, "validate"),
                None,
                env_name,
            )
        )
    for tool in selected:
        for env_name, var_file in zip(env_names, var_files):
            label = tool if single else f"{env_name} {tool}"
            if tool == "tflint":
                argv = ("tflint", "--format", "compact", f"--var-file={var_file}")
            else:
                argv = (
                    "checkov",
                    "-d",
                    ".",
                    "--framework",
                    "terraform",
                    "--output",
                    "cli",
                    "--quiet",
                    "--compact",
                    "--download-external-modules",
                    "false",
                    "--skip-path",
                    ".terraform",
                    "--skip-path",
                    ".toffee",
                    "--var-file",
                    var_file,
                )
            steps.append(CheckStep(label, argv, root, None))
    return steps


def check_names(selected: Sequence[str]) -> List[str]:
    return ["fmt", "validate", *selected]


def status_phrase(label: str, code: int) -> str:
    if code == 0:
        return f"{label} passed"
    return f"{label} failed with exit code {code}"


def status_style(phrase: str) -> str:
    """Return the color for a pass or fail line."""
    return "green" if phrase.endswith(" passed") else "red"


def rerun_command(
    env_names: Sequence[str],
    global_args: Sequence[str],
    checks: Sequence[str],
) -> str:
    """Return the Toffee command that repeats this run."""
    parts = ["toffee", ",".join(env_names), *global_args, "check"]
    if checks:
        parts.extend(["--checks", ",".join(checks)])
    return shlex.join(parts)


def format_missing(
    missing: Sequence[MissingTool],
    rerun: Optional[str],
) -> str:
    """Describe tools that were selected but could not be started."""
    names = [name for _, name in missing]
    verb = "was" if len(names) == 1 else "were"
    located = " on PATH" if all(os.path.dirname(name) == "" for name in names) else ""
    scanners = [kind for kind, _ in missing if kind != "terraform"]
    terraform_missing = any(kind == "terraform" for kind, _ in missing)
    lines = [f"Error: {_join(names)} {verb} not found{located}."]
    if scanners and not terraform_missing:
        pronoun = "it" if len(scanners) == 1 else "them"
        lines.append(
            f"--checks selected {pronoun}, so this run stopped before any check ran."
        )
    else:
        lines.append("This run stopped before any check ran.")
    lines.append("")
    for kind, name in missing:
        if kind == "terraform":
            lines.append(name)
            lines.append("  toffee check runs terraform fmt and terraform validate.")
        elif kind == "tflint":
            lines.extend(tflint_install_lines())
        else:
            lines.append("Install checkov with either command:")
            for command in CHECKOV_INSTALL_COMMANDS:
                lines.append(f"  {command}")
        lines.append("")
    if rerun is not None and scanners and not terraform_missing:
        lines.append(
            "Or run without it:" if len(scanners) == 1 else "Or run without them:"
        )
        lines.append(f"  {rerun}")
    else:
        lines.pop()
    return "\n".join(lines)


def tflint_install_lines(
    system: Optional[str] = None, machine: Optional[str] = None
) -> List[str]:
    """Return the TFLint install hint for this operating system."""
    system_name = (system if system is not None else platform.system()).casefold()
    machine_name = machine if machine is not None else platform.machine()
    if system_name == "darwin":
        commands = ["brew install terraform-linters/tap/tflint"]
    elif system_name == "windows":
        commands = ["winget install -e --id TerraformLinters.tflint"]
    elif system_name == "linux":
        commands = _linux_tflint_commands(machine_name)
    else:
        commands = []
    if not commands:
        return ["Install tflint with:", f"  {TFLINT_GO_INSTALL}"]
    return [
        "Install tflint with:",
        *[f"  {command}" for command in commands],
        "Or with Go:",
        f"  {TFLINT_GO_INSTALL}",
    ]


def _linux_tflint_commands(machine: str) -> List[str]:
    arch = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine.casefold())
    if arch is None:
        return []
    archive = f"tflint_linux_{arch}.zip"
    return [
        f"curl -sSLO {_TFLINT_RELEASE}/{archive}",
        f"curl -sSLO {_TFLINT_RELEASE}/checksums.txt",
        "gh attestation verify checksums.txt -R terraform-linters/tflint",
        "sha256sum --ignore-missing -c checksums.txt",
        f"unzip {archive}",
        "sudo install -c -v tflint /usr/local/bin/",
    ]


def _join(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]
