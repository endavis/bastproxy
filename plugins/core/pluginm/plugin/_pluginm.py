# pylint: disable=too-many-lines
# Project: bastproxy
# Filename: plugins/_manager/_pluginm.py
#
# File Description: holds the plugin manager
#
# By: Bast
"""manages all plugins."""
# Standard Library

# 3rd Party

# Project
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from plugins.core.commands import AddArgument, AddParser
from plugins.core.events import RegisterToEvent


class PluginManager(BasePlugin):
    """a class to manage plugins."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance."""
        self.can_reload_f: bool = False

        self.plugin_info_line_format = (
            "{plugin_id:<30} : {name:<25} {author:<10} {version:<5} {purpose}@w"
        )

        self.api("libs.api:add")(
            self.plugin_id, "save.all.plugins.state", self._api_save_all_plugins_state
        )

    def _command_helper_format_plugin_list(
        self, plugins, header="", columnheader=True, required_color_line=True
    ) -> list[str]:
        """Format a list of loaded plugins to return to client.

        plugins = a list of plugin_info objects
        """
        line_length = self.api("plugins.core.commands:get.output.line.length")()
        header_color = self.api("plugins.core.settings:get")(
            "plugins.core.commands", "output_header_color"
        )

        required_color = "@x75"
        msg = []

        if columnheader:
            msg.extend(
                [
                    self.api("plugins.core.utils:center.colored.string")(
                        f"@x86{header}@w", "-", line_length, filler_color=header_color
                    ),
                    self.plugin_info_line_format.format(
                        plugin_id="Id/Location",
                        name="Name",
                        author="Author",
                        version="Vers",
                        purpose="Purpose",
                    ),
                ]
            )
        msg.append(header_color + "-" * line_length + "@w")

        foundrequired = False
        for plugin_id in plugins:
            plugin_info = self.api("libs.plugins.loader:get.plugin.info")(plugin_id)
            plugin_color = required_color if plugin_info.is_required else ""
            if plugin_color:
                foundrequired = True
            msg.append(
                "".join(
                    [
                        plugin_color,
                        self.plugin_info_line_format.format(**plugin_info.__dict__),
                    ]
                )
            )

        if foundrequired and required_color_line:
            msg.extend(
                ("", f"* {required_color}Required plugins appear in this color@w")
            )
        return msg

    # get a message of plugins in a package
    def _get_package_plugins(self, package):
        """Create a message of loaded plugins in a package.

        Arguments:
          required:
            package - the package name

        returns:
          a list of strings of loaded plugins in the specified package
        """
        msg = []
        if "plugins" not in package:
            if package.startswith("."):
                package = f"plugins{package}"
            else:
                package = f"plugins.{package}"

        loaded_plugins_by_id = self.api("libs.plugins.loader:get.loaded.plugins.list")()
        if plist := [
            plugin_id
            for plugin_id in loaded_plugins_by_id
            if self.api("libs.plugins.loader:get.plugin.info")(plugin_id).package
            == package
        ]:
            plugins = sorted(plist)
            mod = __import__(package)
            try:
                desc = getattr(mod, package).PACKAGE_DESCRIPTION
            except AttributeError:
                desc = ""
            msg.extend(
                self._command_helper_format_plugin_list(
                    plugins, f"Plugins in {package}{f' - {desc}' if desc else ''}"
                )
            )
        else:
            msg.append("That is not a valid package")

        return msg

    # create a message of all plugins
    def _build_all_plugins_message(self):
        """Create a message of all plugins.

        Returns:
          a list of strings
        """
        msg = []
        packages_list = self.api("libs.plugins.loader:get.packages.list")()
        packages = {
            package: self.api("libs.plugins.loader:get.plugins.in.package")(package)
            for package in packages_list
        }
        msg.extend(
            self._command_helper_format_plugin_list(
                packages["plugins.core"], required_color_line=False
            )
        )
        del packages["plugins.core"]
        for package in packages:
            if packages[package]:
                msg.extend(
                    self._command_helper_format_plugin_list(
                        packages[package], required_color_line=False, columnheader=False
                    )
                )

        return msg

    # get plugins that are change on disk
    def _get_changed_plugins(self):
        """Create a message of loaded plugins that are changed on disk."""
        loaded_plugins_by_id = self.api("libs.plugins.loader:get.loaded.plugins.list")()

        msg = []
        if list_to_format := [
            plugin_id
            for plugin_id in loaded_plugins_by_id
            if self.api("libs.plugins.loader:get.plugin.info")(
                plugin_id
            ).get_changed_files()
        ]:
            msg = self._command_helper_format_plugin_list(
                list_to_format, "Changed Plugins"
            )

        return msg or ["No plugins are changed on disk."]

    def _get_invalid_plugins(self):
        """Create a message of plugins that are invalid python code."""
        all_plugins_by_id = self.api("libs.plugins.loader:get.all.plugins")()
        msg = []
        if list_to_format := [
            plugin_id
            for plugin_id in all_plugins_by_id
            if self.api("libs.plugins.loader:get.plugin.info")(
                plugin_id
            ).get_invalid_python_files()
        ]:
            msg = self._command_helper_format_plugin_list(
                list_to_format, "Plugins with invalid python code"
            )

        return msg or ["All plugins are valid python code."]

    # get all not loaded plugins
    def _get_not_loaded_plugins(self):
        """Create a message of all not loaded plugins."""
        msg = []
        not_loaded_plugins = self.api("libs.plugins.loader:get.not.loaded.plugins")()
        msg = self._command_helper_format_plugin_list(
            not_loaded_plugins, "Not Loaded Plugins"
        )

        return msg or ["There are no plugins that are not loaded"]

    @AddParser(description="list plugins")
    @AddArgument(
        "-n",
        "--notloaded",
        help="list plugins that are not loaded",
        action="store_true",
    )
    @AddArgument(
        "-c",
        "--changed",
        help="list plugins that are loaded but are changed on disk",
        action="store_true",
    )
    @AddArgument(
        "-i",
        "--invalid",
        help="list plugins that have files with invalid python code",
        action="store_true",
    )
    @AddArgument(
        "package", help="the package of the plugins to list", default="", nargs="?"
    )
    def _command_list(self):
        """@G%(name)s@w - @B%(cmdname)s@w
        List plugins
        @CUsage@w: list.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()
        msg = []

        if args["notloaded"]:
            msg.extend(self._get_not_loaded_plugins())
        elif args["changed"]:
            msg.extend(self._get_changed_plugins())
        elif args["invalid"]:
            msg.extend(self._get_invalid_plugins())
        elif args["package"]:
            msg.extend(self._get_package_plugins(args["package"]))
        else:
            msg.extend(self._build_all_plugins_message())
        return True, msg

    def _load_other_plugins_after_core_and_client_plugins(self):
        """Load plugins after core and client plugins have been loaded
        from the pluginstoload setting.
        """
        plugins_to_load_setting = self.api("plugins.core.settings:get")(
            self.plugin_id, "pluginstoload"
        )

        plugins_to_load = []

        for plugin in plugins_to_load_setting[:]:
            if not self.api("libs.plugins.loader:does.plugin.exist")(plugin):
                LogRecord(
                    f"plugin {plugin} was marked to load at startup and no longer exists, removing from startup",
                    level="error",
                    sources=[self.plugin_id],
                )()
                plugins_to_load_setting.remove(plugin)
                continue

            if self.api("libs.plugins.loader:is.plugin.loaded")(plugin):
                LogRecord(
                    f"plugin {plugin} was marked to load at startup and is already loaded, removing from startup",
                    level="debug",
                    sources=[self.plugin_id],
                )()
                plugins_to_load_setting.remove(plugin)
                continue

            if self.api("libs.plugins.loader:get.plugin.info")(plugin).is_dev:
                LogRecord(
                    f"plugin {plugin} was marked to load at startup and is a dev plugin, removing from startup",
                    level="debug",
                    sources=[self.plugin_id],
                )()
                plugins_to_load_setting.remove(plugin)
                continue

            plugins_to_load.append(plugin)

        self.api("plugins.core.settings:change")(
            self.plugin_id, "pluginstoload", plugins_to_load_setting
        )

        if plugins_to_load_setting:
            LogRecord("Loading other plugins", level="info", sources=[self.plugin_id])()
            self.api("libs.plugins.loader:load.plugins")(plugins_to_load_setting)
            LogRecord(
                "Finished loading other plugins", level="info", sources=[self.plugin_id]
            )()

    @RegisterToEvent(event_name="ev_plugins.core.proxy_shutdown")
    def _eventcb_shutdown(self, _=None):
        """Do tasks on shutdown."""
        self.api(f"{self.plugin_id}:save.all.plugins.state")()

    # save all plugins
    def _api_save_all_plugins_state(self, _=None):
        """Save all plugins."""
        for plugin_id in self.api("libs.plugins.loader:get.loaded.plugins.list")():
            self.api(f"{plugin_id}:save.state")()

    @AddParser(description="load a plugin")
    @AddArgument(
        "plugin",
        help="the plugin to load, don't include the .py",
        default="",
        nargs="?",
    )
    def _command_load(self):
        """@G%(name)s@w - @B%(cmdname)s@w
          Load a plugin
          @CUsage@w: load @Yplugin@w
            @Yplugin@w    = the id of the plugin to load,
                            example: core.example.timerex.

        will load the plugin and all of its dependencies
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        plugin_id = args["plugin"]

        if not plugin_id:
            return False, ["No plugin specified"]

        if self.api("libs.plugins.loader:is.plugin.loaded")(plugin_id):
            return True, [f"Plugin {plugin_id} is already loaded"]

        not_loaded_plugins_by_id = self.api(
            "libs.plugins.loader:get.not.loaded.plugins"
        )()

        if plugin_id and plugin_id not in not_loaded_plugins_by_id:
            return True, [f"Plugin {plugin_id} not found"]

        plugin_response = self.api("libs.plugins.loader:load.plugins")([plugin_id])

        tmsg = []
        if plugin_response["loaded_plugins"]:
            for plugin_id in plugin_response["loaded_plugins"]:
                self.api("plugins.core.events:raise.event")(f"ev_{plugin_id}_loaded")
                self.api("plugins.core.events:raise.event")(
                    f"ev_{self.plugin_id}_plugin_loaded",
                    event_args={"plugin_id": plugin_id},
                )
            tmsg.extend(
                (
                    "Loaded the following plugins",
                    "   " + ", ".join(plugin_response["loaded_plugins"]),
                )
            )

            # add the loaded plugins to the pluginstoload setting
            plugins_to_load_setting = self.api("plugins.core.settings:get")(
                self.plugin_id, "pluginstoload"
            )
            plugins_to_load_setting.extend(plugin_response["loaded_plugins"])
            self.api("plugins.core.settings:change")(
                self.plugin_id, "pluginstoload", plugins_to_load_setting
            )

        if plugin_response["bad_plugins"]:
            tmsg.extend(
                (
                    "Failed to load the following plugins, please check the logs",
                    "   " + ", ".join(plugin_response["bad_plugins"]),
                )
            )
        return True, tmsg

    @AddParser(description="unload a plugin")
    @AddArgument("plugin", help="the plugin to unload", default="", nargs="?")
    def _command_unload(self):
        """@G%(name)s@w - @B%(cmdname)s@w
        unload a plugin
        @CUsage@w: unload @Yplugin@w
          @Yplugin@w    = the id of the plugin to unload,
                          example: example.timerex.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        plugin_id = args["plugin"]

        if not plugin_id:
            return False, ["No plugin specified"]

        if not self.api("libs.plugins.loader:is.plugin.loaded")(plugin_id):
            return True, [f"Plugin {plugin_id} is not loaded"]

        if self.api("libs.plugins.loader:unload.plugin")(plugin_id):
            plugins_to_load_setting = self.api("plugins.core.settings:get")(
                self.plugin_id, "pluginstoload"
            )
            if plugin_id in plugins_to_load_setting:
                plugins_to_load_setting.remove(plugin_id)
                self.api("plugins.core.settings:change")(
                    self.plugin_id, "pluginstoload", plugins_to_load_setting
                )
            return True, [f"Plugin {plugin_id} unloaded"]

        return False, [f"Plugin {plugin_id} not unloaded, please check logs"]

    @AddParser(description="reload a plugin")
    @AddArgument("plugin", help="the plugin to reload", default="", nargs="?")
    def _command_reload(self):
        """@G%(name)s@w - @B%(cmdname)s@w
        reload a plugin
        @CUsage@w: reload @Yplugin@w
          @Yplugin@w    = the id of the plugin to reload,
                          example: example.timerex.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()

        if not self.api("libs.plugins.loader:is.plugin.id")(args["plugin"]):
            return True, [f"{args['plugin']} is not a valid plugin id"]

        self.api(f'{args["plugin"]}:set.reload')()

        plugins_to_load_setting = self.api("plugins.core.settings:get")(
            self.plugin_id, "pluginstoload"
        )
        if not self.api("libs.plugins.loader:reload.plugin")(args["plugin"]):
            if args["plugin"] in plugins_to_load_setting:
                plugins_to_load_setting.remove(args["plugin"])
                self.api("plugins.core.settings:change")(
                    self.plugin_id, "pluginstoload", plugins_to_load_setting
                )
            return False, [f'{args["plugin"]} not reloaded, please check logs']

        # add the loaded plugins to the pluginstoload setting
        if args["plugin"] not in plugins_to_load_setting:
            plugins_to_load_setting.append(args["plugin"])
        self.api("plugins.core.settings:change")(
            self.plugin_id, "pluginstoload", plugins_to_load_setting
        )
        return True, [f'{args["plugin"]} reloaded']

    @RegisterToEvent(
        event_name="ev_plugins.core.events_all_events_registered", priority=1
    )
    def _eventcb_all_events_registered(self):
        """This resends all the different plugin initialization events,
        saves all plugin states, and adds the save plugin timer.
        """
        self._load_other_plugins_after_core_and_client_plugins()

        loaded_plugins = self.api("libs.plugins.loader:get.loaded.plugins.list")()
        for plugin_id in loaded_plugins:
            self.api("plugins.core.events:raise.event")(f"ev_{plugin_id}_loaded")
            self.api("plugins.core.events:raise.event")(
                "ev_plugin_loaded", event_args={"plugin_id": plugin_id}
            )

        self.api(f"{self.plugin_id}:save.all.plugins.state")()
        self.api("plugins.core.timers:add.timer")(
            "global_save", self._api_save_all_plugins_state, 60, unique=True, log=False
        )

    # initialize this plugin
    @RegisterPluginHook("initialize")
    def _phook_initialize(self):
        """Initialize plugin."""
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "pluginstoload",
            [],
            list,
            "plugins to load on startup",
            readonly=True,
        )

        self.api("plugins.core.events:add.event")(
            "ev_plugin_loaded",
            self.plugin_id,
            description=["Raised when any plugin is loaded"],
            arg_descriptions={
                "plugin": "The plugin name",
                "plugin_id": "The plugin id",
            },
        )
        self.api("plugins.core.events:add.event")(
            "ev_plugin_unloaded",
            self.plugin_id,
            description=["Raised when any plugin is unloaded"],
            arg_descriptions={
                "plugin": "The plugin name",
                "plugin_id": "The plugin id",
            },
        )
