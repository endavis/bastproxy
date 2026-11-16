# Project: bastproxy
# Filename: plugins/core/help/plugin/_init_.py
#
# File Description: a plugin with guides for using the proxy
#
# By: Bast
"""Guides for using the proxy.

Use `#bp.core.help.topic` to list the topics.
"""

__all__ = ["Plugin"]

from ._help import HelpPlugin as Plugin
