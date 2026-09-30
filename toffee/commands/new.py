"""Create a Terraform project laid out for Toffee."""

import os
import shlex
import sys
from typing import Dict, List, Optional, Tuple, Union

import click

from ..core import scaffold
from ..core.placeholders import PLACEHOLDER
from ..core.text import printable

_UNICODE_GLYPHS = ("├── ", "└── ", "│   ", "    ")
_ASCII_GLYPHS = ("|-- ", "`-- ", "|   ", "    ")


class NewCommand:
    """Print a compact, plain-text summary; never prompt."""

    def run(self, options: scaffold.Options, dry_run: bool = False) -> int:
        try:
            plan = scaffold.plan_project(options)
            if not dry_run and self._has_changes(plan):
                scaffold.write_plan(plan)
        except scaffold.ScaffoldError as e:
            raise click.ClickException(str(e)) from None
        except OSError as e:
            raise click.ClickException(
                printable(f"Cannot write the project: {e}")
            ) from None

        for warning in plan.warnings:
            click.echo(f"Warning: {warning}", err=True)

        location = _location(options.directory)
        if not self._has_changes(plan):
            click.echo(
                f"Nothing to create; all files already exist in {location or './'}."
            )
            return 0

        created = plan.with_action(scaffold.CREATE)
        skipped = plan.with_action(scaffold.SKIP)
        verb = "Would create" if dry_run else "Created"
        if created:
            header = f"{verb} {_count(len(created), 'file')}"
        else:
            header = "Would update .gitignore" if dry_run else "Updated .gitignore"
        lines = [f"{header} for project {plan.project}:", ""]

        entries = []
        for change in plan.changes:
            if change.action == scaffold.CREATE:
                entries.append((change.path, ""))
            elif change.action == scaffold.APPEND:
                added = _count(change.added_lines, "line")
                entries.append(
                    (change.path, f" (would add {added})" if dry_run else f" (added {added})")
                )
        lines += _tree(location or "./", entries)

        if skipped:
            skip_verb = "Would skip" if dry_run else "Skipped"
            lines += [
                "",
                f"{skip_verb} {_count(len(skipped), 'file')} that already "
                f"exist{'s' if len(skipped) == 1 else ''} (not overwritten).",
            ]
        if plan.omitted:
            lines += ["", "Found existing Terraform files, so no .tf files were added."]

        if dry_run:
            lines += ["", "Dry run: nothing was written."]
        else:
            steps = self._next_steps(plan, options.directory, location)
            if steps:
                lines += ["", "Next steps:"]
                lines += [f"  {number}. {step}" for number, step in enumerate(steps, 1)]

        click.echo("\n".join(printable(line) for line in lines))
        return 0

    @staticmethod
    def _has_changes(plan: scaffold.Plan) -> bool:
        return any(change.action != scaffold.SKIP for change in plan.changes)

    @staticmethod
    def _next_steps(
        plan: scaffold.Plan, directory: Optional[str], location: str
    ) -> List[str]:
        steps = []
        refs = scaffold.placeholder_refs(plan)
        if refs:
            listed = [f"{location}{path} ({', '.join(keys)})" for path, keys in refs]
            steps.append(f"Replace {PLACEHOLDER} in {_join(listed)}")
        env = plan.envs[0]
        if scaffold.env_is_complete(plan, env):
            cd = f"cd {shlex.quote(os.path.normpath(directory))} && " if location else ""
            steps += [f"{cd}toffee {env} init", f"toffee {env} plan"]
        return steps


def _location(directory: Optional[str]) -> str:
    """Return the directory as typed, with a trailing slash, or "" for cwd."""
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


def _join(items: List[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]
