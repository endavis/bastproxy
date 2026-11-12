# Project: bastproxy
# Filename: plugins/core/settings/libs/_settingsinfo.py
#
# File Description: info class for settings
#
# By: Bast
# Standard Library

# 3rd Party

# Project


class SettingValidationError(ValueError):
    """Raised when a setting's validator rejects a value."""


class SettingInfo:
    def __init__(self, name, default, help, stype, **kwargs):
        self.name = name
        self.default = default
        self.help = help
        self.stype = stype

        self.nocolor = kwargs.get("nocolor", False)
        self.readonly = kwargs.get("readonly", False)
        self.hidden = kwargs.get("hidden", False)
        self.aftersetmessage = kwargs.get("aftersetmessage", "")
        # optional callable taking the converted value; returns None or "" when
        # the value is valid, or an error message string when it is not
        self.validator = kwargs.get("validator")
