"""
Configuration management for the Toffee CLI tool
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG = {
    "vars_dir": "vars",
    "terraform_path": "terraform",
    "verbose": False,
    "auto_approve": False,
    "protected_environments": [],
}

PROJECT_CONFIG_NAME = ".toffee.json"
TERRAFORM_PATH_VARIABLE = "TOFFEE_TERRAFORM_PATH"
PROJECT_TERRAFORM_NAMES = ("terraform", "tofu", "opentofu")
_PROJECT_TERRAFORM_NAME = re.compile(
    "(?:" + "|".join(PROJECT_TERRAFORM_NAMES) + r")(?:-?[0-9]+(?:\.[0-9]+)*)?"
)


class ConfigError(ValueError):
    """Raised when configuration is invalid and guessing would be unsafe."""


def validate_value(key: str, value: Any) -> Optional[str]:
    """Return why a value is invalid for a known setting, or None."""
    default = DEFAULT_CONFIG.get(key)
    if isinstance(default, bool):
        if not isinstance(value, bool):
            return f"{key} must be true or false"
    elif isinstance(default, list):
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            return f"{key} must be a list of environment names"
    elif isinstance(default, str):
        if not isinstance(value, str) or not value.strip():
            return f"{key} must be a non-empty string"
    return None


def is_project_terraform_name(value: str) -> bool:
    """Return whether a project may choose this Terraform executable.

    Any other name could be an interpreter such as ``sh`` that runs a file
    from the repository in place of Terraform.
    """
    return _PROJECT_TERRAFORM_NAME.fullmatch(value) is not None


def untrusted_terraform_path_error(value: str) -> str:
    return (
        f"{PROJECT_CONFIG_NAME} sets terraform_path to {value!r}. A project can "
        f"only choose {', '.join(PROJECT_TERRAFORM_NAMES)}, optionally with a "
        "version suffix such as terraform1.9, looked up on PATH. Set any other "
        "executable or path in ~/.toffee/config.json or the "
        f"{TERRAFORM_PATH_VARIABLE} environment variable."
    )


def read_config_file(path: str) -> Dict[str, Any]:
    """Read and validate a configuration file; a missing file is empty."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            values = json.load(config_file)
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON ({e}); fix or remove it") from e
    if not isinstance(values, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    for key, value in values.items():
        problem = validate_value(key, value)
        if problem:
            raise ConfigError(f"{path}: {problem}")
    return values


def write_config_file(path: str, values: Dict[str, Any]) -> None:
    """Replace a configuration file atomically; raises ConfigError on failure."""
    directory = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(directory, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as config_file:
                json.dump(values, config_file, indent=2)
                config_file.write("\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    except OSError as e:
        raise ConfigError(f"cannot write {path}: {e}") from e


class Config:
    """Manages Toffee configuration"""

    def __init__(self):
        self.config_dir = os.path.join(str(Path.home()), ".toffee")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.global_values = read_config_file(self.config_file)
        self.config = {**DEFAULT_CONFIG, **self.global_values}
        self.sources: Dict[str, str] = {}

    def save_config(self) -> None:
        """Save explicitly set global values; raises ConfigError on failure."""
        write_config_file(self.config_file, self.global_values)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set and save a global configuration value."""
        problem = validate_value(key, value)
        if problem:
            raise ConfigError(problem)
        self.global_values = {**self.global_values, key: value}
        self.config[key] = value
        self.save_config()

    def get_project_config(self, project_dir: str = None) -> Dict[str, Any]:
        """
        Get project-specific configuration from a .toffee.json file in the project directory

        Args:
            project_dir: Project directory, defaults to current working directory

        Returns:
            Project configuration merged with global configuration
        """
        if project_dir is None:
            project_dir = os.getcwd()

        project_config = read_config_file(os.path.join(project_dir, PROJECT_CONFIG_NAME))
        terraform_path = project_config.get("terraform_path")
        if terraform_path is not None and not is_project_terraform_name(terraform_path):
            raise ConfigError(untrusted_terraform_path_error(terraform_path))

        merged = {**self.config, **project_config}
        self.sources = {
            key: "Project"
            if key in project_config
            else "Global"
            if key in self.global_values
            else "Default"
            for key in merged
        }

        environment_path = os.environ.get(TERRAFORM_PATH_VARIABLE)
        if environment_path:
            merged["terraform_path"] = environment_path
            self.sources["terraform_path"] = "Environment"

        # A project can add protected names but never remove global ones.
        protected = []
        for names in (
            self.global_values.get("protected_environments", []),
            project_config.get("protected_environments", []),
        ):
            protected.extend(name for name in names if name not in protected)
        merged["protected_environments"] = protected
        return merged
