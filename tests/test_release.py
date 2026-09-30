"""Release metadata, documentation, and CLI surface drift checks."""

from pathlib import Path

import pytest

from toffee import __version__

ROOT = Path(__file__).parents[1]


def test_release_version_is_single_sourced_and_documented(invoke):
    pyproject = (ROOT / "pyproject.toml").read_text()
    readme = (ROOT / "README.md").read_text()
    result = invoke("--version")

    assert __version__ == "1.0.0"
    assert result.exit_code == 0
    assert result.stdout.strip() == "Toffee version 1.0.0"
    assert 'version = {attr = "toffee.__version__"}' in pyproject
    assert "Version 1.0.0 is the first GA-quality release" in readme


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
        "toffee new demo --provider none --backend local --envs dev,prod",
        "toffee dev init",
        "toffee dev validate",
        "toffee dev plan",
        "toffee dev apply",
        "_TOFFEE_COMPLETE=bash_source toffee",
        "_TOFFEE_COMPLETE=zsh_source toffee",
        "_TOFFEE_COMPLETE=fish_source toffee",
    ):
        assert command in readme

    assert "pip install toffee" not in readme
    assert "[testing guide](TESTING.md)" in readme
