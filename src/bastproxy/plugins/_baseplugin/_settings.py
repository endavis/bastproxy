# Project: bastproxy
# Filename: plugins/_baseplugin/_settings.py
#
# File Description: holds the settings command and hook for the base plugin
#
# By: Bast
# Standard Library
import textwrap
from typing import TYPE_CHECKING, Protocol

# 3rd Party
# Project
from bastproxy.libs import argp
from bastproxy.libs.records import LogRecord
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser

from ._pluginhooks import RegisterPluginHook

if TYPE_CHECKING:
    from bastproxy.plugins._baseplugin import Plugin

SETTINGS_INIT_API = "plugins.core.settings:initialize.plugin.settings"


class Settings(Protocol):
    @AddCommand(group="Base", name="set", show_in_history=False)
    @AddParser(
        formatter_class=argp.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            change a setting in the plugin

            if there are no arguments or 'list' is the first argument then
            it will list the settings for the plugin"""
        ),
    )
    @AddArgument("name", help="the setting name", default="list", nargs="?")
    @AddArgument("value", help="the new value of the setting", default="", nargs="?")
    def _command_settings_plugin_set(self: "Plugin"):
        """@G%(name)s@w - @B%(cmdname)s@w.

        List or set vars
        @CUsage@w: var @Y<varname>@w @Y<varvalue>@w
            @Yname@w    = The setting to set
            @Yvalue@w   = The value to set it to
            if there are no arguments or 'list' is the first argument then
            it will list the settings for the plugin.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        if not args["name"] or args["name"] == "list":
            return True, self.api("plugins.core.settings:get.all.settings.formatted")(
                self.plugin_id
            )

        arg_string = f"-p {self.plugin_id} {args.arg_string}"
        _retval, return_string = self.api("plugins.core.commands:run")(
            "plugins.core.settings", "pset", argument_string=arg_string
        )

        return True, return_string

    @RegisterPluginHook("initialize", priority=75)
    def _phook_settings_post_initialize(self: "Plugin"):
        """Setup the settings for the plugin."""
        self.reset_f = False

        if not self.api("libs.api:has")(SETTINGS_INIT_API):
            LogRecord(
                f"{self.plugin_id}: settings plugin not available, skipping settings init",
                level="debug",
                sources=[self.plugin_id],
            )()
            return

        self.api(SETTINGS_INIT_API)(self.plugin_id)
