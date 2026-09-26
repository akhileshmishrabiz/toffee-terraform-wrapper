"""
Information commands for the Toffee CLI tool
"""

import subprocess

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .. import __version__
from .base import BaseCommand

console = Console()


class InfoCommands(BaseCommand):
    """Handles informational commands in the Toffee CLI tool"""

    def list_environments(self) -> int:
        """List all available environments"""
        console.print(Panel("[bold]Available Terraform Environments[/]", style="blue"))
        self.display_environments()
        return 0

    def list_commands(self) -> int:
        """Ask the installed Terraform binary for its current command list."""
        return self.execute_terraform_command(None, "-help")

    def show_version(self) -> int:
        """Show the version of Toffee and Terraform"""
        toffee_version = __version__

        terraform_version = "Not installed"
        try:
            result = subprocess.run(
                [self.terraform.terraform_path, "-version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Terraform v" in line:
                        terraform_version = line.strip()
                        break
        except OSError:
            pass

        table = Table(title="Versions")
        table.add_column("Component", style="cyan")
        table.add_column("Version", style="green")

        table.add_row("Toffee", toffee_version)
        table.add_row("Terraform", terraform_version)

        console.print(table)
        return 0

    def show_env_info(self, env_name: str) -> int:
        """Show detailed information about an environment"""
        if not self.validate_environment(env_name):
            return 1

        env = self.env_manager.get_environment(env_name)

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

        console.print(
            "[dim]File contents are not printed because tfvars/backend files may "
            "contain secrets.[/]"
        )
        return 0
