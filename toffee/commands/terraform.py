"""Generic Terraform command handling."""

import os
from typing import List, Optional

import click
from rich.console import Console

from ..core.safety import describe_backend, is_protected_environment
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

        return self.execute_for_environments(
            env_names, command, args, parallel, global_args
        )

    def confirm_execution(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: List[str],
    ) -> bool:
        """Require a Toffee confirmation before changing protected targets."""
        if command_name not in {"apply", "destroy"}:
            return True

        protected_targets = self._protected_targets(env_names)
        if not protected_targets:
            if command_name != "destroy" or "-auto-approve" in extra_args:
                return True
            console.print(
                "[bold red]WARNING:[/] This will destroy resources in: "
                f"{', '.join(env_names)}."
            )
            if not click.confirm("Do you want to continue?"):
                console.print("Operation aborted.")
                return False
            extra_args.append("-auto-approve")
            return True

        action = (
            "destroy resources in"
            if command_name == "destroy"
            else "apply changes to"
        )
        names = ", ".join(name.upper() for name in protected_targets)
        error_console.print(
            f"\n[bold yellow]⚠ You are about to {action} {names}.[/]"
        )
        for name in protected_targets:
            env = self.env_manager.get_environment(name)
            error_console.print(f"\nEnvironment: {name}")
            error_console.print(
                "Backend: ",
                describe_backend(self.project_dir, env.backend_file),
                sep="",
                markup=False,
                highlight=False,
            )

        # This is deliberately independent of Terraform's -auto-approve flag.
        if not click.confirm("\nContinue?", default=False, err=True):
            error_console.print("Operation aborted.")
            return False
        return True

    @staticmethod
    def _protected_targets(env_names: List[str]) -> List[str]:
        return [name for name in env_names if is_protected_environment(name)]

    @staticmethod
    def _apply_is_non_interactive(args: List[str]) -> bool:
        return "-auto-approve" in args or any(
            not arg.startswith("-") and os.path.isfile(arg)
            for arg in args
        )
