"""Release metadata, documentation, and CLI surface drift checks."""

from pathlib import Path

import pytest

from toffee import __version__

ROOT = Path(__file__).parents[1]


def test_release_version_is_single_sourced_and_documented(invoke):
    pyproject = (ROOT / "pyproject.toml").read_text()
    readme = (ROOT / "README.md").read_text()
    result = invoke("--version")

    assert __version__ == "1.1.0"
    assert result.exit_code == 0
    assert result.stdout.strip() == "Toffee version 1.1.0"
    assert 'version = {attr = "toffee.__version__"}' in pyproject
    assert "The current version is 1.1.0." in readme


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("new",),
        ("diff",),
        ("env",),
        ("env", "create"),
        ("env", "copy"),
        ("info",),
        ("info", "envs"),
        ("info", "commands"),
        ("info", "env"),
        ("info", "version"),
        ("config",),
        ("config", "show"),
        ("config", "set"),
        ("config", "init"),
    ],
)
def test_every_internal_command_has_help(invoke, args):
    result = invoke(*args, "--help")

    assert result.exit_code == 0
    assert result.stdout.startswith("Usage:")
    assert "Options:" in result.stdout
    assert "Traceback" not in result.output


def test_readme_install_and_first_project_commands_match_cli():
    readme = (ROOT / "README.md").read_text()

    for command in (
        "pipx install git+https://github.com/akhileshmishrabiz/"
        "toffee-terraform-wrapper.git",
        "uv tool install git+https://github.com/akhileshmishrabiz/"
        "toffee-terraform-wrapper.git",
        "Python 3.10 or newer",
        "Terraform 1.5 or newer",
        "toffee new service",
        "service/vars/dev.tfbackend",
        "toffee dev init",
        "toffee dev validate",
        "toffee dev check",
        "toffee dev check --checks tflint,checkov",
        "uv tool install checkov",
        "pipx install checkov",
        "toffee dev plan",
        "toffee dev apply",
    ):
        assert command in readme

    assert "pip install toffee" not in readme
    assert "[testing guide](TESTING.md)" in readme
    for removed in (
        "--name",
        "--envs",
        "--provider",
        "--backend",
        "--region",
        "--dry-run",
        "--agents",
        "--template",
    ):
        assert removed not in readme
