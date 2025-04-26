"""
Main CLI entrypoint for the Toffee CLI tool
"""

import typer
from typing import List, Optional
from rich.console import Console

from .commands.terraform import TerraformCommands
from .commands.info import InfoCommands
from .commands.config import ConfigCommands
from .commands.env import EnvCommands  # Import EnvCommands

app = typer.Typer(
    name="toffee",
    help="A modern CLI tool for deploying Terraform across multiple environments",
    add_completion=False,
)

info_app = typer.Typer(help="Information commands")
config_app = typer.Typer(help="Configuration commands")
env_app = typer.Typer(help="Environment management commands")  # Create env subcommand

app.add_typer(info_app, name="info")
app.add_typer(config_app, name="config")
app.add_typer(env_app, name="env")  # Add env subcommand to main app

console = Console()
error_console = Console(stderr=True)


def get_terraform_commands() -> TerraformCommands:
    """Get the Terraform commands handler"""
    return TerraformCommands()


def get_info_commands() -> InfoCommands:
    """Get the information commands handler"""
    return InfoCommands()


def get_config_commands() -> ConfigCommands:
    """Get the configuration commands handler"""
    return ConfigCommands()


def get_env_commands() -> EnvCommands:
    """Get the environment commands handler"""
    return EnvCommands()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit"
    ),
):
    """
    Toffee - A modern CLI tool for deploying Terraform across multiple environments
    """
    if version:
        from . import __version__

        console.print(f"Toffee version {__version__}")
        raise typer.Exit()


@app.command()
def init(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Initialize Terraform in the specified environment"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee init [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.init(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def plan(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Create a Terraform execution plan for the specified environment"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee plan [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.plan(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def apply(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Apply Terraform changes for the specified environment"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee apply [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.apply(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def destroy(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Destroy Terraform resources for the specified environment"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee destroy [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.destroy(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def output(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Show Terraform outputs for the specified environment"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee output [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.output(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def refresh(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Refresh Terraform state for the specified environment"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee refresh [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.refresh(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def fmt(
    env: Optional[str] = typer.Argument(None, help="Environment name (optional)"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Format Terraform configuration files"""
    cmd = get_terraform_commands()
    exit_code = cmd.fmt(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def validate(
    env: str = typer.Argument(None, help="Environment name"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Validate Terraform configuration files"""
    if not env:
        error_console.print("Error: Environment name is required")
        error_console.print("Usage: toffee validate [ENVIRONMENT]")
        raise typer.Exit(code=1)

    cmd = get_terraform_commands()
    exit_code = cmd.validate(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def state(
    env: Optional[str] = typer.Argument(None, help="Environment name (optional)"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Run state management commands"""
    cmd = get_terraform_commands()
    exit_code = cmd.state(env, args)
    raise typer.Exit(code=exit_code)


@app.command()
def run(
    env: str = typer.Argument(..., help="Environment name"),
    command: str = typer.Argument(..., help="Terraform command to run"),
    args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to Terraform"
    ),
):
    """Run a custom Terraform command for the specified environment"""
    cmd = get_terraform_commands()
    exit_code = cmd.run_command(env, command, args)
    raise typer.Exit(code=exit_code)


@info_app.command("envs")
def list_environments():
    """List all available environments"""
    cmd = get_info_commands()
    exit_code = cmd.list_environments()
    raise typer.Exit(code=exit_code)


@info_app.command("commands")
def list_commands():
    """List all available Terraform commands"""
    cmd = get_info_commands()
    exit_code = cmd.list_commands()
    raise typer.Exit(code=exit_code)


@info_app.command("env")
def show_env_info(
    env: str = typer.Argument(..., help="Environment name"),
):
    """Show detailed information about an environment"""
    cmd = get_info_commands()
    exit_code = cmd.show_env_info(env)
    raise typer.Exit(code=exit_code)


@config_app.command("show")
def show_config():
    """Show the current configuration"""
    cmd = get_config_commands()
    exit_code = cmd.show_config()
    raise typer.Exit(code=exit_code)


@config_app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """Set a global configuration value"""
    cmd = get_config_commands()
    exit_code = cmd.set_config(key, value)
    raise typer.Exit(code=exit_code)


@config_app.command("init")
def init_project_config():
    """Initialize a project configuration file"""
    cmd = get_config_commands()
    exit_code = cmd.init_project_config()
    raise typer.Exit(code=exit_code)


# Add environment commands
@env_app.command("create")
def create_environment(
    name: str = typer.Argument(..., help="Name of the environment to create"),
):
    """Create a new environment with template files"""
    cmd = get_env_commands()
    exit_code = cmd.create_environment(name)
    raise typer.Exit(code=exit_code)


@env_app.command("copy")
def copy_environment(
    source: str = typer.Argument(..., help="Source environment name"),
    target: str = typer.Argument(..., help="Target environment name"),
):
    """Copy an existing environment to a new one"""
    cmd = get_env_commands()
    exit_code = cmd.copy_environment(source, target)
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
