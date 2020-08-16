# pylint: disable=too-many-lines
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
import ast

import libs.argp as argp
from libs.dependency import PluginDependencyResolver
from libs.persistentdict import PersistentDict
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin

REQUIREDRE = re.compile(r'^REQUIRED = (?P<value>.*)$')
SNAMERE = re.compile(r'^SNAME = \'(?P<value>.*)\'$')
NAMERE = re.compile(r'^NAME = \'(?P<value>.*)\'$')
AUTHORRE = re.compile(r'^AUTHOR = \'(?P<value>.*)\'$')
VERSIONRE = re.compile(r'^VERSION = (?P<value>.*)$')
PURPOSERE = re.compile(r'^PURPOSE = \'(?P<value>.*)\'$')
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
                        "core.plugins" # plugin_id
                       )

    self.author = 'Bast'
    self.purpose = 'Manage plugins'
    self.can_reload = False
    self.version = 1

    self.version_functions[1] = self.v1_update_plugins_to_load_location

    #key:   plugin_id
    #value: {'plugin', 'module'}
    # a dictionary of all plugins that have been instantiated
    # sample entry:
    #{
    #   'short_name': 'log',
    #   'base_plugin_dir': '/mnt/d/src/Linux/games/bastproxy/bp/plugins/',
    #   'module': <module 'plugins.core.log' from '/mnt/d/src/Linux/games/bastproxy/bp/plugins/core/log.pyc'>,
    #   'purpose': 'Handle logging to file and console, errors',
    #   'plugin_path': 'core/log.py',
    #   'isimported': True,
    #   'name': 'Logging',
    #   'author': 'Bast',
    #   'isrequired': True,
    #   'dev': False,
    #   'version': 1,
    #   'full_import_location': 'plugins.core.log',
    #   'isinitialized': True,
    #   'plugin_id': 'core.log',
    #   'importedtime': 1596924665.221632,
    #   'plugininstance': <plugins.core.log.Plugin object at 0x7fdcd54f34d0>
    # }
    self.loaded_plugins = {}

    # key is plugin_id
    # a dictionary of all the plugin info
    # sample entry
    # {
    #   'plugin_path': 'core/log.py',
    #   'isrequired': True,
    #   'fullpath': '/mnt/d/src/Linux/games/bastproxy/bp/plugins/core/log.py',
    #   'plugin_id': 'core.log'
    # }
    self.all_plugin_info_on_disk = {}

    # lookups by different types
    self.plugin_lookup_by_short_name = {}
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
    self.api('api.add')('loadedpluginslist', self._api_get_loaded_plugins_list)
    self.api('api.add')('packageslist', self._api_get_packages_list)

  def _api_get_loaded_plugins_list(self):
    """
    get the list of loaded plugins
    """
    return self.loaded_plugins.keys()

  def _api_get_packages_list(self):
    """
    return the list of packages
    """
    packages = []
    for i in self.loaded_plugins:
      packages.append(i.split('.')[0])

    packages = list(set(packages))

    return packages

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
    return self.all_plugin_info_on_disk

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

    plugin = None

    if isinstance(plugin_name, basestring):
      if plugin_name in self.loaded_plugins:
        plugin = self.loaded_plugins[plugin_name]['plugininstance']
      if plugin_name in self.plugin_lookup_by_id:
        plugin = self.loaded_plugins[self.plugin_lookup_by_id[plugin_name]]['plugininstance']
      if plugin_name in self.plugin_lookup_by_short_name:
        plugin = self.loaded_plugins[self.plugin_lookup_by_short_name[plugin_name]]['plugininstance']
      if plugin_name in self.plugin_lookup_by_full_import_location:
        plugin = self.loaded_plugins[self.plugin_lookup_by_full_import_location[plugin_name]]['plugininstance']
      if plugin_name in self.plugin_lookup_by_plugin_filepath:
        plugin = self.loaded_plugins[self.plugin_lookup_by_plugin_filepath[plugin_name]]['plugininstance']
    elif isinstance(plugin_name, BasePlugin):
      plugin = plugin_name

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

  # get plugins that are change on disk
  def _getchangedplugins(self):
    """
    create a message of plugins that are changed on disk
    """
    msg = []

    plugins = [i['plugininstance'] for i in self.loaded_plugins.values()]

    msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                        ('Short Name', 'Name', 'Author', 'Vers', 'Purpose'))
    msg.append('-' * 75)

    found = False
    for tpl in plugins:
      if tpl.is_changed_on_disk():
        found = True
        msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                  (tpl.short_name, tpl.name,
                   tpl.author, tpl.version, tpl.purpose))

    if found:
      return msg

    return ['No plugins are changed on disk.']

  # get all not loaded plugins
  def _getnotloadedplugins(self):
    """
    create a message of all not loaded plugins
    """
    msg = []
    conflicts = self.read_all_plugin_information()
    if conflicts:
      self.api('send.msg')('conflicts with plugins, see console and correct')

    loaded_plugins = self.loaded_plugins.keys()
    all_plugins = self.all_plugin_info_on_disk.keys()
    bad_plugins = [plugin_id for plugin_id in self.all_plugin_info_on_disk \
                      if self.all_plugin_info_on_disk[plugin_id]['isvalidpythoncode'] is False]

    pdiff = set(all_plugins) - set(loaded_plugins)

    if pdiff:
      msg.insert(0, '-' * 75)
      msg.insert(0, "%-20s : %-25s %-10s %-5s %s@w" % \
                          ('Location', 'Name', 'Author', 'Vers', 'Purpose'))
      msg.insert(0, 'The following plugins are not loaded')

      for plugin_id in sorted(pdiff):
        plugin_info = self.all_plugin_info_on_disk[plugin_id]
        msg.append("%-20s : %-25s %-10s %-5s %s@w" % \
                    (plugin_id,
                     plugin_info['name'],
                     plugin_info['author'],
                     plugin_info['version'],
                     plugin_info['purpose']))

    if bad_plugins:
      msg.append('')
      msg.append('The following files are not valid python code')
      for plugin_id in sorted(bad_plugins):
        plugin_info = self.all_plugin_info_on_disk[plugin_id]
        msg.append("%-20s : %-25s %-10s %-5s %s@w" % \
                    (plugin_id,
                     plugin_info['name'],
                     plugin_info['author'],
                     plugin_info['version'],
                     plugin_info['purpose']))

    if not msg:
      msg.append('There are no plugins that are not loaded')

    return msg

  # command to list plugins
  def _cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List plugins
      @CUsage@w: list
    """
    msg = []

    if args['notloaded']:
      msg.extend(self._getnotloadedplugins())
    elif args['changed']:
      msg.extend(self._getchangedplugins())
    elif args['package']:
      msg.extend(self._get_package_plugins(args['package']))
    else:
      msg.extend(self._build_all_plugins_message())
    return True, msg

  @staticmethod
  def scan_plugin_for_info(path):
    """
    function to read info directly from a plugin file
    It looks for the foillowing items:
      a "REQUIRED" line
      a "Plugin" class
      an SNAME line
      a NAME line
      a PURPOSE line
      an AUTHOR line
      a VERSION line

    arguments:
      required:
        path - the location to the file on disk
    returns:
      a dict with the keys: required, isplugin, sname, isvalidpythoncode
    """
    info = {}
    info['isrequired'] = False
    info['isplugin'] = False
    info['name'] = 'not found'
    info['sname'] = 'not found'
    info['author'] = 'not found'
    info['purpose'] = 'not found'
    info['version'] = 'not found'
    tfile = open(path)
    contents = tfile.read()
    tfile.close()

    try:
      ast.parse(contents)
      info['isvalidpythoncode'] = True
    except SyntaxError:
      print 'will not compile set for %s' % path
      info['isvalidpythoncode'] = False


    for tline in contents.split('\n'):
      if info['name'] == 'not found':
        name_match = NAMERE.match(tline)
        if name_match:
          gdict = name_match.groupdict()
          info['name'] = gdict['value']
          continue

      if info['sname'] == 'not found':
        short_name_match = SNAMERE.match(tline)
        if short_name_match:
          gdict = short_name_match.groupdict()
          info['sname'] = gdict['value']
          continue

      if info['purpose'] == 'not found':
        purpose_match = PURPOSERE.match(tline)
        if purpose_match:
          gdict = purpose_match.groupdict()
          info['purpose'] = gdict['value']
          continue

      if info['author'] == 'not found':
        author_match = AUTHORRE.match(tline)
        if author_match:
          gdict = author_match.groupdict()
          info['author'] = gdict['value']
          continue

      if info['version'] == 'not found':
        version_match = VERSIONRE.match(tline)
        if version_match:
          gdict = version_match.groupdict()
          info['version'] = gdict['value']
          continue

      required_match = REQUIREDRE.match(tline)
      if required_match:
        gdict = required_match.groupdict()
        if gdict['value'].lower() == 'true':
          info['isrequired'] = True
        continue

      plugin_match = ISPLUGINRE.match(tline)
      if plugin_match:
        info['isplugin'] = True
        continue

      if info['isrequired'] and info['isplugin'] and info['sname'] and \
         info['name'] and info['author'] and info['purpose'] and info['version']:
        break

    return info

  def read_all_plugin_information(self):
    """
    read all plugins and basic info

    returns:
      a bool, True if conflicts with short name were found, False if not
    """
    self.all_plugin_info_on_disk = {}

    _module_list = imputils.find_modules(self.base_plugin_dir, prefix='plugins.')
    _module_list.sort()

    conflicts = False

    snames = []
    # go through the plugins and read information from them
    for module in _module_list:
      full_path = module['fullpath']
      plugin_path = module['fullpath'].replace(self.base_plugin_dir, '')
      plugin_id = module['plugin_id']

      if plugin_id in ['_baseplugin']:
        continue

      info = self.scan_plugin_for_info(full_path)
      if 'isvalidpythoncode' not in info:
        print '%s info does not have isvalidpythoncode key' % full_path
      if info['isplugin']:
        if info['sname'] not in snames:
          snames.append(info['sname'])
        else:
          self.api('send.error')('at least two plugins have the same short name: %s, please correct' % info['sname'])
          conflicts = True
        info['plugin_path'] = plugin_path
        info['fullpath'] = full_path
        info['plugin_id'] = plugin_id

        self.all_plugin_info_on_disk[plugin_id] = info

    return conflicts

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
    # if the plugin is required, set exit_to_error to True
    exit_on_error = exit_on_error or self.all_plugin_info_on_disk[plugin_id]['isrequired']

    # preinitialize plugin (imports and instantiates)
    return_value, dependencies = self.preinitialize_plugin(plugin_id,
                                                           exit_on_error=exit_on_error)
    if not return_value:
      self.api('send.error')('Could not preinitialize plugin %s' % plugin_id)
      if exit_on_error:
        sys.exit(1)
      return False

    plugin_classes = []

    # build dependencies
    new_dependencies = set(dependencies)
    for tplugin_id in new_dependencies:
      plugin = self.loaded_plugins[tplugin_id]
      plugin_classes.append(plugin)

    plugin_classes.append(self.loaded_plugins[plugin_id])

    # get broken plugins that didn't import
    broken_modules = [tplugin_id for tplugin_id in new_dependencies \
                          if tplugin_id in self.loaded_plugins \
                            and not self.loaded_plugins[tplugin_id]['isimported'] and \
                            not self.loaded_plugins[tplugin_id]['dev']]

    # find the order the dependencies should be loaded
    dependency_solver = PluginDependencyResolver(self, plugin_classes, broken_modules)
    plugin_load_order, unresolved_dependencies = dependency_solver.resolve()
    if unresolved_dependencies:
      self.api('send.error')('The following dependencies could not be loaded:')
      for dep in unresolved_dependencies:
        self.api('send.error')(dep)
      if exit_on_error:
        sys.exit(1)
      return False

    # initiallize all plugins
    success = self.initialize_multiple_plugins(plugin_load_order, exit_on_error=exit_on_error)

    return success

  def preinitialize_plugin(self, plugin_id, exit_on_error=False):
    """
    import a plugin
    instantiate a plugin instance
    return the dependencies

    arguments:
      required:
        plugin_id - the plugin to preinitialize

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      a tuple of two items
      1) a bool that specifies if the plugin was preinitialized
      2) a list of other plugins that the plugin depends on
    """
    if plugin_id in self.loaded_plugins:
      return True, self.loaded_plugins[plugin_id]['plugininstance'].dependencies

    self.api('send.msg')('%-30s : attempting to load' % \
			    (plugin_id))

    try:
      plugin_info = self.all_plugin_info_on_disk[plugin_id]
    except KeyError:
      self.api('send.error')('Could not find plugin %s' % plugin_id)
      return False, []

    try:
      plugin_dict = self.loaded_plugins[plugin_id]
    except KeyError:
      plugin_dict = None

    if not plugin_dict:
      # import the plugin
      if self._import_single_plugin(plugin_info['fullpath'], exit_on_error):
        # instantiate the plugin
        if self._instantiate_plugin(plugin_id, exit_on_error):
          plugin_dict = self.loaded_plugins[plugin_id]

          all_dependencies = []

          # get dependencies
          dependencies = self.loaded_plugins[plugin_id]['plugininstance'].dependencies

          for dependency in dependencies:
            # import and instantiate dependencies and add their dependencies to list
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
    plugin_path = full_file_path.replace(self.base_plugin_dir, '')
    # don't import plugins class
    if '__init__' in plugin_path:
      return False

    # import the plugin
    success, msg, module, full_import_location = \
      imputils.importmodule(plugin_path,
                            self.base_plugin_dir,
                            self, 'plugins')
    if not success:
      return False

    # create the dictionary for the plugin
    plugin_id = full_import_location.replace('plugins.', '')
    plugin = {'module':module, 'full_import_location':full_import_location,
              'plugin_id':plugin_id,
              'isrequired':self.all_plugin_info_on_disk[plugin_id]['isrequired'],
              'plugin_path':plugin_path, 'base_plugin_dir':self.base_plugin_dir,
              'plugininstance':None, 'short_name':None, 'name':None,
              'purpose':None, 'author':None, 'version':None,
              'dev':False, 'isimported':False, 'isinitialized':False}

    if msg == 'dev module':
      plugin['dev'] = True

    if module:
      plugin['short_name'] = module.SNAME
      plugin['name'] = module.NAME
      plugin['purpose'] = module.PURPOSE
      plugin['author'] = module.AUTHOR
      plugin['version'] = module.VERSION
      plugin['importedtime'] = time.time()

    # add dictionary to loaded_plugins
    self.loaded_plugins[plugin_id] = plugin

    if success:
      plugin['isimported'] = True
    elif not success:
      plugin['isimported'] = False
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
    plugin = self.loaded_plugins[plugin_id]

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

    # set the plugin instance
    self.loaded_plugins[plugin_id]['plugininstance'] = plugin_instance
    self.loaded_plugins[plugin_id]['isinitialized'] = False

    # add plugin to lookups
    if plugin_instance.short_name in self.plugin_lookup_by_short_name:
      self.api('send.error')('plugin %s has a short name conflict with already loaded plugin %s' % \
                                (plugin_instance.plugin_path,
                                 self.plugin_lookup_by_short_name[plugin_id].plugin_instance.plugin_path))
    else:
      self.plugin_lookup_by_short_name[plugin_instance.short_name] = plugin_id

    self.plugin_lookup_by_full_import_location[plugin_instance.full_import_location] = plugin_id
    self.plugin_lookup_by_plugin_filepath[plugin_instance.plugin_path] = plugin_id
    self.plugin_lookup_by_id[plugin_id] = plugin_id

    # update plugins to load at startup
    plugins_to_load = self.api('setting.gets')('pluginstoload')
    if plugin_id not in plugins_to_load:
      plugins_to_load.append(plugin_id)
      self.api('setting.change')('pluginstoload', plugins_to_load)

    return True

  def _load_plugins_on_startup(self):
    """
    load plugins on startup
    start with plugins that have REQUIRED=True, then move
    to plugins that were loaded in the config
    """
    self.api('send.msg')('Reading all plugin information')
    conflicts = self.read_all_plugin_information()
    if conflicts:
      self.api('send.msg')('conflicts with plugins, see console and correct')
      sys.exit(1)

    plugins_to_load_setting = self.api('setting.gets')('pluginstoload')

    required_plugins = [plugin['plugin_id'] for plugin in self.all_plugin_info_on_disk.values() \
                           if plugin['isrequired']]

    # add all required plugins
    plugins_to_load = list(set(required_plugins + plugins_to_load_setting))

    # check to make sure all plugins exist on disk
    plugins_not_found = [plugin for plugin in plugins_to_load if plugin not in self.all_plugin_info_on_disk]
    if plugins_not_found:
      for plugin in plugins_not_found:
        self.api('send.error')(
            'plugin %s was marked to load at startup and no longer exists, removing from startup' % plugin)
        plugins_to_load_setting.remove(plugin)
        plugins_to_load.remove(plugin)
      self.api('setting.change')('pluginstoload', plugins_to_load_setting)

    self.load_multiple_plugins(plugins_to_load)

    # clean up plugins that were not imported, initialized, or instantiated
    for plugin in self.loaded_plugins.values():
      found = False
      if not plugin['isinitialized'] or not plugin['isimported'] or not plugin['plugininstance']:
        found = True
        self.api('send.error')('Plugin %s has not been correctly loaded' % \
                                  plugin['plugin_id'])
        self.unload_single_plugin(plugin['plugin_id'])

    if found:
      sys.exit(1)

  def load_multiple_plugins(self, plugins_to_load, exit_on_error=False):
    """
    load a list of plugins

    arguments:
      required:
        plugins_to_load - a list of plugin_ids to load
          plugins_to_load example:
            ['core.errors', 'core.events', 'core.log', 'core.commands',
            'core.colors', 'core.utils', 'core.timers']

      optional:
        exit_on_error - if True, the program will exit on an error
    """
    for plugin in plugins_to_load:
      if plugin not in self.loaded_plugins:
        self.load_single_plugin(plugin, exit_on_error)

  def initialize_multiple_plugins(self, plugins, exit_on_error=False):
    """
    run the load function for a list of plugins

    arguments:
      required:
        plugins - a list of plugin_ids to initialize
          plugins example:
          ['core.errors', 'core.events', 'core.log', 'core.commands',
          'core.colors', 'core.utils', 'core.timers']
      optional:
        exit_on_error - if True, the program will exit on an error

    return True if all plugins were initialized, False otherwise
    """
    all_plugins_initialized = True
    for tplugin in plugins:
      success = self.initialize_plugin(self.loaded_plugins[tplugin], exit_on_error)
      all_plugins_initialized = all_plugins_initialized and success

    return all_plugins_initialized

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
    # don't do anything if the plugin has already been initialized
    if plugin['isinitialized']:
      return True
    self.api('send.msg')('%-30s : attempting to initialize (%s : %s)' % \
              (plugin['plugin_id'], plugin['short_name'], plugin['name']))

    # run the initialize function
    try:
      plugin['plugininstance'].initialize()
      plugin['isinitialized'] = True
      self.api('send.msg')('%-30s : successfully initialized (%s : %s)' % \
                (plugin['plugin_id'], plugin['short_name'], plugin['name']))

      self.api('events.eraise')('plugin_%s_initialized' % plugin['short_name'], {})
      self.api('events.eraise')('plugin_initialized', {'plugin':plugin['short_name']})
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')(
          "load: could not run the initialize function for %s." \
                                              % plugin['short_name'])
      if exit_on_error:
        sys.exit(1)
        self.api('send.msg')('%-30s : DID NOT LOAD' % \
			                      (plugin['plugin_id']))
      return False

    self.api('send.msg')('%-30s : successfully loaded' % \
			    (plugin['plugin_id']))

    # update plugins_to_load
    plugins_to_load = self.api('setting.gets')('pluginstoload')
    if plugin['plugin_id'] not in plugins_to_load:
      plugins_to_load.append(plugin['plugin_id'])

    return True

  def unload_single_plugin(self, plugin_id):
    """
    unload a plugin
      1) run uninitialize function
      2) destroy instance
      3) remove from sys.modules
      4) remove from loaded_plugins
      5) remove from all the plugin lookup dictionaries

    arguments:
      required:
        plugin_id - the plugin to unload

      optional:
        exit_on_error - if True, the program will exit on an error

    returns:
      True if the plugin was unloaded, False otherwise
    """
    plugin = self.loaded_plugins[plugin_id]

    if plugin:
      if plugin['isrequired']:
        self.api('send.msg')('%-30s : this is a required plugin and cannot be unloaded (%s : %s)' % \
                  (plugin['plugin_id'], plugin['short_name'], plugin['name']))
        return False
      else:
        try:
          # run the uninitialize function if it exists
          if plugin['isinitialized']:
            plugin['plugininstance'].uninitialize()
          self.api('events.eraise')('plugin_%s_uninitialized' % plugin['short_name'], {})
          self.api('events.eraise')('plugin_uninitialized', {'name':plugin['short_name']})
          self.api('send.msg')('%-30s : successfully unitialized (%s : %s)' % \
                  (plugin['plugin_id'], plugin['short_name'], plugin['name']))

        except Exception: # pylint: disable=broad-except
          self.api('send.traceback')(
              "unload: had problems running the unload method for %s." \
                                    % plugin['plugin_id'])
          return False

        # remove from pluginstolload so it doesn't load at startup
        plugins_to_load = self.api('setting.gets')('pluginstoload')
        if plugin['plugin_id'] in plugins_to_load:
          plugins_to_load.remove(plugin['plugin_id'])
          self.api('setting.change')('pluginstoload', plugins_to_load)

        # clean up lookup dictionaries
        del self.plugin_lookup_by_short_name[plugin['short_name']]
        del self.plugin_lookup_by_full_import_location[plugin['full_import_location']]
        del self.plugin_lookup_by_plugin_filepath[plugin['plugin_path']]
        del self.plugin_lookup_by_id[plugin_id]

        if plugin['plugininstance']:
          # delete the instance
          del plugin['plugininstance']

        if plugin['isimported']:
          # delete the module
          print plugin
          success = imputils.deletemodule(plugin['full_import_location'])
          if success:
            self.api('send.msg')('%-30s : deleting imported module was successful (%s : %s)' % \
                                (plugin['plugin_id'], plugin['short_name'], plugin['name']))
          else:
            self.api('send.error')('%-30s : deleting imported module failed (%s : %s)' % \
                                (plugin['plugin_id'], plugin['short_name'], plugin['name']))

        # remove from loaded_plugins
        plugin = None
        del self.loaded_plugins[plugin_id]

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
                                        'all_plugin_info_from_disk']
    stats['Base Sizes']['loaded_plugins'] = '%s bytes' % \
                                      sys.getsizeof(self.loaded_plugins)
    stats['Base Sizes']['all_plugin_info_from_disk'] = '%s bytes' % \
                                      sys.getsizeof(self.all_plugin_info_on_disk)

    stats['Base Sizes']['Class'] = '%s bytes' % sys.getsizeof(self)
    stats['Base Sizes']['Api'] = '%s bytes' % sys.getsizeof(self.api)

    stats['Plugins'] = {}
    stats['Plugins']['showorder'] = ['Total', 'Loaded']
    stats['Plugins']['Total'] = len(self.all_plugin_info_on_disk)
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
      if i['plugin_id'] == self.plugin_id:
        continue
      if 'plugininstance' in i and i['plugininstance']:
        i['plugininstance'].savestate()

  # command to load plugins
  def _cmd_load(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Load a plugin
      @CUsage@w: load @Yplugin@w
        @Yplugin@w    = the id of the plugin to load,
                        example: example.timerex
    """
    tmsg = []
    conflicts = self.read_all_plugin_information()
    if conflicts:
      self.api('send.msg')('conflicts with plugins, see errors and correct before loading a plugin')
      tmsg.append('conflicts between plugins, see errors and correct before attempting to load another plugin')
      return True, tmsg

    plugin = args['plugin']
    plugin_found_f = False
    if plugin:
      # TODO: also search each for internal short_name
      if plugin in self.all_plugin_info_on_disk.keys():
        plugin_found_f = True
      else:
        tmsg.append('plugin %s not in cache, rereading plugins from disk' % plugin)
        self.read_all_plugin_information()
        if plugin in self.all_plugin_info_on_disk.keys():
          plugin_found_f = True

    if plugin_found_f:
      if self.api('plugins.isloaded')(plugin):
        tmsg.append('%s is already loaded' % plugin)
      else:
        success = self.load_single_plugin(plugin, exit_on_error=False)
        if success:
          tmsg.append('Plugin %s was loaded' % plugin)
        else:
          tmsg.append('Plugin %s would not load' % plugin)
    else:
      tmsg.append('plugin %s not found' % plugin)

    return True, tmsg

  def _cmd_unload(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      unload a plugin
      @CUsage@w: unload @Yplugin@w
        @Yplugin@w    = the id of the plugin to unload,
                        example: example.timerex
    """
    tmsg = []
    plugin = args['plugin']
    plugin_found_f = False
    if plugin:
      if plugin in self.all_plugin_info_on_disk.keys():
        plugin_found_f = True

    if plugin_found_f:
      success = self.unload_single_plugin(plugin)
      if success:
        tmsg.append('Plugin %s successfully unloaded' % plugin)
      else:
        tmsg.append('Plugin %s could not be unloaded' % plugin)
    else:
      tmsg.append('plugin %s not found' % plugin)

    return True, tmsg

  def _cmd_reload(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      reload a plugin
      @CUsage@w: reload @Yplugin@w
        @Yplugin@w    = the id of the plugin to reload,
                        example: example.timerex
    """
    tmsg = []
    plugin = args['plugin']
    plugin_found_f = False
    if plugin:
      if plugin in self.all_plugin_info_on_disk.keys():
        plugin_found_f = True

    if plugin_found_f:
      success = self.unload_single_plugin(plugin)
      if success:
        tmsg.append('Plugin %s successfully unloaded' % plugin)
      else:
        tmsg.append('Plugin %s could not be unloaded' % plugin)
        return True, tmsg

      if self.api('plugins.isloaded')(plugin):
        tmsg.append('%s is already loaded' % plugin)
      else:
        success = self.load_single_plugin(plugin, exit_on_error=False)
        if success:
          tmsg.append('Plugin %s was loaded' % plugin)
        else:
          tmsg.append('Plugin %s would not load' % plugin)
    else:
      tmsg.append('plugin %s not found' % plugin)

    return True, tmsg

  # initialize this plugin
  def initialize(self):
    """
    initialize plugin
    """
    self.api('setting.add')('pluginstoload', [], list,
                            'plugins to load on startup',
                            readonly=True)

    BasePlugin.initialize(self)

    # add this plugin to loaded plugins and the lookup dictionaries
    self.loaded_plugins[self.plugin_id] = {
        'short_name': self.short_name,
        'base_plugin_dir': self.base_plugin_dir,
        'module': None,
        'purpose': self.purpose,
        'plugin_path': self.plugin_path,
        'isimported': True,
        'name': self.name,
        'author': self.author,
        'isrequired': True,
        'dev': False,
        'version': self.version,
        'full_import_location': self.full_import_location,
        'isinitialized': True,
        'plugin_id': self.plugin_id,
        'importedtime': self.loaded_time,
        'plugininstance': self
    }

    self.plugin_lookup_by_short_name[self.short_name] = self.plugin_id
    self.plugin_lookup_by_full_import_location[self.full_import_location] = self.plugin_id
    self.plugin_lookup_by_plugin_filepath[self.plugin_path] = self.plugin_id
    self.plugin_lookup_by_id[self.plugin_id] = self.plugin_id

    self.can_reload_f = False
    self._load_plugins_on_startup()

    self.api('log.adddtype')(self.short_name)
    self.api('log.console')(self.short_name)
    self.api('log.adddtype')('upgrade')
    self.api('log.console')('upgrade')

    BasePlugin._add_commands(self)

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

    parser = argp.ArgumentParser(add_help=False,
                                 description="load a plugin")
    parser.add_argument('plugin',
                        help='the plugin to load, don\'t include the .py',
                        default='',
                        nargs='?')
    self.api('commands.add')('load',
                             self._cmd_load,
                             lname='Plugin Manager',
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description="unload a plugin")
    parser.add_argument('plugin',
                        help='the plugin to unload',
                        default='',
                        nargs='?')
    self.api('commands.add')('unload',
                             self._cmd_unload,
                             lname='Plugin Manager',
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description="reload a plugin")
    parser.add_argument('plugin',
                        help='the plugin to reload',
                        default='',
                        nargs='?')
    self.api('commands.add')('reload',
                             self._cmd_reload,
                             lname='Plugin Manager',
                             parser=parser)

    self.api('timers.add')('global_save', self.savestate, 60, unique=True, log=False)

    self.api('events.register')('proxy_shutdown', self.shutdown)
