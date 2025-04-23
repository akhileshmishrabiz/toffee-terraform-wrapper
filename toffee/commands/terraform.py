"""
Terraform command handlers for the Toffee CLI tool
"""

import typer
from typing import List, Optional
from rich.console import Console

from .base import BaseCommand

console = Console()


class TerraformCommands(BaseCommand):
    """Handles Terraform-related commands in the Toffee CLI tool"""
    
    def init(self, env_name: str, extra_args: List[str] = None) -> int:
        """Initialize Terraform in the specified environment"""
        console.print(f"[bold blue]Initializing Terraform for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "init", extra_args)
    
    def plan(self, env_name: str, extra_args: List[str] = None) -> int:
        """Create a Terraform execution plan for the specified environment"""
        console.print(f"[bold blue]Planning Terraform changes for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "plan", extra_args)
    
    def apply(self, env_name: str, extra_args: List[str] = None) -> int:
        """Apply Terraform changes for the specified environment"""
        # Check if auto-approve is in project config but not in extra_args
        auto_approve = self.project_config.get("auto_approve", False)
        
        if auto_approve and extra_args and "-auto-approve" not in extra_args:
            if extra_args is None:
                extra_args = []
            extra_args.append("-auto-approve")
            
        console.print(f"[bold blue]Applying Terraform changes for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "apply", extra_args)
    
    def destroy(self, env_name: str, extra_args: List[str] = None) -> int:
        """Destroy Terraform resources for the specified environment"""
        console.print(f"[bold blue]Destroying Terraform resources for environment:[/] [cyan]{env_name}[/]")
        
        # Add warning for destructive action
        console.print("[bold red]WARNING:[/] This will destroy all resources. This action cannot be undone.")
        
        # Add confirmation if -auto-approve is not present
        if not extra_args or "-auto-approve" not in extra_args:
            if not typer.confirm("Do you want to continue?"):
                console.print("Operation aborted.")
                return 0
        
        return self.execute_terraform_command(env_name, "destroy", extra_args)
    
    def output(self, env_name: str, extra_args: List[str] = None) -> int:
        """Show Terraform outputs for the specified environment"""
        console.print(f"[bold blue]Showing Terraform outputs for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "output", extra_args)
        
    def refresh(self, env_name: str, extra_args: List[str] = None) -> int:
        """Refresh Terraform state for the specified environment"""
        console.print(f"[bold blue]Refreshing Terraform state for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "refresh", extra_args)
        
    def validate(self, env_name: str, extra_args: List[str] = None) -> int:
        """Validate Terraform configuration for the specified environment"""
        console.print(f"[bold blue]Validating Terraform configuration for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "validate", extra_args)
        
    def fmt(self, env_name: str, extra_args: List[str] = None) -> int:
        """Format Terraform files"""
        console.print(f"[bold blue]Formatting Terraform files for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, "fmt", extra_args)
        
    def run_command(self, env_name: str, command: str, extra_args: List[str] = None) -> int:
        """Run a custom Terraform command for the specified environment"""
        console.print(f"[bold blue]Running Terraform command [cyan]{command}[/] for environment:[/] [cyan]{env_name}[/]")
        return self.execute_terraform_command(env_name, command, extra_args)