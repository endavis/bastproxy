# Project: bastproxy
# Filename: plugins/core/errors/plugin/_init_.py
#
# File Description: a plugin to handle errors
#
# By: Bast
"""
This plugin shows and clears errors seen during plugin execution
"""
__all__ = ['Plugin']

from ._errors import ErrorPlugin as Plugin
