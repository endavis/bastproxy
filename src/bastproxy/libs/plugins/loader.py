# Project: bastproxy
# Filename: libs/plugins/loader.py
#
# File Description: holds the plugin loading mechanics
# and plugin info
#
# By: Bast
"""Module for managing and loading plugins with tracking capabilities.

This module provides the `PluginLoader` class, which allows for the management and
loading of plugins. It includes methods for loading, unloading, reloading, and
tracking the state of plugins, making it a valuable tool for managing plugin-based
applications.

Key Components:
    - PluginLoader: A class that manages the loading and unloading of plugins.
    - Methods for loading, unloading, reloading, and tracking plugins.
    - Utility methods for handling plugin dependencies and state.

Features:
    - Automatic loading and unloading of plugins.
    - Management of plugin dependencies and state.
    - Notification system for tracking plugin changes and errors.
    - Comprehensive logging of plugin operations and errors.

Usage:
    - Instantiate PluginLoader to create an object that manages plugins.
    - Use `load_plugins_on_startup` to load core and client plugins on startup.
    - Load, unload, and reload plugins using provided methods.
    - Access plugin information and state through provided methods.

Classes:
    - `PluginLoader`: Represents a class that manages the loading and unloading of
        plugins.

"""

# Standard Library
import contextlib
import datetime
import sys
import traceback
import weakref
from collections.abc import KeysView
from functools import partial
from pathlib import Path

# 3rd Party
# Project
from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.libs.records import LogRecord
from bastproxy.plugins._baseplugin import BasePlugin, patch


class PluginLoader:
    """Manage the loading and unloading of plugins."""

    def __init__(self) -> None:
        """Initialize the PluginLoader.

        This method sets up the initial state of the PluginLoader, including
        initializing the API, setting up weak references to modules, and
        preparing the plugin information dictionary.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.api = API(owner_id=__name__)

        self.weak_references_to_modules = {}

        self.plugins_info: dict[str, PluginInfo] = {}
        self.base_plugin_dir = API.BASEPLUGINPATH
        packaged_plugins = Path(__file__).resolve().parents[2] / "plugins"
        self.plugin_search_paths: list[dict[str, Path | str]] = [
            {"path": self.base_plugin_dir, "prefix": "plugins.", "strip": ""},
        ]
        if packaged_plugins.exists():
            self.plugin_search_paths.append(
                {
                    "path": packaged_plugins,
                    "prefix": "bastproxy.plugins.",
                    "strip": "bastproxy.",
                }
            )

        self.api("libs.api:add.apis.for.object")(__name__, self)

    @AddAPI(
        "get.unloaded.plugins.in.memory",
        description="get all stale plugin modules in memory",
    )
    def _api_get_unloaded_plugins_in_memory(self) -> KeysView[str]:
        """Get all stale plugin modules in memory.

        This method retrieves all plugin modules that are currently in memory but
        have not been loaded.

        Args:
            None

        Returns:
            KeysView[str]: A view object that contains a list of keys of unloaded
                plugins.

        Raises:
            None

        """
        return self.weak_references_to_modules.keys()

    def remove_weakref(self, weakref_obj, module_import_path: str) -> None:
        """Remove a weak reference to a module.

        This method removes a weak reference to a module from the internal dictionary
        of weak references. It logs the removal of the stale module and deletes the
        reference if the module is no longer valid.

        Args:
            weakref_obj: The weak reference object pointing to the module.
            module_import_path: The import path of the module to remove.

        Returns:
            None

        Raises:
            None

        """
        old_object = weakref_obj()
        if not old_object and not self.api.shutdown:
            LogRecord(
                f"garbage collect stale module {module_import_path}",
                level="info",
                sources=[__name__],
            )()
            if module_import_path in self.weak_references_to_modules:
                del self.weak_references_to_modules[module_import_path]

    @AddAPI(
        "get.not.loaded.plugins",
        description="get a list of plugins that are not loaded",
    )
    def _api_get_not_loaded_plugins(self) -> list[str]:
        """Get a list of plugins that are not loaded.

        This method retrieves a list of plugins that are currently not loaded by
        comparing the list of all plugins with the list of loaded plugins.

        Args:
            None

        Returns:
            A sorted list of plugin IDs that are not loaded.

        Raises:
            None

        """
        if self.update_all_plugin_information():
            LogRecord(
                "conflicts with plugins, see console and correct",
                level="error",
                sources=[__name__],
            )()

        all_plugins_by_id = list(self.plugins_info.keys())

        loaded_plugins_by_id = self.api(f"{__name__}:get.loaded.plugins.list")()

        pdiff = set(all_plugins_by_id) - set(loaded_plugins_by_id)

        return sorted(pdiff)

    @AddAPI("get.all.plugins", description="get all plugins")
    def _api_get_all_plugins(self) -> KeysView[str]:
        """Get all plugins.

        This method retrieves all plugins currently managed by the PluginLoader.

        Args:
            None

        Returns:
            A view object that contains a list of all plugin IDs.

        Raises:
            None

        """
        return self.plugins_info.keys()

    @AddAPI("get.plugin.info", description="get the plugin info for a plugin")
    def _api_get_plugin_info(self, plugin_id: str) -> PluginInfo:
        """Get the plugin info for a plugin.

        This method retrieves the plugin information for a given plugin ID from the
        internal dictionary of plugins.

        Args:
            plugin_id: The ID of the plugin to retrieve information for.

        Returns:
            The information object for the specified plugin.

        Raises:
            KeyError: If the plugin ID is not found in the plugins_info dictionary.

        """
        return self.plugins_info[plugin_id]

    @AddAPI("does.plugin.exist", description="check if a plugin exists")
    def _api_does_plugin_exist(self, plugin_id: str) -> bool:
        """Check if a plugin exists.

        This method checks if a plugin with the given ID exists in the internal
        dictionary of plugins.

        Args:
            plugin_id: The ID of the plugin to check.

        Returns:
            True if the plugin exists, False otherwise.

        Raises:
            None

        """
        return plugin_id in self.plugins_info

    @AddAPI(
        "plugin.get.changed.files",
        description=("get the list of files that have changed since loading for a plugin"),
    )
    def _api_plugin_get_changed_files(self, plugin: str) -> list[dict]:
        """Get the list of files that have changed since loading for a plugin.

        This method retrieves a list of files that have changed since the plugin was
        loaded. It helps in tracking modifications to the plugin files.

        Args:
            plugin: The plugin for which to get the list of changed files.

        Returns:
            A list of dictionaries containing information about the changed files.

        Raises:
            KeyError: If the plugin is not found in the plugins_info dictionary.

        """
        return self.plugins_info[plugin].get_changed_files()

    @AddAPI(
        "plugin.get.invalid.python.files",
        description=("get the list of files that have invalid python syntax for a plugin"),
    )
    def _api_plugin_get_invalid_python_files(self, plugin: str) -> list[dict]:
        """Get the list of files that have invalid Python syntax for a plugin.

        This method retrieves a list of files that have invalid Python syntax since
        the plugin was loaded. It helps in identifying syntax errors in the plugin
        files.

        Args:
            plugin: The plugin for which to get the list of invalid Python files.

        Returns:
            A list of dictionaries containing information about the invalid Python
            files.

        Raises:
            KeyError: If the plugin is not found in the plugins_info dictionary.

        """
        return self.plugins_info[plugin].get_invalid_python_files()

    @AddAPI("get.loaded.plugins.list", description="get the list of loaded plugins")
    def _api_get_loaded_plugins_list(self) -> list[str]:
        """Get the list of loaded plugins.

        This method retrieves a list of plugins that are currently loaded by
        checking the runtime information of each plugin.

        Args:
            None

        Returns:
            A list of plugin IDs that are currently loaded.

        Raises:
            None

        """
        return [
            plugin_info.plugin_id
            for plugin_info in self.plugins_info.values()
            if plugin_info.runtime_info.is_loaded
        ]

    @AddAPI("get.packages.list", description="get the list of packages")
    def _api_get_packages_list(self, active_only: bool = False) -> list[str]:
        """Get the list of packages.

        This method retrieves a list of packages managed by the PluginLoader. If
        `active_only` is True, only packages with loaded plugins are included.

        Args:
            active_only: A flag indicating whether to include only active packages.

        Returns:
            A list of package names.

        Raises:
            None

        """
        if active_only:
            packages = [
                plugin_info.package
                for plugin_info in self.plugins_info.values()
                if plugin_info.runtime_info.is_loaded
            ]
        else:
            packages = [plugin_info.package for plugin_info in self.plugins_info.values()]

        return list(set(packages))

    @AddAPI(
        "get.plugins.in.package",
        description="get the list of plugins in a package that have been loaded",
    )
    def _api_get_plugins_in_package(self, package: str) -> list[str]:
        """Get the list of plugins in a package that have been loaded.

        This method retrieves a list of plugins that belong to a specified package
        and have been loaded.

        Args:
            package: The package for which to get the list of loaded plugins.

        Returns:
            A list of plugin IDs that belong to the specified package and are loaded.

        Raises:
            None

        """
        return [
            plugin_id
            for plugin_id in self.api(f"{__name__}:get.loaded.plugins.list")()
            if self.plugins_info[plugin_id].package == package
        ]

    @AddAPI("get.plugin.instance", description="get a loaded plugin instance")
    def _api_get_plugin_instance(self, plugin_name: str) -> BasePlugin | None:
        """Get a loaded plugin instance.

        This method retrieves the instance of a loaded plugin based on the provided
        plugin name. If the plugin name is valid and the plugin is loaded, the
        instance is returned. If the plugin name is already an instance of
        BasePlugin, it is returned directly.

        Args:
            plugin_name: The name of the plugin to retrieve the instance for.

        Returns:
            The instance of the loaded plugin, or None if the plugin is not found.

        Raises:
            None

        """
        plugin_instance = None

        if isinstance(plugin_name, str):
            if (
                plugin_name in self.plugins_info
                and self.plugins_info[plugin_name].runtime_info.is_loaded
            ):
                plugin_instance = self.plugins_info[plugin_name].runtime_info.plugin_instance
        elif isinstance(plugin_name, BasePlugin):
            plugin_instance = plugin_name

        if not plugin_instance and not self.api.startup:
            LogRecord(
                f"api_get_plugin_instance - plugin not found: {plugin_name}",
                level="debug",
                sources=[__name__],
                stack_info=True,
            )()

        return plugin_instance

    @AddAPI("is.plugin.id", description="check if a str is a plugin id")
    def _api_is_plugin_id(self, plugin_id: str) -> bool:
        """Check if a string is a plugin ID.

        This method checks if a given string is a valid plugin ID by looking it up
        in the internal dictionary of plugins.

        Args:
            plugin_id: The string to check if it is a plugin ID.

        Returns:
            True if the string is a plugin ID, False otherwise.

        Raises:
            None

        """
        return plugin_id in self.plugins_info

    @AddAPI("is.plugin.loaded", description="check if a plugin is loaded")
    def _api_is_plugin_loaded(self, pluginname: str) -> bool:
        """Check if a plugin is loaded.

        This method checks if a plugin with the given name is currently loaded by
        verifying its runtime information.

        Args:
            pluginname: The name of the plugin to check.

        Returns:
            True if the plugin is loaded, False otherwise.

        Raises:
            None

        """
        if pluginname in self.plugins_info:
            return self.plugins_info[pluginname].runtime_info.is_loaded

        return False

    @AddAPI("is.plugin.instantiated", description="check if a plugin has an instance")
    def _api_is_plugin_instantiated(self, pluginname: str) -> bool:
        """Check if a plugin has an instance.

        This method checks if a plugin with the given name has an instance
        created and stored in the internal dictionary of plugins.

        Args:
            pluginname: The name of the plugin to check.

        Returns:
            True if the plugin has an instance, False otherwise.

        Raises:
            None

        """
        if pluginname in self.plugins_info:
            return bool(self.plugins_info[pluginname].runtime_info.plugin_instance)

        return False

    def update_all_plugin_information(self) -> None:
        """Update all plugin information.

        This method updates the information for all plugins by scanning the plugin
        directory, reading plugin metadata, and updating the internal dictionary of
        plugins. It identifies new plugins, updates existing plugin information, and
        removes stale plugins. It also logs the process and any errors encountered.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        LogRecord("Read all plugin information", level="info", sources=[__name__])()

        packages: list = []
        plugins: list = []
        errors: dict[str, tuple] = {}

        for search in self.plugin_search_paths:
            search_path = search["path"]
            prefix = search["prefix"]
            strip_prefix = search.get("strip", "")

            pkg, plug, err = imputils.find_packages_and_plugins(search_path, prefix)

            for p in plug:
                plugin_id = p["plugin_id"]
                if strip_prefix and plugin_id.startswith(strip_prefix):
                    p["plugin_id"] = plugin_id[len(strip_prefix) :]
            packages.extend(pkg)
            plugins.extend(plug)
            errors.update(err)

        LogRecord(
            f"Found {len(plugins)} total plugins from {self.base_plugin_dir}",
            level="info",
            sources=[__name__],
        )()
        if len(plugins) < 10:
            LogRecord(
                f"WARNING: Only found {len(plugins)} plugins: {[p['plugin_id'] for p in plugins]}",
                level="warning",
                sources=[__name__],
            )()

        LogRecord("Done finding plugins", level="debug", sources=[__name__])()

        old_plugins_info = self.plugins_info
        new_plugins_info = {}

        # go through the plugins and read information from them
        for found_plugin in plugins:
            LogRecord(
                f"{found_plugin['plugin_id']:<30} : Reading plugin information",
                level="info",
                sources=[__name__],
            )()
            if found_plugin["plugin_id"] in old_plugins_info:
                plugin_info = old_plugins_info[found_plugin["plugin_id"]]
                plugin_info.is_plugin = True
                plugin_info.files = {}
            else:
                plugin_info = PluginInfo(plugin_id=found_plugin["plugin_id"])
            plugin_info.package_init_file_path = found_plugin["package_init_file_path"]
            plugin_info.package_path = found_plugin["package_path"]
            plugin_info.package_import_location = found_plugin["package_import_location"]
            plugin_info.data_directory = self.api.BASEDATAPLUGINPATH / plugin_info.plugin_id

            plugin_info.update_from_init()

            if plugin_info.package == "plugins.core":
                plugin_info.is_required = True

            if plugin_info.package_import_location in errors:
                plugin_info.import_errors.append(errors[plugin_info.package_import_location])

            plugin_info.get_file_data()

            new_plugins_info[plugin_info.plugin_id] = plugin_info

        self.plugins_info = new_plugins_info

        # warn about plugins whose path is no longer valid
        removed_plugins = set(old_plugins_info.keys()) - set(self.plugins_info.keys())
        for plugin_id in removed_plugins:
            if plugin_id in old_plugins_info and old_plugins_info[plugin_id].runtime_info:
                LogRecord(
                    [
                        f"Loaded Plugin {plugin_id}'s path is no longer valid: "
                        f"{old_plugins_info[plugin_id].package_path}",
                        "If this plugin is no longer valid, please unload it",
                    ],
                    level="error",
                    sources=[__name__],
                )()

    def _import_single_plugin(self, plugin_id: str, exit_on_error: bool = False) -> bool:
        """Import a single plugin.

        This method imports a single plugin based on the provided plugin ID. It
        attempts to import the plugin module, handles any import errors, and logs
        the process. If the plugin has a patch file, it applies the patch to the
        base plugin.

        Args:
            plugin_id: The ID of the plugin to import.
            exit_on_error: A flag indicating whether to exit on error.

        Returns:
            True if the plugin was imported successfully, False otherwise.

        Raises:
            None

        """
        # import the plugin
        LogRecord(f"{plugin_id:<30} : attempting import", level="info", sources=[__name__])()
        plugin_info = self.plugins_info[plugin_id]
        plugin_info.update_from_init()
        return_info = imputils.importmodule(plugin_info.plugin_class_import_location)
        if (
            not return_info["success"]
            or not return_info["module"]
            or not return_info["full_import_location"]
        ):
            plugin_info.runtime_info.is_imported = False

            if return_info["message"] == "error":
                exc_msg = [
                    line.strip()
                    for line in traceback.format_exception(return_info["exception"])
                    if line.strip() not in ["\n", ""]
                ]

                msg = [f"Could not import plugin {plugin_id}", *exc_msg]
                LogRecord(msg, level="error", sources=[__name__])()
                if exit_on_error:
                    sys.exit(1)

            return False

        plugin_info.runtime_info.is_imported = True
        plugin_info.runtime_info.imported_time = datetime.datetime.now(datetime.UTC)

        LogRecord(f"{plugin_id:<30} : imported successfully", level="info", sources=[__name__])()

        # check for patches to the base plugin
        if (
            patch_file := plugin_info.find_file_by_name("_patch_base.py")
        ) and not plugin_info.has_been_reloaded:
            if len(patch_file) > 1:
                LogRecord(
                    f"{plugin_id:<30} : found more than one _patch_base.py file, only "
                    "the first will be used",
                    level="warning",
                    sources=[__name__],
                )()
            patch_file = patch_file[0]
            LogRecord(
                f"{plugin_id:<30} : attempting to patch base",
                level="info",
                sources=[__name__],
            )()
            if patch(patch_file["full_import_location"]):
                LogRecord(
                    f"{plugin_id:<30} : patching base successful",
                    level="info",
                    sources=[__name__],
                )()
            else:
                LogRecord(
                    f"{plugin_id:<30} : patching base failed",
                    level="error",
                    sources=[__name__],
                )()

        return True

    def _instantiate_single_plugin(self, plugin_id: str, exit_on_error: bool = False) -> bool:
        """Instantiate a single plugin.

        This method creates an instance of a plugin based on the provided plugin ID.
        It attempts to instantiate the plugin class, handles any instantiation errors,
        and logs the process. If the instantiation fails, the plugin is unloaded.

        Args:
            plugin_id: The ID of the plugin to instantiate.
            exit_on_error: A flag indicating whether to exit on error.

        Returns:
            True if the plugin was instantiated successfully, False otherwise.

        Raises:
            None

        """
        plugin_info = self.plugins_info[plugin_id]
        LogRecord(f"{plugin_id:<30} : creating instance", level="info", sources=[__name__])()

        if not plugin_info.plugin_class_import_location:
            LogRecord(
                f"Could not find module for {plugin_id}",
                level="error",
                sources=[__name__],
            )()
            if exit_on_error:
                sys.exit(1)
            else:
                return False
        try:
            plugin_module = sys.modules[str(plugin_info.plugin_class_import_location)]
            plugin_instance = plugin_module.Plugin(plugin_info.plugin_id, plugin_info)
        except Exception:  # pylint: disable=broad-except
            LogRecord(
                f"Could not instantiate plugin {plugin_id}",
                level="error",
                sources=[__name__],
                exc_info=True,
            )()
            if exit_on_error:
                sys.exit(1)
            else:
                self.api(f"{__name__}:unload.plugin")(plugin_id)
                return False

        # set the plugin instance
        plugin_info.runtime_info.plugin_instance = plugin_instance
        plugin_info.runtime_info.is_loaded = False

        LogRecord(
            f"{plugin_id:<30} : instance created successfully",
            level="info",
            sources=[__name__],
        )()

        return True

    # run the initialize method for a plugin
    def _run_initialize_single_plugin(self, plugin_id: str, exit_on_error: bool = False) -> bool:
        """Run the initialize method for a single plugin.

        This method runs the initialize method for a single plugin based on the
        provided plugin ID. It checks if the plugin has already been initialized,
        logs the process, and handles any initialization errors. If the
        initialization fails, the plugin is unloaded.

        Args:
            plugin_id: The ID of the plugin to initialize.
            exit_on_error: A flag indicating whether to exit on error.

        Returns:
            True if the plugin was initialized successfully, False otherwise.

        Raises:
            None

        """
        # don't do anything if the plugin has already had its initialize method ran
        plugin_info = self.plugins_info[plugin_id]
        if plugin_info.runtime_info.is_loaded:
            return True
        LogRecord(
            f"{plugin_info.plugin_id:<30} : attempting to run initialize method for "
            f"({plugin_info.name})",
            level="info",
            sources=[__name__, plugin_info.plugin_id],
        )()

        if not plugin_info.runtime_info.plugin_instance:
            LogRecord(
                f"{plugin_info.plugin_id:<30} : plugin instance is None, not initializing",
                level="error",
                sources=[__name__, plugin_info.plugin_id],
            )()
            return False

        # run the initialize function
        try:
            plugin_info.runtime_info.plugin_instance.initialize()

        except Exception:  # pylint: disable=broad-except
            LogRecord(
                f"could not run the initialize method for {plugin_info.plugin_id}",
                level="error",
                sources=[__name__, plugin_info.plugin_id],
                exc_info=True,
            )()
            if exit_on_error:
                LogRecord(
                    f"{plugin_info.plugin_id:<30} : INITIALIZE METHOD WAS NOT SUCCESSFUL",
                    level="error",
                    sources=[__name__, plugin_info.plugin_id],
                )()
                sys.exit(1)
            self.api(f"{__name__}:unload.plugin")(plugin_id)
            return False

        LogRecord(
            f"{plugin_info.plugin_id:<30} : successfully ran initialize method "
            f"({plugin_info.name})",
            level="info",
            sources=[__name__, plugin_info.plugin_id],
        )()

        LogRecord(
            f"{plugin_info.plugin_id:<30} : successfully loaded",
            level="info",
            sources=[__name__, plugin_info.plugin_id],
        )()

        return True

    @AddAPI("load.plugins", "load a list of plugins")
    def _api_load_plugins(
        self,
        plugins_to_load: list[str],
        exit_on_error: bool = False,
        check_dependencies: bool = True,
    ) -> dict[str, list[str] | set[str]]:
        """Load a list of plugins.

        This method loads a list of plugins by importing, instantiating, and
        initializing them. It handles errors during the loading process and logs
        the progress. If `check_dependencies` is True, it also checks for plugin
        dependencies.

        Args:
            plugins_to_load: A list of plugin IDs to load.
            exit_on_error: A flag indicating whether to exit on error.
            check_dependencies: A flag indicating whether to check for plugin
            dependencies.

        Returns:
            A dictionary containing lists of loaded plugins, bad plugins, and
            already loaded plugins.

        Raises:
            None

        """
        plugins_not_loaded = [
            plugin_id
            for plugin_id in plugins_to_load
            if not self.plugins_info[plugin_id].runtime_info.is_loaded
        ]
        already_loaded_plugins = set(plugins_to_load) - set(plugins_not_loaded)

        bad_plugins = []

        # import bastproxy.plugins
        for plugin_id in plugins_not_loaded:
            LogRecord(
                f"{plugin_id:<30} : attempting to load",
                level="info",
                sources=[__name__],
            )()
            if not self._import_single_plugin(plugin_id, exit_on_error=exit_on_error):
                bad_plugins.append(plugin_id)

        plugins_not_loaded = [
            plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins
        ]

        # instantiate plugins
        for plugin_id in plugins_not_loaded:
            if not self._instantiate_single_plugin(plugin_id, exit_on_error=exit_on_error):
                bad_plugins.append(plugin_id)

        plugins_not_loaded = [
            plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins
        ]

        # check dependencies
        # if check_dependencies:
        #     if plugin_instance := self.loaded_plugins_info[
        #         plugin_id
        #     ].plugininstance:
        #         dependencies = plugin_instance.dependencies
        #     else:
        #         dependencies = []

        #     for dependency in dependencies:
        #         # import and instantiate dependencies and add their dependencies
        #         # to list
        #         return_value, new_dependencies = self.preinitialize_plugin(dependency)
        #         if return_value:
        #             all_dependencies.append(dependency)
        #             all_dependencies.extend(new_dependencies)
        #

        plugins_not_loaded = [
            plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins
        ]

        # run the initialize method for each plugin
        for plugin_id in plugins_not_loaded:
            if not self._run_initialize_single_plugin(plugin_id, exit_on_error=exit_on_error):
                bad_plugins.append(plugin_id)

        loaded_plugins = [
            plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins
        ]

        # clean up plugins that
        #   were not imported
        #   their initialize method did not run
        #   could not be instantiated
        for plugin_id in plugins_to_load:
            plugin_info = self.plugins_info[plugin_id]
            if not plugin_info.runtime_info.is_loaded:
                if plugin_info.runtime_info.plugin_instance:
                    del plugin_info.runtime_info.plugin_instance
                    plugin_info.runtime_info.plugin_instance = None
                for item in plugin_info.files:
                    with contextlib.suppress(Exception):
                        del sys.modules[item["full_import_location"]]
                with contextlib.suppress(Exception):
                    del sys.modules[plugin_info.package_import_location]

        if bad_plugins and exit_on_error:
            sys.exit(1)

        return {
            "loaded_plugins": loaded_plugins,
            "bad_plugins": bad_plugins,
            "already_loaded_plugins": already_loaded_plugins,
        }

    @AddAPI("reload.plugin", "reload a plugin")
    def _api_reload_plugin(self, plugin_id: str) -> bool:
        """Reload a plugin.

        This method reloads a plugin by first unloading it and then loading it again.
        It ensures that the plugin is properly reloaded with its latest state and
        dependencies.

        Args:
            plugin_id: The ID of the plugin to reload.

        Returns:
            True if the plugin was reloaded successfully, False otherwise.

        Raises:
            None

        """
        return (
            self.api(f"{__name__}:load.plugins")(
                [plugin_id], exit_on_error=False, check_dependencies=True
            )
            if self.api(f"{__name__}:unload.plugin")(plugin_id)
            else False
        )

    @AddAPI("set.plugin.is.loaded", "set the is_loaded flag for a plugin")
    def _api_set_plugin_is_loaded(self, plugin_id: str) -> None:
        """Set the is_loaded flag for a plugin.

        This method sets the is_loaded flag to True for the specified plugin ID,
        indicating that the plugin is currently loaded.

        Args:
            plugin_id: The ID of the plugin to set the is_loaded flag for.

        Returns:
            None

        Raises:
            KeyError: If the plugin ID is not found in the plugins_info dictionary.

        """
        self.plugins_info[plugin_id].runtime_info.is_loaded = True

    @AddAPI("unload.plugin", "unload a plugin")
    def _api_unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin.

        This method unloads a plugin by running its uninitialize method, removing
        it from the list of plugins to load at startup, and deleting its instance
        and imported modules. It ensures that the plugin is properly unloaded and
        its runtime information is reset.

        Args:
            plugin_id: The ID of the plugin to unload.

        Returns:
            True if the plugin was unloaded successfully, False otherwise.

        Raises:
            KeyError: If the plugin ID is not found in the plugins_info dictionary.

        """
        try:
            plugin_info = self.plugins_info[plugin_id]
        except Exception:
            return False

        if (
            plugin_info.runtime_info.plugin_instance
            and not plugin_info.runtime_info.plugin_instance.can_reload_f
        ):
            LogRecord(
                f"{plugin_info.plugin_id:<30} : this plugin cannot be unloaded "
                f"({plugin_info.name})",
                level="error",
                sources=[__name__, plugin_info.plugin_id],
            )()
            return False

        try:
            # run the uninitialize method if it exists
            if plugin_info.runtime_info.plugin_instance:
                if plugin_info.runtime_info.is_loaded:
                    plugin_info.runtime_info.plugin_instance.uninitialize()

                LogRecord(
                    f"{plugin_info.plugin_id:<30} : successfully ran uninitialize "
                    f"method ({plugin_info.name})",
                    level="info",
                    sources=[__name__, plugin_info.plugin_id],
                )()
            else:
                LogRecord(
                    f"{plugin_info.plugin_id:<30} : plugin instance not found ({plugin_info.name})",
                    level="info",
                    sources=[__name__, plugin_info.plugin_id],
                )()

        except Exception:  # pylint: disable=broad-except
            LogRecord(
                f"unload: error running the uninitialize method for {plugin_info.plugin_id}",
                level="error",
                sources=[__name__, plugin_info.plugin_id],
                exc_info=True,
            )()
            return False

        # remove from pluginstoload so it doesn't load at startup
        plugins_to_load = self.api("plugins.core.settings:get")(
            "plugins.core.pluginm", "pluginstoload"
        )
        if plugin_info.plugin_id in plugins_to_load:
            plugins_to_load.remove(plugin_info.plugin_id)
            self.api("plugins.core.settings:change")(
                "plugins.core.pluginm", "pluginstoload", plugins_to_load
            )

        if plugin_info.runtime_info.plugin_instance:
            # delete the instance
            del plugin_info.runtime_info.plugin_instance

        modules_to_delete = []
        if plugin_info.runtime_info.is_imported:
            modules_to_delete.extend(
                item
                for item in sys.modules
                if item.startswith(plugin_info.package_import_location)
                and getattr(sys.modules[item], "CANRELOAD", True)
            )

        for item in modules_to_delete:
            cb_weakref = partial(self.remove_weakref, module_import_path=item)
            self.weak_references_to_modules[item] = weakref.ref(sys.modules[item], cb_weakref)
            if imputils.deletemodule(item):
                LogRecord(
                    f"{plugin_info.plugin_id:<30} : deleting imported module {item} "
                    f"was successful ({plugin_info.name})",
                    level="info",
                    sources=[__name__, plugin_info.plugin_id],
                )()
            else:
                LogRecord(
                    f"{plugin_info.plugin_id:<30} : deleting imported module {item} "
                    f"failed ({plugin_info.name})",
                    level="error",
                    sources=[__name__, plugin_info.plugin_id],
                )()

        plugin_info.has_been_reloaded = True

        # set the appropriate plugin_info.runtime_info attributes to None
        plugin_info.reset_runtime_info()

        return True

    def _load_core_and_client_plugins_on_startup(self) -> None:
        """Load core and client plugins on startup.

        This method loads all core and client plugins during the startup process.
        It first updates the plugin information, then loads core plugins, and
        finally loads client plugins. If there are conflicts with plugins, it logs
        the errors and exits the application.

        Args:
            None

        Returns:
            None

        Raises:
            SystemExit: If there are conflicts with plugins.

        """
        if self.update_all_plugin_information():
            LogRecord(
                "conflicts with plugins, see console and correct",
                level="error",
                sources=[__name__],
            )(actor=f"{__name__}.read_all_plugin_information")
            sys.exit(1)

        # load all core plugins first
        core_plugins = [
            plugin_info.plugin_id
            for plugin_info in self.plugins_info.values()
            if plugin_info.package in ["plugins.core", "plugins.client"]
        ]

        LogRecord(
            f"Found {len(core_plugins)} core/client plugins: {core_plugins}",
            level="debug",
            sources=[__name__],
        )()

        # load plugin manager and then log plugin first
        if "plugins.core.log" in core_plugins:
            core_plugins.remove("plugins.core.log")
            core_plugins.insert(0, "plugins.core.log")

        self.api(f"{__name__}:load.plugins")(
            core_plugins, exit_on_error=True, check_dependencies=False
        )

    def load_plugins_on_startup(self) -> None:
        """Load plugins on startup.

        This method loads core and client plugins during the startup process. It
        initializes the loading process, logs the progress, and raises an event
        after loading the plugins. It also warns about any plugins that had import
        errors.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        LogRecord("Loading core and client plugins", level="info", sources=[__name__])()
        self._load_core_and_client_plugins_on_startup()
        LogRecord("Finished Loading core and client plugins", level="info", sources=[__name__])()

        LogRecord(
            f"ev_{__name__}_post_startup_plugins_loaded: Started",
            level="debug",
            sources=[__name__],
        )()

        self.api("plugins.core.events:raise.event")(f"ev_{__name__}_post_startup_plugins_loaded")

        LogRecord(
            f"ev_{__name__}_post_startup_plugins_loaded: Finish",
            level="debug",
            sources=[__name__],
        )()

        # warn about plugins that had import errors
        for plugin_info in self.plugins_info.values():
            if plugin_info.import_errors:
                for error in plugin_info.import_errors:
                    traceback_message = traceback.format_exception(error[1])
                    traceback_message = [
                        item.strip() for item in traceback_message if item and item != "\n"
                    ]
                    LogRecord(
                        [
                            f"Plugin {plugin_info.plugin_id} had an import error: ",
                            *traceback_message,
                        ],
                        level="warning",
                        sources=[__name__],
                    )()

    @AddAPI("fuzzy.match.plugin.id", description="find a plugin id from a string")
    def _api_fuzzy_match_plugin_id(
        self, plugin_id_string: str, active_only: bool = False
    ) -> tuple[str, str]:
        """Find a plugin ID from a string using fuzzy matching.

        This method attempts to find a plugin ID from a given string using fuzzy
        matching. It splits the input string to identify the package and plugin
        names, then uses fuzzy matching to find the best match for the package and
        plugin within the list of available packages and loaded plugins.

        Args:
            plugin_id_string: The input string to match against plugin IDs.
            active_only: A flag indicating whether to include only active packages.

        Returns:
            A tuple containing the matched package and plugin IDs.

        Raises:
            None

        """
        LogRecord(
            f"_api_fuzzy_match_plugin_id: attempting to find {plugin_id_string}",
            level="debug",
            sources=[__name__],
        )()

        psplit = plugin_id_string.split(".", 1)

        LogRecord(
            f"_api_fuzzy_match_plugin_id: {psplit = }",
            level="debug",
            sources=[__name__],
        )()

        if len(psplit) not in [2, 3]:
            return "", ""

        if len(psplit) == 2:
            tmp_package = f"plugins.{psplit[0]}"
            tmp_plugin = psplit[1]
        else:
            tmp_package = f"plugins.{psplit[1]}"
            tmp_plugin = psplit[2]

        LogRecord(
            f"_api_fuzzy_match_plugin_id: {tmp_package = }, {tmp_plugin = }",
            level="debug",
            sources=[__name__],
        )()

        package_list = self.api(f"{__name__}:get.packages.list")(active_only)

        # try and find the package
        new_package = self.api("plugins.core.fuzzy:get.best.match")(
            tmp_package, tuple(package_list), scorer="token_set_ratio", score_cutoff=90
        )

        if not new_package:
            return "", ""

        if not tmp_plugin:
            return new_package, ""

        loaded_list = self.api(f"{__name__}:get.loaded.plugins.list")()

        # try and find the plugin
        new_plugin = self.api("plugins.core.fuzzy:get.best.match")(
            f"{new_package}.{tmp_plugin}", tuple(loaded_list), scorer="token_set_ratio"
        )

        LogRecord(
            f"_api_fuzzy_match_plugin_id: {new_package = }, {new_plugin = }",
            level="debug",
            sources=[__name__],
        )()

        return new_package, new_plugin
