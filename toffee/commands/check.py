"""Run fmt, validate, and selected source scanners."""

from typing import List, Optional, Sequence

import click

from ..core.checks import (
    CheckStep,
    CheckUsage,
    check_names,
    find_executable,
    format_missing,
    parse_checks,
    plan_steps,
    rerun_command,
    status_phrase,
    status_style,
)
from ..core.executor import run_streamed
from ..core.terraform import _relative_path, display_command, working_directory
from .base import BaseCommand, error_console, status_console


@click.command("check")
@click.option(
    "--checks",
    metavar="TOOLS",
    help="Comma-separated scanners to add: tflint, checkov.",
)
def check_help_command() -> None:
    """Run Terraform fmt and validate, plus scanners named with --checks.

    fmt and validate always run. tflint and checkov run only when named, and
    a named scanner must be on PATH. Checkov prints failed checks only.

    \b
    Examples:
      toffee dev check
      toffee dev check help
      toffee dev check --checks tflint,checkov
      toffee dev,prod check --checks checkov
    """


def check_usage() -> str:
    """Return the check usage and options, without the longer description."""
    return (
        "Usage: toffee <env>[,<env>...] check [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  --checks TOOLS  Comma-separated scanners to add: tflint, checkov.\n"
        "  -h, --help      Show this message and exit.\n"
        "  help            Show this message and exit."
    )


def reject_check_usage(message: str) -> None:
    """Print check options, then exit 2. Does not return."""
    click.echo(f"{check_usage()}\n\nError: {message}", err=True)
    raise click.exceptions.Exit(2)


def check_help() -> str:
    """Return Toffee's help for the environment check command."""
    context = click.Context(
        check_help_command,
        info_name="toffee <env>[,<env>...] check",
    )
    return check_help_command.get_help(context)


class CheckCommands(BaseCommand):
    """Orchestrate the checks specified in specs/check.md."""

    def run(
        self,
        env_names: List[str],
        extra_args: Optional[Sequence[str]] = None,
        parallel: bool = False,
        global_args: Optional[Sequence[str]] = None,
    ) -> int:
        try:
            selected = parse_checks(list(extra_args or []))
        except CheckUsage as error:
            reject_check_usage(str(error))
        if parallel:
            reject_check_usage(
                "check runs one step at a time so the report stays in order. "
                "Remove --parallel."
            )

        for env_name in env_names:
            valid_name, name_error = self.env_manager.validate_env_name(env_name)
            if not valid_name:
                error_console.print(f"Error: {name_error}")
                return 1
            if not self.validate_environment(env_name):
                return 1

        global_args = list(global_args or [])
        terraform = self.terraform.terraform_path
        missing = []
        if find_executable(terraform) is None:
            missing.append(("terraform", terraform))
        for tool in selected:
            if find_executable(tool) is None:
                missing.append((tool, tool))
        if missing:
            found = [
                tool for tool in selected if tool not in {kind for kind, _ in missing}
            ]
            rerun = rerun_command(env_names, global_args, found)
            error_console.print(
                format_missing(missing, rerun),
                markup=False,
                highlight=False,
            )
            return 1

        root = working_directory(global_args)
        environments = [
            self.env_manager.get_environment(env_name) for env_name in env_names
        ]
        var_files = [_relative_path(env.vars_file, root) for env in environments]
        steps = plan_steps(terraform, global_args, env_names, var_files, selected, root)
        self._announce(env_names, selected)
        phrases = [self._run_step(step) for step in steps]
        self._summarize(phrases)
        return 1 if any(not phrase.endswith(" passed") for phrase in phrases) else 0

    def _announce(self, env_names: Sequence[str], selected: Sequence[str]) -> None:
        names = ", ".join(check_names(selected))
        status_console.print(
            f"Checks for {', '.join(env_names)}: {names}",
            markup=False,
            highlight=False,
        )

    def _run_step(self, step: CheckStep) -> str:
        status_console.print(f"\n{step.label}", markup=False, highlight=False)
        status_console.print(
            f"Running: {display_command(step.argv)}",
            markup=False,
            highlight=False,
        )
        process_env = (
            self._environment_variables(step.environment) if step.environment else None
        )
        try:
            code = run_streamed(list(step.argv), process_env, cwd=step.cwd)
        except OSError as error:
            error_console.print(
                f"Error executing command: {error}",
                markup=False,
                highlight=False,
            )
            code = 1
        phrase = status_phrase(step.label, code)
        self._print_status(phrase)
        return phrase

    def _summarize(self, phrases: Sequence[str]) -> None:
        status_console.print("\nSummary", markup=False, highlight=False)
        for phrase in phrases:
            self._print_status(phrase, indent="  ")

    @staticmethod
    def _print_status(phrase: str, indent: str = "") -> None:
        status_console.print(
            f"{indent}{phrase}",
            style=status_style(phrase),
            markup=False,
            highlight=False,
        )
