# Project: bastproxy
# Filename: libs/plugins/reloadutils.py
#
# File Description: adds a cache to support plugin reloading
# and plugin info
#
# By: Bast
"""Module for managing plugin cache with reloading support.

This module provides the `ReloadHelper` class, which allows for the management of
plugin cache and supports reloading of plugins. It includes methods for adding,
retrieving, and removing cache entries for plugins, making it a valuable tool for
plugin management in an application.

Key Components:
    - ReloadHelper: A class that manages plugin cache and supports reloading.
    - Methods for adding, retrieving, and removing cache entries for plugins.

Features:
    - Add cache entries for plugins.
    - Retrieve cache entries for plugins.
    - Remove cache entries for plugins.

Usage:
    - Instantiate ReloadHelper to create an object that manages plugin cache.
    - Use `add.cache` API to add data to the cache.
    - Use `get.plugin.cache` API to retrieve cache for a plugin.
    - Use `remove.plugin.cache` API to remove the cache for a plugin.

Classes:
    - `ReloadHelper`: Represents a class that manages plugin cache and supports
        reloading.

"""
# Standard Library

# 3rd Party

# Project
from typing import Any

from libs.api import API, AddAPI


class ReloadHelper:
    """Class for managing plugin cache with reloading support."""

    def __init__(self) -> None:
        """Initialize the ReloadHelper instance.

        This constructor initializes the ReloadHelper instance, setting up the API
        and the reload cache for managing plugin data.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.api = API(owner_id=f"{__name__}")
        self.reload_cache = {}
        self.api("libs.api:add.apis.for.object")(__name__, self)

    @AddAPI("add.cache", description="add data to the cache")
    def _api_add_cache(self, plugin_id: str, data_name: str, data: Any) -> None:
        if plugin_id not in self.reload_cache:
            self.reload_cache[plugin_id] = {}
        self.reload_cache[plugin_id][data_name] = data

    @AddAPI("get.plugin.cache", description="get cache for a plugin")
    def _api_get_plugin_cache(self, plugin_id: str) -> dict:
        """Retrieve cache for a plugin.

        This method retrieves the cache entries for a specified plugin from the
        reload cache. If the plugin is not found in the cache, an empty dictionary
        is returned.

        Args:
            plugin_id: The identifier of the plugin whose cache is to be retrieved.

        Returns:
            dict: The cache entries for the specified plugin.

        Raises:
            None

        """
        return self.reload_cache.get(plugin_id, {})

    @AddAPI("remove.plugin.cache", description="remove the cache for a plugin")
    def _api_remove_plugin_cache(self, plugin_id: str) -> None:
        """Remove the cache for a plugin.

        This method removes the cache entries for a specified plugin from the
        reload cache. If the plugin is not found in the cache, no action is taken.

        Args:
            plugin_id: The identifier of the plugin whose cache is to be removed.

        Returns:
            None

        Raises:
            None

        """
        if plugin_id in self.reload_cache:
            del self.reload_cache[plugin_id]


HELPER = ReloadHelper()
