# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/__init__.py
#
# File Description: holds the plugin manager
#
# By: Bast
"""
manages all plugins

#TODO: make all functions that add things use kwargs instead of a dict

How plugin loading works on startup:
1. Plugin directories are scanned for basic plugin information
    see readpluginforinformation and scan_plugin_for_info
2. All plugins with REQUIRED=True are loaded and initialized
3. the pluginstoload variable is used to load all other plugins

When loading a plugin:
  1. Import if it isn't already imported (goes in imported_plugins dictionary)
  2. Instantiate it (goes in loaded_plugins dictionary)
  3. Import and instantiate all dependencies
  4. Run initialize function of all instantiated plugins in dependency order
"""
# Standard Library
import sys
import operator
import re
import ast
import datetime
from pathlib import Path

# 3rd Party

# Project
import libs.argp as argp
from libs.dependency import PluginDependencyResolver
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord

REQUIREDRE = re.compile(r'^REQUIRED = (?P<value>.*)$')
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
        super().__init__('Plugin Manager', #name,
                      'plugins', #short_name,
                      Path('__init__.py'), #plugin_path
                      API.BASEPLUGINPATH, # base_plugin_dir
                      'plugins.__init__', # full_import_location
                      'plugins.core.plugins' # plugin_id
            )

        self.author = 'Bast'
        self.purpose = 'Manage plugins'
        self.can_reload = False
        self.version = 1

        #key:   plugin_id
        #value: {'plugin', 'module'}
        # a dictionary of all plugins that have been instantiated
        # sample entry:
        #{
        #   'short_name': 'log',
        #   'base_plugin_dir': '/mnt/d/src/Linux/games/bastproxy/bp/plugins/',
        #   'module': <module 'plugins.core.msg' from '/mnt/d/src/Linux/games/bastproxy/bp/plugins/core/msg.pyc'>,
        #   'purpose': 'Handle logging to file and console, errors',
        #   'plugin_path': 'core/msg.py',
        #   'isimported': True,
        #   'name': 'Message',
        #   'author': 'Bast',
        #   'isrequired': True,
        #   'dev': False,
        #   'version': 1,
        #   'full_import_location': 'plugins.core.msg',
        #   'isinitialized': True,
        #   'plugin_id': 'core.msg',
        #   'importedtime': 1596924665.221632,
        #   'plugininstance': <plugins.core.msg.Plugin object at 0x7fdcd54f34d0>
        # }
        self.loaded_plugins = {}

        # key is plugin_id
        # a dictionary of all the plugin info
        # sample entry
        # {
        #   'plugin_path': 'core/msg.py',
        #   'isrequired': True,
        #   'fullpath': '/mnt/d/src/Linux/games/bastproxy/bp/plugins/core/msg.py',
        #   'plugin_id': 'core.msg'
        # }
        self.all_plugin_info_on_disk = {}

        # lookups by different types
        self.plugin_lookup_by_full_import_location = {}
        self.plugin_lookup_by_plugin_filepath = {}
        self.plugin_lookup_by_id = {}

        self.plugin_format_string = "%-22s : %-25s %-10s %-5s %s@w"

        self.api('libs.api:add')('is:plugin:loaded', self._api_is_plugin_loaded)
        self.api('libs.api:add')('get:plugin:instance', self._api_get_plugin_instance)
        self.api('libs.api:add')('get:plugin:module', self._api_get_plugin_module)
        self.api('libs.api:add')('get:all:plugin:info', self._api_get_all_plugin_info)
        self.api('libs.api:add')('save:state', self.api_save_state)
        self.api('libs.api:add')('get:loaded:plugins:list', self._api_get_loaded_plugins_list)
        self.api('libs.api:add')('get:packages:list', self._api_get_packages_list)
        self.api('libs.api:add')('get:all:short:names', self._api_get_all_short_names)
        self.api('libs.api:add')('short:name:convert:plugin:id', self._api_short_name_convert_plugin_id)

        self.api('setting:add')('pluginstoload', [], list,
                                'plugins to load on startup',
                                readonly=True)

    def _api_short_name_convert_plugin_id(self, short_name):
        """
        convert a short_name to a plugin_id
        Note: short_names are not guaranteed to be unique
        """
        short_name_list = []
        plugin_id_list = []
        for loaded_plugin_dict in self.loaded_plugins.values():
            short_name_list.append(loaded_plugin_dict['short_name'])
            plugin_id_list.append(loaded_plugin_dict['plugin_id'])

        found_short_name = self.api('plugins.core.fuzzy:get:best:match')(short_name, short_name_list)
        if found_short_name:
            short_name_index = short_name_list.index(found_short_name)
            return plugin_id_list[short_name_index]

        return None

    # get a list of loaded plugins
    def _api_get_loaded_plugins_list(self):
        """
        get the list of loaded plugins
        """
        return self.loaded_plugins.keys()

    # return all short names
    def _api_get_all_short_names(self):
        """
        return a list of all short names
        """
        short_name_list = []
        for loaded_plugin_dict in self.loaded_plugins.values():
            short_name_list.append(loaded_plugin_dict['short_name'])
        return short_name_list

    # get a list of all packages
    def _api_get_packages_list(self):
        """
        return the list of packages
        """
        packages = []
        for i in self.loaded_plugins:
            packages.append(i.split('.')[0])

        packages = list(set(packages))

        return packages

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
        return self.api('plugins.core.plugins:get:plugin:instance')(plugin)

    # get a plugin instance
    def _api_get_plugin_module(self, pluginname):
        """  returns the module of a plugin
        @Ypluginname@w  = the plugin to check for

        returns:
          the module for a plugin"""
        plugin = self.api('plugins.core.plugins:get:plugin:instance')(pluginname)

        if plugin:
            return self.loaded_plugins[plugin.plugin_id]['module']

        return None

    # get a plugin instance
    def _api_get_plugin_instance(self, plugin_name):
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""

        plugin = None

        if isinstance(plugin_name, str):
            if plugin_name in self.loaded_plugins:
                plugin = self.loaded_plugins[plugin_name]['plugininstance']
            if plugin_name in self.plugin_lookup_by_id:
                plugin = self.loaded_plugins[self.plugin_lookup_by_id[plugin_name]]['plugininstance']
            if plugin_name in self.plugin_lookup_by_full_import_location:
                plugin = self.loaded_plugins[self.plugin_lookup_by_full_import_location[plugin_name]]['plugininstance']
            if plugin_name in self.plugin_lookup_by_plugin_filepath:
                plugin = self.loaded_plugins[self.plugin_lookup_by_plugin_filepath[plugin_name]]['plugininstance']
            if not plugin:
                # do some fuzzy matching of the string against plugin_id
                pass
        elif isinstance(plugin_name, BasePlugin):
            plugin = plugin_name

        return plugin

    # check if a plugin is loaded
    def _api_is_plugin_loaded(self, pluginname):
        """  check if a plugin is loaded
        @Ypluginname@w  = the plugin to check for

        returns:
          True if the plugin is loaded, False if not"""
        plugin = self.api('plugins.core.plugins:get:plugin:instance')(pluginname)

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
        for plugin in [i['plugininstance'] for i in self.loaded_plugins.values()]:
            if plugin.package == package:
                plist.append(plugin)

        if plist:
            plugins = sorted(plist, key=operator.attrgetter('plugin_id'))
            limp = f"plugins.{package}"
            mod = __import__(limp)
            try:
                desc = getattr(mod, package).DESCRIPTION
            except AttributeError:
                desc = ''
            msg.append(f"@GPackage: {package}{' - ' + desc if desc else ''}@w")
            msg.append('@G' + '-' * 75 + '@w')
            msg.append(self.plugin_format_string % \
                                ('Id', 'Name',
                                 'Author', 'Vers', 'Purpose'))
            msg.append('-' * 75)

            for tpl in plugins:
                msg.append(self.plugin_format_string % \
                          (tpl.plugin_id, tpl.name,
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
        msg.append(self.plugin_format_string % \
                            ('Id', 'Name', 'Author', 'Vers', 'Purpose'))
        msg.append('-' * 75)
        for tpl in plugins:
            if tpl.package not in package_header:
                if package_header:
                    msg.append('')
                package_header.append(tpl.package)
                limp = tpl.package
                mod = __import__(limp)
                try:
                    desc = getattr(mod, tpl.package).DESCRIPTION
                except AttributeError:
                    desc = ''
                msg.append(f"@GPackage: {tpl.package}{' - ' + desc if desc else ''}@w")
                msg.append('@G' + '-' * 75 + '@w')
            msg.append(self.plugin_format_string % \
                        (tpl.plugin_id, tpl.name,
                         tpl.author, tpl.version, tpl.purpose))
        return msg

    # get plugins that are change on disk
    def _get_changed_plugins(self):
        """
        create a message of plugins that are changed on disk
        """
        msg = []

        plugins = [i['plugininstance'] for i in self.loaded_plugins.values()]

        msg.append(self.api('plugins.core.utils:center:colored:string')('@x86Changed Plugins@w', '-',
                                                                        80, filler_color='@B'))
        msg.append(self.plugin_format_string % \
                            ('Id', 'Name', 'Author', 'Vers', 'Purpose'))
        msg.append('-' * 75)

        found = False
        for tpl in plugins:
            if tpl.is_changed_on_disk():
                found = True
                msg.append(self.plugin_format_string % \
                          (tpl.plugin_id, tpl.name,
                           tpl.author, tpl.version, tpl.purpose))

        if found:
            return msg

        return ['No plugins are changed on disk.']

    # get all not loaded plugins
    def _get_not_loaded_plugins(self):
        """
        create a message of all not loaded plugins
        """
        msg = []
        conflicts = self.read_all_plugin_information()
        if conflicts:
            LogRecord('conflicts with plugins, see console and correct', level='error', sources=[self.plugin_id]).send()

        loaded_plugins = self.loaded_plugins.keys()
        all_plugins = self.all_plugin_info_on_disk.keys()
        bad_plugins = [plugin_id for plugin_id in self.all_plugin_info_on_disk \
                          if self.all_plugin_info_on_disk[plugin_id]['isvalidpythoncode'] is False]

        pdiff = set(all_plugins) - set(loaded_plugins)

        if pdiff:
            msg.insert(0, self.api('plugins.core.utils:center:colored:string')('@x86Not Loaded Plugins@w', '-',
                                                                               80, filler_color='@B'))
            msg.insert(0, '-' * 75)
            msg.insert(0, self.plugin_format_string % \
                                ('Location', 'Name', 'Author', 'Vers', 'Purpose'))
            msg.insert(0, 'The following plugins are not loaded')

            for plugin_id in sorted(pdiff):
                plugin_info = self.all_plugin_info_on_disk[plugin_id]
                msg.append(self.plugin_format_string % \
                            (plugin_id,
                             plugin_info['name'],
                             plugin_info['author'],
                             plugin_info['version'],
                             plugin_info['purpose']))

        if bad_plugins:
            msg.append('')
            msg.append(self.api('plugins.core.utils:center:colored:string')('@x86Bad Plugins@w', '-',
                                                                        80, filler_color='@B'))
            msg.append('The following files are not valid python code')
            for plugin_id in sorted(bad_plugins):
                plugin_info = self.all_plugin_info_on_disk[plugin_id]
                msg.append(self.plugin_format_string % \
                            (plugin_id,
                             plugin_info['name'],
                             plugin_info['author'],
                             plugin_info['version'],
                             plugin_info['purpose']))

        if not msg:
            msg.append('There are no plugins that are not loaded')

        return msg

    # command to list plugins
    def _command_list(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          List plugins
          @CUsage@w: list
        """
        msg = []

        if args['notloaded']:
            msg.extend(self._get_not_loaded_plugins())
        elif args['changed']:
            msg.extend(self._get_changed_plugins())
        elif args['package']:
            msg.extend(self._get_package_plugins(args['package']))
        else:
            msg.extend(self._build_all_plugins_message())
        return True, msg

    def scan_plugin_for_info(self, path):
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
        # info['sname'] = 'not found'
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
            LogRecord(f"isvalidpythoncode set to false for {path}",
                      level='warning', sources=[self.plugin_id]).send()
            info['isvalidpythoncode'] = False


        for tline in contents.split('\n'):
            if info['name'] == 'not found':
                name_match = NAMERE.match(tline)
                if name_match:
                    gdict = name_match.groupdict()
                    info['name'] = gdict['value']
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

            if info['isrequired'] and info['isplugin'] and \
               info['name'] and info['author'] and info['purpose'] and info['version']:
                break

        return info

    def read_all_plugin_information(self):
        """
        read all plugins and basic info

        returns:
          a bool, True if conflicts with short name were found, False if not
        """
        LogRecord('Read all plugin information', level='info', sources=[self.plugin_id]).send()
        self.all_plugin_info_on_disk = {}

        _module_list = imputils.find_modules(self.base_plugin_dir, prefix='plugins.')

        conflicts = False

        # go through the plugins and read information from them
        for module in _module_list:
            #print(f"fullpath: {module['fullpath']}")
            #print(f"type: {type(module['fullpath'])}")
            full_path = module['fullpath']
            plugin_path = full_path.relative_to(self.base_plugin_dir)
            plugin_id = module['plugin_id']
            filename = module['filename']

            if filename.startswith('_'):
                continue

            info = self.scan_plugin_for_info(full_path)
            if 'isvalidpythoncode' not in info:
                LogRecord(f"{full_path} info does not have isvalidpythoncode key",
                          levele='error', sources=[self.plugin_id]).send()
            if info['isplugin']:
                info['plugin_path'] = plugin_path
                info['fullpath'] = full_path
                info['plugin_id'] = plugin_id
                info['filename'] = filename

                self.all_plugin_info_on_disk[plugin_id] = info

        return conflicts

    def load_single_plugin(self, plugin_id, exit_on_error=False, run_initialize=True, check_dependencies=True):
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
                                                               exit_on_error=exit_on_error,
                                                               check_dependencies=check_dependencies)
        if not return_value:
            LogRecord(f"Could not preinitialize plugin {plugin_id}",
                      level='error', sources=[self.plugin_id, plugin_id]).send()
            if exit_on_error:
                sys.exit(1)
            return False

        plugin_classes = []

        # build dependencies
        new_dependencies = set(dependencies)
        for tplugin_id in new_dependencies:
            plugin_classes.append(self.loaded_plugins[tplugin_id])

        plugin_classes.append(self.loaded_plugins[plugin_id])

        # get broken plugins that didn't import
        broken_modules = [tplugin_id for tplugin_id in new_dependencies \
                              if tplugin_id in self.loaded_plugins \
                                and not self.loaded_plugins[tplugin_id]['isimported'] and \
                                not self.loaded_plugins[tplugin_id]['dev']]

        # find the order the dependencies should be loaded
        if check_dependencies:
            dependency_solver = PluginDependencyResolver(self, plugin_classes, broken_modules)
            plugin_load_order, unresolved_dependencies = dependency_solver.resolve()
            # print(f"{plugin_id} dependencies plugin_load_order:")
            # print(pprint.pformat(plugin_load_order))
            if unresolved_dependencies:
                LogRecord(f"The following dependencies could not be loaded for plugin {plugin_id}:",
                          level='error', sources=[self.plugin_id]).send()
                for dep in unresolved_dependencies:
                    LogRecord(f"  {dep}", level='error', sources=[self.plugin_id]).send()
                if exit_on_error:
                    sys.exit(1)
                return False
        else:
            plugin_load_order = [plugin_id]

        # initiallize all plugins
        if run_initialize:
            success = self.initialize_multiple_plugins(plugin_load_order, exit_on_error=exit_on_error)
            return success

        return True

    def preinitialize_plugin(self, plugin_id, exit_on_error=False, check_dependencies=True):
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

        LogRecord(f"{plugin_id:<30} : attempting to load", level='info', sources=[self.plugin_id]).send()

        try:
            plugin_info = self.all_plugin_info_on_disk[plugin_id]
        except KeyError:
            LogRecord('Could not find plugin {plugin_id}', level='error', sources=[self.plugin_id]).send()
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

                    if check_dependencies:
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
        plugin_path = full_file_path.relative_to(self.base_plugin_dir)

        # don't import plugins class
        if '__init__.py' in plugin_path.parts:
            return False

        # import the plugin
        success, msg, module, full_import_location = \
          imputils.importmodule(plugin_path,
                                self, 'plugins')
        if not success:
            return False

        # create the dictionary for the plugin
        plugin_id = full_import_location
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
            plugin['short_name'] = plugin_id.split('.')[-1]
            plugin['name'] = module.NAME
            plugin['purpose'] = module.PURPOSE
            plugin['author'] = module.AUTHOR
            plugin['version'] = module.VERSION
            plugin['importedtime'] = datetime.datetime.now(datetime.timezone.utc)

        # add dictionary to loaded_plugins
        self.loaded_plugins[plugin_id] = plugin

        if success:
            plugin['isimported'] = True
        elif not success:
            plugin['isimported'] = False
            if msg == 'error':
                LogRecord(f"Could not import plugin {plugin_id}", level='error', sources=[self.plugin_id]).send()
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
                                                      plugin['short_name'],
                                                      plugin['plugin_path'],
                                                      plugin['base_plugin_dir'],
                                                      plugin['full_import_location'],
                                                      plugin['plugin_id'])
        except Exception: # pylint: disable=broad-except
            LogRecord(f"Could not instantiate plugin {plugin_id}", level='error',
                      sources=[self.plugin_id], exc_info=True).send()
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
        self.plugin_lookup_by_full_import_location[plugin_instance.full_import_location] = plugin_id
        self.plugin_lookup_by_plugin_filepath[plugin_instance.plugin_path] = plugin_id
        self.plugin_lookup_by_id[plugin_id] = plugin_id

        # update plugins to load at startup
        plugins_to_load = self.api('setting:get')('pluginstoload')
        if plugin_id not in plugins_to_load and not self.loaded_plugins[plugin_id]['dev']:
            plugins_to_load.append(plugin_id)
            self.api('setting:change')('pluginstoload', plugins_to_load)

        return True

    def _load_plugins_on_startup(self):
        """
        load plugins on startup
        start with plugins that have REQUIRED=True, then move
        to plugins that were loaded in the config
        """
        conflicts = self.read_all_plugin_information()
        if conflicts:
            LogRecord(f"conflicts with plugins, see console and correct", level='error', sources=[self.plugin_id]).send()
            sys.exit(1)

        plugins_to_load_setting = self.api('setting:get')('pluginstoload')

        required_plugins = [plugin['plugin_id'] for plugin in self.all_plugin_info_on_disk.values() \
                               if plugin['isrequired']]

        ## load all required plugins first

        # load the log plugin first
        required_plugins.remove('plugins.core.log')
        required_plugins.insert(0, 'plugins.core.log')
        #print(f"loading required plugins: {required_plugins}")
        self.load_multiple_plugins(required_plugins, check_dependencies=False, run_initialize=False)
        self.initialize_multiple_plugins(required_plugins)

        # add all required plugins
        plugins_to_load = set(plugins_to_load_setting) - set(required_plugins)

        # check to make sure all plugins exist on disk
        plugins_not_found = [plugin for plugin in plugins_to_load if plugin not in self.all_plugin_info_on_disk]
        if plugins_not_found:
            for plugin in plugins_not_found:
                LogRecord(f"plugin {plugin} was marked to load at startup and no longer exists, removing from startup",
                          level='error', sources=[self.plugin_id]).send()
                plugins_to_load_setting.remove(plugin)
                plugins_to_load.remove(plugin)
            self.api('setting:change')('pluginstoload', plugins_to_load_setting)

        # print('Loading the following plugins')
        # print(pprint.pformat(plugins_to_load))
        self.load_multiple_plugins(plugins_to_load)

        # clean up plugins that were not imported, initialized, or instantiated
        for plugin in self.loaded_plugins.values():
            found = False
            if not plugin['isinitialized'] or not plugin['isimported'] or not plugin['plugininstance']:
                found = True
                LogRecord(f"Plugin {plugin['plugin_id']} has not been correctly loaded", level='error',
                          sources=[self.plugin_id, plugin['plugin_id']]).send()
                self.unload_single_plugin(plugin['plugin_id'])

        if found:
            sys.exit(1)

    def load_multiple_plugins(self, plugins_to_load, exit_on_error=False, run_initialize=True, check_dependencies=True):
        """
        load a list of plugins

        arguments:
          required:
            plugins_to_load - a list of plugin_ids to load
              plugins_to_load example:
                ['core.errors', 'core.events', 'core.msg', 'core.commands',
                'core.colors', 'core.utils', 'core.timers']

          optional:
            exit_on_error - if True, the program will exit on an error
        """
        for plugin in plugins_to_load:
            if plugin not in self.loaded_plugins:
                self.load_single_plugin(plugin, exit_on_error, run_initialize=run_initialize, check_dependencies=check_dependencies)

    def initialize_multiple_plugins(self, plugins, exit_on_error=False):
        """
        run the load function for a list of plugins

        arguments:
          required:
            plugins - a list of plugin_ids to initialize
              plugins example:
              ['core.errors', 'core.events', 'core.msg', 'core.commands',
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

    # initialize a plugin
    def initialize_plugin(self, plugin, exit_on_error=False):
        """
        run the initialize method for a plugin

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
        LogRecord(f"{plugin['plugin_id']:<30} : attempting to initialize ({plugin['name']})", level='info',
                  sources=[self.plugin_id, plugin['plugin_id']]).send()

        # run the initialize function
        try:
            plugin['plugininstance'].initialize()
            plugin['isinitialized'] = True
            LogRecord(f"{plugin['plugin_id']:<30} : successfully initialized ({plugin['name']})", level='info',
                      sources=[self.plugin_id, plugin['plugin_id']]).send()

            self.api('plugins.core.events:add:event')(f"ev_{plugin['plugininstance'].plugin_id}_initialized", self.plugin_id,
                                                        description=f"Raised when {plugin['plugininstance'].plugin_id} is initialized",
                                                        arg_descriptions={'None': None})



            self.api('plugins.core.events:raise:event')(f"ev_{plugin['plugininstance'].plugin_id}_initialized", {})
            self.api('plugins.core.events:raise:event')(f"ev_{self.plugin_id}_plugin_initialized",
                                                {'plugin':plugin['name'],
                                                 'plugin_id':plugin['plugin_id']})

        except Exception: # pylint: disable=broad-except
            LogRecord(f"could not run the initialize function for {plugin['plugin_id']}", level='error',
                      sources=[self.plugin_id, plugin['plugin_id']], exc_info=True).send()
            if exit_on_error:
                LogRecord(f"{plugin['plugin_id']:<30} : DID NOT INITIALIZE", level='error',
                          sources=[self.plugin_id, plugin['plugin_id']]).send()
                sys.exit(1)
            return False

        LogRecord(f"{plugin['plugin_id']:<30} : successfully loaded", level='info',
                  sources=[self.plugin_id, plugin['plugin_id']]).send()

        # update plugins_to_load
        plugins_to_load = self.api('setting:get')('pluginstoload')
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
            if not plugin['plugininstance'].can_reload_f:
                LogRecord(f"{plugin['plugin_id']:<30} : this plugin cannot be unloaded ({plugin['name']})",
                          level='error', sources=[self.plugin_id, plugin['plugin_id']]).send()
                return False
            else:
                try:
                    # run the uninitialize function if it exists
                    if plugin['isinitialized']:
                        plugin['plugininstance'].uninitialize()
                    self.api('plugins.core.events:raise:event')(f"ev_{plugin['plugininstance'].plugin_id}_uninitialized", {})
                    self.api('plugins.core.events:raise:event')(f"ev_{self.plugin_id}_plugin_uninitialized",
                                                        {'plugin':plugin['name'],
                                                         'plugin_id':plugin['plugin_id']})
                    LogRecord(f"{plugin['plugin_id']:<30} : successfully unitialized ({plugin['name']})", level='info',
                              sources=[self.plugin_id, plugin['plugin_id']]).send()

                except Exception: # pylint: disable=broad-except
                    LogRecord(f"unload: erros running the uninitialize method for {plugin['plugin_id']}", level='error',
                              sources=[self.plugin_id, plugin['plugin_id']], exc_info=True).send()
                    return False

                # remove from pluginstoload so it doesn't load at startup
                plugins_to_load = self.api('setting:get')('pluginstoload')
                if plugin['plugin_id'] in plugins_to_load:
                    plugins_to_load.remove(plugin['plugin_id'])
                    self.api('setting:change')('pluginstoload', plugins_to_load)

                # clean up lookup dictionaries
                # del self.plugin_lookup_by_short_name[plugin['short_name']]
                del self.plugin_lookup_by_full_import_location[plugin['full_import_location']]
                del self.plugin_lookup_by_plugin_filepath[plugin['plugin_path']]
                del self.plugin_lookup_by_id[plugin_id]

                if plugin['plugininstance']:
                    # delete the instance
                    del plugin['plugininstance']

                if plugin['isimported']:
                    # delete the module
                    success = imputils.deletemodule(plugin['full_import_location'])
                    if success:
                        LogRecord(f"{plugin['plugin_id']:<30} : deleting imported module was successful ({plugin['name']})",
                                  level='info', sources=[self.plugin_id, plugin['plugin_id']]).send()
                    else:
                        LogRecord(f"{plugin['plugin_id']:<30} : deleting imported module failed ({plugin['name']})",
                                  level='error', sources=[self.plugin_id, plugin['plugin_id']]).send()

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
        stats['Base Sizes']['loaded_plugins'] = f"{sys.getsizeof(self.loaded_plugins)} bytes"
        stats['Base Sizes']['all_plugin_info_from_disk'] = f"{sys.getsizeof(self.all_plugin_info_on_disk)} bytes"

        stats['Base Sizes']['Class'] = f"{sys.getsizeof(self)} bytes"
        stats['Base Sizes']['Api'] = f"{sys.getsizeof(self.api)} bytes"

        stats['Plugins'] = {}
        stats['Plugins']['showorder'] = ['Total', 'Loaded']
        stats['Plugins']['Total'] = len(self.all_plugin_info_on_disk)
        stats['Plugins']['Loaded'] = len(self.loaded_plugins)

        return stats

    def shutdown(self, _=None):
        """
        do tasks on shutdown
        """
        self.api_save_state()

    # save all plugins
    def api_save_state(self, _=None):
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
    def _command_load(self, args):
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
            LogRecord(f"conflicts between plugins, see errors and correct before attempting to load another plugin",
                      level='error', sources=[self.plugin_id]).send()
            tmsg.append('conflicts between plugins, see errors and correct before attempting to load another plugin')
            return True, tmsg

        plugin = args['plugin']
        plugin_found_f = False
        if plugin:
            if plugin in self.all_plugin_info_on_disk.keys():
                plugin_found_f = True
            else:
                tmsg.append(f"plugin {plugin} not in cache, rereading plugins from disk")
                self.read_all_plugin_information()
                if plugin in self.all_plugin_info_on_disk.keys():
                    plugin_found_f = True

        if plugin_found_f:
            if self.api('plugins.core.plugins:is:plugin:loaded')(plugin):
                tmsg.append(f"{plugin} is already loaded")
            else:
                success = self.load_single_plugin(plugin, exit_on_error=False)
                if success:
                    tmsg.append(f"Plugin {plugin} was loaded")
                else:
                    tmsg.append(f"Plugin {plugin} would not load")
        else:
            tmsg.append(f"plugin {plugin} not found")

        return True, tmsg

    def _command_unload(self, args):
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
                tmsg.append(f"Plugin {plugin} successfully unloaded")
            else:
                tmsg.append(f"Plugin {plugin} could not be unloaded")
        else:
            tmsg.append(f"plugin {plugin} not found")

        return True, tmsg

    def _command_reload(self, args):
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
                tmsg.append(f"Plugin {plugin} successfully unloaded")
            else:
                tmsg.append(f"Plugin {plugin} could not be unloaded")
                return True, tmsg

            if self.api('plugins.core.plugins:is:plugin:loaded')(plugin):
                tmsg.append(f"{plugin} is already loaded")
            else:
                success = self.load_single_plugin(plugin, exit_on_error=False)
                if success:
                    tmsg.append(f"Plugin {plugin} was loaded")
                else:
                    tmsg.append(f"Plugin {plugin} would not load")
        else:
            tmsg.append(f"plugin {plugin} not found")

        return True, tmsg

    # initialize this plugin
    def initialize(self):
        """
        initialize plugin
        """

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

        self.plugin_lookup_by_full_import_location[self.full_import_location] = self.plugin_id
        self.plugin_lookup_by_plugin_filepath[self.plugin_path] = self.plugin_id
        self.plugin_lookup_by_id[self.plugin_id] = self.plugin_id

        self.can_reload_f = False
        LogRecord('Loading plugins', level='info', sources=[self.plugin_id]).send()
        self._load_plugins_on_startup()

        super().initialize()

        super()._add_commands()

        parser = argp.ArgumentParser(add_help=False,
                                     description='list plugins')
        parser.add_argument('-n',
                            '--notloaded',
                            help='list plugins that are not loaded',
                            action='store_true')
        parser.add_argument('-c',
                            '--changed',
                            help='list plugins that are load but are changed on disk',
                            action='store_true')
        parser.add_argument('package',
                            help='the to list',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('list',
                                              self._command_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='load a plugin')
        parser.add_argument('plugin',
                            help='the plugin to load, don\'t include the .py',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('load',
                                              self._command_load,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='unload a plugin')
        parser.add_argument('plugin',
                            help='the plugin to unload',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('unload',
                                              self._command_unload,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='reload a plugin')
        parser.add_argument('plugin',
                            help='the plugin to reload',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('reload',
                                              self._command_reload,
                                              parser=parser)

        self.api('plugins.core.timers:add:timer')('global_save', self.api_save_state, 60, unique=True, log=False)

        self.api('plugins.core.events:add:event')(f"ev_{self.plugin_id}_plugin_initialized", self.plugin_id,
                                                    description=f"Raised when any plugin is initialized",
                                                    arg_descriptions={'plugin': 'The plugin name',
                                                                          'plugin_id': 'The plugin id'})
        self.api('plugins.core.events:add:event')(f"ev_{self.plugin_id}_plugin_uninitialized", self.plugin_id,
                                                    description=f"Raised when any plugin is initialized",
                                                    arg_descriptions={'plugin': 'The plugin name',
                                                                        'plugin_id': 'The plugin id'})

        self.initializing_f = False

        for plugin in self.loaded_plugins.values():
            plugin_id = plugin['plugin_id']
            self.api('plugins.core.events:add:event')(f"ev_{plugin_id}_initialized", self.plugin_id,
                                                        description=f"Raised when {plugin_id} is initialized",
                                                        arg_descriptions={'None': None})
            self.api('plugins.core.events:add:event')(f"ev_{plugin_id}_uninitialized", self.plugin_id,
                                                        description=f"Raised when {plugin_id} is initialized",
                                                        arg_descriptions={'None': None})
        self.api('plugins.core.events:register:to:event')('ev_net.proxy_proxy_shutdown', self.shutdown)
