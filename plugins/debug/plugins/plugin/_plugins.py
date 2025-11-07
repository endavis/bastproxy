# Project: bastproxy
# Filename: plugins/debug/plugins/plugin/_plugins.py
#
# File Description: a plugin to debug other plugins
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from plugins.core.commands import AddArgument, AddParser


class PluginsPlugin(BasePlugin):
    """a plugin to debug other plugins"""

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
        """Dump a plugin object or attribute"""
        args = self.api("plugins.core.commands:get.current.command.args")()

        if not args["plugin"]:
            return False, ["Please enter a plugin id"]

        if not self.api("libs.plugins.loader:is.plugin.id")(args["plugin"]):
            return True, [f'Plugin {args["plugin"]} not found']

        return True, self.api(f"{args['plugin']}:dump")(
            args["object"], args["detailed"]
        )[1]

    @AddParser(description="show internal plugin hooks")
    @AddArgument("plugin", help="the plugin to show the hooks for", default="")
    def _command_hooks(self):
        """@G%(name)s@w - @B%(cmdname)s@w
        show internal plugin hooks
        @CUsage@w: hooks
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        if not args["plugin"]:
            return False, ["Please enter a plugin name"]

        tmsg = []

        hooks = self.api(f'{args["plugin"]}:get.plugin.hooks')()

        tmsg.extend(
            self.api("plugins.core.commands:format.output.header")(
                f'Plugin Hooks for {args["plugin"]}'
            )
        )

        for hook in hooks:
            tmsg.extend(
                self.api("plugins.core.commands:format.output.subheader")(f"{hook}")
            )
            priorities = hooks[hook].keys()
            priorities = sorted(list(priorities))
            for priority in priorities:
                tmsg.extend(f"{priority:<5} : {item}" for item in hooks[hook][priority])
            tmsg.append("")

        return True, tmsg

    @AddParser(description="show plugin data summary")
    @AddArgument("plugin", help="the plugin to show the summary for", default="")
    def _command_summary(self):
        """@G%(name)s@w - @B%(cmdname)s@w
        show a summary of what data a plugin has
        @CUsage@w: stats
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        if not args["plugin"]:
            return False, ["Please enter a plugin name"]

        data = {}

        loaded_plugins = self.api("libs.plugins.loader:get.loaded.plugins.list")()

        for plugin in loaded_plugins:
            api = f"{plugin}:get.summary.data.for.plugin"
            if self.api("libs.api:has")(api):
                data[plugin] = self.api(api)(args["plugin"])

        tmsg = []
        for plugin in data:
            tmsg.extend(
                self.api("plugins.core.commands:format.output.header")(
                    f'{plugin}: data for {args["plugin"]}'
                )
            )
            tmsg.extend(data[plugin])
            tmsg.append("")

        return True, tmsg

    @AddParser(description="show detailed plugin data in other plugins")
    @AddArgument("plugin", help="the plugin to show the data for", default="")
    def _command_detail(self):
        """@G%(name)s@w - @B%(cmdname)s@w
        show stats, memory, profile, etc.. for this plugin
        @CUsage@w: stats
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        if not args["plugin"]:
            return False, ["Please enter a plugin name"]

        data = {}

        loaded_plugins = self.api("libs.plugins.loader:get.loaded.plugins.list")()

        for plugin in loaded_plugins:
            api = f"{plugin}:get.detailed.data.for.plugin"
            if self.api("libs.api:has")(api):
                data[plugin] = self.api(api)(args["plugin"])

        tmsg = []
        for plugin in data:
            tmsg.extend(
                self.api("plugins.core.commands:format.output.header")(
                    f'{plugin}: data for {args["plugin"]}'
                )
            )
            tmsg.extend(data[plugin])
            tmsg.append("")

        return True, tmsg
