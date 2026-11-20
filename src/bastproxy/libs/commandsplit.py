# Project: bastproxy
# Filename: libs/commandsplit.py
#
# File Description: build the regex that splits a line into commands
#
# By: Bast
"""Build the command-split regex from the ``cmdseperator`` setting (#639)."""

# Standard Library
import re


def build_command_split_regex(separator: str) -> str:
    """Return a regex matching ``separator`` only as a single, undoubled character.

    The separator is escaped, so a regex metacharacter splits literally. A doubled
    separator (for example ``||``) does not match, so it is left in the line.
    """
    esc = re.escape(separator)
    return rf"(?<=[^{esc}]){esc}(?=[^{esc}])"
