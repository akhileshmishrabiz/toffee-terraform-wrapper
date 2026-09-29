"""Safety helpers for commands that can change infrastructure."""

import os
import re
from typing import Dict, Optional

PROTECTED_ENVIRONMENT_NAMES = frozenset({"prod", "production"})

_ASSIGNMENT_PATTERN = re.compile(
    r'^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*"((?:[^"\\]|\\.)*)"',
    re.MULTILINE,
)
_BACKEND_PATTERN = re.compile(r'\bbackend\s+"([^"]+)"\s*\{')


def is_protected_environment(name: str) -> bool:
    """Return whether an environment receives production safeguards."""
    return name.casefold() in PROTECTED_ENVIRONMENT_NAMES


def describe_backend(project_dir: str, backend_file: str) -> str:
    """Return a concise backend destination without exposing credentials."""
    backend_type = _find_backend_type(project_dir)
    values = _read_string_assignments(backend_file)
    backend_name = os.path.basename(backend_file)

    if backend_type == "s3":
        return _uri("s3", values.get("bucket"), values.get("key"))
    if backend_type == "gcs":
        return _uri("gs", values.get("bucket"), values.get("prefix"))
    if backend_type == "local":
        path = values.get("path")
        return f"local://{path}" if path else "local (destination not configured)"
    if backend_type:
        return f"{backend_type} (configured by {backend_name})"
    return f"configured by {backend_name}"


def _find_backend_type(project_dir: str) -> Optional[str]:
    for entry in sorted(os.scandir(project_dir), key=lambda item: item.name):
        if not entry.is_file() or not entry.name.endswith(".tf"):
            continue
        try:
            with open(entry.path, "r") as terraform_file:
                match = _BACKEND_PATTERN.search(terraform_file.read())
        except OSError:
            continue
        if match:
            return match.group(1)
    return None


def _read_string_assignments(path: str) -> Dict[str, str]:
    try:
        with open(path, "r") as config_file:
            content = config_file.read()
    except OSError:
        return {}
    return {
        key: value
        for key, value in _ASSIGNMENT_PATTERN.findall(content)
        if not any(ord(character) < 32 or ord(character) == 127 for character in value)
    }


def _uri(scheme: str, container: Optional[str], path: Optional[str]) -> str:
    if not container:
        return f"{scheme}:// (destination not configured)"
    if path:
        return f"{scheme}://{container}/{path.lstrip('/')}"
    return f"{scheme}://{container}"
