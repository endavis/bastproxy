# Project: bastproxy
# Filename: plugins/core/settings/libs/_settingsinfo.py
#
# File Description: info class for settings
#
# By: Bast
# Standard Library

# 3rd Party

# Project


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
