"""
Environment management for the Toffee CLI tool
"""

import glob
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ENV_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
RESERVED_ENV_NAMES = frozenset({"config", "env", "info"})


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
        self.vars_dir = os.path.abspath(vars_dir)
        self._environments: Dict[str, Environment] = {}
        self.refresh_environments()

    def refresh_environments(self) -> None:
        """Discover available environments from the vars directory"""
        self._environments.clear()
        self._discover_environments()

    def _discover_environments(self) -> None:
        """Discover available environments from the vars directory"""
        if not os.path.isdir(self.vars_dir):
            return

        vars_dir_real = os.path.realpath(self.vars_dir)

        tfvars_files = glob.glob(os.path.join(self.vars_dir, "*.tfvars"))
        for vars_file in tfvars_files:
            env_name = Path(vars_file).stem
            if not self._is_safe_env_path(env_name, vars_dir_real):
                continue

            backend_file = os.path.join(self.vars_dir, f"{env_name}.tfbackend")
            self._environments[env_name] = Environment(
                name=env_name, vars_file=vars_file, backend_file=backend_file
            )

        backend_files = glob.glob(os.path.join(self.vars_dir, "*.tfbackend"))
        for backend_file in backend_files:
            env_name = Path(backend_file).stem
            if not self._is_safe_env_path(env_name, vars_dir_real):
                continue

            if env_name not in self._environments:
                vars_file = os.path.join(self.vars_dir, f"{env_name}.tfvars")
                self._environments[env_name] = Environment(
                    name=env_name, vars_file=vars_file, backend_file=backend_file
                )

    def _is_safe_env_path(self, env_name: str, vars_dir_real: str) -> bool:
        """Ensure resolved env file paths stay directly inside vars_dir."""
        for suffix in (".tfvars", ".tfbackend"):
            candidate = os.path.realpath(
                os.path.join(self.vars_dir, f"{env_name}{suffix}")
            )
            if os.path.dirname(candidate) != vars_dir_real:
                return False
        return True

    @staticmethod
    def validate_env_name(name: str) -> Tuple[bool, Optional[str]]:
        """Validate an environment name before creating or using it."""
        if not name:
            return False, "Environment name cannot be empty"
        if not ENV_NAME_PATTERN.match(name):
            return (
                False,
                "Environment name must start with a letter or digit and contain "
                "only letters, digits, underscores, and hyphens",
            )
        if name in RESERVED_ENV_NAMES:
            return False, f"Environment name '{name}' is reserved by Toffee"
        if ".." in name or "/" in name or "\\" in name:
            return False, f"Invalid environment name: '{name}'"
        return True, None

    def get_environment(self, name: str) -> Optional[Environment]:
        """Get an environment by name"""
        return self._environments.get(name)

    def get_environment_names(self) -> List[str]:
        """Get a list of all available environment names"""
        return sorted(self._environments.keys())

    def validate_environment(
        self,
        name: str,
        require_vars: bool = False,
        require_backend: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that an environment exists and optionally has required files.

        Returns:
            tuple: (is_valid, error_message)
        """
        valid_name, name_error = self.validate_env_name(name)
        if not valid_name:
            return False, name_error

        env = self.get_environment(name)
        if not env:
            available_envs = self.get_environment_names()
            if available_envs:
                return (
                    False,
                    f"Environment '{name}' not found. Available environments: "
                    f"{', '.join(available_envs)}",
                )
            return (
                False,
                f"Environment '{name}' not found. No environments available in "
                f"{self.vars_dir}/",
            )

        if require_vars and not os.path.isfile(env.vars_file):
            return False, f"Missing vars file for '{name}': {env.vars_file}"

        if require_backend and not os.path.isfile(env.backend_file):
            return False, f"Missing backend file for '{name}': {env.backend_file}"

        return True, None

    def suggest_environment(self, name: str) -> Optional[str]:
        """Suggest a correct environment name if user made a typo"""
        if not self._environments:
            return None

        available = self.get_environment_names()

        for env in available:
            if env.startswith(name):
                return env

        for env in available:
            if name in env:
                return env

        best_match = None
        best_score = float("inf")

        for env in available:
            distance = self._levenshtein_distance(name, env)
            if distance < best_score:
                best_score = distance
                best_match = env

        if best_match and best_score <= max(2, len(name) // 2):
            return best_match

        return None

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

    def create_environment_template(self, name: str) -> Tuple[bool, Optional[str]]:
        """
        Create template files for a new environment.

        Returns:
            Tuple of (success, error_message)
        """
        valid_name, name_error = self.validate_env_name(name)
        if not valid_name:
            return False, name_error

        try:
            os.makedirs(self.vars_dir, exist_ok=True)
            vars_dir_real = os.path.realpath(self.vars_dir)

            vars_file = os.path.join(self.vars_dir, f"{name}.tfvars")
            backend_file = os.path.join(self.vars_dir, f"{name}.tfbackend")

            if not self._is_safe_env_path(name, vars_dir_real):
                return False, f"Invalid environment name: '{name}'"

            if not os.path.exists(vars_file):
                with open(vars_file, "w") as f:
                    f.write(f"# Terraform variables for {name} environment\n\n")

            if not os.path.exists(backend_file):
                with open(backend_file, "w") as f:
                    f.write(f"# Backend configuration for {name} environment\n\n")
                    f.write('bucket = "your-terraform-state-bucket"\n')
                    f.write(f'key = "terraform/{name}/terraform.tfstate"\n')
                    f.write('region = "us-east-1"\n')
                    f.write("encrypt = true\n")

            self._environments[name] = Environment(
                name=name, vars_file=vars_file, backend_file=backend_file
            )

            return True, None
        except OSError as e:
            return False, str(e)
