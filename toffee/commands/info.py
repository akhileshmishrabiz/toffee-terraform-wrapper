"""
Information commands for the Toffee CLI tool
"""

import os
from rich.console import Console
from rich.panel import Panel
from rich import box

from .base import BaseCommand
from .. import __version__

console = Console()


class InfoCommands(BaseCommand):
    """Handles informational commands in the Toffee CLI tool"""

    def list_environments(self) -> int:
        """List all available environments"""
        console.print(Panel("[bold]Available Terraform Environments[/]", style="blue"))
        self.display_environments()
        return 0

    def list_commands(self) -> int:
        """List all available Terraform commands"""
        console.print(Panel("[bold]Available Terraform Commands[/]", style="blue"))
        self.display_terraform_commands()
        return 0

    def show_version(self) -> int:
        """Show the version of Toffee"""
        console.print(f"[bold cyan]Toffee[/] version [bold green]{__version__}[/]")
        return 0

    def show_env_info(self, env_name: str) -> int:
        """Show detailed information about an environment"""
        if not self.validate_environment(env_name):
            return 1

        env = self.env_manager.get_environment(env_name)

        # Create a panel with environment info
        console.print(
            Panel(
                f"[bold cyan]Environment:[/] {env_name}\n\n"
                f"[bold]Vars File:[/] {env.vars_file}\n"
                f"[bold]Backend File:[/] {env.backend_file}",
                title=f"Environment: {env_name}",
                style="blue",
                box=box.ROUNDED,
            )
        )

        # Try to read vars file content
        if os.path.exists(env.vars_file):
            try:
                with open(env.vars_file, "r") as f:
                    vars_content = f.read()
                console.print(
                    Panel(
                        vars_content,
                        title=f"Contents of {os.path.basename(env.vars_file)}",
                        style="green",
                    )
                )
            except Exception as e:
                console.print(f"[yellow]Could not read vars file: {e}[/]")

        # Try to read backend file content
        if os.path.exists(env.backend_file):
            try:
                with open(env.backend_file, "r") as f:
                    backend_content = f.read()
                console.print(
                    Panel(
                        backend_content,
                        title=f"Contents of {os.path.basename(env.backend_file)}",
                        style="green",
                    )
                )
            except Exception as e:
                console.print(f"[yellow]Could not read backend file: {e}[/]")

        return
