"""
Environment management commands for the Toffee CLI tool
"""

import os
import shutil
from rich.console import Console
from rich.panel import Panel

from .base import BaseCommand

console = Console()
error_console = Console(stderr=True)


class EnvCommands(BaseCommand):
    """Handles environment-related commands in the Toffee CLI tool"""

    def create_environment(self, name: str) -> int:
        """Create a new environment with template files"""
        # Check if environment already exists
        env = self.env_manager.get_environment(name)
        if env and env.is_valid:
            error_console.print(f"[bold yellow]Warning:[/] Environment '{name}' already exists")
            
            # List the existing files
            missing_files = env.get_missing_files()
            if missing_files:
                console.print(f"The following files are missing and will be created:")
                for file in missing_files:
                    console.print(f"  - {file}")
            else:
                return 0
                
        # Create the environment
        success = self.env_manager.create_environment_template(name)
        
        if success:
            console.print(f"[bold green]Success:[/] Created environment '{name}'")
            console.print(f"Files created:")
            
            env = self.env_manager.get_environment(name)
            if env:
                console.print(f"  - {env.vars_file}")
                console.print(f"  - {env.backend_file}")
                
            console.print("")
            console.print(Panel(
                f"[bold]Next steps:[/]\n\n"
                f"1. Edit the vars file: [cyan]{os.path.join(self.env_manager.vars_dir, name + '.tfvars')}[/]\n"
                f"2. Edit the backend config: [cyan]{os.path.join(self.env_manager.vars_dir, name + '.tfbackend')}[/]\n"
                f"3. Initialize Terraform: [cyan]toffee init {name}[/]",
                title="Environment Setup", 
                border_style="green"
            ))
            return 0
        else:
            error_console.print(f"[bold red]Error:[/] Failed to create environment '{name}'")
            return 1

    def copy_environment(self, source: str, target: str) -> int:
        """Copy an existing environment to a new one"""
        # Check if source environment exists
        source_env = self.env_manager.get_environment(source)
        if not source_env:
            error_console.print(f"[bold red]Error:[/] Source environment '{source}' not found")
            return 1
            
        # Check if target environment already exists
        target_env = self.env_manager.get_environment(target)
        if target_env and target_env.is_valid:
            error_console.print(f"[bold yellow]Warning:[/] Target environment '{target}' already exists")
            if not console.input("[bold]Overwrite? (y/n)[/] ").lower().startswith("y"):
                return 0
                
        # Create target vars directory if needed
        os.makedirs(self.env_manager.vars_dir, exist_ok=True)
        
        # Copy files
        try:
            # Define target file paths
            target_vars_file = os.path.join(self.env_manager.vars_dir, f"{target}.tfvars")
            target_backend_file = os.path.join(self.env_manager.vars_dir, f"{target}.tfbackend")
            
            # Copy vars file if it exists
            if os.path.isfile(source_env.vars_file):
                shutil.copy2(source_env.vars_file, target_vars_file)
                
                # Update content to reference new environment
                with open(target_vars_file, 'r') as f:
                    content = f.read()
                
                # Replace occurrences of source name with target name
                content = content.replace(source, target)
                
                with open(target_vars_file, 'w') as f:
                    f.write(content)
            
            # Copy backend file if it exists
            if os.path.isfile(source_env.backend_file):
                shutil.copy2(source_env.backend_file, target_backend_file)
                
                # Update content to reference new environment
                with open(target_backend_file, 'r') as f:
                    content = f.read()
                
                # Replace key in backend config
                content = content.replace(f"/{source}/", f"/{target}/")
                
                with open(target_backend_file, 'w') as f:
                    f.write(content)
                    
            # Refresh environments
            self.env_manager._discover_environments()
            
            console.print(f"[bold green]Success:[/] Copied environment '{source}' to '{target}'")
            console.print(f"Files created:")
            console.print(f"  - {target_vars_file}")
            console.print(f"  - {target_backend_file}")
            
            return 0
        except Exception as e:
            error_console.print(f"[bold red]Error:[/] Failed to copy environment: {e}")
            return 1