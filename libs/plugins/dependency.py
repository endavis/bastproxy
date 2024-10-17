# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/plugins/dependency.py
#
# File Description: class to resolve plugin dependencies
#
# By: Bast
"""
libraries to resolve plugin dependencies
"""
# Standard Library
import sys

# 3rd Party

# Project
from libs.records import LogRecord

class PluginDependencyResolver(object):
    """
    a class to resolve dependencies in order to load plugins
    """
    def __init__(self, plugin_list: list, resolved=None, broken_modules=None):
        """
        init the class
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

    def resolve(self):
        """
        resolve dependencies
        """
        for plugin in self.plugin_list:
            self.resolve_helper(plugin)

        return self.resolved, self.unresolved

    def resolve_helper(self, plugin):
        """
        resolve helper
        """
        if plugin.plugin_id in self.resolved:
            return
        self.unresolved.append(plugin.plugin_id)
        for edge in plugin.plugininstance.dependencies:
            edge_plugin = None
            try:
                edge_plugin = self.plugin_lookup[edge]
            except KeyError:
                if 'REQUIRED' in plugin.module.__dict__ \
                       and plugin.module.REQUIRED:
                    LogRecord(f"Required plugin {plugin.plugin_id} could not be loaded, dependency {edge} would not load",
                              level='error', sources=[plugin.plugin_id, __name__])()
                    sys.exit(1)

            if edge_plugin:
                if plugin.plugin_id != edge_plugin.plugin_id:
                    if edge_plugin.plugin_id not in self.resolved:
                        if edge_plugin.plugin_id in self.unresolved:
                            raise Exception(f"Circular reference detected: {plugin.plugin_id} -> {plugin.plugin_id}")
                        self.resolve_helper(edge_plugin)
        self.resolved.append(plugin.plugin_id)
        self.unresolved.remove(plugin.plugin_id)
