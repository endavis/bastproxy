# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/argp.py
#
# File Description: setup argument parser with some customizations
#
# By: Bast
"""
This plugin overrides some default argparse behavior to allow for
errors to be raised instead of exiting the program.
It also adds a CustomFormatter to wrap help text at 73 characters
and print default arguments.
"""

# Standard Library
import sys
import argparse
import textwrap as _textwrap

# Third Party

# Project

class ArgumentParser(argparse.ArgumentParser):
    """
    argparse class that doesn't exit on error
    """
    def error(self, message):
        """
        override the error class to raise an error and not exit
        """
        if exc := sys.exc_info()[1]:
            exc.add_note(message)
            raise exc


RawDescriptionHelpFormatter = argparse.RawDescriptionHelpFormatter
HelpFormatter = argparse.RawTextHelpFormatter
SUPPRESS = argparse.SUPPRESS
OPTIONAL = argparse.OPTIONAL
ZERO_OR_MORE = argparse.ZERO_OR_MORE
ArgumentError = argparse.ArgumentError

class CustomFormatter(HelpFormatter):
    """
    custom formatter for argparser for commands
    """
    # override _fill_text
    def _fill_text(self, text, width, indent):
        """
        change the help text wrap at 73 characters

        arguments:
          required:
            text   - a string of items, newlines can be included
            width  - the width of the text to wrap, not used
            indent - the indent for each line after first, not used

        returns:
          returns a string of lines separated by newlines
        """
        text = _textwrap.dedent(text)
        lines = text.splitlines() if text else ['']
        multiline_text = ''
        for line in lines:
            wrapped_line = _textwrap.fill(line, 73)
            multiline_text = multiline_text + '\n' + wrapped_line
        return multiline_text

    # override _get_help_string
    def _get_help_string(self, action):
        """
        get the help string for an action, which maps to an argument for a command

        arguments:
          required:
            action  - the action to get the help for

        returns:
          returns a formatted help string
        """
        temp_help: str | None = action.help
        # add the default value to the argument help
        if (
            action.help
            and temp_help
            and '%(default)' not in action.help
            and '(default: ' not in action.help
            and action.default is not SUPPRESS
        ):
            defaulting_nargs = [OPTIONAL, ZERO_OR_MORE]
            if (
                action.option_strings or action.nargs in defaulting_nargs
            ) and action.default != '':
                temp_help += ' (default: %(default)s)'

        return temp_help
