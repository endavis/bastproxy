# pylint: disable=too-many-lines
# Project: bastproxy
# Filename: plugins/_manager/_pluginm.py
#
# File Description: holds the plugin manager
#
# By: Bast
"""manages all plugins."""

# Standard Library
from importlib import import_module

from bastproxy.libs.logger import get_logger

# 3rd Party
# Project
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent


def _package_description(plugin_info: PluginInfo) -> str:
    """Return the PACKAGE_DESCRIPTION of the package a plugin lives in.

    Args:
        plugin_info: The plugin whose package to describe.

    Returns:
        The description, or an empty string if the package has none.

    """
    package_location = plugin_info.package_import_location.rpartition(".")[0]
    try:
        return str(import_module(package_location).PACKAGE_DESCRIPTION)
    except (ImportError, AttributeError, ValueError):
        return ""


class PluginManager(BasePlugin):
    """a class to manage plugins."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance."""
        self.can_reload_f: bool = False

        self.api("libs.api:api.add")(
            self.plugin_id, "plugin.state.save.all", self._api_plugin_state_save_all
        )

    def _command_helper_format_plugin_list(
        self, plugins, header="", required_color_line=True
    ) -> list[str]:
        """Format a list of loaded plugins to return to client.

        plugins = a list of plugin_info objects
        """
        # three digits: a cell starting with a digit (Vers) would otherwise extend the code
        required_color = "@x075"
        columns = [
            {"name": "Id/Location", "key": "plugin_id"},
            {"name": "Name", "key": "name"},
            {"name": "Author", "key": "author"},
            {"name": "Vers", "key": "version"},
            {"name": "Purpose", "key": "purpose"},
        ]

        foundrequired = False
        data = []
        for plugin_id in plugins:
            plugin_info = self.api("libs.plugins.loader:plugin.info.get")(plugin_id)
            plugin_color = required_color if plugin_info.is_required else ""
            if plugin_color:
                foundrequired = True
            data.append(
                {
                    column["key"]: f"{plugin_color}{getattr(plugin_info, column['key'])}"
                    for column in columns
                }
            )

        msg = self.api("plugins.core.utils:table.format")(header, data, columns)

        if foundrequired and required_color_line:
            msg.extend(("", f"* {required_color}Required plugins appear in this color@w"))
        return msg

    # get a message of plugins in a package
    def _get_package_plugins(self, package):
        """Create a message of loaded plugins in a package.

        Args:
            package: The package name to list plugins from.

        Returns:
            A list of strings of loaded plugins in the specified package.

        """
        msg = []
        if "plugins" not in package:
            if package.startswith("."):
                package = f"plugins{package}"
            else:
                package = f"plugins.{package}"

        loaded_plugins_by_id = self.api("libs.plugins.loader:plugin.list.loaded")()
        if plist := [
            plugin_id
            for plugin_id in loaded_plugins_by_id
            if self.api("libs.plugins.loader:plugin.info.get")(plugin_id).package == package
        ]:
            plugins = sorted(plist)
            desc = _package_description(self.api("libs.plugins.loader:plugin.info.get")(plugins[0]))
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
        packages_list = self.api("libs.plugins.loader:package.list")()
        packages = {
            package: self.api("libs.plugins.loader:plugin.list.in.package")(package)
            for package in packages_list
        }
        # one table so every row shares one column layout; core plugins come first
        all_plugins = list(packages.pop("plugins.core"))
        for plugins_list in packages.values():
            all_plugins.extend(plugins_list)

        msg = self._command_helper_format_plugin_list(
            all_plugins, "Plugins", required_color_line=False
        )

        return msg

    # get plugins that are change on disk
    def _get_changed_plugins(self):
        """Create a message of loaded plugins that are changed on disk."""
        loaded_plugins_by_id = self.api("libs.plugins.loader:plugin.list.loaded")()

        msg = []
        if list_to_format := [
            plugin_id
            for plugin_id in loaded_plugins_by_id
            if self.api("libs.plugins.loader:plugin.info.get")(plugin_id).get_changed_files()
        ]:
            msg = self._command_helper_format_plugin_list(list_to_format, "Changed Plugins")

        return msg or ["No plugins are changed on disk."]

    def _get_invalid_plugins(self):
        """Create a message of plugins that are invalid python code."""
        all_plugins_by_id = self.api("libs.plugins.loader:plugin.list")()
        msg = []
        if list_to_format := [
            plugin_id
            for plugin_id in all_plugins_by_id
            if self.api("libs.plugins.loader:plugin.info.get")(plugin_id).get_invalid_python_files()
        ]:
            msg = self._command_helper_format_plugin_list(
                list_to_format, "Plugins with invalid python code"
            )

        return msg or ["All plugins are valid python code."]

    # get all not loaded plugins
    def _get_not_loaded_plugins(self):
        """Create a message of all not loaded plugins."""
        msg = []
        not_loaded_plugins = self.api("libs.plugins.loader:plugin.list.not.loaded")()
        msg = self._command_helper_format_plugin_list(not_loaded_plugins, "Not Loaded Plugins")

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
    @AddArgument("package", help="the package of the plugins to list", default="", nargs="?")
    def _command_list(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        List plugins
        @CUsage@w: list.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
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
        return CommandResult(True, msg)

    def _load_other_plugins_after_core_and_client_plugins(self):
        """Load plugins after core and client plugins have been loaded.

        from the pluginstoload setting.
        """
        plugins_to_load_setting = self.api("plugins.core.settings:setting.get")(
            self.plugin_id, "pluginstoload"
        )

        plugins_to_load = []

        for plugin in plugins_to_load_setting[:]:
            if not self.api("libs.plugins.loader:plugin.exists")(plugin):
                get_logger(self.plugin_id).error(
                    "plugin %s was marked to load at startup and no longer exists, removing from startup",
                    plugin,
                )
                plugins_to_load_setting.remove(plugin)
                continue

            if self.api("libs.plugins.loader:plugin.is.loaded")(plugin):
                get_logger(self.plugin_id).debug(
                    "plugin %s was marked to load at startup and is already loaded, removing from startup",
                    plugin,
                )
                plugins_to_load_setting.remove(plugin)
                continue

            if self.api("libs.plugins.loader:plugin.info.get")(plugin).is_dev:
                get_logger(self.plugin_id).debug(
                    "plugin %s was marked to load at startup and is a dev plugin, removing from startup",
                    plugin,
                )
                plugins_to_load_setting.remove(plugin)
                continue

            plugins_to_load.append(plugin)

        self.api("plugins.core.settings:setting.set")(
            self.plugin_id, "pluginstoload", plugins_to_load_setting
        )

        if plugins_to_load_setting:
            get_logger(self.plugin_id).info("Loading other plugins")
            self.api("libs.plugins.loader:plugin.load")(plugins_to_load_setting)
            get_logger(self.plugin_id).info("Finished loading other plugins")

    @RegisterToEvent(event_name="ev_plugins.core.proxy_shutdown")
    def _eventcb_shutdown(self, _=None):
        """Do tasks on shutdown."""
        self.api(f"{self.plugin_id}:plugin.state.save.all")()

    # save all plugins
    def _api_plugin_state_save_all(self, _=None):
        """Save every loaded plugin.

        Unlike the base ``plugin.state.save`` API, which saves one plugin, this
        calls ``plugin.state.save`` on each loaded plugin.
        """
        for plugin_id in self.api("libs.plugins.loader:plugin.list.loaded")():
            self.api(f"{plugin_id}:plugin.state.save")()

    @AddParser(description="load a plugin")
    @AddArgument(
        "plugin",
        help="the plugin to load, don't include the .py",
        default="",
        nargs="?",
    )
    def _command_load(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

          Load a plugin
          @CUsage@w: load @Yplugin@w
            @Yplugin@w    = the id of the plugin to load,
                            example: core.example.timerex.

        will load the plugin and all of its dependencies
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        plugin_id = args["plugin"]

        if not plugin_id:
            return CommandResult(False, ["No plugin specified"])

        if self.api("libs.plugins.loader:plugin.is.loaded")(plugin_id):
            return CommandResult(True, [f"Plugin {plugin_id} is already loaded"])

        not_loaded_plugins_by_id = self.api("libs.plugins.loader:plugin.list.not.loaded")()

        if plugin_id and plugin_id not in not_loaded_plugins_by_id:
            return CommandResult(True, [f"Plugin {plugin_id} not found"])

        plugin_response = self.api("libs.plugins.loader:plugin.load")([plugin_id])

        tmsg = []
        if plugin_response["loaded_plugins"]:
            for plugin_id in plugin_response["loaded_plugins"]:
                self.api("plugins.core.events:event.raise")(f"ev_{plugin_id}_loaded")
                self.api("plugins.core.events:event.raise")(
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
            plugins_to_load_setting = self.api("plugins.core.settings:setting.get")(
                self.plugin_id, "pluginstoload"
            )
            plugins_to_load_setting.extend(plugin_response["loaded_plugins"])
            self.api("plugins.core.settings:setting.set")(
                self.plugin_id, "pluginstoload", plugins_to_load_setting
            )

        if plugin_response["bad_plugins"]:
            tmsg.extend(
                (
                    "Failed to load the following plugins, please check the logs",
                    "   " + ", ".join(plugin_response["bad_plugins"]),
                )
            )
        return CommandResult(True, tmsg)

    @AddParser(description="unload a plugin")
    @AddArgument("plugin", help="the plugin to unload", default="", nargs="?")
    def _command_unload(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        unload a plugin
        @CUsage@w: unload @Yplugin@w
          @Yplugin@w    = the id of the plugin to unload,
                          example: example.timerex.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        plugin_id = args["plugin"]

        if not plugin_id:
            return CommandResult(False, ["No plugin specified"])

        if not self.api("libs.plugins.loader:plugin.is.loaded")(plugin_id):
            return CommandResult(True, [f"Plugin {plugin_id} is not loaded"])

        if self.api("libs.plugins.loader:plugin.info.get")(plugin_id).is_required:
            return CommandResult(False, [f"Plugin {plugin_id} is required and cannot be unloaded"])

        if self.api("libs.plugins.loader:plugin.unload")(plugin_id):
            plugins_to_load_setting = self.api("plugins.core.settings:setting.get")(
                self.plugin_id, "pluginstoload"
            )
            if plugin_id in plugins_to_load_setting:
                plugins_to_load_setting.remove(plugin_id)
                self.api("plugins.core.settings:setting.set")(
                    self.plugin_id, "pluginstoload", plugins_to_load_setting
                )
            return CommandResult(True, [f"Plugin {plugin_id} unloaded"])

        return CommandResult(False, [f"Plugin {plugin_id} not unloaded, please check logs"])

    @AddParser(description="reload a plugin")
    @AddArgument("plugin", help="the plugin to reload", default="", nargs="?")
    def _command_reload(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        reload a plugin
        @CUsage@w: reload @Yplugin@w
          @Yplugin@w    = the id of the plugin to reload,
                          example: example.timerex.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not self.api("libs.plugins.loader:plugin.id.is.valid")(args["plugin"]):
            return CommandResult(True, [f"{args['plugin']} is not a valid plugin id"])

        if not self.api("libs.plugins.loader:plugin.is.loaded")(args["plugin"]):
            return CommandResult(
                True,
                [f"{args['plugin']} is not loaded; use #bp.core.pluginm.load {args['plugin']}"],
            )

        self.api(f"{args['plugin']}:plugin.reloading.set")()

        plugins_to_load_setting = self.api("plugins.core.settings:setting.get")(
            self.plugin_id, "pluginstoload"
        )
        if not self.api("libs.plugins.loader:plugin.reload")(args["plugin"]):
            if args["plugin"] in plugins_to_load_setting:
                plugins_to_load_setting.remove(args["plugin"])
                self.api("plugins.core.settings:setting.set")(
                    self.plugin_id, "pluginstoload", plugins_to_load_setting
                )
            return CommandResult(False, [f"{args['plugin']} not reloaded, please check logs"])

        # add the loaded plugins to the pluginstoload setting
        if args["plugin"] not in plugins_to_load_setting:
            plugins_to_load_setting.append(args["plugin"])
        self.api("plugins.core.settings:setting.set")(
            self.plugin_id, "pluginstoload", plugins_to_load_setting
        )
        return CommandResult(True, [f"{args['plugin']} reloaded"])

    @RegisterToEvent(event_name="ev_plugins.core.events_all_events_registered", priority=1)
    def _eventcb_all_events_registered(self):
        """This resends all the different plugin initialization events,.

        saves all plugin states, and adds the save plugin timer.
        """
        self._load_other_plugins_after_core_and_client_plugins()

        loaded_plugins = self.api("libs.plugins.loader:plugin.list.loaded")()
        for plugin_id in loaded_plugins:
            self.api("plugins.core.events:event.raise")(f"ev_{plugin_id}_loaded")
            self.api("plugins.core.events:event.raise")(
                "ev_plugin_loaded", event_args={"plugin_id": plugin_id}
            )

        self.api(f"{self.plugin_id}:plugin.state.save.all")()
        self.api("plugins.core.timers:timer.add")(
            "global_save", self._api_plugin_state_save_all, 60, unique=True, log=False
        )

    # initialize this plugin
    @RegisterPluginHook("after_load")
    def _phook_initialize(self):
        """Initialize plugin."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "pluginstoload",
            [],
            list,
            "plugins to load on startup",
            readonly=True,
        )

        self.api("plugins.core.events:event.add")(
            "ev_plugin_loaded",
            self.plugin_id,
            description=["Raised when any plugin is loaded"],
            arg_descriptions={
                "plugin": "The plugin name",
                "plugin_id": "The plugin id",
            },
        )
        self.api("plugins.core.events:event.add")(
            "ev_plugin_unloaded",
            self.plugin_id,
            description=["Raised when any plugin is unloaded"],
            arg_descriptions={
                "plugin": "The plugin name",
                "plugin_id": "The plugin id",
            },
        )
