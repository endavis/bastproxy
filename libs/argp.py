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
from typing import NoReturn

# Third Party

# Project


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

    # override _fill_text
    def _fill_text(self, text: str, width: int = 0, indent: str = "") -> str:
        """Fill the text with custom wrapping at 73 characters.

        This method overrides the default _fill_text method of argparse's help
        formatter to wrap the text at 73 characters.

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
            wrapped_line = _textwrap.fill(line, 73)
            multiline_text = multiline_text + "\n" + wrapped_line
        return multiline_text

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
            if (
                action.option_strings or action.nargs in defaulting_nargs
            ) and action.default != "":
                temp_help += " (default: %(default)s)"

        return temp_help
