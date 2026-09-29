"""Compare the configuration files for two environments."""

from typing import Dict

from rich.console import Console
from rich.text import Text

from ..core.environment_diff import is_sensitive_key, read_assignments
from .base import BaseCommand

console = Console()


class DiffCommands(BaseCommand):
    """Handle environment configuration comparisons."""

    def compare(
        self,
        source_name: str,
        target_name: str,
        show_sensitive: bool = False,
    ) -> int:
        for name in (source_name, target_name):
            if not self.validate_environment(name):
                return 1

        source = self.env_manager.get_environment(source_name)
        target = self.env_manager.get_environment(target_name)
        comparisons = (
            ("Variables", source.vars_file, target.vars_file),
            ("Backend", source.backend_file, target.backend_file),
        )

        difference_count = 0
        for title, source_path, target_path in comparisons:
            source_values = read_assignments(source_path)
            target_values = read_assignments(target_path)
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
        return 0

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
        if is_sensitive_key(key) and not show_sensitive:
            return Text("<redacted>", style="dim")
        value = "".join(
            character if ord(character) >= 32 and ord(character) != 127 else "�"
            for character in values[key]
        )
        return Text(value)
