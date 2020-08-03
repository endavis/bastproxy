"""
manages all plugins

#TODO: make all functions that add things use kwargs instead of a table

How plugin loading works on startup:
1. Plugin directories are scanned for basic plugin information
    see readpluginforinformation and scan_plugin_for_info
2. Find the list of plugins to load
    the pluginstoload variable is used. If it is empty, then plugins
      that have REQUIRED=True will be loaded
3. Go through the list of plugins
  1. Import if it isn't already imported (goes in imported_plugins dictionary)
  2. Instantiate it (goes in loaded_plugins dictionary)
  3. Import and instantiate all dependencies
  4. Run initialize function of all instantiated plugins in dependency order
"""
import glob
import os
import sys
import inspect
import operator
import fnmatch
import re
import time
import traceback
import pprint

import libs.argp as argp
from libs.dependency import PluginDependencyResolver
from libs.persistentdict import PersistentDict
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin

REQUIREDRE = re.compile(r'^REQUIRED = (?P<value>.*)$')
ISPLUGINRE = re.compile(r'^class Plugin\(.*\):$')

class PluginMgr(BasePlugin):
  """
  a class to manage plugins
  """
  def __init__(self):
    """
    initialize the instance
    """
    BasePlugin.__init__(self,
                        'Plugin Manager', #name,
                        'plugins', #short_name,
                        "/__init__.py", #plugin_path
                        "$base_plugin_dir$", # base_plugin_dir
                        "plugins.__init__", # full_import_location
                        "plugins" # plugin_id
                       )

    self.can_reload = False
    self.version = 1

    self.version_functions[1] = self.v1_update_plugins_to_load_location

    #key:   plugin_id
    #value: {'plugin', 'module'}
    # a dictionary of all plugins that have been imported but
    # are not instantiated
    self.imported_plugins = {}

    #key:   plugin_id
    #value: {'plugin', 'module'}
    # a dictionary of all plugins that have been instantiated
    # a plugin will have a key
    self.loaded_plugins = {}

    # key is plugin_id
    # a dictionary of all the plugin info
    self.all_plugin_info = {}

    # lookups by different types
    self.plugin_lookup_by_short_name = {}
    self.plugin_lookup_by_name = {}
    self.plugin_lookup_by_full_import_location = {}
    self.plugin_lookup_by_plugin_filepath = {}
    self.plugin_lookup_by_id = {}

    # find the base plugin path
    index = __file__.rfind(os.sep)
    if index == -1:
      self.base_plugin_dir = "." + os.sep
    else:
      self.base_plugin_dir = __file__[:index + 1]

    self.api('api.add')('isloaded', self._api_is_loaded)
    self.api('api.add')('getp', self._api_getp)
    self.api('api.add')('module', self._api_get_module)
    self.api('api.add')('allplugininfo', self._api_get_all_plugin_info)
    self.api('api.add')('savestate', self.savestate)

  def v1_update_plugins_to_load_location(self):
    """
    update the loaded plugins location
    """
    old_loadplugins_file = os.path.join(self.api.BASEPATH, 'data',
                                        'plugins', 'loadedplugins.txt')

    old_plugins_to_load = PersistentDict(old_loadplugins_file, 'c')

    new_plugins_to_load = self.api('setting.gets')('pluginstoload')

    for i in old_plugins_to_load:
      if '/' in i:
        i = i.replace('/', '.')
        i = i.replace('plugins.', '')
        i = i.replace('.py', '')
        if i[0] == '.':
          i = i[1:]
      self.api('send.msg')('setting plugin %s to load' % i, secondary=['upgrade'])
      new_plugins_to_load.append(i)

    self.api('settings.change')('pluginstoload', new_plugins_to_load)
    self.setting_values.sync()

    os.remove(old_loadplugins_file)

  # return the dictionary of all plugins
  def _api_get_all_plugin_info(self):
    """
    return the plugininfo dictionary

    returns:
      a dictionary with keys of plugin_id
    """
    return self.all_plugin_info

  def find_loaded_plugin(self, plugin):
    """
    find a plugin

    arguments:
      required:
        plugin - the plugin to find

    returns:
      if found, returns a plugin object, else returns None
    """
    return self.api('plugins.getp')(plugin)

  # get a plugin instance
  def _api_get_module(self, pluginname):
    """  returns the module of a plugin
    @Ypluginname@w  = the plugin to check for

    returns:
      the module for a plugin"""
    plugin = self.api('plugins.getp')(pluginname)

    if plugin:
      return self.loaded_plugins[plugin.plugin_id]['module']

    return None

  # get a plugin instance
  def _api_getp(self, plugin_name):
    """  get a loaded plugin instance
    @Ypluginname@w  = the plugin to get

    returns:
      if the plugin exists, returns a plugin instance, otherwise returns None"""

    # print('api.getp: finding %s' % pluginname)

    plugin = None

    if isinstance(plugin_name, basestring):
      if plugin_name in self.loaded_plugins:
        plugin = self.loaded_plugins[plugin_name]['plugininstance']
      if plugin_name in self.plugin_lookup_by_id:
        plugin = self.loaded_plugins[self.plugin_lookup_by_id[plugin_name]['plugininstance']]
      if plugin_name in self.plugin_lookup_by_short_name:
        plugin = self.loaded_plugins[self.plugin_lookup_by_short_name[plugin_name]]['plugininstance']
      if plugin_name in self.plugin_lookup_by_name:
        plugin = self.loaded_plugins[self.plugin_lookup_by_name[plugin_name]]['plugininstance']
      if plugin_name in self.plugin_lookup_by_full_import_location:
        plugin = self.loaded_plugins[self.plugin_lookup_by_full_import_location[plugin_name]]['plugininstance']
      if plugin_name in self.plugin_lookup_by_plugin_filepath:
        plugin = self.loaded_plugins[self.plugin_lookup_by_plugin_filepath[plugin_name]]['plugininstance']
    elif isinstance(plugin_name, BasePlugin):
      plugin = plugin_name

    # print('api.getp: found %s' % plugin)
    return plugin

  # check if a plugin is loaded
  def _api_is_loaded(self, pluginname):
    """  check if a plugin is loaded
    @Ypluginname@w  = the plugin to check for

    returns:
      True if the plugin is loaded, False if not"""
    plugin = self.api('plugins.getp')(pluginname)

    if plugin:
      return True

    return False

  # get a message of plugins in a package
  def _get_package_plugins(self, package):
    """
    create a message of plugins in a package

    arguments:
      required:
        package - the package name

    returns:
      a list of strings of plugins in the specified package
    """
    msg = []

    plist = []
    for plugin in [i['plugin'] for i in self.loaded_plugins.values()]:
      if plugin.package == package:
        plist.append(plugin)

    if plist:
      plugins = sorted(plist, key=operator.attrgetter('short_name'))
      limp = 'plugins.%s' % package
      mod = __import__(limp)
      try:
        desc = getattr(mod, package).DESCRIPTION
      except AttributeError:
        desc = ''
      msg.append('@GPackage: %s%s@w' % \
            (package, ' - ' + desc if desc else ''))
      msg.append('@G' + '-' * 75 + '@w')
      msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                          ('Short Name', 'Name',
                           'Author', 'Vers', 'Purpose'))
      msg.append('-' * 75)

      for tpl in plugins:
        msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                  (tpl.short_name, tpl.name,
                   tpl.author, tpl.version, tpl.purpose))
    else:
      msg.append('That is not a valid package')

    return msg

  # create a message of all plugins
  def _build_all_plugins_message(self):
    """
    create a message of all plugins

    returns:
      a list of strings
    """
    msg = []

    plugins = sorted([i['plugininstance'] for i in self.loaded_plugins.values()],
                     key=operator.attrgetter('package'))
    package_header = []
    msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                        ('Short Name', 'Name', 'Author', 'Vers', 'Purpose'))
    msg.append('-' * 75)
    for tpl in plugins:
      if tpl.package not in package_header:
        if package_header:
          msg.append('')
        package_header.append(tpl.package)
        limp = 'plugins.%s' % tpl.package
        mod = __import__(limp)
        try:
          desc = getattr(mod, tpl.package).DESCRIPTION
        except AttributeError:
          desc = ''
        msg.append('@GPackage: %s%s@w' % \
            (tpl.package, ' - ' + desc if desc else ''))
        msg.append('@G' + '-' * 75 + '@w')
      msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                  (tpl.short_name, tpl.name,
                   tpl.author, tpl.version, tpl.purpose))
    return msg

  # command to list plugins
  def _cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List plugins
      @CUsage@w: list
    """
    msg = []

    # if args['notloaded']:
    #   msg.extend(self._getnotloadedplugins())
    # elif args['changed']:
    #   msg.extend(self._getchangedplugins())
    if args['package']:
      msg.extend(self._get_package_plugins(args['package']))
    else:
      msg.extend(self._build_all_plugins_message())
    return True, msg

  @staticmethod
  def scan_plugin_for_info(path):
    """
    function to read info directly from a plugin file
    It looks for 2 items:
      a "REQUIRED" line
      a "Plugin" class

    arguments:
      required:
        path - the location to the file on disk
    returns:
      a dict with two keys: required and isplugin
    """
    info = {}
    info['required'] = False
    info['isplugin'] = False
    tfile = open(path)
    for tline in tfile:
      rmatch = REQUIREDRE.match(tline)
      pmatch = ISPLUGINRE.match(tline)
      if rmatch:
        gdict = rmatch.groupdict()
        if gdict['value'].lower() == 'true':
          info['required'] = True
      if pmatch:
        info['isplugin'] = True
      if info['required'] and info['isplugin']:
        break

    tfile.close()
    return info

  def read_all_plugin_information(self):
    """
    read all plugins and basic info
    """
    self.all_plugin_info = {}

    _module_list = imputils.find_modules(self.base_plugin_dir, prefix='plugins.')
    _module_list.sort()

    # go through the plugins and read information from them
    for module in _module_list:
      full_path = module['fullpath']
      plugin_path = module['fullpath'].replace(self.base_plugin_dir, '')
      plugin_id = module['plugin_id']
      # print plugin_id

      if plugin_id in ['_baseclass']:
        continue

      info = self.scan_plugin_for_info(full_path)
      if info['isplugin']:
        plugin = {'plugin_path':plugin_path, 'required':info['required'],
                  'fullpath':full_path, 'plugin_id':plugin_id}
        self.all_plugin_info[plugin_id] = plugin

  def load_single_plugin(self, plugin_id, exit_on_error=False):
    """
    load a plugin
      1) import Plugin - _import_single_plugin via preinitialize_plugin
      2) instantiate Plugin - _instantiate_plugin via preinitialize_plugin
      3) check for dependencies - load_plugin
          import all dependencies
            instantiate all dependencies
            add to dependency list
      4) run initialize function in dependency order
          single - initialize_plugin
          multiple - initialize_multiple_plugins

    arguments:
      required:
        plugin_id - the plugin to load

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      True if the plugin was loaded, False otherwise
    """
    # print('test loading: %s' % plugin_id)

    # if the plugin is required, set exit_to_error to True
    exit_on_error = exit_on_error or self.all_plugin_info[plugin_id]['required']
    return_value, dependencies = self.preinitialize_plugin(plugin_id,
                                                           exit_on_error=exit_on_error)
    if not return_value:
      self.api('send.error')('Could not preinitialize plugin %s' % plugin_id)
      if exit_on_error:
        sys.exit(1)
      return False

    plugin_classes = []

    new_dependencies = set(dependencies)
    # print('new_dependencies', new_dependencies)
    for tplugin_id in new_dependencies:
      plugin = self.loaded_plugins[tplugin_id]
      plugin_classes.append(plugin)

    plugin_classes.append(self.loaded_plugins[plugin_id])

    broken_modules = [tplugin_id for tplugin_id in new_dependencies \
                          if tplugin_id in self.imported_plugins \
                            and not self.imported_plugins[tplugin_id]['imported'] and \
                            not self.imported_plugins[tplugin_id]['dev']]

    # print('plugin_classes', plugin_classes)
    # print('broken_modules', broken_modules)
    dependency_solver = PluginDependencyResolver(self, plugin_classes, broken_modules)
    plugin_load_order, unresolved_dependencies = dependency_solver.resolve()
    if unresolved_dependencies:
      self.api('send.error')('The following dependencies could not be loaded:')
      for dep in unresolved_dependencies:
        self.api('send.error')(dep)
      if exit_on_error:
        sys.exit(1)
      return False

    # print('load_single_plugin: %s' % plugin_id)
    # print('loadorder: %s' % loadorder)
    self.initialize_multiple_plugins(plugin_load_order, exit_on_error=exit_on_error)

  def preinitialize_plugin(self, plugin_id, exit_on_error=False):
    """
    import a plugin
    instantiate a plugin instance
    return the dependencies

    arguments:
      required:
        plugin_id - the plugin to load

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      a tuple of two items
      1) a bool that specifies if the plugin was preinitialized
      2) a list of other plugins that the plugin depends on
    """
    if plugin_id in self.loaded_plugins:
      return True, self.loaded_plugins[plugin_id]['plugininstance'].dependencies
    # print('preload_plugin %s' % plugin_id)
    try:
      plugin_info = self.all_plugin_info[plugin_id]
    except KeyError:
      self.api('send.error')('Could not find plugin %s' % plugin_id)
      return False, []

    try:
      plugin_dict = self.imported_plugins[plugin_id]
    except KeyError:
      plugin_dict = None

    if not plugin_dict:
      if self._import_single_plugin(plugin_info['fullpath'], exit_on_error):
        if self._instantiate_plugin(plugin_id, exit_on_error):
          plugin_dict = self.loaded_plugins[plugin_id]

          # print 'preload_plugin finished %s' % plugin_id
          # print 'plugin_info: %s' % plugin_info
          # print 'all_plugin_info: %s' % self.all_plugin_info[plugin_id]
          # print 'loaded_plugins: %s' % self.loaded_plugins[plugin_id]

          all_dependencies = []

          dependencies = self.loaded_plugins[plugin_id]['plugininstance'].dependencies

          for dependency in dependencies:
            return_value, new_dependencies = self.preinitialize_plugin(dependency)
            if return_value:
              all_dependencies.append(dependency)
              all_dependencies.extend(new_dependencies)

          return True, all_dependencies

    return False, []

  def _import_single_plugin(self, full_file_path, exit_on_error=False):
    """
    import a plugin module

    arguments:
      required:
        fullpath - the full path to the file on disk

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      True if the plugin was imported, False otherwise
    """
    #print 'fullpath: importing %s' % full_file_path
    plugin_path = full_file_path.replace(self.base_plugin_dir, '')
    if '__init__' in plugin_path:
      return False
    success, msg, module, full_import_location = \
      imputils.importmodule(plugin_path,
                            self.base_plugin_dir,
                            self, 'plugins')
    plugin_id = full_import_location.replace('plugins.', '')
    plugin = {'module':module, 'full_import_location':full_import_location,
              'plugin_id':plugin_id,
              'required':self.all_plugin_info[plugin_id]['required'],
              'plugin_path':plugin_path, 'base_plugin_dir':self.base_plugin_dir,
              'plugininstance':None, 'short_name':None, 'name':None,
              'purpose':None, 'author':None, 'version':None,
              'dev':False}

    if msg == 'dev module':
      plugin['dev'] = True

    if module:
      plugin['short_name'] = module.SNAME
      plugin['name'] = module.NAME
      plugin['purpose'] = module.PURPOSE
      plugin['author'] = module.AUTHOR
      plugin['version'] = module.VERSION
      plugin['importedtime'] = time.time()

    self.imported_plugins[plugin_id] = plugin

    if success:
      plugin['imported'] = True
    elif not success:
      plugin['imported'] = False
      if msg == 'error':
        self.api('send.error')(
            'Could not import plugin %s' % plugin_id)
        if exit_on_error:
          sys.exit(1)
        return False

    return True

  def _instantiate_plugin(self, plugin_id, exit_on_error=False):
    """
    instantiate a single plugin

    arguments:
      required:
        plugin_id - the plugin to load

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      True if the plugin was instantiated, False otherwise
    """
    # print('_instantiate_plugin %s' % plugin_id)
    plugin = self.imported_plugins[plugin_id]

    try:
      plugin_instance = plugin['module'].Plugin(plugin['module'].NAME,
                                                plugin['module'].SNAME,
                                                plugin['plugin_path'],
                                                plugin['base_plugin_dir'],
                                                plugin['full_import_location'],
                                                plugin['plugin_id'])
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')('could not instantiate instance for plugin %s' % plugin_id)
      if exit_on_error:
        sys.exit(1)
      else:
        return False

    plugin_instance.author = plugin['module'].AUTHOR
    plugin_instance.purpose = plugin['module'].PURPOSE
    plugin_instance.version = plugin['module'].VERSION

    # add to loaded plugins and remove from imported plugins
    self.loaded_plugins[plugin_id] = self.imported_plugins[plugin_id]
    del self.imported_plugins[plugin_id]

    # set the plugin instance
    self.loaded_plugins[plugin_id]['plugininstance'] = plugin_instance
    self.loaded_plugins[plugin_id]['isinitialized'] = False

    self.plugin_lookup_by_id[plugin_id] = plugin_id
    self.plugin_lookup_by_short_name[plugin_instance.short_name] = plugin_id
    self.plugin_lookup_by_name[plugin_instance.name] = plugin_id
    self.plugin_lookup_by_full_import_location[plugin_instance.full_import_location] = plugin_id
    self.plugin_lookup_by_plugin_filepath[plugin_instance.plugin_path] = plugin_id

    plugins_to_load = self.api('setting.gets')('pluginstoload')
    if plugin_id not in plugins_to_load:
      plugins_to_load.append(plugin_id)
    self.api('setting.change')('pluginstoload', plugins_to_load)

    # print('_instantiate_plugin finished %s' % plugin_id)
    return True

  def _load_plugins_on_startup(self):
    """
    load plugins on startup
    start with plugins that have REQUIRED=True, then move
    to plugins that were loaded in the config
    """
    self.api('send.msg')('Reading all plugin information')
    self.read_all_plugin_information()

    plugins_to_load = self.api('setting.gets')('pluginstoload')

    # pp = pprint.PrettyPrinter(indent=4)
    # pp.pprint(self.all_plugin_info)

    required_plugins = [plugin['plugin_id'] for plugin in self.all_plugin_info.values() \
                           if plugin['required']]

    # add all required plugins
    plugins_to_load = list(set(required_plugins + plugins_to_load))

    # print('plugins_to_load: %s' % plugins_to_load)
    self.load_multiple_plugins(plugins_to_load)

    for plugin in self.loaded_plugins.values():
      found = False
      if not plugin['isinitialized']:
        found = True
        self.api('send.error')('Plugin %s has not been correctly loaded' % \
                                  plugin['plugin_id'])
    if found:
      sys.exit(1)

  def load_multiple_plugins(self, plugins_to_load, exit_on_error=False):
    """
    load a list of plugins

    plugins_to_load example:
      ['core.errors', 'core.events', 'core.log', 'core.commands',
       'core.colors', 'core.utils', 'core.timers']

    arguments:
      required:
        plugins_to_load - a list of plugin_ids to load

      optional:
        exit_on_error - if True, the program will exit on an error
    """
    print "load_multiple_plugins: %s" % plugins_to_load
    for plugin in plugins_to_load:
      if plugin not in self.loaded_plugins:
        self.load_single_plugin(plugin, exit_on_error)

  def initialize_multiple_plugins(self, plugins, exit_on_error=False):
    """
    run the load function for a list of plugins

    plugins example:
    ['core.errors', 'core.events', 'core.log', 'core.commands',
     'core.colors', 'core.utils', 'core.timers']

    arguments:
      required:
        plugins - a list of plugin_ids to initialize

      optional:
        exit_on_error - if True, the program will exit on an error
    """
    #print "pluginlist_runload: %s" % plugins
    for tplugin in plugins:
      self.initialize_plugin(self.loaded_plugins[tplugin], exit_on_error)

  # load a plugin
  def initialize_plugin(self, plugin, exit_on_error=False):
    """
    check dependencies and run the initialize

    arguments:
      required:
        plugin - the plugin to initialize, the dict from loaded_plugins

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      True if the plugin was initialized, False otherwise
    """
    if plugin['isinitialized']:
      return
    self.api('send.client')('%-30s : attempting to initialize (%s : %s)' % \
			    (plugin['plugin_id'], plugin['short_name'], plugin['name']))
    self.api('send.msg')('%-30s : attempting to initialize (%s : %s)' % \
              (plugin['plugin_id'], plugin['short_name'], plugin['name']))
    try:
      plugin['plugininstance'].initialize()
      plugin['isinitialized'] = True
      self.api('send.client')('%-30s : successfully initialized (%s : %s)' % \
			    (plugin['plugin_id'], plugin['short_name'], plugin['name']))
      self.api('send.msg')('%-30s : successfully initialize (%s : %s)' % \
                (plugin['plugin_id'], plugin['short_name'], plugin['name']))

      self.api('events.eraise')('plugin_%s_loaded' % plugin['short_name'], {})
      self.api('events.eraise')('plugin_loaded', {'plugin':plugin['short_name']})
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')(
          "load: could not run the initialize function for %s." \
                                              % plugin['short_name'])
      imputils.deletemodule(plugin['full_import_location'])
      self.api('send.error')('could not instantiate plugin %s' % \
                                plugin['plugin_id'])
      if exit_on_error:
        sys.exit(1)
      return False

    return True

  # get stats for this plugin
  def get_stats(self):
    """
    return stats for events

    returns:
      a dict of statistics
    """
    stats = {}
    stats['Base Sizes'] = {}

    stats['Base Sizes']['showorder'] = ['Class', 'Api', 'loaded_plugins',
                                        'all_plugin_info']
    stats['Base Sizes']['loaded_plugins'] = '%s bytes' % \
                                      sys.getsizeof(self.loaded_plugins)
    stats['Base Sizes']['all_plugin_info'] = '%s bytes' % \
                                      sys.getsizeof(self.all_plugin_info)

    stats['Base Sizes']['Class'] = '%s bytes' % sys.getsizeof(self)
    stats['Base Sizes']['Api'] = '%s bytes' % sys.getsizeof(self.api)

    stats['Plugins'] = {}
    stats['Plugins']['showorder'] = ['Total', 'Loaded']
    stats['Plugins']['Total'] = len(self.all_plugin_info)
    stats['Plugins']['Loaded'] = len(self.loaded_plugins)

    # bad_plugins = self._updateall_plugin_info()

    # stats['Plugins']['Bad'] = len(bad_plugins)

    return stats

  def shutdown(self, _=None):
    """
    do tasks on shutdown
    """
    self.savestate()

  # save all plugins
  def savestate(self, _=None):
    """
    save all plugins
    """
    BasePlugin.savestate(self)

    for i in self.loaded_plugins.values():
      i['plugininstance'].savestate()

  # initialize this plugin
  def initialize(self):
    """
    initialize plugin
    """
    self.api('setting.add')('pluginstoload', [], list,
                            'plugins to load on startup',
                            readonly=True)

    BasePlugin.initialize(self)

    self._load_plugins_on_startup()

    self.api('log.adddtype')(self.short_name)
    self.api('log.console')(self.short_name)
    self.api('log.adddtype')('upgrade')
    self.api('log.console')('upgrade')

    BasePlugin._load_commands(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description="list plugins")
    parser.add_argument('-n',
                        "--notloaded",
                        help="list plugins that are not loaded",
                        action="store_true")
    parser.add_argument('-c',
                        "--changed",
                        help="list plugins that are load but are changed on disk",
                        action="store_true")
    parser.add_argument('package',
                        help='the to list',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self._cmd_list,
                             lname='Plugin Manager',
                             parser=parser)

    # parser = argp.ArgumentParser(add_help=False,
    #                              description="load a plugin")
    # parser.add_argument('plugin',
    #                     help='the plugin to load, don\'t include the .py',
    #                     default='',
    #                     nargs='?')
    # self.api('commands.add')('load',
    #                          self._cmd_load,
    #                          lname='Plugin Manager',
    #                          parser=parser)

    self.api('timers.add')('global_save', self.savestate, 60, unique=True, log=False)

    self.api('events.register')('proxy_shutdown', self.shutdown)
