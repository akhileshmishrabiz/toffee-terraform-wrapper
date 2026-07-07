"""
Terraform command execution for the Toffee CLI tool
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .environment import Environment

logger = logging.getLogger(__name__)

STATE_SUBCOMMANDS = frozenset(
    {"list", "show", "mv", "rm", "pull", "push", "replace-provider"}
)


@dataclass
class TerraformCommand:
    """Represents a Terraform command configuration"""

    name: str
    description: str
    needs_vars_file: bool = True
    needs_backend_config: bool = False
    default_args: List[str] = field(default_factory=list)


class TerraformRunner:
    """Builds Terraform command lines for environment-aware execution."""

    COMMANDS: Dict[str, TerraformCommand] = {
        "init": TerraformCommand(
            name="init",
            description="Initialize a Terraform working directory",
            needs_vars_file=False,
            needs_backend_config=True,
            default_args=["-reconfigure"],
        ),
        "plan": TerraformCommand(
            name="plan",
            description="Create an execution plan",
            needs_vars_file=True,
        ),
        "apply": TerraformCommand(
            name="apply",
            description="Apply changes to infrastructure",
            needs_vars_file=True,
        ),
        "destroy": TerraformCommand(
            name="destroy",
            description="Destroy Terraform-managed infrastructure",
            needs_vars_file=True,
        ),
        "refresh": TerraformCommand(
            name="refresh",
            description="Update local state file against real resources",
            needs_vars_file=True,
        ),
        "output": TerraformCommand(
            name="output",
            description="Show output values from your infrastructure",
            needs_vars_file=False,
        ),
        "validate": TerraformCommand(
            name="validate",
            description="Validate the configuration files",
            needs_vars_file=False,
        ),
        "fmt": TerraformCommand(
            name="fmt",
            description="Format the configuration files",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "state": TerraformCommand(
            name="state",
            description="Advanced state management",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "workspace": TerraformCommand(
            name="workspace",
            description="Workspace management",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "import": TerraformCommand(
            name="import",
            description="Import existing infrastructure into Terraform",
            needs_vars_file=True,
        ),
        "graph": TerraformCommand(
            name="graph",
            description="Create a visual graph of Terraform resources",
            needs_vars_file=False,
        ),
        "providers": TerraformCommand(
            name="providers",
            description="Show information about providers",
            needs_vars_file=False,
        ),
        "version": TerraformCommand(
            name="version",
            description="Show Terraform version",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "test": TerraformCommand(
            name="test",
            description="Run experimental tests",
            needs_vars_file=True,
        ),
        "console": TerraformCommand(
            name="console",
            description="Interactive console for Terraform expressions",
            needs_vars_file=True,
        ),
        "show": TerraformCommand(
            name="show",
            description="Show the current state or a saved plan",
            needs_vars_file=False,
        ),
        "get": TerraformCommand(
            name="get",
            description="Install or upgrade remote Terraform modules",
            needs_vars_file=False,
        ),
        "login": TerraformCommand(
            name="login",
            description="Obtain and save credentials for a remote host",
            needs_vars_file=False,
        ),
        "force-unlock": TerraformCommand(
            name="force-unlock",
            description="Release a stuck state lock",
            needs_vars_file=False,
        ),
        "taint": TerraformCommand(
            name="taint",
            description="Mark a resource for recreation",
            needs_vars_file=False,
        ),
        "untaint": TerraformCommand(
            name="untaint",
            description="Remove the taint from a resource",
            needs_vars_file=False,
        ),
    }

    def __init__(self, terraform_path: str = "terraform"):
        self.terraform_path = terraform_path

    def get_command(self, name: str) -> Optional[TerraformCommand]:
        """Get a command by name"""
        return self.COMMANDS.get(name)

    def get_command_names(self) -> List[str]:
        """Get a list of all available command names"""
        return sorted(self.COMMANDS.keys())

    def build_command(
        self,
        command_name: str,
        env: Optional[Environment] = None,
        extra_args: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Build a Terraform command with the appropriate options for the environment.
        """
        if extra_args is None:
            extra_args = []

        cmd = [self.terraform_path, command_name]
        command = self.get_command(command_name)

        if env:
            if command:
                if command.needs_backend_config and os.path.isfile(env.backend_file):
                    cmd.append(f"-backend-config={env.backend_file}")

                if command.needs_vars_file and os.path.isfile(env.vars_file):
                    cmd.append(f"-var-file={env.vars_file}")

                if command.default_args:
                    cmd.extend(command.default_args)
            elif os.path.isfile(env.vars_file):
                cmd.append(f"-var-file={env.vars_file}")

        cmd.extend(extra_args)
        return cmd

    @staticmethod
    def parse_state_arguments(
        env_arg: Optional[str],
        extra_args: Optional[List[str]],
        known_envs: List[str],
    ) -> Tuple[Optional[str], List[str]]:
        """
        Parse state command arguments.

        Supports:
          toffee state list
          toffee state dev list
        """
        extra_args = extra_args or []
        known_env_set = set(known_envs)

        if env_arg is None:
            return None, extra_args

        if env_arg in known_env_set:
            return env_arg, extra_args

        if env_arg in STATE_SUBCOMMANDS:
            return None, [env_arg, *extra_args]

        return env_arg, extra_args
