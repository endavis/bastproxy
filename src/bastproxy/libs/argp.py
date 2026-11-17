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
        at 73 characters and includes default values in help strings.

"""

# Standard Library
import argparse
import textwrap as _textwrap
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


RawDescriptionHelpFormatter = argparse.RawDescriptionHelpFormatter
HelpFormatter = argparse.RawTextHelpFormatter
SUPPRESS = argparse.SUPPRESS
OPTIONAL = argparse.OPTIONAL
ZERO_OR_MORE = argparse.ZERO_OR_MORE
ArgumentError = argparse.ArgumentError


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
        **kwargs: Any,
    ) -> None:
        """Create the formatter.

        Args:
            prog: The program name.
            indent_increment: Indent step, as for argparse's HelpFormatter.
            max_help_position: Help column limit, as for argparse's HelpFormatter.
            width: The line length to wrap help text and usage to. When None, usage
                follows argparse's terminal width and text wraps at 73 characters.
            **kwargs: Keyword arguments for argparse's HelpFormatter.

        """
        super().__init__(prog, indent_increment, max_help_position, width, **kwargs)
        self._fill_width = self.DEFAULT_FILL_WIDTH if width is None else width

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
            wrapped_line = "\n".join(wcwidth.wrap(line, max(self._fill_width - len(indent), 11)))
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
            lines.extend(wcwidth.wrap(line, max(width, 11)) or [""])
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
