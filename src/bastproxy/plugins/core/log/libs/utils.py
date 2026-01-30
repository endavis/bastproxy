# Project: bastproxy
# Filename: plugins/core/log/libs/utils.py
#
# File Description: utility functions
# By: Bast
"""Utility functions for logger name manipulation.

This module provides helper functions for working with logger names,
particularly for extracting the top-level logger name from hierarchical
logger identifiers.

Features:
    - Extract top-level logger names from hierarchical logger names.

Usage:
    - Use get_toplevel() to get the root logger name from a qualified name.

Functions:
    - `get_toplevel`: Extract the top-level logger name from a logger name.

"""


def get_toplevel(logger_name):
    """Get the toplevel logger from a name."""
    return logger_name.split(":")[0] if ":" in logger_name else logger_name
