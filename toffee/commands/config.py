"""
Configuration commands for the Toffee CLI tool
"""

import os
import json
from rich.console import Console
from rich.table import Table

from .base import BaseCommand
from ..core.config import DEFAULT_CONFIG

console = Console()


class ConfigCommands(BaseCommand):
    """Handles configuration commands in the Toffee CLI tool"""

    def show_config(self) -> int:
        """Show the current configuration"""
        # Create a table of config values
        table = Table(title="Toffee Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        table.add_column("Source", style="yellow")

        project_config = {}

        # Check if there's a project config file
        project_config_file = os.path.join(os.getcwd(), ".toffee.json")
        if os.path.exists(project_config_file):
            try:
                with open(project_config_file, "r") as f:
                    project_config = json.load(f)
            except Exception:
                pass

        # Merged config is what's actually used
        merged_config = self.project_config

        # Add rows for each config value
        for key in sorted(merged_config.keys()):
            value = merged_config.get(key)
            value_str = str(value) if value is not None else "None"

            # Determine source
            source = "Global"
            if key in project_config:
                source = "Project"

            # Format value for display
            if isinstance(value, bool):
                value_str = "[green]Yes[/]" if value else "[red]No[/]"
            elif value is None:
                value_str = "[italic]None[/]"

            table.add_row(key, value_str, source)

        console.print(table)
        return 0

    def set_config(self, key: str, value: str) -> int:
        """Set a global configuration value"""
        # Validate key
        if key not in DEFAULT_CONFIG:
            console.print(f"[bold red]Error:[/] Unknown configuration key: {key}")
            console.print(f"[yellow]Valid keys:[/] {', '.join(DEFAULT_CONFIG.keys())}")
            return 1

        # Convert value to the right type based on the default
        default_value = DEFAULT_CONFIG[key]

        if isinstance(default_value, bool):
            if value.lower() in ("yes", "true", "1", "y", "t"):
                typed_value = True
            elif value.lower() in ("no", "false", "0", "n", "f"):
                typed_value = False
            else:
                console.print(f"[bold red]Error:[/] Invalid boolean value: {value}")
                console.print("[yellow]Use 'true' or 'false'[/]")
                return 1
        elif isinstance(default_value, int):
            try:
                typed_value = int(value)
            except ValueError:
                console.print(f"[bold red]Error:[/] Invalid integer value: {value}")
                return 1
        elif default_value is None:
            if value.lower() in ("none", "null"):
                typed_value = None
            else:
                typed_value = value
        else:
            # String or other type
            typed_value = value

        # Set the value
        self.config.set(key, typed_value)
        console.print(f"[green]Set [bold]{key}[/] to [bold]{typed_value}[/][/]")
        return 0

    def init_project_config(self) -> int:
        """Initialize a project configuration file"""
        project_config_file = os.path.join(os.getcwd(), ".toffee.json")

        if os.path.exists(project_config_file):
            console.print(
                f"[yellow]Project configuration already exists:[/] {project_config_file}"
            )
            if not console.input("[bold]Overwrite? (y/n)[/] ").lower().startswith("y"):
                return 0

        # Create a default project config
        default_project_config = {"vars_dir": "vars", "terraform_path": "terraform"}

        with open(project_config_file, "w") as f:
            json.dump(default_project_config, f, indent=2)

        console.print(f"[green]Created project configuration:[/] {project_config_file}")
        return 0
