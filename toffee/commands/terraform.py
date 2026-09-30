"""Generic Terraform command handling."""

import os
from typing import List, Optional, Tuple

import click
from rich.console import Console

from ..core import plans
from ..core.backend import BackendError, read_settings
from ..core.placeholders import PLACEHOLDER, placeholder_keys
from ..core.safety import describe_backend
from ..core.terraform import (
    bool_flag,
    flag_value,
    saved_plan_path,
    split_flag,
    working_directory,
)
from ..core.text import printable
from .base import BaseCommand

error_console = Console(stderr=True, soft_wrap=True)

# Commands that can change the state of the environments they target.
STATE_CHANGING_COMMANDS = frozenset(
    {
        "apply",
        "destroy",
        "force-unlock",
        "import",
        "refresh",
        "taint",
        "test",
        "untaint",
    }
)
STATE_CHANGING_SUBCOMMANDS = {
    "state": frozenset({"mv", "push", "replace-provider", "rm"}),
    "workspace": frozenset({"delete"}),
}


class TerraformCommands(BaseCommand):
    """Apply Toffee safety policy, then pass argv directly to Terraform."""

    def _with_auto_approve(self, args: List[str]) -> List[str]:
        if not self.project_config.get("auto_approve", False):
            return args
        if bool_flag(args, "auto-approve") is not None:
            return args
        # Go's flag parser stops at the first positional argument.
        return ["-auto-approve", *args]

    def run_command(
        self,
        env_names: List[str],
        command: str,
        extra_args: Optional[List[str]] = None,
        parallel: bool = False,
        global_args: Optional[List[str]] = None,
    ) -> int:
        args = list(extra_args or [])
        global_args = list(global_args or [])
        working_dir = working_directory(global_args)
        saved_plan = saved_plan_path(args, working_dir) if command == "apply" else None
        plan_out = flag_value(args, "out") if command == "plan" else None

        if len(env_names) > 1 and saved_plan:
            error_console.print(
                "Error: A saved plan belongs to a single environment. Apply it "
                "with one target: toffee <env> apply <plan>"
            )
            return 1
        if len(env_names) > 1 and plan_out:
            error_console.print(
                "Error: plan -out writes one file, so each environment would "
                "overwrite the previous plan. Run plan -out once per environment."
            )
            return 1

        if command == "apply" and not saved_plan and not self._destroys(command, args):
            args = self._with_auto_approve(args)
            if parallel and not bool_flag(args, "auto-approve"):
                error_console.print(
                    "Error: Parallel apply requires -auto-approve or a saved plan."
                )
                return 1

        if (
            parallel
            and self._destroys(command, args)
            and not bool_flag(args, "auto-approve")
        ):
            error_console.print("Error: Parallel destroy requires -auto-approve.")
            return 1

        if parallel and command in {"console", "login"}:
            error_console.print(
                f"Error: Terraform {command} is interactive and cannot run in parallel."
            )
            return 1

        code = self.execute_for_environments(
            env_names, command, args, parallel, global_args
        )
        if plan_out and self._plan_succeeded(code, args):
            self._record_plan(os.path.join(working_dir, plan_out), env_names[0])
        return code

    def prepare_execution(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: List[str],
        global_args: List[str],
    ) -> bool:
        """Require a Toffee confirmation before changing protected targets."""
        working_dir = working_directory(global_args)

        if command_name == "init":
            return self._backends_are_filled_in(env_names, extra_args)

        if command_name == "plan":
            plan_out = flag_value(extra_args, "out")
            if plan_out:
                try:
                    plans.remove_record(os.path.join(working_dir, plan_out))
                except OSError as e:
                    error_console.print(f"Error: Cannot replace plan record: {e}")
                    return False
            return True

        if not self._changes_state(command_name, extra_args):
            return True

        notes = []
        if command_name == "apply":
            saved_plan = saved_plan_path(extra_args, working_dir)
            if saved_plan:
                verified, problem = self._verify_saved_plan(saved_plan, env_names[0])
                if not verified and problem is None:
                    return False
                if problem and self._project_has_protected_environment():
                    notes.append(
                        "The origin of saved plan "
                        f"{printable(self.display_path(saved_plan))} cannot be "
                        f"verified: {printable(problem)}. Toffee cannot tell which "
                        "environment it was created for. A saved plan changes the "
                        "state it was planned against, which may belong to a "
                        "protected environment."
                    )

        if notes or any(self.is_protected(name) for name in env_names):
            return self._confirm_protected(
                env_names, command_name, extra_args, working_dir, notes
            )
        if self._destroys(command_name, extra_args) and not bool_flag(
            extra_args, "auto-approve"
        ):
            return self._confirm_destroy(env_names, extra_args)
        return True

    def _backends_are_filled_in(self, env_names: List[str], args: List[str]) -> bool:
        """Stop init while a target's .tfbackend still holds the placeholder."""
        if bool_flag(args, "backend") is False:
            return True
        supplied = set()
        index = 0
        while index < len(args):
            flag = split_flag(args[index])
            if flag and flag[0] == "backend-config":
                value = flag[1]
                if value is None and index + 1 < len(args):
                    index += 1
                    value = args[index]
                key, separator, _ = (value or "").partition("=")
                if not separator:
                    # A supplemental file may set any of the missing values.
                    return True
                supplied.add(key.strip())
            index += 1

        filled_in = True
        for name in env_names:
            backend_file = self.env_manager.get_environment(name).backend_file
            try:
                keys = placeholder_keys(read_settings(backend_file))
            except BackendError:
                continue
            keys = [key for key in keys if key not in supplied]
            if keys:
                error_console.print(
                    f"Error: Replace {PLACEHOLDER} in "
                    f"{printable(self.display_path(backend_file))} "
                    f"({', '.join(keys)}) before running: toffee {name} init",
                    markup=False,
                    highlight=False,
                )
                filled_in = False
        return filled_in

    def _confirm_protected(
        self,
        env_names: List[str],
        command_name: str,
        extra_args: List[str],
        working_dir: str,
        notes: List[str],
    ) -> bool:
        targets = ", ".join(
            f"[bold red]{name.upper()}[/]" if self.is_protected(name) else name
            for name in env_names
        )
        action = self._describe_action(command_name, extra_args)
        error_console.print(f"\n[bold yellow]⚠ You are about to {action} {targets}.[/]")
        for note in notes:
            error_console.print(note, markup=False, highlight=False)
        for name in env_names:
            env = self.env_manager.get_environment(name)
            error_console.print(f"\nEnvironment: {name}", markup=False)
            error_console.print(
                "Backend: ",
                describe_backend(working_dir, env.backend_file),
                sep="",
                markup=False,
                highlight=False,
            )

        # This is deliberately independent of Terraform's -auto-approve flag.
        if not self._ask("\nContinue?"):
            error_console.print("Operation aborted.")
            return False
        return True

    def _confirm_destroy(self, env_names: List[str], extra_args: List[str]) -> bool:
        error_console.print(
            "[bold red]WARNING:[/] This will destroy resources in: "
            f"{', '.join(env_names)}."
        )
        if not self._ask("Do you want to continue?"):
            error_console.print("Operation aborted.")
            return False
        extra_args.insert(0, "-auto-approve")
        return True

    def _verify_saved_plan(
        self, plan_path: str, env_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Return (True, None) if verified, (False, reason) if the origin is
        unknown, or (False, None) after printing why the plan is refused."""
        name = printable(self.display_path(plan_path))
        try:
            record = plans.read_record(plan_path)
            if record is None:
                return False, "it has no Toffee record"
            problem = plans.signature_problem(record)
            if problem:
                return False, problem
            digest = plans.file_digest(plan_path)
        except (OSError, plans.PlanRecordError) as e:
            error_console.print(
                f"Error: Cannot verify saved plan {name}: {e}",
                markup=False,
                highlight=False,
            )
            return False, None

        if record.environment != env_name:
            error_console.print(
                f"Error: Saved plan {name} was created for environment "
                f"'{printable(record.environment)}', not '{env_name}'. A saved plan "
                "changes the state it was planned against.",
                markup=False,
                highlight=False,
            )
            return False, None
        if digest != record.sha256:
            error_console.print(
                f"Error: Saved plan {name} changed after Toffee recorded it for "
                f"'{env_name}'. Re-create it with: toffee {env_name} plan -out=<file>",
                markup=False,
                highlight=False,
            )
            return False, None
        return True, None

    def _record_plan(self, plan_path: str, env_name: str) -> None:
        if not plans.is_plan_file(plan_path):
            return
        try:
            plans.write_record(plan_path, env_name)
        except (OSError, plans.SigningKeyError) as e:
            error_console.print(
                f"Warning: Could not record the plan's environment ({e}). "
                "Applying it will require confirmation if the project has a "
                "protected environment.",
                markup=False,
                highlight=False,
            )

    def _project_has_protected_environment(self) -> bool:
        return any(
            self.is_protected(name) for name in self.env_manager.get_environment_names()
        )

    @staticmethod
    def _plan_succeeded(code: int, args: List[str]) -> bool:
        return code == 0 or (code == 2 and bool(bool_flag(args, "detailed-exitcode")))

    @staticmethod
    def _ask(question: str) -> bool:
        try:
            return click.confirm(question, default=False, err=True)
        except click.Abort:
            return False

    @staticmethod
    def _destroys(command_name: str, args: List[str]) -> bool:
        return command_name == "destroy" or (
            command_name == "apply" and bool(bool_flag(args, "destroy"))
        )

    @staticmethod
    def _changes_state(command_name: str, args: List[str]) -> bool:
        if command_name in STATE_CHANGING_COMMANDS:
            return True
        subcommands = STATE_CHANGING_SUBCOMMANDS.get(command_name)
        return bool(subcommands and args and args[0] in subcommands)

    def _describe_action(self, command_name: str, args: List[str]) -> str:
        if self._destroys(command_name, args):
            return "destroy resources in"
        if command_name == "apply":
            return "apply changes to"
        if command_name in STATE_CHANGING_SUBCOMMANDS:
            return f"run 'terraform {command_name} {args[0]}' against"
        return f"run 'terraform {command_name}' against"
