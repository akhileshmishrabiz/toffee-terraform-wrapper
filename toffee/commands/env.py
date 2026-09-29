"""
Environment management commands for the Toffee CLI tool
"""

import os
import shutil
import tempfile
from typing import List, Tuple

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from ..core import hcl
from ..core.backend import BackendError, find_backend, read_settings, settings_from_text
from ..core.text import printable
from .base import BaseCommand

console = Console()
error_console = Console(stderr=True, soft_wrap=True)

# Backend settings whose path segments conventionally name the environment.
_PATH_SETTINGS = frozenset({"key", "path", "prefix"})


class EnvCommands(BaseCommand):
    """Handles environment-related commands in the Toffee CLI tool"""

    def create_environment(self, name: str) -> int:
        """Create a new environment with template files"""
        valid_name, name_error = self.env_manager.validate_env_name(name)
        if not valid_name:
            error_console.print(f"[bold red]Error:[/] {name_error}")
            return 1

        conflict = self.env_manager.case_conflict(name)
        if conflict:
            self._print_case_conflict(name, conflict)
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
                f"[bold red]Error:[/] Failed to create environment '{name}': {error}",
                highlight=False,
            )
            return 1

        env = self.env_manager.get_environment(name)
        console.print(f"[bold green]Success:[/] Created environment '{name}'")
        console.print("Files created:")
        if env:
            console.print(f"  - {env.vars_file}", markup=False)
            console.print(f"  - {env.backend_file}", markup=False)

        vars_file = escape(printable(env.vars_file)) if env else name
        backend_file = escape(printable(env.backend_file)) if env else name
        console.print(
            Panel(
                f"[bold]Next steps:[/]\n\n"
                f"1. Edit the vars file: [cyan]{vars_file}[/]\n"
                f"2. Edit the backend config: [cyan]{backend_file}[/]\n"
                f"3. Initialize Terraform: [cyan]toffee {name} init[/]",
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
        if source == target:
            error_console.print(
                "[bold red]Error:[/] Source and target must be different environments"
            )
            return 1

        conflict = self.env_manager.case_conflict(target)
        if conflict:
            self._print_case_conflict(target, conflict)
            return 1
        target_files = self.env_manager.env_file_paths(target)
        for path in target_files:
            if os.path.islink(path):
                error_console.print(
                    f"Error: Refusing to write through symlink: {self.display_path(path)}",
                    markup=False,
                    highlight=False,
                )
                return 1
        if not self.env_manager.is_safe_env_path(target):
            error_console.print(f"[bold red]Error:[/] Invalid environment name: '{target}'")
            return 1

        planned = []
        rewrites = []
        backend_text = None
        try:
            sources = zip(
                (source_env.vars_file, source_env.backend_file),
                target_files,
                (False, True),
            )
            for source_path, target_path, is_backend in sources:
                if not os.path.isfile(source_path):
                    continue
                with open(source_path, "r", encoding="utf-8") as source_file:
                    content, changes = _rewrite(
                        source_file.read(), source, target, is_backend
                    )
                planned.append((source_path, target_path, content))
                rewrites.extend((target_path, *change) for change in changes)
                if is_backend:
                    backend_text = content
        except (OSError, UnicodeDecodeError, hcl.HCLError) as e:
            error_console.print(
                f"Error: Cannot read environment '{source}': {e}",
                markup=False,
                highlight=False,
            )
            return 1

        if backend_text is not None and not self._copy_keeps_state_separate(
            target, backend_text
        ):
            return 1

        if any(os.path.lexists(path) for path in target_files):
            error_console.print(
                f"[bold yellow]Warning:[/] Target environment '{target}' already exists"
            )
            if not _confirm("Overwrite?"):
                error_console.print("Operation aborted.")
                return 1

        try:
            _write_all(self.env_manager.vars_dir, target, planned)
        except OSError as e:
            error_console.print(
                f"Error: Failed to copy environment: {e}",
                markup=False,
                highlight=False,
            )
            return 1
        self.env_manager.refresh_environments()

        console.print(
            f"[bold green]Success:[/] Copied environment '{source}' to '{target}'"
        )
        console.print("Files created:")
        for _source_path, target_path, _content in planned:
            console.print(f"  - {target_path}", markup=False, highlight=False)
        if rewrites:
            console.print(f"Rewrote references to '{source}':")
            for path, line, old, new in rewrites:
                console.print(
                    printable(f"  {self.display_path(path)}:{line}: {old} -> {new}"),
                    markup=False,
                    highlight=False,
                )
        else:
            console.print(f"No references to '{source}' were rewritten.")
        console.print(
            "Review the copied files before running Terraform, especially the "
            "backend state location."
        )
        return 0

    def _copy_keeps_state_separate(self, target: str, backend_text: str) -> bool:
        try:
            backend = find_backend(self.project_dir)
            identity = self.state_identity(
                backend, target, settings_from_text(backend_text), self.project_dir
            )
            for other in self.env_manager.get_environment_names():
                other_env = self.env_manager.get_environment(other)
                if other == target or not os.path.isfile(other_env.backend_file):
                    continue
                other_identity = self.state_identity(
                    backend,
                    other,
                    read_settings(other_env.backend_file),
                    self.project_dir,
                )
                if other_identity == identity:
                    self.print_shared_state(
                        target, other, identity, backend, self.project_dir
                    )
                    error_console.print(
                        "Nothing was written. Copy the files manually and change "
                        f"the state location, or run: toffee env create {target}"
                    )
                    return False
        except (BackendError, hcl.HCLError) as e:
            error_console.print(
                f"Error: Cannot verify that '{target}' would use separate state: {e}",
                markup=False,
                highlight=False,
            )
            return False
        return True

    @staticmethod
    def _print_case_conflict(name: str, existing: str) -> None:
        error_console.print(
            f"[bold red]Error:[/] '{name}' differs only by case from existing "
            f"environment '{existing}'. Environment names must be unique ignoring "
            "case."
        )


def _confirm(question: str) -> bool:
    try:
        return click.confirm(question, default=False, err=True)
    except click.Abort:
        return False


def _rewrite(
    text: str, source: str, target: str, is_backend: bool
) -> Tuple[str, List[Tuple[int, str, str]]]:
    """Rename quoted references to the source environment."""
    literals = hcl.string_literals(text)
    edits = {}
    for start, end in literals:
        if hcl.string_value(text[start:end]) == source:
            edits[start] = (end, f'"{target}"')

    if is_backend:
        for item in hcl.parse(text):
            if item.is_block or item.key not in _PATH_SETTINGS:
                continue
            if hcl.string_value(item.raw) is None:
                continue
            for start, end in literals:
                if start >= item.start and end <= item.end:
                    inner = text[start + 1 : end - 1]
                    replaced = _rewrite_path(inner, source, target)
                    if replaced != inner:
                        edits[start] = (end, f'"{replaced}"')

    changes = []
    result = text
    for start in sorted(edits, reverse=True):
        end, replacement = edits[start]
        changes.append((text.count("\n", 0, start) + 1, text[start:end], replacement))
        result = result[:start] + replacement + result[end:]
    return result, sorted(changes)


def _rewrite_path(value: str, source: str, target: str) -> str:
    segments = value.split("/")
    for index, segment in enumerate(segments):
        if segment == source:
            segments[index] = target
        elif index == len(segments) - 1:
            stem, dot, rest = segment.partition(".")
            if dot and stem == source:
                segments[index] = f"{target}.{rest}"
    return "/".join(segments)


def _write_all(directory: str, name: str, planned: list) -> None:
    """Write every file to a temporary name first, then move them into place."""
    os.makedirs(directory, exist_ok=True)
    temporaries = []
    try:
        for source_path, _target_path, content in planned:
            handle, temporary = tempfile.mkstemp(
                dir=directory, prefix=f".{name}.", suffix=".tmp"
            )
            temporaries.append(temporary)
            with os.fdopen(handle, "w", encoding="utf-8") as target_file:
                target_file.write(content)
            shutil.copymode(source_path, temporary)
        for (_source_path, target_path, _content), temporary in zip(
            planned, temporaries
        ):
            os.replace(temporary, target_path)
    finally:
        for temporary in temporaries:
            if os.path.exists(temporary):
                os.remove(temporary)
