"""
Terraform command execution for the Toffee CLI tool
"""

import subprocess
import logging
import os
import re
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass

from .environment import Environment

logger = logging.getLogger(__name__)


@dataclass
class TerraformCommand:
    """Represents a Terraform command configuration"""

    name: str
    description: str
    needs_vars_file: bool = True
    needs_backend_config: bool = False
    default_args: List[str] = None

    def __post_init__(self):
        if self.default_args is None:
            self.default_args = []


class TerraformRunner:
    """Handles the execution of Terraform commands"""

    # Define standard terraform commands
    COMMANDS: Dict[str, TerraformCommand] = {
        "init": TerraformCommand(
            name="init",
            description="Initialize a Terraform working directory",
            needs_vars_file=False,
            needs_backend_config=True,
        ),
        "plan": TerraformCommand(
            name="plan", description="Create an execution plan", needs_vars_file=True
        ),
        "apply": TerraformCommand(
            name="apply",
            description="Apply changes to infrastructure",
            needs_vars_file=True,
        ),
        "destroy": TerraformCommand(
            name="destroy",
            description="Destroy Terraform-managed infrastructure",
            needs_vars_file=True,
        ),
        "refresh": TerraformCommand(
            name="refresh",
            description="Update local state file against real resources",
            needs_vars_file=True,
        ),
        "output": TerraformCommand(
            name="output",
            description="Show output values from your infrastructure",
            needs_vars_file=False,
        ),
        "validate": TerraformCommand(
            name="validate",
            description="Validate the configuration files",
            needs_vars_file=False,
        ),
        "fmt": TerraformCommand(
            name="fmt",
            description="Format the configuration files",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "state": TerraformCommand(
            name="state", 
            description="Advanced state management", 
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "workspace": TerraformCommand(
            name="workspace",
            description="Workspace management",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
        "import": TerraformCommand(
            name="import",
            description="Import existing infrastructure into Terraform",
            needs_vars_file=True,
        ),
        "graph": TerraformCommand(
            name="graph",
            description="Create a visual graph of Terraform resources",
            needs_vars_file=False,
        ),
        "providers": TerraformCommand(
            name="providers",
            description="Show information about providers",
            needs_vars_file=False,
        ),
        "version": TerraformCommand(
            name="version",
            description="Show Terraform version",
            needs_vars_file=False,
            needs_backend_config=False,
        ),
    }

    # Common error patterns to handle specially
    ERROR_PATTERNS = {
        "no_s3_bucket": r"S3 bucket \"(.*?)\" does not exist",
        "no_workspace": r"workspace \"(.*?)\" does not exist",
        "no_terraform_files": r"No Terraform configuration files",
        "locked_state": r"Error: (.*?) is locked",
        "invalid_json": r"Error: Invalid JSON",
        "invalid_module_path": r"Error: Module not found",
    }

    def __init__(self, terraform_path: str = "terraform"):
        self.terraform_path = terraform_path

    def get_command(self, name: str) -> Optional[TerraformCommand]:
        """Get a command by name"""
        return self.COMMANDS.get(name)

    def get_command_names(self) -> List[str]:
        """Get a list of all available command names"""
        return list(self.COMMANDS.keys())

    def build_command(
        self, command_name: str, env: Environment, extra_args: List[str] = None
    ) -> List[str]:
        """
        Build a Terraform command with the appropriate options for the environment

        Args:
            command_name: The name of the Terraform command to run
            env: The environment to run the command in
            extra_args: Additional arguments to pass to the command

        Returns:
            The command as a list of strings
        """
        if extra_args is None:
            extra_args = []

        cmd = [self.terraform_path, command_name]

        # Get command configuration
        command = self.get_command(command_name)
        if command:
            # Add backend config if needed
            if command.needs_backend_config and os.path.exists(env.backend_file):
                cmd.append(f"-backend-config={env.backend_file}")

            # Add var file if needed
            if command.needs_vars_file and os.path.exists(env.vars_file):
                cmd.append(f"-var-file={env.vars_file}")

            # Add default args for this command
            if command.default_args:
                cmd.extend(command.default_args)
        else:
            # For custom/unknown commands, add the var file only if it exists
            if os.path.exists(env.vars_file):
                cmd.append(f"-var-file={env.vars_file}")

        # Add any extra args
        if extra_args:
            cmd.extend(extra_args)

        return cmd

    def run_command(
        self, command_name: str, env: Environment, extra_args: List[str] = None
    ) -> Tuple[int, str, str]:
        """
        Run a Terraform command

        Args:
            command_name: The name of the Terraform command to run
            env: The environment to run the command in
            extra_args: Additional arguments to pass to the command

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = self.build_command(command_name, env, extra_args)

        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,  # Don't raise an exception on non-zero exit
            )
            
            # Analyze the output for known error patterns
            if result.returncode != 0:
                enhanced_stderr = self._enhance_error_output(result.stderr, env)
                return result.returncode, result.stdout, enhanced_stderr
            
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            logger.error(f"Error running command: {e}")
            return 1, "", str(e)
    
    def _enhance_error_output(self, stderr: str, env: Environment) -> str:
        """
        Enhance error output with more helpful information
        
        Args:
            stderr: The original stderr output
            env: The environment
            
        Returns:
            Enhanced error message
        """
        # Check for known error patterns
        for error_name, pattern in self.ERROR_PATTERNS.items():
            match = re.search(pattern, stderr)
            if match:
                if error_name == "no_s3_bucket" and match.group(1):
                    bucket_name = match.group(1)
                    stderr += f"\n\nToffee Tip: The S3 bucket '{bucket_name}' doesn't exist. You may need to:\n"
                    stderr += f"1. Create the bucket: aws s3 mb s3://{bucket_name}\n"
                    stderr += f"2. Enable versioning: aws s3api put-bucket-versioning --bucket {bucket_name} --versioning-configuration Status=Enabled\n"
                
                elif error_name == "no_workspace" and match.group(1):
                    workspace = match.group(1)
                    stderr += f"\n\nToffee Tip: The workspace '{workspace}' doesn't exist. You may need to create it:\n"
                    stderr += f"toffee run {env.name} workspace new {workspace}\n"
                
                elif error_name == "no_terraform_files":
                    stderr += "\n\nToffee Tip: No Terraform configuration files found. Make sure you're in the right directory."
                
                elif error_name == "locked_state" and match.group(1):
                    state_file = match.group(1)
                    stderr += "\n\nToffee Tip: The state file is locked. This usually happens when:\n"
                    stderr += "1. Another Terraform operation is in progress\n"
                    stderr += "2. A previous operation ended abnormally\n"
                    stderr += f"\nYou can force-unlock with: toffee run {env.name} force-unlock [LOCK_ID]\n"
                
                elif error_name == "invalid_json":
                    stderr += "\n\nToffee Tip: There's an issue with your JSON formatting. Check your variable files or module inputs."
                
                elif error_name == "invalid_module_path":
                    stderr += "\n\nToffee Tip: Module not found. Make sure module paths are correct and run 'toffee init' if you've added new modules."
                
                break
                
        return stderr