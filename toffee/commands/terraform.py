"""Generic Terraform command handling."""

import os
from typing import List, Optional

import click
from rich.console import Console

from .base import BaseCommand

console = Console()
error_console = Console(stderr=True)


class TerraformCommands(BaseCommand):
    """Apply Toffee safety policy, then pass argv directly to Terraform."""

    def _with_auto_approve(self, extra_args: Optional[List[str]]) -> List[str]:
        args = list(extra_args or [])
        if self.project_config.get("auto_approve", False) and "-auto-approve" not in args:
            args.append("-auto-approve")
        return args

    def run_command(
        self,
        env_names: List[str],
        command: str,
        extra_args: Optional[List[str]] = None,
        parallel: bool = False,
        global_args: Optional[List[str]] = None,
    ) -> int:
        args = list(extra_args or [])

        if command == "apply":
            args = self._with_auto_approve(args)
            if parallel and not self._apply_is_non_interactive(args):
                error_console.print(
                    "Error: Parallel apply requires -auto-approve or a saved plan."
                )
                return 1

        if parallel and command in {"console", "login"}:
            error_console.print(
                f"Error: Terraform {command} is interactive and cannot run in parallel."
            )
            return 1

        if command == "destroy" and "-auto-approve" not in args:
            console.print(
                "[bold red]WARNING:[/] This will destroy resources in: "
                f"{', '.join(env_names)}."
            )
            if not click.confirm("Do you want to continue?"):
                console.print("Operation aborted.")
                return 1
            args.append("-auto-approve")

        return self.execute_for_environments(
            env_names, command, args, parallel, global_args
        )

    @staticmethod
    def _apply_is_non_interactive(args: List[str]) -> bool:
        return "-auto-approve" in args or any(
            not arg.startswith("-") and os.path.isfile(arg)
            for arg in args
        )
