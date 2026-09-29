"""Build Terraform argv without maintaining a Terraform command registry."""

import os
from typing import List, Optional, Sequence, Tuple

from .environment import Environment
from .plans import is_plan_file

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


class TerraformRunner:
    """Add the environment flags that Terraform cannot infer itself."""

    # These Terraform commands accept -var-file. Unknown and future commands
    # are passed through untouched, so Toffee never blocks Terraform upgrades.
    VAR_FILE_COMMANDS = frozenset(
        {"apply", "console", "destroy", "import", "plan", "refresh", "test"}
    )

    def __init__(self, terraform_path: str = "terraform"):
        self.terraform_path = terraform_path

    def build_command(
        self,
        command_name: str,
        env: Optional[Environment] = None,
        extra_args: Optional[List[str]] = None,
        global_args: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Build a Terraform command with the appropriate options for the environment.
        """
        if extra_args is None:
            extra_args = []
        if global_args is None:
            global_args = []

        cmd = [self.terraform_path, *global_args, command_name]

        has_backend_override = any(
            arg == "-backend-config" or arg.startswith("-backend-config=")
            for arg in extra_args
        )
        if (
            env
            and command_name == "init"
            and os.path.isfile(env.backend_file)
            and not has_backend_override
        ):
            cmd.append(f"-backend-config={env.backend_file}")
            if not any(
                arg in {"-reconfigure", "-migrate-state"} for arg in extra_args
            ):
                cmd.append("-reconfigure")

        if (
            env
            and command_name in self.VAR_FILE_COMMANDS
            and os.path.isfile(env.vars_file)
            and not (
                command_name == "apply"
                and saved_plan_path(extra_args, working_directory(global_args))
            )
        ):
            cmd.append(f"-var-file={env.vars_file}")

        return [*cmd, *extra_args]
