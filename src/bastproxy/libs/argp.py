# Project: bastproxy
# Filename: libs/argp.py
#
# File Description: setup argument parser with some customizations
#
# By: Bast
"""Module for setting up an argument parser with customizations.

This module provides a customized argument parser that does not exit on error and
includes a custom help formatter for better command help text formatting.

Key Components:
    - ArgumentParser: A subclass of argparse.ArgumentParser that raises an error
        instead of exiting on error.
    - CustomFormatter: A custom help formatter for argparse that wraps help text
        at 73 characters and includes default values in help strings.

Features:
    - ArgumentParser class that overrides the default error handling to raise an
        error instead of exiting.
    - CustomFormatter class that customizes the help text formatting and includes
        default values in the help strings.

Usage:
    - Use ArgumentParser to create an argument parser that does not exit on error.
    - Use CustomFormatter to format help text with custom wrapping and default
        value inclusion.

Classes:
    - `ArgumentParser`: A subclass of argparse.ArgumentParser that raises an error
        instead of exiting on error.
    - `CustomFormatter`: A custom help formatter for argparse that wraps help text
        at 73 characters and includes default values in help strings. Given a
        tokenizer, it counts ``@`` colour codes as zero columns and carries the
        active colour onto each continuation line.

"""

# Standard Library
import argparse
import textwrap as _textwrap
from collections.abc import Callable
from typing import Any, NoReturn

# Third Party
import wcwidth

# Project


# plac was evaluated and rejected in #435; see docs/claude/command_system.md.
# prefix_chars="-+" gives `+` prefixes.
class ArgumentParser(argparse.ArgumentParser):
    """A subclass of argparse.ArgumentParser that raises an error instead of exiting."""

    def error(self, message: str) -> NoReturn:
        """Raise an error instead of exiting.

        This method overrides the default error handling behavior of
        argparse.ArgumentParser to raise an error instead of exiting the program.

        Args:
            message: The error message to be displayed.

        Raises:
            ArgumentError: If there is an error in the arguments.

        """
        raise argparse.ArgumentError(None, message)

    def has_positionals(self) -> bool:
        """Return True if the parser has a positional argument (#791).

        Any positional counts, including an optional one (``nargs="?"``), because
        it could hold the word ``help``.
        """
        return any(not action.option_strings for action in self._actions)


RawDescriptionHelpFormatter = argparse.RawDescriptionHelpFormatter
HelpFormatter = argparse.RawTextHelpFormatter
SUPPRESS = argparse.SUPPRESS
OPTIONAL = argparse.OPTIONAL
ZERO_OR_MORE = argparse.ZERO_OR_MORE
ArgumentError = argparse.ArgumentError


def _wrap_coded(
    line: str,
    width: int,
    tokenize: Callable[[str], list[tuple[str, str]]],
) -> list[str]:
    """Wrap one line of text holding colour codes, counting codes as zero columns.

    The visible text goes through ``wcwidth.wrap``, so every break decision is the one
    plain text gets. The raw text, codes included, is then mapped back onto the wrapped
    lines. A colour that is still active at a break is repeated at the start of the
    next line, unless it is ``@w``. A code that sat on whitespace dropped at a break
    moves to the start of the next line.

    Args:
        line: One line as the author wrote it.
        width: The column width to wrap to.
        tokenize: Splits text into ``(raw, visible)`` pairs, as ``colorcode.to.tokens``.

    Returns:
        The wrapped lines, codes included. Plain text gives what ``wcwidth.wrap`` gives.

    """
    tokens = tokenize(line)
    if all(raw == visible for raw, visible in tokens):
        return wcwidth.wrap(line, width)

    visible_text: list[str] = []
    raw_of: list[str] = []
    codes_before: list[list[str]] = [[]]
    for raw, visible in tokens:
        if not visible:
            codes_before[-1].append(raw)
            continue
        for number, char in enumerate(visible):
            visible_text.append(char)
            if raw == visible:
                raw_of.append(char)
            else:
                raw_of.append(raw if number == 0 else "")
            codes_before.append([])
    # codes_before[i] holds the codes in front of visible char i; the last entry holds
    # the codes after the final visible char.
    text = "".join(visible_text)

    wrapped = wcwidth.wrap(text, width)
    if not wrapped:
        return (
            ["".join(code for codes in codes_before for code in codes)] if any(codes_before) else []
        )

    lines: list[str] = []
    last_code = ""
    pending: list[str] = []
    pos = 0
    for number, wrapped_line in enumerate(wrapped):
        parts: list[str] = []
        if number and last_code and last_code != "@w":
            parts.append(last_code)
        for char in wrapped_line:
            if char == " " and pos < len(text) and text[pos].isspace():
                emit = [*pending, *codes_before[pos]]
                raw = " "
                pos += 1
            else:
                if char == " ":
                    parts.extend(pending)
                    pending = []
                    parts.append(" ")
                    continue
                while pos < len(text) and text[pos] != char:
                    if not text[pos].isspace():
                        return wcwidth.wrap(line, width)
                    pending.extend(codes_before[pos])
                    pos += 1
                if pos >= len(text):
                    return wcwidth.wrap(line, width)
                emit = [*pending, *codes_before[pos]]
                raw = raw_of[pos]
                pos += 1
            pending = []
            parts.extend(emit)
            if emit:
                last_code = emit[-1]
            parts.append(raw)
        lines.append("".join(parts))
    trailing = [*pending, *(code for codes in codes_before[pos:] for code in codes)]
    lines[-1] += "".join(trailing)
    return lines


class CustomFormatter(HelpFormatter):
    """A custom help formatter for argparse that wraps help text at 73 characters.

    This class customizes the help text formatting for argparse by wrapping help
    text at 73 characters and including default values in the help strings.

    """

    DEFAULT_FILL_WIDTH = 73

    def __init__(
        self,
        prog: str,
        indent_increment: int = 2,
        max_help_position: int = 24,
        width: int | None = None,
        tokenize: Callable[[str], list[tuple[str, str]]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the formatter.

        Args:
            prog: The program name.
            indent_increment: Indent step, as for argparse's HelpFormatter.
            max_help_position: Help column limit, as for argparse's HelpFormatter.
            width: The line length to wrap help text and usage to. When None, usage
                follows argparse's terminal width and text wraps at 73 characters.
            tokenize: Splits text into ``(raw, visible)`` pairs, as the
                ``colorcode.to.tokens`` API does. When given, colour codes count as zero
                columns when help wraps. When None, text wraps as written.
            **kwargs: Keyword arguments for argparse's HelpFormatter.

        """
        super().__init__(prog, indent_increment, max_help_position, width, **kwargs)
        self._fill_width = self.DEFAULT_FILL_WIDTH if width is None else width
        self._tokenize = tokenize

    def _wrap(self, line: str, width: int) -> list[str]:
        """Wrap one author line, treating colour codes as zero columns when possible."""
        if self._tokenize is None:
            return wcwidth.wrap(line, width)
        return _wrap_coded(line, width, self._tokenize)

    # override _fill_text
    def _fill_text(self, text: str, width: int = 0, indent: str = "") -> str:
        """Fill the text with custom wrapping at the formatter's width.

        This method overrides the default _fill_text method of argparse's help
        formatter to wrap the text at the width given to the formatter (73 characters
        when none was given), minus the indent.

        Args:
            text: The text to be wrapped.
            width: The maximum width of the wrapped text.
            indent: The indentation level for the wrapped text.

        Returns:
            The wrapped text.

        """
        text = _textwrap.dedent(text)
        lines = text.splitlines() if text else [""]
        multiline_text = ""
        for line in lines:
            wrapped_line = "\n".join(self._wrap(line, max(self._fill_width - len(indent), 11)))
            multiline_text = multiline_text + "\n" + wrapped_line
        return multiline_text

    # override _split_lines
    def _split_lines(self, text: str, width: int) -> list[str]:
        """Wrap argument help to the column width argparse computed.

        RawTextHelpFormatter keeps each line as written, so a long argument help
        ran past the client's line length. Each line the author wrote is wrapped
        on its own, keeping deliberate line breaks.

        Args:
            text: The argument help text.
            width: The width available after the help column.

        Returns:
            The wrapped lines.

        """
        lines: list[str] = []
        for line in text.splitlines() or [""]:
            lines.extend(self._wrap(line, max(width, 11)) or [""])
        return lines

    # override _get_help_string
    def _get_help_string(self, action: argparse.Action) -> str | None:
        """Get the help string for an action, including the default value if applicable.

        This method overrides the default _get_help_string method of argparse's help
        formatter to include the default value in the help string if it is not
        already included.

        Args:
            action: The argparse.Action object for which the help string is generated.

        Returns:
            The help string for the action, including the default value if applicable.

        """
        temp_help: str | None = action.help
        # add the default value to the argument help
        if (
            action.help
            and temp_help
            and "%(default)" not in action.help
            and "(default: " not in action.help
            and action.default is not SUPPRESS
        ):
            defaulting_nargs = [OPTIONAL, ZERO_OR_MORE]
            if (action.option_strings or action.nargs in defaulting_nargs) and action.default != "":
                temp_help += " (default: %(default)s)"

        return temp_help
