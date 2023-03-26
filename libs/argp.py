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
"""

# Standard Library
import sys
import argparse

# Third Party

# Project

class ArgumentParser(argparse.ArgumentParser):
    """
    argparse class that doesn't exit on error
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the class
        """
        argparse.ArgumentParser.__init__(self, *args, **kwargs)
        self.exit_on_error = False


RawDescriptionHelpFormatter = argparse.RawDescriptionHelpFormatter
HelpFormatter = argparse.HelpFormatter
SUPPRESS = argparse.SUPPRESS
OPTIONAL = argparse.OPTIONAL
ZERO_OR_MORE = argparse.ZERO_OR_MORE
ArgumentError = argparse.ArgumentError
