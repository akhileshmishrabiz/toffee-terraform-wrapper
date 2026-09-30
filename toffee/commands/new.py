"""Create the fixed Terraform project layout used by Toffee."""

import os
import shlex
import sys
from typing import Dict, List, Optional, Tuple, Union

import click

from ..core import scaffold
from ..core.text import printable

_UNICODE_GLYPHS = ("├── ", "└── ", "│   ", "    ")
_ASCII_GLYPHS = ("|-- ", "`-- ", "|   ", "    ")


class NewCommand:
    """Write a fixed scaffold without prompting."""

    def run(self, directory: Optional[str]) -> int:
        try:
            plan = scaffold.plan_project(directory)
            if any(change.action != scaffold.SKIP for change in plan.changes):
                scaffold.write_plan(plan)
        except scaffold.ScaffoldError as error:
            raise click.ClickException(str(error)) from None
        except OSError as error:
            raise click.ClickException(
                printable(f"Cannot write the project: {error}")
            ) from None

        location = _location(directory)
        changed = [change for change in plan.changes if change.action != scaffold.SKIP]
        if not changed:
            click.echo(
                f"Nothing to create; all files already exist in {location or './'}."
            )
            return 0

        created = plan.with_action(scaffold.CREATE)
        appended = plan.with_action(scaffold.APPEND)
        if created:
            header = f"Created {_count(len(created), 'file')}"
        else:
            header = "Updated .gitignore"
        lines = [f"{header} for project {plan.project}:", ""]
        entries = [(change.path, "") for change in created]
        entries += [
            (change.path, f" (added {_count(change.added_lines, 'line')})")
            for change in appended
        ]
        lines += _tree(location or "./", entries)

        skipped = plan.with_action(scaffold.SKIP)
        if skipped:
            lines += [
                "",
                f"Skipped {_count(len(skipped), 'file')} that already "
                f"exist{'s' if len(skipped) == 1 else ''} (not overwritten).",
            ]
        if plan.omitted:
            lines += ["", "Found existing Terraform files, so no .tf files were added."]

        backend = f"{location}vars/dev.tfbackend"
        cd = f"cd {shlex.quote(os.path.normpath(directory))} && " if location else ""
        lines += [
            "",
            "Next steps:",
            f"  1. Replace CHANGE-ME in {backend} (bucket)",
            f"  2. {cd}toffee dev init",
            "  3. toffee dev plan",
        ]
        click.echo("\n".join(printable(line) for line in lines))
        return 0


def _location(directory: Optional[str]) -> str:
    if directory is None:
        return ""
    normalized = os.path.normpath(directory)
    if os.path.abspath(normalized) == os.getcwd():
        return ""
    return normalized.rstrip("/\\") + "/"


def _tree(root: str, entries: List[Tuple[str, str]]) -> List[str]:
    branch, last_branch, pipe, space = _glyphs()
    nodes: Dict[str, Union[dict, str]] = {}
    for path, note in entries:
        node = nodes
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = note
    lines = [root]

    def walk(node: dict, indent: str) -> None:
        items = list(node.items())
        for index, (name, child) in enumerate(items):
            last = index == len(items) - 1
            prefix = indent + (last_branch if last else branch)
            if isinstance(child, dict):
                lines.append(prefix + name)
                walk(child, indent + (space if last else pipe))
            else:
                lines.append(prefix + name + child)

    walk(nodes, "")
    return lines


def _glyphs() -> Tuple[str, str, str, str]:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "".join(_UNICODE_GLYPHS).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return _ASCII_GLYPHS
    return _UNICODE_GLYPHS


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"
