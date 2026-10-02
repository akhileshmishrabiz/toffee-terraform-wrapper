"""
Main CLI entrypoint for the Toffee CLI tool
"""

from typing import Optional

import click
from rich.console import Console

from . import __version__
from .commands.check import CheckCommands, check_help
from .commands.config import ConfigCommands
from .commands.diff import DiffCommands
from .commands.env import EnvCommands
from .commands.info import InfoCommands
from .commands.new import NewCommand
from .commands.terraform import TerraformCommands
from .core.config import ConfigError
from .core.terraform import help_requested

PASSTHROUGH_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}


class EnvironmentFirstGroup(click.Group):
    """Treat every non-Toffee command name as an environment target."""

    def get_command(self, ctx: click.Context, cmd_name: str):
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        return _environment_target_command(cmd_name)

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except ConfigError as e:
            raise click.ClickException(f"Invalid configuration: {e}") from e


console = Console()
error_console = Console(stderr=True)


def get_terraform_commands() -> TerraformCommands:
    return TerraformCommands()


def get_info_commands() -> InfoCommands:
    return InfoCommands()


def get_config_commands() -> ConfigCommands:
    return ConfigCommands()


def get_env_commands() -> EnvCommands:
    return EnvCommands()


def get_diff_commands() -> DiffCommands:
    return DiffCommands()


def get_new_command() -> NewCommand:
    return NewCommand()


def get_check_commands() -> CheckCommands:
    return CheckCommands()


def _environment_target_command(target_spec: str) -> click.Command:
    """Create a passthrough command for an environment target expression."""

    # --help and -h belong to Terraform here, e.g. `toffee dev plan --help`.
    @click.command(
        name=target_spec,
        context_settings=PASSTHROUGH_CONTEXT,
        add_help_option=False,
    )
    @click.argument("terraform_command", required=False)
    @click.argument("terraform_args", nargs=-1, type=click.UNPROCESSED)
    @click.option(
        "--parallel",
        is_flag=True,
        help="Run the Terraform command concurrently for all target environments.",
    )
    def target_command(
        terraform_command: Optional[str],
        terraform_args: tuple,
        parallel: bool,
    ) -> None:
        if terraform_command is None:
            raise click.UsageError(
                f"Missing Terraform command after environment target {target_spec!r}. "
                "Run: toffee <env>[,<env>...] <terraform-command> [args]"
            )
        env_names = list(dict.fromkeys(name.strip() for name in target_spec.split(",")))
        if any(not name for name in env_names):
            raise click.UsageError(
                "Environment targets must be comma-separated names, for example: "
                "toffee dev,prod plan"
            )
        folded = [name.casefold() for name in env_names]
        if len(folded) != len(set(folded)):
            raise click.UsageError(
                "Environment targets must be unique ignoring letter case."
            )

        raw_argv = [terraform_command, *terraform_args]
        # Terraform skips empty arguments when choosing its subcommand, so an
        # unset shell variable could otherwise hide the real command from Toffee.
        if any(not arg.strip() for arg in raw_argv):
            raise click.UsageError(
                "Empty or whitespace-only arguments are not allowed. "
                "Check for unset shell variables."
            )
        command_index = next(
            (index for index, arg in enumerate(raw_argv) if not arg.startswith("-")),
            0,
        )
        global_args = raw_argv[:command_index]
        command = raw_argv[command_index]
        command_args = raw_argv[command_index + 1 :]

        if command == "check":
            if help_requested([*global_args, *command_args]):
                click.echo(check_help())
                raise click.exceptions.Exit(0)
            code = get_check_commands().run(
                env_names,
                command_args,
                parallel=parallel,
                global_args=global_args,
            )
            raise click.exceptions.Exit(code)

        code = get_terraform_commands().run_command(
            env_names,
            command,
            command_args,
            parallel=parallel,
            global_args=global_args,
        )
        raise click.exceptions.Exit(code)

    return target_command


@click.group(
    cls=EnvironmentFirstGroup,
    invoke_without_command=True,
    help=(
        "Environment-first Terraform wrapper.\n\n"
        "Run: toffee <env>[,<env>...] <terraform-command> [args]"
    ),
)
@click.version_option(
    __version__,
    "--version",
    "-v",
    prog_name="Toffee",
    message="Toffee version %(version)s",
)
@click.pass_context
def app(ctx: click.Context) -> None:
    """Route internal commands or pass an environment-scoped command through."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@app.group("info")
def info_app() -> None:
    """Information commands."""


@app.group("config")
def config_app() -> None:
    """Configuration commands."""


@app.group("env")
def env_app() -> None:
    """Environment management commands."""


@app.command("diff")
@click.argument("source")
@click.argument("target")
@click.option(
    "--show-sensitive",
    is_flag=True,
    help="Show values that are redacted by default.",
)
@click.option(
    "--exit-code",
    is_flag=True,
    help="Exit with status 1 when the environments differ.",
)
def diff_environments(
    source: str,
    target: str,
    show_sensitive: bool,
    exit_code: bool,
) -> None:
    """Compare variable and backend mappings for two environments."""
    raise click.exceptions.Exit(
        get_diff_commands().compare(source, target, show_sensitive, exit_code)
    )


@app.command("new")
@click.argument(
    "directory",
    required=False,
    metavar="[DIRECTORY]",
)
def new_project(directory: Optional[str]) -> None:
    """Create a minimal Terraform project for Toffee.

    \b
    Examples:
      toffee new service
      toffee new

    DIRECTORY defaults to the current directory.
    """
    raise click.exceptions.Exit(get_new_command().run(directory))


@info_app.command("envs")
def list_environments() -> None:
    """List all available environments."""
    raise click.exceptions.Exit(get_info_commands().list_environments())


@info_app.command("commands")
def list_commands() -> None:
    """List commands reported by the installed Terraform binary."""
    raise click.exceptions.Exit(get_info_commands().list_commands())


@info_app.command("env")
@click.argument("env")
def show_env_info(env: str) -> None:
    """Show detailed information about an environment."""
    raise click.exceptions.Exit(get_info_commands().show_env_info(env))


@info_app.command("version")
def show_version() -> None:
    """Show Toffee and Terraform versions."""
    raise click.exceptions.Exit(get_info_commands().show_version())


@config_app.command("show")
def show_config() -> None:
    """Show the current configuration."""
    raise click.exceptions.Exit(get_config_commands().show_config())


@config_app.command("set")
@click.argument("key")
@click.argument("value")
@click.option(
    "--project",
    is_flag=True,
    help="Write to project .toffee.json instead of global config.",
)
def set_config(
    key: str,
    value: str,
    project: bool,
) -> None:
    """Set a configuration value."""
    raise click.exceptions.Exit(get_config_commands().set_config(key, value, project))


@config_app.command("init")
def init_project_config() -> None:
    """Initialize a project configuration file."""
    raise click.exceptions.Exit(get_config_commands().init_project_config())


@env_app.command("create")
@click.argument("name")
def create_environment(
    name: str,
) -> None:
    """Create a new environment with template files."""
    raise click.exceptions.Exit(get_env_commands().create_environment(name))


@env_app.command("copy")
@click.argument("source")
@click.argument("target")
def copy_environment(
    source: str,
    target: str,
) -> None:
    """Copy an existing environment to a new one."""
    raise click.exceptions.Exit(get_env_commands().copy_environment(source, target))


if __name__ == "__main__":
    app()
