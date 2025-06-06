"""
Terraform command execution for the Toffee CLI tool
"""

import subprocess
import logging
import os
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

from .environment import Environment

logger = logging.getLogger(__name__)


@dataclass
class TerraformCommand:
    """Represents a Terraform command configuration"""

    name: str
    description: str
    needs_vars_file: bool = True
    needs_backend_config: bool = False
    default_args: List[str] = None

    def __post_init__(self):
        if self.default_args is None:
            self.default_args = []


class TerraformRunner:
    """Handles the execution of Terraform commands"""

    # Define standard terraform commands
    COMMANDS: Dict[str, TerraformCommand] = {
        "init": TerraformCommand(
            name="init",
            description="Initialize a Terraform working directory",
            needs_vars_file=False,
            needs_backend_config=True,
        ),
        "plan": TerraformCommand(
            name="plan", description="Create an execution plan", needs_vars_file=True
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
    }

    def __init__(self, terraform_path: str = "terraform"):
        self.terraform_path = terraform_path

    def get_command(self, name: str) -> Optional[TerraformCommand]:
        """Get a command by name"""
        return self.COMMANDS.get(name)

    def get_command_names(self) -> List[str]:
        """Get a list of all available command names"""
        return list(self.COMMANDS.keys())

    def build_command(
        self,
        command_name: str,
        env: Optional[Environment] = None,
        extra_args: List[str] = None,
    ) -> List[str]:
        """
        Build a Terraform command with the appropriate options for the environment

        Args:
            command_name: The name of the Terraform command to run
            env: The environment to run the command in (optional)
            extra_args: Additional arguments to pass to the command

        Returns:
            The command as a list of strings
        """
        if extra_args is None:
            extra_args = []

        cmd = [self.terraform_path, command_name]

        # Only add environment-specific args if an environment is provided
        if env:
            # Get command configuration
            command = self.get_command(command_name)
            if command:
                # Add backend config if needed
                if command.needs_backend_config and os.path.exists(env.backend_file):
                    cmd.append(f"-backend-config={env.backend_file}")

                # Add var file if needed
                if command.needs_vars_file and os.path.exists(env.vars_file):
                    cmd.append(f"-var-file={env.vars_file}")

                # Add default args for this command
                if command.default_args:
                    cmd.extend(command.default_args)
            else:
                # For custom/unknown commands, add the var file only if it exists
                if os.path.exists(env.vars_file):
                    cmd.append(f"-var-file={env.vars_file}")

        # Add any extra args
        if extra_args:
            cmd.extend(extra_args)

        return cmd

    def run_command(
        self,
        command_name: str,
        env: Optional[Environment] = None,
        extra_args: List[str] = None,
    ) -> Tuple[int, str, str]:
        """
        Run a Terraform command

        Args:
            command_name: The name of the Terraform command to run
            env: The environment to run the command in (optional)
            extra_args: Additional arguments to pass to the command

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = self.build_command(command_name, env, extra_args)

        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            # Run the process with direct output to ensure interactive prompts work
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,  # Line buffered
            )

            # Capture output while displaying it
            stdout_lines = []
            stderr_lines = []

            # Process stdout
            for line in process.stdout:
                stdout_lines.append(line)
                print(line, end="")

            # Process stderr
            for line in process.stderr:
                stderr_lines.append(line)
                print(line, end="")

            # Wait for process to complete
            return_code = process.wait()

            return return_code, "".join(stdout_lines), "".join(stderr_lines)
        except Exception as e:
            logger.error(f"Error running command: {e}")
            return 1, "", str(e)
