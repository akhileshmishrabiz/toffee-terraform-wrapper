"""
Configuration commands for the Toffee CLI tool
"""

import os

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..core.config import (
    DEFAULT_CONFIG,
    PROJECT_CONFIG_NAME,
    ConfigError,
    is_project_terraform_name,
    project_vars_dir_error,
    read_config_file,
    untrusted_terraform_path_error,
    validate_value,
    write_config_file,
)
from ..core.text import printable
from .base import BaseCommand

console = Console()
error_console = Console(stderr=True, soft_wrap=True)


class ConfigCommands(BaseCommand):
    """Handles configuration commands in the Toffee CLI tool"""

    def show_config(self) -> int:
        """Show the current configuration"""
        table = Table(title="Toffee Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        table.add_column("Source", style="yellow")

        merged_config = self.project_config
        for key in sorted(merged_config.keys()):
            value = merged_config.get(key)
            if isinstance(value, bool):
                value_text = (
                    Text("Yes", style="green") if value else Text("No", style="red")
                )
            elif value is None:
                value_text = Text("None", style="italic")
            elif isinstance(value, list):
                value_text = Text(printable(", ".join(map(str, value))) or "(none)")
            else:
                value_text = Text(printable(str(value)))
            source = self.config.sources.get(key, "Default")
            table.add_row(Text(printable(key)), value_text, source)

        console.print(table)
        return 0

    def set_config(self, key: str, value: str, project: bool = False) -> int:
        """Set a configuration value"""
        if key not in DEFAULT_CONFIG:
            error_console.print(
                f"Error: Unknown configuration key: {key}", markup=False
            )
            error_console.print(f"Valid keys: {', '.join(DEFAULT_CONFIG.keys())}")
            return 1

        default_value = DEFAULT_CONFIG[key]
        if isinstance(default_value, list):
            error_console.print(
                f"[bold red]Error:[/] {key} is a list. Edit it in {PROJECT_CONFIG_NAME}, "
                f'for example: "{key}": ["staging"]'
            )
            return 1

        if isinstance(default_value, bool):
            if value.lower() in ("yes", "true", "1", "y", "t"):
                typed_value = True
            elif value.lower() in ("no", "false", "0", "n", "f"):
                typed_value = False
            else:
                error_console.print(
                    f"Error: Invalid boolean value: {value}. Use 'true' or 'false'.",
                    markup=False,
                )
                return 1
        else:
            typed_value = value

        problem = validate_value(key, typed_value)
        if problem:
            error_console.print(f"Error: {problem}", markup=False)
            return 1
        if project and key == "terraform_path" and not is_project_terraform_name(value):
            error_console.print(
                f"Error: {untrusted_terraform_path_error(value)}", markup=False
            )
            return 1
        if project and key == "vars_dir":
            problem = project_vars_dir_error(os.getcwd(), value)
            if problem:
                error_console.print(f"Error: {problem}", markup=False)
                return 1

        try:
            if project:
                project_config_file = os.path.join(os.getcwd(), PROJECT_CONFIG_NAME)
                project_config = read_config_file(project_config_file)
                project_config[key] = typed_value
                write_config_file(project_config_file, project_config)
            else:
                self.config.set(key, typed_value)
        except ConfigError as e:
            error_console.print(f"Error: {e}", markup=False, highlight=False)
            return 1

        scope = "project" if project else "global"
        console.print(
            printable(f"Set {scope} {key} to {typed_value}"),
            style="green",
            markup=False,
            highlight=False,
        )
        return 0

    def init_project_config(self) -> int:
        """Initialize a project configuration file"""
        project_config_file = os.path.join(os.getcwd(), PROJECT_CONFIG_NAME)

        if os.path.exists(project_config_file):
            console.print(
                f"Project configuration already exists: {project_config_file}",
                style="yellow",
                markup=False,
            )
            try:
                overwrite = click.confirm("Overwrite?", default=False, err=True)
            except click.Abort:
                overwrite = False
            if not overwrite:
                return 0

        default_project_config = {
            "vars_dir": "vars",
            "terraform_path": "terraform",
            "auto_approve": False,
            "verbose": False,
        }

        try:
            write_config_file(project_config_file, default_project_config)
        except ConfigError as e:
            error_console.print(f"Error: {e}", markup=False, highlight=False)
            return 1

        console.print(
            f"Created project configuration: {project_config_file}",
            style="green",
            markup=False,
        )
        return 0
