"""
Base command handler for the Toffee CLI tool
"""

import os
import subprocess  # Add this import
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from ..core.environment import EnvironmentManager
from ..core.terraform import TerraformRunner
from ..core.config import Config


# Create rich console for output
console = Console()
error_console = Console(stderr=True)


class BaseCommand:
    """Base class for all Toffee commands"""

    def __init__(self):
        self.config = Config()
        self.project_config = self.config.get_project_config()

        # Initialize environment manager
        vars_dir = self.project_config.get("vars_dir", "vars")
        self.env_manager = EnvironmentManager(vars_dir=vars_dir)

        # Initialize terraform runner
        terraform_path = self.project_config.get("terraform_path", "terraform")
        self.terraform = TerraformRunner(terraform_path=terraform_path)

    def validate_environment(self, env_name: str) -> bool:
        """
        Validate that an environment exists and has all required files

        Args:
            env_name: Name of the environment to validate

        Returns:
            True if valid, False otherwise
        """
        valid, error_msg = self.env_manager.validate_environment(env_name)

        if not valid:
            error_console.print(f"Error: {error_msg}")

            # If environment wasn't found, suggest a similar one
            if "not found" in error_msg:
                suggestion = self.env_manager.suggest_environment(env_name)
                if suggestion:
                    error_console.print(
                        f"Did you mean: {suggestion}?"
                    )

            return False

        return True

    def display_environments(self) -> None:
        """Display a list of available environments"""
        env_names = self.env_manager.get_environment_names()

        if not env_names:
            console.print(
                "No environments found. Make sure you have .tfvars files in the vars/ directory."
            )
            return

        # Create a table of environments
        table = Table(title="Available Environments")
        table.add_column("Environment", style="cyan")
        table.add_column("Vars File", style="green")
        table.add_column("Backend File", style="green")
        table.add_column("Status", style="yellow")

        for name in env_names:
            env = self.env_manager.get_environment(name)
            vars_exists = os.path.exists(env.vars_file)
            backend_exists = os.path.exists(env.backend_file)

            status = "✓" if vars_exists and backend_exists else "✗"

            table.add_row(
                name,
                os.path.basename(env.vars_file) + (" ✓" if vars_exists else " ✗"),
                os.path.basename(env.backend_file) + (" ✓" if backend_exists else " ✗"),
                status,
            )

        console.print(table)

    def display_terraform_commands(self) -> None:
        """Display a list of available Terraform commands"""
        cmd_names = self.terraform.get_command_names()

        if not cmd_names:
            console.print("No Terraform commands available.")
            return

        # Create a table of commands
        table = Table(title="Available Terraform Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="green")

        for name in cmd_names:
            cmd = self.terraform.get_command(name)
            table.add_row(name, cmd.description)

        console.print(table)

    def execute_terraform_command(
        self, env_name: str, command_name: str, extra_args: List[str] = None
    ) -> int:
        """
        Execute a Terraform command for the given environment

        Args:
            env_name: Name of the environment to run in
            command_name: Name of the Terraform command to run
            extra_args: Additional arguments to pass to the command

        Returns:
            The command exit code
        """
        # Validate environment
        if not self.validate_environment(env_name):
            return 1

        # Get environment
        env = self.env_manager.get_environment(env_name)

        # Build command
        cmd = self.terraform.build_command(command_name, env, extra_args)
        cmd_str = " ".join(cmd)

        # Display command
        console.print(f"Running: {cmd_str}")

        # Run command directly to allow for interactive prompts
        try:
            process = subprocess.Popen(
                cmd,
                bufsize=1,  # Line buffered
                universal_newlines=True  # Use text mode
            )
            
            # Wait for completion
            return_code = process.wait()
            
            if return_code == 0:
                console.print("Command succeeded")
            else:
                console.print(f"Command failed with exit code {return_code}")
                
            return return_code
        except Exception as e:
            error_console.print(f"Error executing command: {e}")
            return 1