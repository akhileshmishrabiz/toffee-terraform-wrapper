"""
Environment management for the Toffee CLI tool
"""

import os
import glob
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from pathlib import Path


@dataclass
class Environment:
    """Represents a Terraform environment"""

    name: str
    vars_file: str
    backend_file: str

    @property
    def is_valid(self) -> bool:
        """Check if the environment has valid files"""
        return os.path.isfile(self.vars_file) and os.path.isfile(self.backend_file)
        
    @property
    def is_partially_valid(self) -> bool:
        """Check if at least the vars file exists"""
        return os.path.isfile(self.vars_file)
        
    def get_missing_files(self) -> List[str]:
        """Get a list of missing files"""
        missing = []
        if not os.path.isfile(self.vars_file):
            missing.append(self.vars_file)
        if not os.path.isfile(self.backend_file):
            missing.append(self.backend_file)
        return missing


class EnvironmentManager:
    """Manages discovery and validation of Terraform environments"""

    def __init__(self, vars_dir: str = "vars"):
        self.vars_dir = vars_dir
        self._environments: Dict[str, Environment] = {}
        self._create_vars_dir_if_needed()
        self._discover_environments()

    def _create_vars_dir_if_needed(self) -> None:
        """Create vars directory if it doesn't exist"""
        if not os.path.isdir(self.vars_dir):
            try:
                os.makedirs(self.vars_dir, exist_ok=True)
            except Exception:
                # If we can't create it, just continue
                pass

    def _discover_environments(self) -> None:
        """Discover available environments from the vars directory"""
        if not os.path.isdir(self.vars_dir):
            return

        # Find all .tfvars files
        tfvars_files = glob.glob(os.path.join(self.vars_dir, "*.tfvars"))

        for vars_file in tfvars_files:
            # Extract environment name from filename (remove path and extension)
            env_name = Path(vars_file).stem

            # Corresponding backend file
            backend_file = os.path.join(self.vars_dir, f"{env_name}.tfbackend")

            # Create environment object
            self._environments[env_name] = Environment(
                name=env_name, vars_file=vars_file, backend_file=backend_file
            )
            
        # Also check for backend files without corresponding vars files
        backend_files = glob.glob(os.path.join(self.vars_dir, "*.tfbackend"))
        
        for backend_file in backend_files:
            env_name = Path(backend_file).stem
            if env_name not in self._environments:
                # Create environment with a vars file that may not exist
                vars_file = os.path.join(self.vars_dir, f"{env_name}.tfvars")
                self._environments[env_name] = Environment(
                    name=env_name, vars_file=vars_file, backend_file=backend_file
                )

    def get_environment(self, name: str) -> Optional[Environment]:
        """Get an environment by name"""
        return self._environments.get(name)

    def get_environment_names(self) -> List[str]:
        """Get a list of all available environment names"""
        return sorted(list(self._environments.keys()))

    def validate_environment(self, name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that an environment exists and has all required files

        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if the environment exists
        env = self.get_environment(name)
        if not env:
            # Create the environment on the fly for commands that might not need vars files
            vars_file = os.path.join(self.vars_dir, f"{name}.tfvars")
            backend_file = os.path.join(self.vars_dir, f"{name}.tfbackend")
            
            # Check if either file exists
            if os.path.isfile(vars_file) or os.path.isfile(backend_file):
                self._environments[name] = Environment(
                    name=name, vars_file=vars_file, backend_file=backend_file
                )
                env = self._environments[name]
            else:
                available_envs = self.get_environment_names()
                if available_envs:
                    return (
                        False,
                        f"Environment '{name}' not found. Available environments: {', '.join(available_envs)}",
                    )
                else:
                    return (
                        False,
                        f"Environment '{name}' not found. No environments available in {self.vars_dir}/",
                    )

        # For fmt and certain commands, we don't need to validate files
        return True, None

    def suggest_environment(self, name: str) -> Optional[str]:
        """Suggest a correct environment name if user made a typo"""
        if not self._environments:
            return None

        # Get the available environment names
        available = self.get_environment_names()

        # Exact prefix match
        for env in available:
            if env.startswith(name):
                return env

        # Contains match
        for env in available:
            if name in env:
                return env
                
        # Try Levenshtein distance for better suggestions
        # Simple implementation - could be replaced with a proper library
        best_match = None
        best_score = float('inf')
        
        for env in available:
            distance = self._levenshtein_distance(name, env)
            if distance < best_score:
                best_score = distance
                best_match = env
                
        # Only suggest if reasonably close
        if best_score <= len(name) / 2:
            return best_match

        # Return the first available as fallback if nothing matches
        return available[0] if available else None
        
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Simple Levenshtein distance implementation"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1 
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
            
        return previous_row[-1]

    def create_environment_template(self, name: str) -> bool:
        """
        Create template files for a new environment
        
        Args:
            name: Name for the new environment
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Make sure the vars directory exists
            os.makedirs(self.vars_dir, exist_ok=True)
            
            # Create vars file
            vars_file = os.path.join(self.vars_dir, f"{name}.tfvars")
            if not os.path.exists(vars_file):
                with open(vars_file, "w") as f:
                    f.write(f"# Terraform variables for {name} environment\n\n")
                    
            # Create backend file
            backend_file = os.path.join(self.vars_dir, f"{name}.tfbackend")
            if not os.path.exists(backend_file):
                with open(backend_file, "w") as f:
                    f.write(f"# Backend configuration for {name} environment\n\n")
                    f.write("bucket = \"your-terraform-state-bucket\"\n")
                    f.write(f"key = \"terraform/{name}/terraform.tfstate\"\n")
                    f.write("region = \"us-east-1\"\n")
                    f.write("encrypt = true\n")
                    
            # Add the environment to our collection
            self._environments[name] = Environment(
                name=name, vars_file=vars_file, backend_file=backend_file
            )
            
            return True
        except Exception as e:
            print(f"Error creating environment: {e}")
            return False