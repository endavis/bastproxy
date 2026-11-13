# Project: bastproxy
# Filename: plugins/debug/plugins/plugin/_plugins.py
#
# File Description: a plugin to debug other plugins
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult


class PluginsPlugin(BasePlugin):
    """a plugin to debug other plugins."""

    @AddParser(description="dump the internals of a plugin")
    @AddArgument("plugin", help="the plugin to inspect", default="")
    @AddArgument(
        "-o",
        "--object",
        help="show an object of the plugin, can be method or variable",
        default="",
    )
    @AddArgument("-d", "--detailed", help="show a detailed output", action="store_true")
    def _command_dump(self):
        """Dump a plugin object or attribute."""
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not args["plugin"]:
            return CommandResult(False, ["Please enter a plugin id"])

        if not self.api("libs.plugins.loader:plugin.id.is.valid")(args["plugin"]):
            return CommandResult(True, [f"Plugin {args['plugin']} not found"])

        return CommandResult(
            True, self.api(f"{args['plugin']}:plugin.dump")(args["object"], args["detailed"])[1]
        )

    @AddParser(description="show internal plugin hooks")
    @AddArgument("plugin", help="the plugin to show the hooks for", default="")
    def _command_hooks(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        show internal plugin hooks
        @CUsage@w: hooks.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not args["plugin"]:
            return CommandResult(False, ["Please enter a plugin name"])

        tmsg = []

        hooks = self.api(f"{args['plugin']}:plugin.hook.list")()

        tmsg.extend(
            self.api("plugins.core.commands:output.header.format")(
                f"Plugin Hooks for {args['plugin']}"
            )
        )

        for hook in hooks:
            tmsg.extend(self.api("plugins.core.commands:output.subheader.format")(f"{hook}"))
            priorities = hooks[hook].keys()
            priorities = sorted(priorities)
            for priority in priorities:
                tmsg.extend(f"{priority:<5} : {item}" for item in hooks[hook][priority])
            tmsg.append("")

        return CommandResult(True, tmsg)

    @AddParser(description="show plugin data summary")
    @AddArgument("plugin", help="the plugin to show the summary for", default="")
    def _command_summary(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        show a summary of what data a plugin has
        @CUsage@w: stats.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not args["plugin"]:
            return CommandResult(False, ["Please enter a plugin name"])

        data = {}

        loaded_plugins = self.api("libs.plugins.loader:plugin.list.loaded")()

        for plugin in loaded_plugins:
            api = f"{plugin}:summary.get.for.plugin"
            if self.api("libs.api:api.exists")(api):
                data[plugin] = self.api(api)(args["plugin"])

        tmsg = []
        for plugin, plugin_data in data.items():
            tmsg.extend(
                self.api("plugins.core.commands:output.header.format")(
                    f"{plugin}: data for {args['plugin']}"
                )
            )
            tmsg.extend(plugin_data)
            tmsg.append("")

        return CommandResult(True, tmsg)

    @AddParser(description="show detailed plugin data in other plugins")
    @AddArgument("plugin", help="the plugin to show the data for", default="")
    def _command_detail(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        show stats, memory, profile, etc.. for this plugin
        @CUsage@w: stats.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not args["plugin"]:
            return CommandResult(False, ["Please enter a plugin name"])

        data = {}

        loaded_plugins = self.api("libs.plugins.loader:plugin.list.loaded")()

        for plugin in loaded_plugins:
            api = f"{plugin}:detail.get.for.plugin"
            if self.api("libs.api:api.exists")(api):
                data[plugin] = self.api(api)(args["plugin"])

        tmsg = []
        for plugin, plugin_data in data.items():
            tmsg.extend(
                self.api("plugins.core.commands:output.header.format")(
                    f"{plugin}: data for {args['plugin']}"
                )
            )
            tmsg.extend(plugin_data)
            tmsg.append("")

        return CommandResult(True, tmsg)
