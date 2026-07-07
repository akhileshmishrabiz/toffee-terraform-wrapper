"""
Terraform command handlers for the Toffee CLI tool
"""

from typing import List, Optional

import typer
from rich.console import Console

from .base import BaseCommand

console = Console()
error_console = Console(stderr=True)


class TerraformCommands(BaseCommand):
    """Handles Terraform-related commands in the Toffee CLI tool"""

    def _with_auto_approve(self, extra_args: Optional[List[str]]) -> List[str]:
        args = list(extra_args or [])
        if self.project_config.get("auto_approve", False) and "-auto-approve" not in args:
            args.append("-auto-approve")
        return args

    def init(
        self,
        env_names: List[str],
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        return self.execute_for_environments(envs, "init", extra_args, parallel)

    def plan(
        self,
        env_names: List[str],
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        return self.execute_for_environments(envs, "plan", extra_args, parallel)

    def apply(
        self,
        env_names: List[str],
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        extra_args = self._with_auto_approve(extra_args)
        return self.execute_for_environments(envs, "apply", extra_args, parallel)

    def destroy(
        self,
        env_names: List[str],
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        extra_args = list(extra_args or [])

        if "-auto-approve" not in extra_args:
            console.print(
                "[bold red]WARNING:[/] This will destroy all resources. "
                "This action cannot be undone."
            )
            if not typer.confirm("Do you want to continue?"):
                console.print("Operation aborted.")
                return 1
            extra_args.append("-auto-approve")

        return self.execute_for_environments(envs, "destroy", extra_args, parallel)

    def output(
        self,
        env_names: List[str],
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        return self.execute_for_environments(envs, "output", extra_args, parallel)

    def refresh(
        self,
        env_names: List[str],
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        return self.execute_for_environments(envs, "refresh", extra_args, parallel)

    def validate(
        self,
        env_names: Optional[List[str]] = None,
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        if not envs:
            return self.execute_terraform_command(None, "validate", extra_args)
        return self.execute_for_environments(envs, "validate", extra_args, parallel)

    def fmt(
        self,
        env_name: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> int:
        if env_name:
            return self.execute_terraform_command(env_name, "fmt", extra_args)
        return self.execute_terraform_command(None, "fmt", extra_args)

    def state(
        self,
        env_arg: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> int:
        env_name, state_args = self.terraform.parse_state_arguments(
            env_arg,
            extra_args,
            self.env_manager.get_environment_names(),
        )
        return self.execute_terraform_command(env_name, "state", state_args)

    def run_command(
        self,
        env_names: List[str],
        command: str,
        extra_args: Optional[List[str]] = None,
        all_envs: bool = False,
        parallel: bool = False,
    ) -> int:
        envs = self.resolve_environments(env_names, all_envs)
        return self.execute_for_environments(envs, command, extra_args, parallel)
