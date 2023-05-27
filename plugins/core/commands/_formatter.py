# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/commands/_plugin.py
#
# File Description: a plugin that is the command interpreter for clients
#
# By: Bast

# Standard Library
from __future__ import print_function
import textwrap as _textwrap


# 3rd Party

# Project
import libs.argp as argp

# this class creates a custom formatter for help text to wrap at 73 characters
# and it adds what the default value for an argument is if set
class CustomFormatter(argp.HelpFormatter):
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
        lines = text.split('\n')
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
            and action.default is not argp.SUPPRESS
        ):
            defaulting_nargs = [argp.OPTIONAL, argp.ZERO_OR_MORE]
            if (
                action.option_strings or action.nargs in defaulting_nargs
            ) and action.default != '':
                temp_help += ' (default: %(default)s)'

        return temp_help
