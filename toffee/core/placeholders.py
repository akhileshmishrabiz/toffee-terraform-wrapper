"""The marker for values a user must fill in before Terraform can use them."""

from typing import Dict, List

PLACEHOLDER = "CHANGE-ME"


def placeholder_keys(settings: Dict[str, object], prefix: str = "") -> List[str]:
    """Return the dotted names of settings whose value still holds the marker."""
    keys = []
    for key, value in settings.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            keys.extend(placeholder_keys(value, f"{name}."))
        elif PLACEHOLDER in str(value):
            keys.append(name)
    return keys
