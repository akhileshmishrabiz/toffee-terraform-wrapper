"""
Tests for the command modules of Toffee
"""

import os
from unittest.mock import patch

# Import command modules
from commands.base import BaseCommand
from commands.terraform import TerraformCommands
from commands.info import InfoCommands
from commands.config import ConfigCommands


# -------- Base Command Tests --------

def test_base_command_initialization(temp_terraform_project, temp_config_dir):
    """Test initializing the BaseCommand class"""
    cmd = BaseCommand()
    
    # Check that dependencies are initialized
    assert cmd.config is not None
    assert cmd.env_manager is not None
    assert cmd.terraform is not None


def test_validate_environment_valid(temp_terraform_project, monkeypatch):
    """Test validating a valid environment"""
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    cmd = BaseCommand()
    assert cmd.validate_environment("dev") is True


def test_validate_environment_invalid(temp_terraform_project, monkeypatch):
    """Test validating an invalid environment"""
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    with patch('commands.base.error_console') as mock_console:
        cmd = BaseCommand()
        assert cmd.validate_environment("nonexistent") is False
        
        # Check that an error message was displayed
        mock_console.print.assert_called()
        args, _ = mock_console.print.call_args
        assert "Error:" in args[0]
        assert "not found" in args[0]


@patch('core.terraform.TerraformRunner.run_command')
def test_execute_terraform_command(mock_run_command, temp_terraform_project, monkeypatch):
    """Test executing a Terraform command"""
    # Mock the run_command method to return success
    mock_run_command.return_value = (0, "Terraform output", "")
    
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    cmd = BaseCommand()
    exit_code = cmd.execute_terraform_command("dev", "plan")
    
    # Check that the command was run
    mock_run_command.assert_called_once()
    args, _ = mock_run_command.call_args
    assert args[0] == "plan"
    assert args[1].name == "dev"
    
    # Check return value
    assert exit_code ==.0


# -------- Terraform Commands Tests --------

@patch('commands.terraform.BaseCommand.execute_terraform_command')
def test_terraform_init_command(mock_execute, temp_terraform_project, monkeypatch):
    """Test the init command"""
    # Mock the execute_terraform_command method to return success
    mock_execute.return_value = 0
    
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    cmd = TerraformCommands()
    exit_code = cmd.init("dev")
    
    # Check that the command was executed
    mock_execute.assert_called_once_with("dev", "init", None)
    
    # Check return value
    assert exit_code == 0


@patch('commands.terraform.BaseCommand.execute_terraform_command')
def test_terraform_plan_command(mock_execute, temp_terraform_project, monkeypatch):
    """Test the plan command"""
    # Mock the execute_terraform_command method to return success
    mock_execute.return_value = 0
    
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    cmd = TerraformCommands()
    exit_code = cmd.plan("dev")
    
    # Check that the command was executed
    mock_execute.assert_called_once_with("dev", "plan", None)
    
    # Check return value
    assert exit_code == 0


@patch('commands.terraform.BaseCommand.execute_terraform_command')
def test_terraform_apply_command(mock_execute, temp_terraform_project, monkeypatch):
    """Test the apply command"""
    # Mock the execute_terraform_command method to return success
    mock_execute.return_value = 0
    
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    cmd = TerraformCommands()
    exit_code = cmd.apply("dev")
    
    # Check that the command was executed
    mock_execute.assert_called_once_with("dev", "apply", None)
    
    # Check return value
    assert exit_code == 0


@patch('commands.terraform.BaseCommand.execute_terraform_command')
def test_terraform_apply_with_auto_approve(mock_execute, temp_terraform_project, monkeypatch):
    """Test the apply command with auto-approve from config"""
    # Mock the execute_terraform_command method to return success
    mock_execute.return_value = 0
    
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    # Create a project config file with auto_approve=True
    os.makedirs(os.path.join(temp_terraform_project["temp_dir"], ".toffee"), exist_ok=True)
    with open(os.path.join(temp_terraform_project["temp_dir"], ".toffee.json"), "w") as f:
        f.write('{"auto_approve": true}')
    
    # Create command with mocked project_config
    cmd = TerraformCommands()
    cmd.project_config = {"auto_approve": True}
    
    exit_code = cmd.apply("dev")
    
    # Check that the command was executed with auto-approve
    mock_execute.assert_called_once()
    args, _ = mock_execute.call_args
    assert args[0] == "dev"
    assert args[1] == "apply"
    assert "-auto-approve" in args[2]
    
    # Check return value
    assert exit_code == 0


# -------- Info Commands Tests --------

@patch('commands.base.BaseCommand.display_environments')
def test_info_list_environments(mock_display, temp_terraform_project, monkeypatch):
    """Test the list_environments command"""
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    cmd = InfoCommands()
    exit_code = cmd.list_environments()
    
    # Check that the display method was called
    mock_display.assert_called_once()
    
    # Check return value
    assert exit_code == 0


@patch('commands.base.BaseCommand.validate_environment')
def test_info_show_env_info(mock_validate, temp_terraform_project, monkeypatch):
    """Test the show_env_info command"""
    # Mock the validate_environment method to return success
    mock_validate.return_value = True
    
    # Create a mock environment
    from core.environment import Environment
    mock_env = Environment(
        name="dev",
        vars_file=os.path.join(temp_terraform_project["vars_dir"], "dev.tfvars"),
        backend_file=os.path.join(temp_terraform_project["vars_dir"], "dev.tfbackend")
    )
    
    # Change to the temp project directory
    monkeypatch.chdir(temp_terraform_project["temp_dir"])
    
    with patch('commands.info.InfoCommands.env_manager.get_environment', return_value=mock_env):
        with patch('commands.info.console'):
            cmd = InfoCommands()
            exit_code = cmd.show_env_info("dev")
            
            # Check that validate was called
            mock_validate.assert_called_once_with("dev")
            
            # Check return value
            assert exit_code == 0


# -------- Config Commands Tests --------

@patch('commands.config.console')
def test_config_show_config(mock_console, temp_config_dir):
    """Test the show_config command"""
    cmd = ConfigCommands()
    exit_code = cmd.show_config()
    
    # Check that a table was printed
    mock_console.print.assert_called_once()
    
    # Check return value
    assert exit_code == 0


@patch('core.config.Config.set')
def test_config_set_config(mock_set, temp_config_dir):
    """Test the set_config command"""
    cmd = ConfigCommands()
    exit_code = cmd.set_config("terraform_path", "/custom/terraform")
    
    # Check that the config value was set
    mock_set.assert_called_once_with("terraform_path", "/custom/terraform")
    
    # Check return value
    assert exit_code == 0


def test_config_set_config_invalid_key(temp_config_dir):
    """Test the set_config command with an invalid key"""
    with patch('commands.config.console') as mock_console:
        cmd = ConfigCommands()
        exit_code = cmd.set_config("invalid_key", "value")
        
        # Check that an error was displayed
        mock_console.print.assert_called()
        args, _ = mock_console.print.call_args
        assert "Error:" in args[0]
        assert "Unknown configuration key" in args[0]
        
        # Check return value
        assert exit_code == 1