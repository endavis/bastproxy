# Project: bastproxy
# Filename: plugins/core/log/libs/utils.py
#
# File Description: utility functions
# By: Bast


def get_toplevel(logger_name):
    """Get the toplevel logger from a name."""
    return logger_name.split(":")[0] if ":" in logger_name else logger_name
