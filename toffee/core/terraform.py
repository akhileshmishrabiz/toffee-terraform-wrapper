"""Build Terraform argv without maintaining a Terraform command registry."""

import os
from typing import List, Optional

from .environment import Environment


class TerraformRunner:
    """Add only the environment flags that Terraform cannot infer itself."""

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
            and not self._applies_saved_plan(command_name, extra_args)
        ):
            cmd.append(f"-var-file={env.vars_file}")

        return [*cmd, *extra_args]

    @staticmethod
    def _applies_saved_plan(command_name: str, args: List[str]) -> bool:
        """A saved plan already contains its variable values."""
        return command_name == "apply" and any(
            not arg.startswith("-") and os.path.isfile(arg) for arg in args
        )
