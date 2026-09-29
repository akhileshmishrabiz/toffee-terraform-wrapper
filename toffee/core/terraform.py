"""Build Terraform argv without maintaining a Terraform command registry."""

import os
import shlex
from typing import List, Optional, Sequence, Tuple

from .environment import Environment
from .plans import is_plan_file
from .text import printable

# Terraform parses booleans with Go's strconv.ParseBool.
_TRUE_VALUES = frozenset({"1", "t", "T", "TRUE", "true", "True"})

# Flags that consume the next argument when written without "=".
VALUE_FLAGS = frozenset(
    {
        "backup",
        "generate-config-out",
        "lock-timeout",
        "out",
        "parallelism",
        "replace",
        "state",
        "state-out",
        "target",
        "var",
        "var-file",
    }
)


def split_flag(arg: str) -> Optional[Tuple[str, Optional[str]]]:
    """Split ``-name=value`` or ``--name`` into its name and optional value."""
    if not arg.startswith("-") or arg in ("-", "--"):
        return None
    body = arg[2:] if arg.startswith("--") else arg[1:]
    name, separator, value = body.partition("=")
    return name, value if separator else None


def bool_flag(args: Sequence[str], name: str) -> Optional[bool]:
    """Return the last value given for a boolean flag, or None if absent."""
    result = None
    for arg in args:
        flag = split_flag(arg)
        if flag and flag[0] == name:
            result = flag[1] is None or flag[1] in _TRUE_VALUES
    return result


def has_flag(args: Sequence[str], *names: str) -> bool:
    return any(
        flag is not None and flag[0] in names
        for flag in (split_flag(arg) for arg in args)
    )


def flag_value(args: Sequence[str], name: str) -> Optional[str]:
    """Return the last value given for a value-taking flag."""
    value = None
    index = 0
    while index < len(args):
        flag = split_flag(args[index])
        if flag and flag[0] == name:
            if flag[1] is not None:
                value = flag[1]
            elif index + 1 < len(args):
                index += 1
                value = args[index]
        index += 1
    return value


def first_positional(args: Sequence[str]) -> Optional[int]:
    """Return the index of the first positional argument, as Go's flag parser sees it."""
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return index + 1 if index + 1 < len(args) else None
        flag = split_flag(arg)
        if flag is None:
            return index
        name, value = flag
        if value is None and name in VALUE_FLAGS:
            index += 1
        index += 1
    return None


def working_directory(global_args: Sequence[str], cwd: Optional[str] = None) -> str:
    """Return the directory Terraform runs in, honoring the last -chdir option."""
    base = cwd or os.getcwd()
    chdir = None
    for arg in global_args:
        if arg.startswith("-chdir="):
            chdir = arg[len("-chdir=") :]
    return os.path.abspath(os.path.join(base, chdir)) if chdir else base


def saved_plan_path(args: Sequence[str], working_dir: str) -> Optional[str]:
    """Return the saved plan an apply command would use, if any."""
    index = first_positional(args)
    if index is None:
        return None
    candidate = os.path.join(working_dir, args[index])
    return candidate if is_plan_file(candidate) else None


def display_command(cmd: Sequence[str]) -> str:
    """Quote argv for display, hiding -var and inline -backend-config values."""
    shown = []
    redact_next = False
    for arg in cmd:
        if redact_next:
            shown.append(_redact_assignment(arg))
            redact_next = False
            continue
        flag = split_flag(arg)
        if flag and flag[0] in _REDACTED_FLAGS:
            if flag[1] is None:
                redact_next = True
                shown.append(arg)
            else:
                prefix = arg[: len(arg) - len(flag[1])]
                shown.append(prefix + _redact_assignment(flag[1]))
            continue
        shown.append(arg)
    return printable(shlex.join(shown))


_REDACTED_FLAGS = frozenset({"backend-config", "var"})


def _redact_assignment(value: str) -> str:
    name, separator, _secret = value.partition("=")
    return f"{name}=<redacted>" if separator else value


def _relative_path(path: str, working_dir: str) -> str:
    """Terraform resolves relative paths from its (possibly -chdir) directory.

    Absolute paths break when the directory is reached through a symlink,
    because Terraform relativizes them against the logical $PWD.
    """
    try:
        return os.path.relpath(os.path.realpath(path), os.path.realpath(working_dir))
    except ValueError:
        return path


class TerraformRunner:
    """Add the environment flags that Terraform cannot infer itself."""

    # These Terraform commands accept -var-file. Unknown and future commands
    # are passed through untouched, so Toffee never blocks Terraform upgrades.
    VAR_FILE_COMMANDS = frozenset(
        {"apply", "console", "destroy", "import", "plan", "refresh", "test"}
    )
    INPUT_COMMANDS = frozenset(
        {"apply", "destroy", "import", "init", "plan", "refresh"}
    )

    def __init__(self, terraform_path: str = "terraform"):
        self.terraform_path = terraform_path

    def build_command(
        self,
        command_name: str,
        env: Optional[Environment] = None,
        extra_args: Optional[List[str]] = None,
        global_args: Optional[List[str]] = None,
        non_interactive: bool = False,
    ) -> List[str]:
        """
        Build a Terraform command with the appropriate options for the environment.
        """
        if extra_args is None:
            extra_args = []
        if global_args is None:
            global_args = []

        working_dir = working_directory(global_args)
        cmd = [self.terraform_path, *global_args, command_name]

        # User -backend-config values are appended after the environment's
        # file, so they supplement it rather than replace it.
        if env and command_name == "init" and os.path.isfile(env.backend_file):
            cmd.append(
                f"-backend-config={_relative_path(env.backend_file, working_dir)}"
            )
            if not has_flag(extra_args, "reconfigure", "migrate-state"):
                cmd.append("-reconfigure")

        if (
            env
            and command_name in self.VAR_FILE_COMMANDS
            and os.path.isfile(env.vars_file)
            and not (
                command_name == "apply" and saved_plan_path(extra_args, working_dir)
            )
        ):
            cmd.append(f"-var-file={_relative_path(env.vars_file, working_dir)}")

        if (
            non_interactive
            and command_name in self.INPUT_COMMANDS
            and not has_flag(extra_args, "input")
        ):
            cmd.append("-input=false")

        return [*cmd, *extra_args]
