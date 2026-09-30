"""Helpers for printing untrusted file contents to a terminal."""

import unicodedata

REPLACEMENT_CHARACTER = "\N{REPLACEMENT CHARACTER}"


def printable(text: str) -> str:
    """Replace control and invisible formatting characters (Cc/Cf)."""
    return "".join(
        REPLACEMENT_CHARACTER
        if unicodedata.category(character) in ("Cc", "Cf")
        else character
        for character in text
    )
