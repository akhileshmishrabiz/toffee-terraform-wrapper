"""Safety helpers for commands that can change infrastructure."""

import os
from typing import Iterable

from .backend import BackendError, describe, find_backend, read_settings

PROTECTED_ENVIRONMENT_NAMES = frozenset({"prod", "production"})


def is_protected_environment(name: str, extra_names: Iterable[str] = ()) -> bool:
    """Return whether an environment receives production safeguards."""
    folded = name.casefold()
    return folded in PROTECTED_ENVIRONMENT_NAMES or any(
        folded == extra.casefold() for extra in extra_names
    )


def describe_backend(root_dir: str, backend_file: str) -> str:
    """Return a concise backend destination without exposing credentials."""
    try:
        backend = find_backend(root_dir)
        settings = read_settings(backend_file) if os.path.isfile(backend_file) else {}
    except BackendError:
        return "unknown (backend configuration could not be read)"
    return describe(backend, settings, os.path.basename(backend_file))
