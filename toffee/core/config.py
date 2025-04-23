"""
Configuration management for the Toffee CLI tool
"""

import os
import json
from pathlib import Path
from typing import Dict, Any


DEFAULT_CONFIG = {
    "vars_dir": "vars",
    "terraform_path": "terraform",
    "verbose": False,
    "default_environment": None,
    "auto_approve": False,
}


class Config:
    """Manages Toffee configuration"""

    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = self._load_config()

    def _get_config_dir(self) -> str:
        """Get the configuration directory, creating it if it doesn't exist"""
        config_dir = os.path.join(str(Path.home()), ".toffee")
        os.makedirs(config_dir, exist_ok=True)
        return config_dir

    def _load_config(self) -> Dict[str, Any]:
        """Load the configuration from disk"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                # Merge with defaults to ensure all keys exist
                return {**DEFAULT_CONFIG, **config}
            except Exception:
                # If there's any error, fall back to defaults
                return DEFAULT_CONFIG.copy()
        else:
            return DEFAULT_CONFIG.copy()

    def save_config(self) -> None:
        """Save the current configuration to disk"""
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
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

        project_config_file = os.path.join(project_dir, ".toffee.json")
        project_config = {}

        if os.path.exists(project_config_file):
            try:
                with open(project_config_file, "r") as f:
                    project_config = json.load(f)
            except Exception:
                # If there's any error, ignore the project config
                pass

        # Project config overrides global config
        return {**self.config, **project_config}
