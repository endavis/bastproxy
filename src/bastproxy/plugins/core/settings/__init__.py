# Project: bastproxy
# Filename: plugins/core/settings/__init__.py
#
# File Description: a plugin to manage all settings
#
# By: Bast
"""This module handles commands and parsing input."""

# these 4 are required
PLUGIN_NAME = "Settings"
PLUGIN_PURPOSE = "Plugin to handle settings"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

__all__ = [
    "SettingValidationError",
    "int_range",
    "validate_ipv4_host",
    "validate_ipv6_host",
    "validate_port",
    "validate_port_or_unset",
]

from .libs._settinginfo import SettingValidationError
from .libs._validators import (
    int_range,
    validate_ipv4_host,
    validate_ipv6_host,
    validate_port,
    validate_port_or_unset,
)
