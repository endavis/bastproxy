# Project: bastproxy
# Filename: libs/commandprefix.py
#
# File Description: match the command prefix case-insensitively
#
# By: Bast
"""Match the command prefix in any case, so ``#BP.core.proxy.info`` runs (#782)."""


def starts_with_command_prefix(text: str, prefix: str) -> bool:
    """Return True if ``text`` starts with ``prefix``, ignoring case and leading whitespace.

    The text is sliced before it is casefolded, so a casefold that changes the
    length cannot shift the comparison. An empty prefix never matches.
    """
    if not prefix:
        return False
    return text.lstrip()[: len(prefix)].casefold() == prefix.casefold()


def normalize_command_prefix(text: str, prefix: str) -> str:
    """Return ``text`` with a leading prefix, in any case, rewritten to ``prefix``.

    Leading whitespace is dropped when the prefix matches. Text that does not start
    with the prefix is returned unchanged.
    """
    if not starts_with_command_prefix(text, prefix):
        return text
    return prefix + text.lstrip()[len(prefix) :]
