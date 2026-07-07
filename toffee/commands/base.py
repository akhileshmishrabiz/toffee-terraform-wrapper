"""
Base command handler for the Toffee CLI tool
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from rich.console import Console
from rich.table import Table

from ..core.config import Config
from ..core.environment import EnvironmentManager
from ..core.executor import run_terraform_command
from ..core.terraform import TerraformRunner

console = Console()
error_console = Console(stderr=True)
logger = logging.getLogger(__name__)


class BaseCommand:
    """Base class for all Toffee commands"""

    def __init__(self):
        self.config = Config()
        self.project_config = self.config.get_project_config()
        self._setup_logging()

        vars_dir = self.project_config.get("vars_dir", "vars")
        self.env_manager = EnvironmentManager(vars_dir=vars_dir)

        terraform_path = self.project_config.get("terraform_path", "terraform")
        self.terraform = TerraformRunner(terraform_path=terraform_path)

    def _setup_logging(self) -> None:
        if self.project_config.get("verbose", False):
            logging.basicConfig(level=logging.DEBUG, force=True)

    def resolve_environments(
        self,
        env_names: Optional[List[str]],
        all_envs: bool = False,
    ) -> List[str]:
        """Resolve which environments to target for a command."""
        if all_envs:
            return self.env_manager.get_environment_names()

        if env_names:
            return env_names

        default_env = self.project_config.get("default_environment")
        if default_env:
            return [default_env]

        return []

    def validate_environment(
        self,
        env_name: str,
        command_name: Optional[str] = None,
    ) -> bool:
        """Validate that an environment exists and has required files."""
        command = self.terraform.get_command(command_name) if command_name else None
        require_vars = bool(command and command.needs_vars_file)
        require_backend = bool(
            command and command.needs_backend_config and command_name == "init"
        )

        valid, error_msg = self.env_manager.validate_environment(
            env_name,
            require_vars=require_vars,
            require_backend=require_backend,
        )

        if not valid:
            error_console.print(f"Error: {error_msg}")
            if error_msg and "not found" in error_msg:
                suggestion = self.env_manager.suggest_environment(env_name)
                if suggestion:
                    error_console.print(f"Did you mean: {suggestion}?")
            return False

        return True

    def display_environments(self) -> None:
        """Display a list of available environments"""
        env_names = self.env_manager.get_environment_names()

        if not env_names:
            console.print(
                "No environments found. Create one with "
                "[cyan]toffee env create <name>[/] or add files under vars/."
            )
            return

        table = Table(title="Available Environments")
        table.add_column("Environment", style="cyan")
        table.add_column("Vars File", style="green")
        table.add_column("Backend File", style="green")
        table.add_column("Status", style="yellow")

        for name in env_names:
            env = self.env_manager.get_environment(name)
            vars_exists = os.path.isfile(env.vars_file)
            backend_exists = os.path.isfile(env.backend_file)
            status = "ready" if vars_exists and backend_exists else "incomplete"

            table.add_row(
                name,
                os.path.basename(env.vars_file) + (" ✓" if vars_exists else " ✗"),
                os.path.basename(env.backend_file)
                + (" ✓" if backend_exists else " ✗"),
                status,
            )

        console.print(table)

    def display_terraform_commands(self) -> None:
        """Display a list of available Terraform commands"""
        table = Table(title="Available Terraform Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="green")

        for name in self.terraform.get_command_names():
            cmd = self.terraform.get_command(name)
            table.add_row(name, cmd.description)

        console.print(table)

    def execute_terraform_command(
        self,
        env_name: Optional[str],
        command_name: str,
        extra_args: Optional[List[str]] = None,
    ) -> int:
        """Execute a Terraform command, optionally scoped to an environment."""
        extra_args = extra_args or []
        env = None

        if env_name:
            if not self.validate_environment(env_name, command_name):
                return 1
            env = self.env_manager.get_environment(env_name)

        cmd = self.terraform.build_command(command_name, env, extra_args)
        console.print(f"Running: {' '.join(cmd)}")

        try:
            return_code = run_terraform_command(cmd)
            if return_code == 0:
                console.print("Command succeeded")
            else:
                console.print(f"Command failed with exit code {return_code}")
            return return_code
        except OSError as e:
            error_console.print(f"Error executing command: {e}")
            return 1

    def execute_for_environments(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: Optional[List[str]] = None,
        parallel: bool = False,
    ) -> int:
        """Execute a Terraform command across one or more environments."""
        extra_args = extra_args or []

        if not env_names:
            error_console.print(
                "Error: No environment specified. Pass environment name(s), "
                "use --all, or set default_environment in config."
            )
            return 1

        for env_name in env_names:
            valid_name, name_error = self.env_manager.validate_env_name(env_name)
            if not valid_name:
                error_console.print(f"Error: {name_error}")
                return 1

        if len(env_names) == 1 and not parallel:
            return self.execute_terraform_command(
                env_names[0], command_name, extra_args
            )

        console.print(
            f"Running [bold]{command_name}[/] for environments: "
            f"{', '.join(env_names)}"
        )

        if parallel:
            return self._execute_parallel(env_names, command_name, extra_args)

        exit_code = 0
        for env_name in env_names:
            console.print(f"\n[bold]Environment:[/] {env_name}")
            code = self.execute_terraform_command(env_name, command_name, extra_args)
            if code != 0:
                exit_code = code
        return exit_code

    def _execute_parallel(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: List[str],
    ) -> int:
        exit_code = 0
        with ThreadPoolExecutor(max_workers=len(env_names)) as executor:
            futures = {
                executor.submit(
                    self._execute_quiet, env_name, command_name, extra_args
                ): env_name
                for env_name in env_names
            }
            for future in as_completed(futures):
                env_name = futures[future]
                try:
                    code = future.result()
                except Exception as e:
                    error_console.print(f"Error in {env_name}: {e}")
                    code = 1
                if code != 0:
                    exit_code = code
                    console.print(
                        f"[red]{env_name} failed with exit code {code}[/]"
                    )
                else:
                    console.print(f"[green]{env_name} succeeded[/]")
        return exit_code

    def _execute_quiet(
        self,
        env_name: str,
        command_name: str,
        extra_args: List[str],
    ) -> int:
        if not self.validate_environment(env_name, command_name):
            return 1

        env = self.env_manager.get_environment(env_name)
        cmd = self.terraform.build_command(command_name, env, extra_args)
        logger.debug("Running in parallel: %s", " ".join(cmd))
        return run_terraform_command(cmd)
