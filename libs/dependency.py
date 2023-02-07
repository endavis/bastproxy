"""
libraries to resolve plugin dependencies
"""
# Standard Library
import sys

# 3rd Party

# Project

class PluginDependencyResolver(object):
    """
    a class to resolve dependencies in order to load plugins
    """
    def __init__(self, plugin_manager, plugin_list, resolved=None, broken_modules=None):
        """
        init the class
        """
        self.plugin_manager = plugin_manager
        self.plugin_list = plugin_list
        self.unresolved = []
        self.resolved = []
        self.broken_modules = []
        self.plugin_lookup = {}
        for plugin in plugin_list:
            self.plugin_lookup[plugin['plugin_id']] = plugin
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
        if plugin['plugin_id'] in self.resolved:
            return
        self.unresolved.append(plugin['plugin_id'])
        for edge in plugin['plugininstance'].dependencies:
            try:
                edge_plugin = self.plugin_lookup[edge]
            except KeyError:
                if 'REQUIRED' in plugin['module'].__dict__ \
                       and plugin['module'].REQUIRED:
                    self.plugin_manager.api('libs.io:send:error')(
                        'Required plugin %s could not be loaded, dependency %s' \
                        ' would not load' % \
                          (plugin['plugin_id'], edge))
                    sys.exit(1)

            if plugin['plugin_id'] != edge_plugin['plugin_id']:
                if edge_plugin['plugin_id'] not in self.resolved:
                    if edge_plugin['plugin_id'] in self.unresolved:
                        raise Exception('Circular reference detected: %s -> %s' % \
                                            (plugin['plugin_id'], edge_plugin['plugin_id']))
                    self.resolve_helper(edge_plugin)
        self.resolved.append(plugin['plugin_id'])
        self.unresolved.remove(plugin['plugin_id'])
