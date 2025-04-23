"""
Test fixtures for Toffee tests
"""

import os
import shutil
import tempfile
import pytest
import sys

# Add the project root to the Python path
# This ensures imports work correctly in tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def temp_terraform_project():
    """Creates a temporary Terraform project structure for testing"""
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    vars_dir = os.path.join(temp_dir, "vars")
    os.makedirs(vars_dir, exist_ok=True)
    
    # Create mock env files
    with open(os.path.join(vars_dir, "dev.tfvars"), "w") as f:
        f.write('environment = "dev"')
    
    with open(os.path.join(vars_dir, "dev.tfbackend"), "w") as f:
        f.write('bucket = "tf-state"\nkey = "dev/terraform.tfstate"')
    
    with open(os.path.join(vars_dir, "prod.tfvars"), "w") as f:
        f.write('environment = "prod"')
    
    with open(os.path.join(vars_dir, "prod.tfbackend"), "w") as f:
        f.write('bucket = "tf-state"\nkey = "prod/terraform.tfstate"')
    
    # Create a dummy terraform file
    with open(os.path.join(temp_dir, "main.tf"), "w") as f:
        f.write('# Dummy terraform file')
    
    # Change to the temporary directory for testing
    original_dir = os.getcwd()
    os.chdir(temp_dir)
    
    # Return the fixture data
    yield {
        "temp_dir": temp_dir,
        "vars_dir": vars_dir,
    }
    
    # Cleanup after test
    os.chdir(original_dir)
    shutil.rmtree(temp_dir)

@pytest.fixture
def temp_config_dir():
    """Creates a temporary config directory for testing"""
    # Create a temporary directory for config
    temp_dir = tempfile.mkdtemp()
    
    # Store original HOME to restore it later
    original_home = os.environ.get("HOME")
    
    # Set HOME to our temp directory so config is stored there
    os.environ["HOME"] = temp_dir
    
    # Return the fixture data
    yield {
        "temp_dir": temp_dir,
        "config_dir": os.path.join(temp_dir, ".toffee")
    }
    
    # Restore original HOME
    if original_home:
        os.environ["HOME"] = original_home
    else:
        del os.environ["HOME"]
        
    # Clean up the temporary directory
    shutil.rmtree(temp_dir)