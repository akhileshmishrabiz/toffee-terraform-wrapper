"""Dependency-free comparison helpers for simple Terraform variable files."""

import re
from typing import Dict

ASSIGNMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.*?)\s*$"
)
SENSITIVE_KEY_PATTERN = re.compile(
    r"(access.?key|credential|password|private.?key|secret|token)",
    re.IGNORECASE,
)


def read_assignments(path: str) -> Dict[str, str]:
    """Read top-level HCL assignments without attempting full HCL evaluation."""
    assignments: Dict[str, str] = {}
    current_key = None
    current_parts = []
    nesting = 0

    with open(path, "r") as config_file:
        for raw_line in config_file:
            line = _strip_comment(raw_line).strip()
            if not line:
                continue

            if current_key is None:
                match = ASSIGNMENT_PATTERN.match(line)
                if not match:
                    continue
                current_key, value = match.groups()
                current_parts = [value]
                nesting = _nesting_delta(value)
            else:
                current_parts.append(line)
                nesting += _nesting_delta(line)

            if nesting <= 0:
                assignments[current_key] = " ".join(current_parts).strip()
                current_key = None
                current_parts = []
                nesting = 0

    if current_key is not None:
        assignments[current_key] = " ".join(current_parts).strip()

    return assignments


def is_sensitive_key(key: str) -> bool:
    """Return whether a setting should be redacted in terminal output."""
    return SENSITIVE_KEY_PATTERN.search(key) is not None


def _strip_comment(line: str) -> str:
    in_string = False
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and in_string:
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if not in_string and character == "#":
            return line[:index]
        if (
            not in_string
            and character == "/"
            and index + 1 < len(line)
            and line[index + 1] == "/"
        ):
            return line[:index]
    return line


def _nesting_delta(value: str) -> int:
    delta = 0
    in_string = False
    escaped = False
    for character in value:
        if escaped:
            escaped = False
            continue
        if character == "\\" and in_string:
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
        elif not in_string and character in "[{(":
            delta += 1
        elif not in_string and character in "]})":
            delta -= 1
    return delta
