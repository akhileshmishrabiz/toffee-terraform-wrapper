"""
Tests for the main CLI interface
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from cli import app


@pytest.fixture
def runner():
    """Creates a CLI runner for testing"""
    return CliRunner()


def test_version(runner):
    """Test displaying the version"""
    with patch('cli.__version__', 'test-version'):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Toffee version test-version" in result.output


@patch('cli.get_terraform_commands')
def test_init_command(mock_get_commands, runner):
    """Test the init command"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_cmd.init.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["init", "dev"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.init.assert_called_once_with("dev", None)


@patch('cli.get_terraform_commands')
def test_init_command_missing_env(mock_get_commands, runner):
    """Test init command with missing environment"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_get_commands.return_value = mock_cmd
    
    # Run the command without environment
    result = runner.invoke(app, ["init"])
    
    # Should report an error
    assert result.exit_code == 1
    assert "Error: Environment name is required" in result.output
    mock_cmd.init.assert_not_called()


@patch('cli.get_terraform_commands')
def test_plan_command(mock_get_commands, runner):
    """Test the plan command"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_cmd.plan.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["plan", "dev"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.plan.assert_called_once_with("dev", None)


@patch('cli.get_terraform_commands')
def test_apply_command(mock_get_commands, runner):
    """Test the apply command"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_cmd.apply.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["apply", "dev"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.apply.assert_called_once_with("dev", None)


@patch('cli.get_terraform_commands')
def test_apply_command_with_args(mock_get_commands, runner):
    """Test the apply command with extra arguments"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_cmd.apply.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command with extra args
    result = runner.invoke(app, ["apply", "dev", "-auto-approve"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.apply.assert_called_once_with("dev", ["-auto-approve"])


@patch('cli.get_terraform_commands')
def test_destroy_command(mock_get_commands, runner):
    """Test the destroy command"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_cmd.destroy.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["destroy", "dev"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.destroy.assert_called_once_with("dev", None)


@patch('cli.get_terraform_commands')
def test_run_command(mock_get_commands, runner):
    """Test the run command for custom terraform commands"""
    # Mock the terraform commands
    mock_cmd = MagicMock()
    mock_cmd.run_command.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["run", "dev", "state", "list"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.run_command.assert_called_once_with("dev", "state", ["list"])


@patch('cli.get_info_commands')
def test_list_environments_command(mock_get_commands, runner):
    """Test the list environments command"""
    # Mock the info commands
    mock_cmd = MagicMock()
    mock_cmd.list_environments.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["info", "envs"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.list_environments.assert_called_once()


@patch('cli.get_info_commands')
def test_show_env_info_command(mock_get_commands, runner):
    """Test the show environment info command"""
    # Mock the info commands
    mock_cmd = MagicMock()
    mock_cmd.show_env_info.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["info", "env", "dev"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.show_env_info.assert_called_once_with("dev")


@patch('cli.get_config_commands')
def test_show_config_command(mock_get_commands, runner):
    """Test the show config command"""
    # Mock the config commands
    mock_cmd = MagicMock()
    mock_cmd.show_config.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["config", "show"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.show_config.assert_called_once()


@patch('cli.get_config_commands')
def test_set_config_command(mock_get_commands, runner):
    """Test the set config command"""
    # Mock the config commands
    mock_cmd = MagicMock()
    mock_cmd.set_config.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["config", "set", "terraform_path", "/custom/terraform"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.set_config.assert_called_once_with("terraform_path", "/custom/terraform")


@patch('cli.get_config_commands')
def test_init_project_config_command(mock_get_commands, runner):
    """Test the init project config command"""
    # Mock the config commands
    mock_cmd = MagicMock()
    mock_cmd.init_project_config.return_value = 0
    mock_get_commands.return_value = mock_cmd
    
    # Run the command
    result = runner.invoke(app, ["config", "init"])
    
    # Check that it ran correctly
    assert result.exit_code == 0
    mock_cmd.init_project_config.assert_called_once()