"""
Base command handler for the Toffee CLI tool
"""

import os
import re
from typing import List, Optional, Dict, Tuple, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

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
        
        # Set verbosity level
        self.verbose = self.project_config.get("verbose", False)

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
            error_console.print(f"[bold red]Error:[/] {error_msg}")

            # If environment wasn't found, suggest a similar one
            if "not found" in error_msg:
                suggestion = self.env_manager.suggest_environment(env_name)
                if suggestion:
                    error_console.print(
                        f"[yellow]Did you mean:[/] [bold]{suggestion}[/]?"
                    )

            return False

        return True

    def display_environments(self) -> None:
        """Display a list of available environments"""
        env_names = self.env_manager.get_environment_names()

        if not env_names:
            console.print(
                "[yellow]No environments found.[/] Make sure you have .tfvars files in the vars/ directory."
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
            console.print("[yellow]No Terraform commands available.[/]")
            return

        # Create a table of commands
        table = Table(title="Available Terraform Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="green")
        table.add_column("Requires var file", style="yellow")
        table.add_column("Requires backend config", style="yellow")

        for name in sorted(cmd_names):
            cmd = self.terraform.get_command(name)
            if cmd:
                table.add_row(
                    name, 
                    cmd.description,
                    "✓" if cmd.needs_vars_file else "✗",
                    "✓" if cmd.needs_backend_config else "✗"
                )

        console.print(table)

    def _format_terraform_output(self, output: str) -> None:
        """
        Format and display Terraform output with syntax highlighting
        
        Args:
            output: Terraform output string
        """
        if not output.strip():
            return
            
        # Check if output contains JSON
        if output.strip().startswith('{') or output.strip().startswith('['):
            try:
                # Try to parse as JSON for better formatting
                syntax = Syntax(output, "json", theme="monokai", line_numbers=False)
                console.print(syntax)
                return
            except Exception:
                pass
                
        # Handle HCL/Terraform output with proper coloring
        # Look for common Terraform output patterns
        lines = output.split('\n')
        formatted_output = []
        
        for line in lines:
            # Color Terraform resource addresses
            if re.match(r'^\s*[+#~-]?\s*\w+\.\w+(\.\w+)*(\[\d+\])?:', line):
                line = re.sub(r'^(\s*[+#~-]?\s*)(\w+\.\w+(\.\w+)*(\[\d+\])?:)', r'\1[cyan]\2[/]', line)
                
            # Color plan summary items
            if re.search(r'Plan:', line) or re.search(r'Apply complete!', line):
                line = f"[bold green]{line}[/]"
                
            # Color warnings
            if "warning" in line.lower():
                line = f"[yellow]{line}[/]"
                
            # Format Terraform "Error:" lines with red
            if re.search(r'Error:', line):
                line = re.sub(r'(Error:.*)', r'[bold red]\1[/]', line)
                
            formatted_output.append(line)
            
        console.print("\n".join(formatted_output))

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
        console.print(f"[bold blue]Running:[/] {cmd_str}")
        console.print("")  # Add spacing for readability
        
        # Special handling for fmt command which might not need environment files
        if command_name == "fmt" and not os.path.exists(env.vars_file):
            # For fmt command, we don't need the var file
            cmd = [self.terraform.terraform_path, command_name]
            if extra_args:
                cmd.extend(extra_args)
                
        # Run command
        return_code, stdout, stderr = self.terraform.run_command(
            command_name, env, extra_args
        )

        # Display formatted output
        if stdout:
            self._format_terraform_output(stdout)
            
        if stderr:
            if return_code != 0:
                error_console.print("\n[bold red]Error output:[/]")
                error_console.print(stderr)
            else:
                # Sometimes terraform sends valid output to stderr
                self._format_terraform_output(stderr)

        if return_code == 0:
            console.print("\n[bold green]Command succeeded[/]")
        else:
            error_console.print(
                f"\n[bold red]Command failed with exit code {return_code}[/]"
            )

        return return_code