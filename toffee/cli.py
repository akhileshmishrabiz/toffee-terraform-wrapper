"""
Main CLI entrypoint for the Toffee CLI tool
"""

from typing import List, Optional

import typer
from rich.console import Console

from .cli_helpers import normalize_envs_and_args
from .commands.config import ConfigCommands
from .commands.env import EnvCommands
from .commands.info import InfoCommands
from .commands.terraform import TerraformCommands

TYper_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}

app = typer.Typer(
    name="toffee",
    help="A thin wrapper for Terraform multi-environment workflows",
    add_completion=False,
)

info_app = typer.Typer(help="Information commands")
config_app = typer.Typer(help="Configuration commands")
env_app = typer.Typer(help="Environment management commands")

app.add_typer(info_app, name="info")
app.add_typer(config_app, name="config")
app.add_typer(env_app, name="env")

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


def terraform_extra_args(ctx: typer.Context) -> List[str]:
    return list(ctx.args)


def run_terraform_command(
    ctx: typer.Context,
    handler,
    envs: Optional[List[str]],
    all_envs: bool,
    parallel: bool,
):
    extra_args = terraform_extra_args(ctx)
    envs, extra_args = normalize_envs_and_args(envs, extra_args)
    return handler(envs or [], extra_args, all_envs, parallel)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit"
    ),
):
    """Toffee - Terraform wrapper for multi-environment deployments."""
    if version:
        from . import __version__

        console.print(f"Toffee version {__version__}")
        raise typer.Exit(0)

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit(0)


@app.command(context_settings=TYper_CONTEXT)
def init(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Initialize Terraform for one or more environments."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.init, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def plan(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Create a Terraform execution plan."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.plan, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def apply(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Apply Terraform changes."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.apply, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def destroy(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Destroy Terraform resources."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.destroy, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def output(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Show Terraform outputs."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.output, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def refresh(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Refresh Terraform state."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.refresh, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def fmt(
    ctx: typer.Context,
    env: Optional[str] = typer.Argument(None, help="Environment name (optional)"),
):
    """Format Terraform configuration files."""
    cmd = get_terraform_commands()
    raise typer.Exit(code=cmd.fmt(env, terraform_extra_args(ctx)))


@app.command(context_settings=TYper_CONTEXT)
def validate(
    ctx: typer.Context,
    envs: Optional[List[str]] = typer.Argument(
        None, help="Environment name(s, optional)"
    ),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Validate Terraform configuration files."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(ctx, cmd.validate, envs, all_envs, parallel)
    )


@app.command(context_settings=TYper_CONTEXT)
def state(
    ctx: typer.Context,
    env: Optional[str] = typer.Argument(
        None, help="Environment name or state subcommand"
    ),
):
    """Run Terraform state management commands."""
    cmd = get_terraform_commands()
    raise typer.Exit(code=cmd.state(env, terraform_extra_args(ctx)))


@app.command(context_settings=TYper_CONTEXT)
def run(
    ctx: typer.Context,
    env: str = typer.Argument(..., help="Environment name"),
    command: str = typer.Argument(..., help="Terraform command to run"),
    all_envs: bool = typer.Option(False, "--all", help="Run for all environments"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run environments in parallel"
    ),
):
    """Run any Terraform command for one or more environments."""
    cmd = get_terraform_commands()
    raise typer.Exit(
        code=run_terraform_command(
            ctx,
            lambda envs, extra_args, use_all, use_parallel: cmd.run_command(
                envs, command, extra_args, use_all, use_parallel
            ),
            [env],
            all_envs,
            parallel,
        )
    )


@info_app.command("envs")
def list_environments():
    """List all available environments."""
    raise typer.Exit(code=get_info_commands().list_environments())


@info_app.command("commands")
def list_commands():
    """List supported Terraform command metadata."""
    raise typer.Exit(code=get_info_commands().list_commands())


@info_app.command("env")
def show_env_info(env: str = typer.Argument(..., help="Environment name")):
    """Show detailed information about an environment."""
    raise typer.Exit(code=get_info_commands().show_env_info(env))


@info_app.command("version")
def show_version():
    """Show Toffee and Terraform versions."""
    raise typer.Exit(code=get_info_commands().show_version())


@config_app.command("show")
def show_config():
    """Show the current configuration."""
    raise typer.Exit(code=get_config_commands().show_config())


@config_app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
    project: bool = typer.Option(
        False, "--project", help="Write to project .toffee.json instead of global config"
    ),
):
    """Set a configuration value."""
    raise typer.Exit(code=get_config_commands().set_config(key, value, project))


@config_app.command("init")
def init_project_config():
    """Initialize a project configuration file."""
    raise typer.Exit(code=get_config_commands().init_project_config())


@env_app.command("create")
def create_environment(
    name: str = typer.Argument(..., help="Name of the environment to create"),
):
    """Create a new environment with template files."""
    raise typer.Exit(code=get_env_commands().create_environment(name))


@env_app.command("copy")
def copy_environment(
    source: str = typer.Argument(..., help="Source environment name"),
    target: str = typer.Argument(..., help="Target environment name"),
):
    """Copy an existing environment to a new one."""
    raise typer.Exit(code=get_env_commands().copy_environment(source, target))


if __name__ == "__main__":
    app()
