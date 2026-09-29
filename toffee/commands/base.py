"""
Base command handler for the Toffee CLI tool
"""

import logging
import os
import sys
from typing import List, Optional, Sequence

from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..core.backend import (
    Backend,
    BackendError,
    Identity,
    describe_identity,
    find_backend,
    read_settings,
    selected_workspace,
    state_identity,
)
from ..core.config import Config
from ..core.environment import EnvironmentManager
from ..core.executor import run_parallel, run_streamed
from ..core.safety import is_protected_environment
from ..core.terraform import (
    TerraformRunner,
    bool_flag,
    display_command,
    working_directory,
)
from ..core.text import printable

console = Console()
error_console = Console(stderr=True, soft_wrap=True)
status_console = Console(stderr=True, soft_wrap=True)
logger = logging.getLogger(__name__)


class BaseCommand:
    """Base class for all Toffee commands"""

    def __init__(self):
        self.project_dir = os.path.abspath(os.getcwd())
        self.config = Config()
        self.project_config = self.config.get_project_config()
        self._setup_logging()

        vars_dir = self.project_config.get("vars_dir", "vars")
        self.env_manager = EnvironmentManager(vars_dir=vars_dir)

        terraform_path = self.project_config.get("terraform_path", "terraform")
        self.terraform = TerraformRunner(terraform_path=terraform_path)
        self.protected_names = self.project_config.get("protected_environments", [])

    def is_protected(self, env_name: str) -> bool:
        return is_protected_environment(env_name, self.protected_names)

    def display_path(self, path: str) -> str:
        relative = os.path.relpath(path, self.project_dir)
        return path if relative.startswith("..") else relative

    def _setup_logging(self) -> None:
        if self.project_config.get("verbose", False):
            logging.basicConfig(level=logging.DEBUG, force=True)

    def validate_environment(
        self,
        env_name: str,
    ) -> bool:
        """Validate that a target is a complete, isolated environment."""
        valid, error_msg = self.env_manager.validate_environment(
            env_name,
            require_vars=True,
            require_backend=True,
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
                Text(printable(name)),
                Text(
                    printable(os.path.basename(env.vars_file))
                    + (" ✓" if vars_exists else " ✗")
                ),
                Text(
                    printable(os.path.basename(env.backend_file))
                    + (" ✓" if backend_exists else " ✗")
                ),
                status,
            )

        console.print(table)

    def execute_terraform_command(
        self,
        env_name: Optional[str],
        command_name: str,
        extra_args: Optional[List[str]] = None,
        global_args: Optional[List[str]] = None,
    ) -> int:
        """Execute a Terraform command, optionally scoped to an environment."""
        extra_args = extra_args or []
        env = None

        if env_name:
            if not self.validate_environment(env_name):
                return 1
            env = self.env_manager.get_environment(env_name)

        cmd = self.terraform.build_command(
            command_name, env, extra_args, global_args
        )
        status_console.print(
            f"Running: {display_command(cmd)}", markup=False, highlight=False
        )

        try:
            process_env = self._environment_variables(env_name) if env_name else None
            return_code = run_streamed(cmd, process_env)
        except OSError as e:
            error_console.print(
                f"Error executing command: {e}", markup=False, highlight=False
            )
            return 1
        status_console.print(
            self._result_message("Command", return_code, extra_args),
            markup=False,
            highlight=False,
        )
        return return_code

    def execute_for_environments(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: Optional[List[str]] = None,
        parallel: bool = False,
        global_args: Optional[List[str]] = None,
    ) -> int:
        """Execute a Terraform command across one or more environments."""
        extra_args = extra_args or []

        if not env_names:
            error_console.print(
                "Error: No environment specified. Run "
                "'toffee <env>[,<env>...] <terraform-command>'."
            )
            return 1

        for env_name in env_names:
            valid_name, name_error = self.env_manager.validate_env_name(env_name)
            if not valid_name:
                error_console.print(f"Error: {name_error}")
                return 1
            if not self.validate_environment(env_name):
                return 1

        global_args = list(global_args or [])
        if not self.check_state_isolation(env_names, working_directory(global_args)):
            return 1
        if not self.prepare_execution(
            env_names, command_name, extra_args, global_args
        ):
            return 1

        if parallel and command_name == "init":
            status_console.print(
                "[yellow]Terraform init is serialized because environments share "
                ".terraform.lock.hcl; backend metadata remains isolated.[/]"
            )
            parallel = False

        if len(env_names) == 1 and not parallel:
            return self.execute_terraform_command(
                env_names[0], command_name, extra_args, global_args
            )

        status_console.print(
            f"Running {command_name} for environments: {', '.join(env_names)}",
            markup=False,
            highlight=False,
        )

        if parallel:
            return self._execute_parallel(
                env_names, command_name, extra_args, global_args
            )

        codes = []
        for env_name in env_names:
            status_console.print(f"\n[bold]Environment:[/] {env_name}")
            code = self.execute_terraform_command(
                env_name, command_name, extra_args, global_args
            )
            codes.append(code)
            if self._is_failure(code, extra_args):
                return code
        return self.combined_exit_code(codes, extra_args)

    @staticmethod
    def _is_failure(code: int, extra_args: Sequence[str]) -> bool:
        # With -detailed-exitcode, Terraform exits 2 when changes are present.
        return code != 0 and not (
            code == 2 and bool_flag(extra_args, "detailed-exitcode")
        )

    @classmethod
    def combined_exit_code(cls, codes: Sequence[int], extra_args: Sequence[str]) -> int:
        """Report the first failure, else 2 if any target had changes, else 0."""
        for code in codes:
            if cls._is_failure(code, extra_args):
                return code
        return 2 if 2 in codes else 0

    @classmethod
    def _result_message(cls, subject: str, code: int, extra_args: Sequence[str]) -> str:
        if code == 0:
            return f"{subject} succeeded"
        if not cls._is_failure(code, extra_args):
            return f"{subject} succeeded with changes present"
        return f"{subject} failed with exit code {code}"

    def prepare_execution(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: List[str],
        global_args: List[str],
    ) -> bool:
        """Allow subclasses to confirm execution after all targets are validated."""
        return True

    def check_state_isolation(self, env_names: List[str], root_dir: str) -> bool:
        """Refuse to run when a target shares files or state with another env."""
        all_names = self.env_manager.get_environment_names()
        owners = {}
        for name in all_names:
            env = self.env_manager.get_environment(name)
            for path in (env.vars_file, env.backend_file):
                if os.path.exists(path):
                    owners.setdefault(os.path.realpath(path), []).append((name, path))

        for target in env_names:
            env = self.env_manager.get_environment(target)
            for path in (env.vars_file, env.backend_file):
                for owner, owner_path in owners.get(os.path.realpath(path), []):
                    if owner != target:
                        error_console.print(
                            f"Error: {self.display_path(path)} resolves to the same "
                            f"file as {self.display_path(owner_path)} "
                            f"(environment '{owner}'). Each environment needs its "
                            "own files.",
                            markup=False,
                            highlight=False,
                        )
                        return False

        comparable = [
            name
            for name in all_names
            if os.path.isfile(self.env_manager.get_environment(name).backend_file)
        ]
        if len(comparable) < 2:
            return True
        try:
            backend = find_backend(root_dir)
            identities = {
                name: self.state_identity(
                    backend,
                    name,
                    read_settings(self.env_manager.get_environment(name).backend_file),
                    root_dir,
                )
                for name in comparable
            }
        except BackendError as e:
            error_console.print(
                f"Error: Cannot verify that environments use separate state: {e}",
                markup=False,
                highlight=False,
            )
            return False

        for target in env_names:
            for other in comparable:
                if other != target and identities[other] == identities[target]:
                    self.print_shared_state(
                        target, other, identities[target], backend, root_dir
                    )
                    return False
        return True

    def state_identity(
        self,
        backend: Optional[Backend],
        env_name: str,
        settings: dict,
        root_dir: str,
    ) -> Identity:
        workspace = selected_workspace(self.terraform_data_dir(env_name))
        return state_identity(backend, settings, root_dir, workspace)

    def print_shared_state(
        self,
        env_name: str,
        other_name: str,
        identity: Identity,
        backend: Optional[Backend],
        root_dir: str,
    ) -> None:
        error_console.print(
            f"Error: Environments '{env_name}' and '{other_name}' would share "
            f"Terraform state ({describe_identity(identity)}).",
            markup=False,
            highlight=False,
        )
        if backend is None:
            error_console.print(
                f"No backend block was found in {root_dir}, so every environment "
                "uses the default local state. Add a backend block to the root "
                "module.",
                markup=False,
                highlight=False,
            )
        else:
            error_console.print(
                "Give each environment its own state location in "
                f"{self.display_path(self.env_manager.vars_dir)}/<env>.tfbackend.",
                markup=False,
                highlight=False,
            )

    def _execute_parallel(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: List[str],
        global_args: Optional[List[str]],
    ) -> int:
        commands = [
            self.terraform.build_command(
                command_name,
                self.env_manager.get_environment(env_name),
                extra_args,
                global_args,
                non_interactive=True,
            )
            for env_name in env_names
        ]
        results = run_parallel(
            [
                (cmd, self._environment_variables(env_name))
                for env_name, cmd in zip(env_names, commands)
            ]
        )

        codes = []
        for env_name, cmd, (code, stdout, stderr) in zip(env_names, commands, results):
            status_console.rule(f"[bold]{env_name}[/]")
            status_console.print(
                f"Running: {display_command(cmd)}", markup=False, highlight=False
            )
            # Raw bytes keep machine-readable output (such as -json) intact.
            _write_raw(sys.stdout, stdout)
            _write_raw(sys.stderr, stderr)
            style = "red" if self._is_failure(code, extra_args) else "green"
            status_console.print(
                self._result_message(env_name, code, extra_args),
                style=style,
                markup=False,
                highlight=False,
            )
            codes.append(code)
        return self.combined_exit_code(codes, extra_args)

    def terraform_data_dir(self, env_name: str) -> str:
        return os.path.join(self.project_dir, ".toffee", "terraform-data", env_name)

    def _environment_variables(self, env_name: str) -> dict:
        """Return a subprocess environment with isolated Terraform metadata."""
        data_dir = self.terraform_data_dir(env_name)
        os.makedirs(data_dir, exist_ok=True)
        process_env = os.environ.copy()
        process_env["TF_DATA_DIR"] = data_dir
        return process_env


def _write_raw(stream, data: bytes) -> None:
    if not data:
        return
    stream.flush()
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        stream.write(data.decode(errors="replace"))
    else:
        buffer.write(data)
        buffer.flush()
    stream.flush()
