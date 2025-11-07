# Project: bastproxy
# Filename: libs/plugins/dependency.py
#
# File Description: class to resolve plugin dependencies
#
# By: Bast
"""Module for resolving plugin dependencies in the bastproxy project.

This module provides the `PluginDependencyResolver` class, which is used to resolve
dependencies among plugins to ensure they are loaded in the correct order. It includes
methods for resolving dependencies and handling circular references, making it a
valuable tool for managing plugin relationships in the application.

Key Components:
    - PluginDependencyResolver: A class that resolves plugin dependencies.
    - Methods for resolving dependencies and handling circular references.

Features:
    - Automatic resolution of plugin dependencies.
    - Detection and handling of circular references.
    - Logging of errors when required plugins cannot be loaded.

Usage:
    - Instantiate PluginDependencyResolver with a list of plugins to resolve
        dependencies.
    - Use `resolve` method to start the dependency resolution process.
    - Access resolved and unresolved plugins through the class attributes.

Classes:
    - `PluginDependencyResolver`: Represents a class that resolves plugin dependencies.

"""

# Standard Library
import sys

# 3rd Party
# Project
from libs.records import LogRecord


class PluginDependencyResolver:
    """Resolve plugin dependencies.

    This class resolves dependencies among plugins to ensure they are loaded in the
    correct order. It includes methods for resolving dependencies and handling circular
    references.

    """

    def __init__(
        self,
        plugin_list: list,
        resolved: list[str] | None = None,
        broken_modules: list[str] | None = None,
    ) -> None:
        """Initialize the PluginDependencyResolver.

        This method initializes the PluginDependencyResolver with a list of plugins,
        resolved plugins, and broken modules. It also creates a lookup dictionary for
        quick access to plugins by their ID.

        Args:
            plugin_list: The list of plugins to resolve dependencies for.
            resolved: The list of already resolved plugins.
            broken_modules: The list of broken modules.

        """
        self.plugin_list = plugin_list
        self.unresolved: list[str] = []
        self.resolved: list[str] = []
        self.broken_modules: list[str] = []
        self.plugin_lookup: dict = {}
        for plugin in plugin_list:
            self.plugin_lookup[plugin.plugin_id] = plugin
        if resolved:
            self.resolved.extend(resolved)
        if broken_modules:
            self.broken_modules.extend(broken_modules)

    def resolve(self) -> tuple[list[str], list[str]]:
        """Resolve plugin dependencies.

        This method resolves the dependencies among plugins to ensure they are loaded
        in the correct order. It iterates through the list of plugins and uses the
        resolve_helper method to handle each plugin's dependencies.

        Returns:
            A tuple containing two lists:
            - resolved: The list of resolved plugins.
            - unresolved: The list of unresolved plugins.

        Raises:
            Exception: If a circular reference is detected among the plugins.

        Example:
            >>> resolver = PluginDependencyResolver(plugin_list)
            >>> resolved, unresolved = resolver.resolve()
            >>> print(resolved, unresolved)

        """
        for plugin in self.plugin_list:
            self.resolve_helper(plugin)

        return self.resolved, self.unresolved

    def resolve_helper(self, plugin) -> None:
        """Resolve a plugin's dependencies helper method.

        This method assists in resolving the dependencies of a given plugin by
        recursively resolving its dependencies and ensuring there are no circular
        references.

        Args:
            plugin: The plugin whose dependencies need to be resolved.

        Returns:
            None

        Raises:
            Exception: If a circular reference is detected among the plugins.

        Example:
            >>> resolver = PluginDependencyResolver(plugin_list)
            >>> resolver.resolve_helper(plugin)

        """
        if plugin.plugin_id in self.resolved:
            return
        self.unresolved.append(plugin.plugin_id)
        for edge in plugin.plugininstance.dependencies:
            edge_plugin = None
            try:
                edge_plugin = self.plugin_lookup[edge]
            except KeyError:
                if "REQUIRED" in plugin.module.__dict__ and plugin.module.REQUIRED:
                    LogRecord(
                        f"Required plugin {plugin.plugin_id} could not be loaded, "
                        f"dependency {edge} would not load",
                        level="error",
                        sources=[plugin.plugin_id, __name__],
                    )()
                    sys.exit(1)

            if edge_plugin and plugin.plugin_id != edge_plugin.plugin_id:
                if edge_plugin.plugin_id not in self.resolved:
                    if edge_plugin.plugin_id in self.unresolved:
                        raise Exception(
                            f"Circular reference detected: {plugin.plugin_id} -> "
                            f"{plugin.plugin_id}"
                        )
                    self.resolve_helper(edge_plugin)
        self.resolved.append(plugin.plugin_id)
        self.unresolved.remove(plugin.plugin_id)
