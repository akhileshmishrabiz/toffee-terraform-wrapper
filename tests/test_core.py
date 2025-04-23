"""
Tests for the core modules of Toffee
"""

import os
import json
from unittest.mock import patch, MagicMock

# Import core modules
from core.environment import Environment, EnvironmentManager
from core.terraform import TerraformCommand, TerraformRunner
from core.config import Config, DEFAULT_CONFIG


# -------- Environment Tests --------

def test_environment_creation():
    """Test creating an Environment object"""
    env = Environment(name="dev", vars_file="vars/dev.tfvars", backend_file="vars/dev.tfbackend")
    assert env.name == "dev"
    assert env.vars_file == "vars/dev.tfvars"
    assert env.backend_file == "vars/dev.tfbackend"


def test_environment_is_valid(temp_terraform_project):
    """Test the is_valid property of Environment"""
    # Valid environment
    env = Environment(name="dev", 
                      vars_file=os.path.join(temp_terraform_project["vars_dir"], "dev.tfvars"),
                      backend_file=os.path.join(temp_terraform_project["vars_dir"], "dev.tfbackend"))
    assert env.is_valid is True
    
    # Invalid environment (non-existent files)
    env = Environment(name="stage", 
                      vars_file=os.path.join(temp_terraform_project["vars_dir"], "stage.tfvars"),
                      backend_file=os.path.join(temp_terraform_project["vars_dir"], "stage.tfbackend"))
    assert env.is_valid is False


def test_environment_manager_discovery(temp_terraform_project):
    """Test that EnvironmentManager discovers environments correctly"""
    manager = EnvironmentManager(vars_dir=temp_terraform_project["vars_dir"])
    
    # Should discover both dev and prod environments
    env_names = manager.get_environment_names()
    assert "dev" in env_names
    assert "prod" in env_names
    assert len(env_names) == 2
    
    # Get environments and check they're valid
    dev_env = manager.get_environment("dev")
    assert dev_env is not None
    assert dev_env.name == "dev"
    assert dev_env.is_valid is True


def test_environment_validation(temp_terraform_project):
    """Test environment validation"""
    manager = EnvironmentManager(vars_dir=temp_terraform_project["vars_dir"])
    
    # Valid environment
    valid, error = manager.validate_environment("dev")
    assert valid is True
    assert error is None
    
    # Invalid environment
    valid, error = manager.validate_environment("stage")
    assert valid is False
    assert "not found" in error
    assert "Available environments: " in error


def test_environment_suggestion(temp_terraform_project):
    """Test environment name suggestions"""
    manager = EnvironmentManager(vars_dir=temp_terraform_project["vars_dir"])
    
    # Typo in environment name
    suggestion = manager.suggest_environment("de")
    assert suggestion == "dev"
    
    # Another typo
    suggestion = manager.suggest_environment("pro")
    assert suggestion == "prod"


# -------- Terraform Tests --------

def test_terraform_command_creation():
    """Test creating a TerraformCommand object"""
    cmd = TerraformCommand(name="init", description="Initialize terraform", 
                           needs_vars_file=False, needs_backend_config=True)
    assert cmd.name == "init"
    assert cmd.description == "Initialize terraform"
    assert cmd.needs_vars_file is False
    assert cmd.needs_backend_config is True
    assert cmd.default_args == []  # Should initialize empty list


def test_terraform_runner_commands():
    """Test that TerraformRunner has the expected commands"""
    runner = TerraformRunner()
    commands = runner.get_command_names()
    
    # Check that common commands are available
    assert "init" in commands
    assert "plan" in commands
    assert "apply" in commands
    assert "destroy" in commands


def test_build_command():
    """Test building Terraform commands"""
    runner = TerraformRunner()
    env = Environment(name="dev", vars_file="vars/dev.tfvars", backend_file="vars/dev.tfbackend")
    
    # Test init command
    cmd = runner.build_command("init", env)
    assert cmd == ["terraform", "init", "-backend-config=vars/dev.tfbackend"]
    
    # Test plan command
    cmd = runner.build_command("plan", env)
    assert cmd == ["terraform", "plan", "-var-file=vars/dev.tfvars"]
    
    # Test with extra args
    cmd = runner.build_command("apply", env, ["-auto-approve"])
    assert cmd == ["terraform", "apply", "-var-file=vars/dev.tfvars", "-auto-approve"]


@patch('subprocess.run')
def test_run_command(mock_run):
    """Test running a Terraform command"""
    # Mock the subprocess.run function to return success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "Terraform output"
    mock_process.stderr = ""
    mock_run.return_value = mock_process
    
    runner = TerraformRunner()
    env = Environment(name="dev", vars_file="vars/dev.tfvars", backend_file="vars/dev.tfbackend")
    
    # Run a command
    returncode, stdout, stderr = runner.run_command("plan", env)
    
    # Check that subprocess.run was called correctly
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == ["terraform", "plan", "-var-file=vars/dev.tfvars"]
    
    # Check return values
    assert returncode == 0
    assert stdout == "Terraform output"
    assert stderr == ""


# -------- Config Tests --------

def test_config_creation(temp_config_dir):
    """Test creating a Config object"""
    config = Config()
    
    # Check that config directory was created
    assert os.path.exists(temp_config_dir["config_dir"])
    
    # Check that config has default values
    for key, value in DEFAULT_CONFIG.items():
        assert config.get(key) == value


def test_config_save_and_load(temp_config_dir):
    """Test saving and loading config values"""
    # Create and modify config
    config = Config()
    config.set("terraform_path", "/custom/terraform")
    config.set("default_environment", "dev")
    
    # Create a new config instance that should load the saved values
    config2 = Config()
    assert config2.get("terraform_path") == "/custom/terraform"
    assert config2.get("default_environment") == "dev"


def test_project_config(temp_terraform_project, temp_config_dir):
    """Test loading project-specific config"""
    # Create a global config
    config = Config()
    config.set("terraform_path", "/global/terraform")
    
    # Create a project config file
    project_config = {
        "terraform_path": "/project/terraform",
        "auto_approve": True
    }
    
    with open(os.path.join(temp_terraform_project["temp_dir"], ".toffee.json"), "w") as f:
        json.dump(project_config, f)
    
    # Get project config
    project_config = config.get_project_config(temp_terraform_project["temp_dir"])
    
    # Project config should override global config
    assert project_config["terraform_path"] == "/project/terraform"
    assert project_config["auto_approve"] is True