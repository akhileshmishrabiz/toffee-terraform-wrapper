"""Compare the configuration files for two environments."""

from typing import Dict

from rich.console import Console
from rich.text import Text

from ..core.environment_diff import (
    HCLError,
    contains_secret,
    is_sensitive_key,
    read_assignments,
)
from ..core.text import printable
from .base import BaseCommand

console = Console()
error_console = Console(stderr=True, soft_wrap=True)


class DiffCommands(BaseCommand):
    """Handle environment configuration comparisons."""

    def compare(
        self,
        source_name: str,
        target_name: str,
        show_sensitive: bool = False,
        exit_code: bool = False,
    ) -> int:
        # With --exit-code, 1 means "different", so errors need their own status.
        error_code = 2 if exit_code else 1
        for name in (source_name, target_name):
            if not self.validate_environment(name):
                return error_code

        source = self.env_manager.get_environment(source_name)
        target = self.env_manager.get_environment(target_name)
        comparisons = (
            ("Variables", source.vars_file, target.vars_file),
            ("Backend", source.backend_file, target.backend_file),
        )

        loaded = []
        for title, source_path, target_path in comparisons:
            values = []
            for path in (source_path, target_path):
                try:
                    values.append(read_assignments(path))
                except (OSError, UnicodeDecodeError, HCLError) as e:
                    error_console.print(
                        f"Error: Cannot read {self.display_path(path)}: {e}",
                        markup=False,
                        highlight=False,
                    )
                    return error_code
            loaded.append((title, *values))

        difference_count = 0
        for title, source_values, target_values in loaded:
            difference_count += self._print_differences(
                title,
                source_name,
                target_name,
                source_values,
                target_values,
                show_sensitive,
            )

        if difference_count == 0:
            console.print(
                f"No configuration differences between "
                f"[cyan]{source_name}[/] and [cyan]{target_name}[/]."
            )
        return 1 if exit_code and difference_count else 0

    def _print_differences(
        self,
        title: str,
        source_name: str,
        target_name: str,
        source_values: Dict[str, str],
        target_values: Dict[str, str],
        show_sensitive: bool,
    ) -> int:
        keys = sorted(
            key
            for key in source_values.keys() | target_values.keys()
            if source_values.get(key) != target_values.get(key)
        )
        if not keys:
            return 0

        console.print(f"[bold]{title} differences[/]")
        for key in keys:
            console.print(Text(key, style="cyan"))
            self._print_value(
                source_name,
                self._display_value(key, source_values, show_sensitive),
                "green",
            )
            self._print_value(
                target_name,
                self._display_value(key, target_values, show_sensitive),
                "yellow",
            )
        return len(keys)

    @staticmethod
    def _print_value(name: str, value: Text, style: str) -> None:
        line = Text("  ")
        line.append(f"{name}: ", style=style)
        line.append_text(value)
        console.print(line, soft_wrap=True)

    @staticmethod
    def _display_value(
        key: str,
        values: Dict[str, str],
        show_sensitive: bool,
    ) -> Text:
        if key not in values:
            return Text("<not set>", style="dim")
        value = values[key]
        if not show_sensitive and (is_sensitive_key(key) or contains_secret(value)):
            return Text("<redacted>", style="dim")
        return Text(printable(value.replace("\n", "\\n")))
