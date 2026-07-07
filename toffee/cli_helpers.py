"""CLI argument parsing helpers."""

from typing import List, Optional, Tuple


def normalize_envs_and_args(
    envs: Optional[List[str]],
    extra_args: List[str],
) -> Tuple[List[str], List[str]]:
    """
    Move terraform flags accidentally captured as env positional args.

    With ignore_unknown_options, flags like -auto-approve can land in envs.
    """
    if not envs:
        return [], extra_args

    normalized_envs: List[str] = []
    passthrough = list(extra_args)

    for item in envs:
        if item.startswith("-"):
            passthrough.append(item)
        else:
            normalized_envs.append(item)

    return normalized_envs, passthrough
