# Project: bastproxy
# Filename: plugins/_baseplugin/libs/_settings.py
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
from bastproxy.libs.logger import get_logger
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser, CommandResult

from ._pluginhooks import RegisterPluginHook

if TYPE_CHECKING:
    from bastproxy.plugins._baseplugin import Plugin

SETTINGS_INIT_API = "plugins.core.settings:setting.initialize.for.plugin"


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
    @AddArgument(
        "value",
        help='the new value of the setting, "" for an empty string',
        default=None,
        nargs="?",
    )
    @AddArgument("--default", help="reset the setting to its default value", action="store_true")
    def _command_settings_plugin_set(self: "Plugin"):
        """@G%(name)s@w - @B%(cmdname)s@w.

        List or set vars
        @CUsage@w: set @Y<name>@w [@Y<value>@w | @Y--default@w]
            @Yname@w      = The setting to set
            @Yvalue@w     = The value to set it to, "" for an empty string
            @Y--default@w = Reset the setting to its default value
            if there are no arguments or 'list' is the first argument then
            it will list the settings for the plugin.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not args["name"] or args["name"] == "list":
            return CommandResult(
                True, self.api("plugins.core.settings:setting.list.formatted")(self.plugin_id)
            )

        if args.get("default"):
            success, message = self.api("plugins.core.settings:setting.set.from.user")(
                args["name"], args["value"], self.plugin_id, reset=True
            )
        else:
            success, message = self.api("plugins.core.settings:setting.set.from.user")(
                args["name"], args["value"], self.plugin_id
            )
        return CommandResult(success, message)

    @RegisterPluginHook("after_load", priority=75)
    def _phook_settings_post_initialize(self: "Plugin"):
        """Setup the settings for the plugin."""
        self.reset_f = False

        if not self.api("libs.api:api.exists")(SETTINGS_INIT_API):
            get_logger(self.plugin_id).debug(
                "%s: settings plugin not available, skipping settings init", self.plugin_id
            )
            return

        self.api(SETTINGS_INIT_API)(self.plugin_id)
