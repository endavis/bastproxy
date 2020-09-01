"""
libraries to resolve plugin dependencies
"""
import sys

class PluginDependencyResolver(object):
  """
  a class to resolve dependencies in order to load plugins
  """
  def __init__(self, pluginmanager, plugins, resolved=None, brokenmodules=None):
    """
    init the class
    """
    self.pluginmanager = pluginmanager
    self.plugins = plugins
    self.unresolved = []
    self.resolved = []
    self.brokenmodules = []
    self.pluginlookup = {}
    for plugin in plugins:
      self.pluginlookup[plugin['plugin_id']] = plugin
    if resolved:
      self.resolved.extend(resolved)
    if brokenmodules:
      self.brokenmodules.extend(brokenmodules)

  def resolve(self):
    """
    resolve dependencies
    """
    for plugin in self.plugins:
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
        eplugin = self.pluginlookup[edge]
      except KeyError:
        if 'REQUIRED' in plugin['module'].__dict__ \
            and plugin['module'].REQUIRED:
          self.pluginmanager.api('send.error')(
              'Required plugin %s could not be loaded, dependency %s' \
              ' would not load' % \
                (plugin['plugin_id'], edge))
          sys.exit(1)

      if plugin['plugin_id'] != eplugin['plugin_id']:
        if eplugin['plugin_id'] not in self.resolved:
          if eplugin['plugin_id'] in self.unresolved:
            raise Exception('Circular reference detected: %s -> %s' % \
                                (plugin['plugin_id'], eplugin['plugin_id']))
          self.resolve_helper(eplugin)
    self.resolved.append(plugin['plugin_id'])
    self.unresolved.remove(plugin['plugin_id'])
