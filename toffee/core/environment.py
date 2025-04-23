"""
Environment management for the Toffee CLI tool
"""

import os
import glob
from dataclasses import dataclass
from typing import List, Optional, Dict
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


class EnvironmentManager:
    """Manages discovery and validation of Terraform environments"""
    
    def __init__(self, vars_dir: str = "vars"):
        self.vars_dir = vars_dir
        self._environments: Dict[str, Environment] = {}
        self._discover_environments()
    
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
                name=env_name,
                vars_file=vars_file,
                backend_file=backend_file
            )
    
    def get_environment(self, name: str) -> Optional[Environment]:
        """Get an environment by name"""
        return self._environments.get(name)
    
    def get_environment_names(self) -> List[str]:
        """Get a list of all available environment names"""
        return list(self._environments.keys())
    
    def validate_environment(self, name: str) -> tuple[bool, Optional[str]]:
        """
        Validate that an environment exists and has all required files
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if the environment exists
        env = self.get_environment(name)
        if not env:
            available_envs = self.get_environment_names()
            if available_envs:
                return False, f"Environment '{name}' not found. Available environments: {', '.join(available_envs)}"
            else:
                return False, f"Environment '{name}' not found. No environments available in {self.vars_dir}/"
        
        # Check if the vars file exists
        if not os.path.isfile(env.vars_file):
            return False, f"Environment file '{env.vars_file}' not found"
        
        # Check if the backend file exists
        if not os.path.isfile(env.backend_file):
            return False, f"Backend config file '{env.backend_file}' not found"
        
        return True, None
    
    def suggest_environment(self, name: str) -> Optional[str]:
        """Suggest a correct environment name if user made a typo"""
        if not self._environments:
            return None
            
        # Very simple suggestion algorithm - find the closest match
        # Could be improved with more sophisticated algorithms like Levenshtein distance
        available = self.get_environment_names()
        
        # Exact prefix match
        for env in available:
            if env.startswith(name):
                return env
        
        # Contains match
        for env in available:
            if name in env:
                return env
                
        # Return the first available as fallback if nothing matches
        return available[0] if available else None