"""
Environment management commands for the Toffee CLI tool
"""

import os
import re
import shutil

from rich.console import Console
from rich.panel import Panel

from .base import BaseCommand

console = Console()
error_console = Console(stderr=True)


class EnvCommands(BaseCommand):
    """Handles environment-related commands in the Toffee CLI tool"""

    def create_environment(self, name: str) -> int:
        """Create a new environment with template files"""
        valid_name, name_error = self.env_manager.validate_env_name(name)
        if not valid_name:
            error_console.print(f"[bold red]Error:[/] {name_error}")
            return 1

        env = self.env_manager.get_environment(name)
        if env and env.is_valid:
            error_console.print(
                f"[bold yellow]Warning:[/] Environment '{name}' already exists"
            )
            return 0

        success, error = self.env_manager.create_environment_template(name)
        if not success:
            error_console.print(
                f"[bold red]Error:[/] Failed to create environment '{name}': {error}"
            )
            return 1

        env = self.env_manager.get_environment(name)
        console.print(f"[bold green]Success:[/] Created environment '{name}'")
        console.print("Files created:")
        if env:
            console.print(f"  - {env.vars_file}")
            console.print(f"  - {env.backend_file}")

        console.print(
            Panel(
                f"[bold]Next steps:[/]\n\n"
                f"1. Edit the vars file: [cyan]{env.vars_file if env else name}[/]\n"
                f"2. Edit the backend config: [cyan]{env.backend_file if env else name}[/]\n"
                f"3. Initialize Terraform: [cyan]toffee init {name}[/]",
                title="Environment Setup",
                border_style="green",
            )
        )
        return 0

    def copy_environment(self, source: str, target: str) -> int:
        """Copy an existing environment to a new one"""
        for env_name in (source, target):
            valid_name, name_error = self.env_manager.validate_env_name(env_name)
            if not valid_name:
                error_console.print(f"[bold red]Error:[/] {name_error}")
                return 1

        source_env = self.env_manager.get_environment(source)
        if not source_env:
            error_console.print(
                f"[bold red]Error:[/] Source environment '{source}' not found"
            )
            return 1

        target_env = self.env_manager.get_environment(target)
        if target_env and (
            os.path.isfile(target_env.vars_file)
            or os.path.isfile(target_env.backend_file)
        ):
            error_console.print(
                f"[bold yellow]Warning:[/] Target environment '{target}' already exists"
            )
            if not console.input("[bold]Overwrite? (y/n)[/] ").lower().startswith("y"):
                return 1

        os.makedirs(self.env_manager.vars_dir, exist_ok=True)

        try:
            target_vars_file = os.path.join(
                self.env_manager.vars_dir, f"{target}.tfvars"
            )
            target_backend_file = os.path.join(
                self.env_manager.vars_dir, f"{target}.tfbackend"
            )

            if os.path.isfile(source_env.vars_file):
                shutil.copy2(source_env.vars_file, target_vars_file)
                with open(target_vars_file, "r") as f:
                    content = f.read()
                pattern = rf"\b{re.escape(source)}\b"
                content = re.sub(pattern, target, content)
                with open(target_vars_file, "w") as f:
                    f.write(content)

            if os.path.isfile(source_env.backend_file):
                shutil.copy2(source_env.backend_file, target_backend_file)
                with open(target_backend_file, "r") as f:
                    content = f.read()
                content = content.replace(f"/{source}/", f"/{target}/")
                with open(target_backend_file, "w") as f:
                    f.write(content)

            self.env_manager.refresh_environments()

            console.print(
                f"[bold green]Success:[/] Copied environment '{source}' to '{target}'"
            )
            console.print("Files created:")
            console.print(f"  - {target_vars_file}")
            console.print(f"  - {target_backend_file}")
            return 0
        except OSError as e:
            error_console.print(f"[bold red]Error:[/] Failed to copy environment: {e}")
            return 1
