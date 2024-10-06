# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/reloadutils.py
#
# File Description: adds a cache to support plugin reloading
# and plugin info
#
# By: Bast
"""
holds data for reloading
"""
# Standard Library

# 3rd Party

# Project
from libs.api import API, AddAPI

class ReloadHelper:
    def __init__(self):
        self.api = API(owner_id=f"{__name__}")
        self.reload_cache = {}
        self.api('libs.api:add.apis.for.object')(__name__, self)

    @AddAPI('add.cache', description='add data to the cache')
    def _api_add_cache(self, plugin_id, name, data):
        if plugin_id not in self.reload_cache:
            self.reload_cache[plugin_id] = {}
        self.reload_cache[plugin_id][name] = data

    @AddAPI('get.plugin.cache', description='get cache for a plugin')
    def _api_get_plugin_cache(self, plugin_id):
        return self.reload_cache[plugin_id] if plugin_id in self.reload_cache else {}

    @AddAPI('remove.plugin.cache', description='remove the cache for a plugin')
    def _api_remove_plugin_cache(self, plugin_id):
        if plugin_id in self.reload_cache:
            del self.reload_cache[plugin_id]


HELPER = ReloadHelper()
