"""Dependency-free comparison helpers for Terraform variable files."""

import re

from .hcl import HCLError, read_assignments

__all__ = [
    "HCLError",
    "contains_secret",
    "is_sensitive_key",
    "read_assignments",
]

# Whole words in a setting name, e.g. db_pass, github_pat, authHeader.
_SENSITIVE_WORDS = frozenset(
    {
        "auth",
        "cookie",
        "credential",
        "credentials",
        "dsn",
        "pass",
        "passphrase",
        "passwd",
        "password",
        "pat",
        "pwd",
        "secret",
        "secrets",
        "token",
        "tokens",
    }
)
# Fragments of a name with separators removed, e.g. api_key -> apikey.
_SENSITIVE_FRAGMENTS = (
    "accesskey",
    "apikey",
    "authkey",
    "authorization",
    "connectionstring",
    "connstr",
    "credential",
    "databaseurl",
    "dburl",
    "passwd",
    "password",
    "privatekey",
    "secret",
    "signingkey",
    "sshkey",
    "token",
    "webhook",
)
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_WORD_SEPARATOR = re.compile(r"[^a-z0-9]+")
_NESTED_KEY = re.compile(
    r'(?:"((?:[^"\\]|\\.)*)"|([A-Za-z_][A-Za-z0-9_-]*))\s*[=:](?!=)'
)
_URL_CREDENTIALS = re.compile(r"://[^/\s:@\"]+:[^/\s@\"]+@")


def is_sensitive_key(key: str) -> bool:
    """Return whether a setting should be redacted in terminal output."""
    words = [
        word
        for word in _WORD_SEPARATOR.split(_CAMEL_BOUNDARY.sub(r"\1_\2", key).lower())
        if word
    ]
    compact = "".join(words)
    return any(word in _SENSITIVE_WORDS for word in words) or any(
        fragment in compact for fragment in _SENSITIVE_FRAGMENTS
    )


def contains_secret(value: str) -> bool:
    """Return whether a value embeds a sensitive nested key or URL credentials."""
    if _URL_CREDENTIALS.search(value):
        return True
    if not value.lstrip().startswith(("{", "[")):
        return False
    return any(
        is_sensitive_key(quoted or bare) for quoted, bare in _NESTED_KEY.findall(value)
    )
