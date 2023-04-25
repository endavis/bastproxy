# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_manager.py
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
import os
from pathlib import Path

# 3rd Party

# Project
import libs.argp as argp
from libs.dependency import PluginDependencyResolver
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord
from libs.info import LoadedPluginInfo, PluginFileInfo

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
                      Path('_manager.py'), #plugin_path
                      API.BASEPLUGINPATH, # base_plugin_dir
                      'plugins._manager', # full_import_location
                      'plugins.core.pluginm' # plugin_id
            )

        self.author = 'Bast'
        self.purpose = 'Manage plugins'
        self.can_reload = False
        self.version = 1

        # key : plugin_id
        self.loaded_plugins_info: dict[str, LoadedPluginInfo] = {}

        # key: full_import_location
        self.all_plugin_file_info: dict[str, PluginFileInfo] = {}

        # lookups by different types
        self.plugin_lookup_by_full_import_location = {}
        self.plugin_lookup_by_plugin_filepath = {}

        self.plugin_format_string = "%-22s : %-25s %-10s %-5s %s@w"

        self.api('libs.api:add')(self.plugin_id, 'is.plugin.loaded', self._api_is_plugin_loaded)
        self.api('libs.api:add')(self.plugin_id, 'is.plugin.id', self._api_is_plugin_id)
        self.api('libs.api:add')(self.plugin_id, 'get.plugin.instance', self._api_get_plugin_instance)
        self.api('libs.api:add')(self.plugin_id, 'get.plugin.module', self._api_get_plugin_module)
        self.api('libs.api:add')(self.plugin_id, 'get.all.plugin.info', self._api_get_all_plugin_info)
        self.api('libs.api:add')(self.plugin_id, 'save.all.plugins.state', self.api_save_all_plugins_state)
        self.api('libs.api:add')(self.plugin_id, 'get.loaded.plugins.list', self._api_get_loaded_plugins_list)
        self.api('libs.api:add')(self.plugin_id, 'get.packages.list', self._api_get_packages_list)
        self.api('libs.api:add')(self.plugin_id, 'get.all.short.names', self._api_get_all_short_names)
        self.api('libs.api:add')(self.plugin_id, 'short.name.convert.plugin:id', self._api_short_name_convert_plugin_id)

        self.api(f"{self.plugin_id}:setting.add")('pluginstoload', [], list,
                                'plugins to load on startup',
                                readonly=True)

    def _api_short_name_convert_plugin_id(self, short_name):
        """
        convert a short_name to a plugin_id
        Note: short_names are not guaranteed to be unique
        """
        short_name_list = []
        plugin_id_list = []
        for loaded_plugin_info in self.loaded_plugins_info.values():
            short_name_list.append(loaded_plugin_info.short_name)
            plugin_id_list.append(loaded_plugin_info.plugin_id)

        if found_short_name := self.api('plugins.core.fuzzy:get.best.match')(
            short_name, short_name_list
        ):
            short_name_index = short_name_list.index(found_short_name)
            return plugin_id_list[short_name_index]

        return None

    # get a list of loaded plugins
    def _api_get_loaded_plugins_list(self):
        """
        get the list of loaded plugins
        """
        return list(self.loaded_plugins_info.keys())

    # return all short names
    def _api_get_all_short_names(self):
        """
        return a list of all short names
        """
        return [
            loaded_plugin_info.short_name
            for loaded_plugin_info in self.loaded_plugins_info.values()
        ]

    # get a list of all packages
    def _api_get_packages_list(self):
        """
        return the list of packages
        """
        packages = [i.rsplit('.', 1)[0] for i in self.loaded_plugins_info]
        packages = list(set(packages))

        return packages

    # return the dictionary of all plugins
    def _api_get_all_plugin_info(self):
        """
        return the plugininfo dictionary

        returns:
          a dictionary with keys of plugin_id
        """
        return self.all_plugin_file_info

    def find_loaded_plugin(self, plugin):
        """
        find a plugin

        arguments:
          required:
            plugin - the plugin to find

        returns:
          if found, returns a plugin object, else returns None
        """
        return self.api(f"{self.plugin_id}:get.plugin.instance")(plugin)

    # get a plugin instance
    def _api_get_plugin_module(self, pluginname):
        """  returns the module of a plugin
        @Ypluginname@w  = the plugin to check for

        returns:
          the module for a plugin"""
        if self.api(f"{self.plugin_id}:is.plugin.id")(pluginname):
            return self.loaded_plugins_info[pluginname].module

        return None

    # get a plugin instance
    def _api_get_plugin_instance(self, plugin_name) -> BasePlugin | None:
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""

        plugin_instance = None

        if isinstance(plugin_name, str):
            if plugin_name in self.loaded_plugins_info:
                plugin_instance = self.loaded_plugins_info[plugin_name].plugininstance
            if plugin_name in self.plugin_lookup_by_full_import_location:
                plugin_instance = self.loaded_plugins_info[self.plugin_lookup_by_full_import_location[plugin_name]].plugininstance
            if plugin_name in self.plugin_lookup_by_plugin_filepath:
                plugin_instance = self.loaded_plugins_info[self.plugin_lookup_by_plugin_filepath[plugin_name]].plugininstance
        elif isinstance(plugin_name, BasePlugin):
            plugin_instance = plugin_name

        if not plugin_instance:
            LogRecord(f"api_get_plugin_instance - plugin not found: {plugin_name}", level="error", sources=[self.plugin_id], stack_info=True)

        return plugin_instance

    # get a plugin instance
    def _api_is_plugin_id(self, plugin_id):
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""
        return bool(
            self.api(f"{self.plugin_id}:get.plugin.instance")(plugin_id)
        )

    # check if a plugin is loaded
    def _api_is_plugin_loaded(self, pluginname):
        """  check if a plugin is loaded
        @Ypluginname@w  = the plugin to check for

        returns:
          True if the plugin is loaded, False if not"""
        return bool(
            self.api(f"{self.plugin_id}:get.plugin.instance")(pluginname)
        )

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
        if 'plugins' not in package:
            if package.startswith('.'):
                package = f"plugins{package}"
            else:
                package = f"plugins.{package}"

        if plist := [
            plugin_instance
            for plugin_instance in [
                i.plugininstance for i in self.loaded_plugins_info.values()
            ]
            if plugin_instance and plugin_instance.package == package
        ]:
            plugins = sorted(plist, key=operator.attrgetter('plugin_id'))
            mod = __import__(package)
            try:
                desc = getattr(mod, package).DESCRIPTION
            except AttributeError:
                desc = ''
            msg.extend(
                (
                    f"@GPackage: {package}{f' - {desc}' if desc else ''}@w",
                    '@G' + '-' * 75 + '@w',
                    self.plugin_format_string
                    % ('Id', 'Name', 'Author', 'Vers', 'Purpose'),
                    '-' * 75,
                )
            )
            msg.extend(
                self.plugin_format_string
                % (tpl.plugin_id, tpl.name, tpl.author, tpl.version, tpl.purpose)
                for tpl in plugins
            )
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
        plugin_instances = sorted([i.plugininstance for i in self.loaded_plugins_info.values()],
                         key=operator.attrgetter('package'))
        package_header = []
        msg = [
            self.plugin_format_string
            % ('Id', 'Name', 'Author', 'Vers', 'Purpose'),
            '-' * 75,
        ]
        for tpl in plugin_instances:
            if tpl:
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
                    msg.extend(
                        (
                            f"@GPackage: {tpl.package}{f' - {desc}' if desc else ''}@w",
                            '@G' + '-' * 75 + '@w',
                        )
                    )
                msg.append(self.plugin_format_string % \
                                (tpl.plugin_id, tpl.name,
                            tpl.author, tpl.version, tpl.purpose))
        return msg

    # get plugins that are change on disk
    def _get_changed_plugins(self):
        """
        create a message of plugins that are changed on disk
        """
        plugin_instances = [i.plugininstance for i in self.loaded_plugins_info.values()]

        msg = [
            self.api('plugins.core.utils:center.colored.string')(
                '@x86Changed Plugins@w', '-', 80, filler_color='@B'
            ),
            self.plugin_format_string
            % ('Id', 'Name', 'Author', 'Vers', 'Purpose'),
            '-' * 75,
        ]
        found = False
        for tpl in plugin_instances:
            if tpl and tpl.is_changed_on_disk():
                found = True
                msg.append(self.plugin_format_string % \
                            (tpl.plugin_id, tpl.name,
                        tpl.author, tpl.version, tpl.purpose))

        return msg if found else ['No plugins are changed on disk.']

    # get all not loaded plugins
    def _get_not_loaded_plugins(self):
        """
        create a message of all not loaded plugins
        """
        msg = []
        if self.read_all_plugin_information():
            LogRecord('conflicts with plugins, see console and correct', level='error', sources=[self.plugin_id]).send()

        loaded_plugins = self.loaded_plugins_info.keys()
        all_plugins = self.all_plugin_file_info.keys()
        bad_plugins = [plugin_id for plugin_id in self.all_plugin_file_info \
                              if self.all_plugin_file_info[plugin_id].isvalidpythoncode is False]

        if pdiff := set(all_plugins) - set(loaded_plugins):
            msg.insert(0, self.api('plugins.core.utils:center.colored.string')('@x86Not Loaded Plugins@w', '-',
                                                                               80, filler_color='@B'))
            msg.insert(0, '-' * 75)
            msg.insert(0, self.plugin_format_string % \
                                    ('Location', 'Name', 'Author', 'Vers', 'Purpose'))
            msg.insert(0, 'The following plugins are not loaded')

            for plugin_id in sorted(pdiff):
                plugin_info = self.all_plugin_file_info[plugin_id]
                msg.append(self.plugin_format_string % \
                                (plugin_id,
                             plugin_info.name,
                             plugin_info.author,
                             plugin_info.version,
                             plugin_info.purpose))

        if bad_plugins:
            msg.extend(
                (
                    '',
                    self.api('plugins.core.utils:center.colored.string')(
                        '@x86Bad Plugins@w', '-', 80, filler_color='@B'
                    ),
                    'The following files are not valid python code',
                )
            )
            for plugin_id in sorted(bad_plugins):
                plugin_info = self.all_plugin_file_info[plugin_id]
                msg.append(self.plugin_format_string % \
                                (plugin_id,
                             plugin_info.name,
                             plugin_info.author,
                             plugin_info.version,
                             plugin_info.purpose))

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
        info = PluginFileInfo()
        contents = Path(path).read_text()
        try:
            ast.parse(contents)
            info.isvalidpythoncode = True
        except SyntaxError:
            LogRecord(f"isvalidpythoncode set to false for {path}",
                      level='warning', sources=[self.plugin_id]).send()

        for tline in contents.split('\n'):
            if name_match := NAMERE.match(tline):
                if not info.name:
                    gdict = name_match.groupdict()
                    info.name = gdict['value']
                    continue

            if purpose_match := PURPOSERE.match(tline):
                if not info.purpose:
                    gdict = purpose_match.groupdict()
                    info.purpose = gdict['value']
                    continue

            if author_match := AUTHORRE.match(tline):
                if not info.author:
                    gdict = author_match.groupdict()
                    info.author = gdict['value']
                    continue

            if version_match := VERSIONRE.match(tline):
                if not info.version:
                    gdict = version_match.groupdict()
                    info.version = int(gdict['value'])
                    continue

            if required_match := REQUIREDRE.match(tline):
                gdict = required_match.groupdict()
                if gdict['value'].lower() == 'true':
                    info.isrequired = True
                continue

            plugin_match = ISPLUGINRE.match(tline)
            if plugin_match:
                info.isplugin = True
                continue

            if info.isrequired and info.isplugin and \
                   info.name and info.author and info.purpose and info.version > -1:
                break

        return info

    def read_all_plugin_information(self):
        """
        read all plugins and basic info

        returns:
          a bool, True if conflicts with short name were found, False if not
        """
        LogRecord('Read all plugin information', level='info', sources=[self.plugin_id]).send()

        _module_list = imputils.find_modules(self.base_plugin_dir, prefix='plugins.')

        found_plugins = []
        # go through the plugins and read information from them
        for module in _module_list:
            full_path = module['fullpath']
            plugin_id = module['plugin_id']
            filename = module['filename']

            if filename.startswith('_'):
                continue

            found_plugins.append(plugin_id)

            if plugin_id in self.all_plugin_file_info:
                mtime = os.path.getmtime(full_path)
                mtimedt = datetime.datetime.now(datetime.timezone.utc).fromtimestamp(mtime, tz=datetime.timezone.utc)
                if mtimedt < self.all_plugin_file_info[plugin_id].lastchecked:
                    continue
                del self.all_plugin_file_info[plugin_id]

            LogRecord(f'Reading plugin information for {plugin_id}', level='info', sources=[self.plugin_id]).send()

            info = self.scan_plugin_for_info(full_path)

            if info.isplugin:
                info.plugin_path = full_path.relative_to(self.base_plugin_dir)
                info.fullpath = full_path
                info.plugin_id = plugin_id
                info.filename = filename

                self.all_plugin_file_info[plugin_id] = info

        # remove plugins that are no longer found
        for plugin_id in list(self.all_plugin_file_info.keys()):
            if plugin_id not in found_plugins:
                del self.all_plugin_file_info[plugin_id]

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
        exit_on_error = exit_on_error or self.all_plugin_file_info[plugin_id].isrequired

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

        # build dependencies
        new_dependencies = set(dependencies)
        plugin_classes = [
            self.loaded_plugins_info[tplugin_id] for tplugin_id in new_dependencies
        ]
        plugin_classes.append(self.loaded_plugins_info[plugin_id])

        # get broken plugins that didn't import
        broken_modules = [tplugin_id for tplugin_id in new_dependencies \
                                  if tplugin_id in self.loaded_plugins_info \
                                    and not self.loaded_plugins_info[tplugin_id].isimported and \
                                    not self.loaded_plugins_info[tplugin_id].dev]

        # find the order the dependencies should be loaded
        if check_dependencies:
            dependency_solver = PluginDependencyResolver(plugin_classes, broken_modules)
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
            return self.initialize_multiple_plugins(
                plugin_load_order, exit_on_error=exit_on_error
            )
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
        if plugin_id in self.loaded_plugins_info:
            if plugin_instance := self.loaded_plugins_info[
                plugin_id
            ].plugininstance:
                return True, plugin_instance.dependencies
            else:
                return False, []

        LogRecord(f"{plugin_id:<30} : attempting to load", level='info', sources=[self.plugin_id]).send()

        try:
            plugin_disk_info = self.all_plugin_file_info[plugin_id]
        except KeyError:
            LogRecord('Could not find plugin {plugin_id}', level='error', sources=[self.plugin_id]).send()
            return False, []

        try:
            plugin_dict = self.loaded_plugins_info[plugin_id]
        except KeyError:
            plugin_dict = None

        if (
            not plugin_dict
            and self._import_single_plugin(
                plugin_disk_info.fullpath, exit_on_error
            )
            and self._instantiate_plugin(plugin_id, exit_on_error)
        ):
            plugin_dict = self.loaded_plugins_info[plugin_id]

            all_dependencies = []

            if check_dependencies:
                if plugin_instance := self.loaded_plugins_info[
                    plugin_id
                ].plugininstance:
                    dependencies = plugin_instance.dependencies
                else:
                    dependencies = []

                for dependency in dependencies:
                    # import and instantiate dependencies and add their dependencies to list
                    return_value, new_dependencies = self.preinitialize_plugin(dependency)
                    if return_value:
                        all_dependencies.append(dependency)
                        all_dependencies.extend(new_dependencies)

            return True, all_dependencies

        return False, []

    def _import_single_plugin(self, full_file_path: Path, exit_on_error: bool = False):
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
        loaded_plugin_info = LoadedPluginInfo()
        loaded_plugin_info.plugin_id = plugin_id
        loaded_plugin_info.full_import_location = full_import_location
        loaded_plugin_info.plugin_path = plugin_path
        loaded_plugin_info.base_plugin_dir = self.base_plugin_dir

        if msg == 'dev module':
            loaded_plugin_info.dev = True

        if module:
            loaded_plugin_info.module = module
            loaded_plugin_info.name = module.NAME
            loaded_plugin_info.purpose = module.PURPOSE
            loaded_plugin_info.author = module.AUTHOR
            loaded_plugin_info.version = module.VERSION
            loaded_plugin_info.short_name = loaded_plugin_info.plugin_path.stem
            loaded_plugin_info.importedtime = datetime.datetime.now(datetime.timezone.utc)

        # add dictionary to loaded_plugins
        self.loaded_plugins_info[plugin_id] = loaded_plugin_info

        if success:
            loaded_plugin_info.isimported = True
        else:
            loaded_plugin_info.isimported = False
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
        loaded_plugin_info = self.loaded_plugins_info[plugin_id]

        if not loaded_plugin_info.module:
            LogRecord(f"Could not find module for {plugin_id}", level='error',
                      sources=[self.plugin_id]).send()
            if exit_on_error:
                sys.exit(1)
            else:
                return False
        try:
            plugin_instance = loaded_plugin_info.module.Plugin(
                                                loaded_plugin_info.module.NAME,
                                                loaded_plugin_info.plugin_path,
                                                loaded_plugin_info.base_plugin_dir,
                                                loaded_plugin_info.full_import_location,
                                                loaded_plugin_info.plugin_id)
        except Exception: # pylint: disable=broad-except
            LogRecord(f"Could not instantiate plugin {plugin_id}", level='error',
                      sources=[self.plugin_id], exc_info=True).send()
            if exit_on_error:
                sys.exit(1)
            else:
                return False

        plugin_instance.author = loaded_plugin_info.module.AUTHOR
        plugin_instance.purpose = loaded_plugin_info.module.PURPOSE
        plugin_instance.version = loaded_plugin_info.module.VERSION

        # set the plugin instance
        self.loaded_plugins_info[plugin_id].plugininstance = plugin_instance
        self.loaded_plugins_info[plugin_id].isinitialized = False

        # add plugin to lookups
        self.plugin_lookup_by_full_import_location[plugin_instance.full_import_location] = plugin_id
        self.plugin_lookup_by_plugin_filepath[plugin_instance.plugin_path] = plugin_id

        # update plugins to load at startup
        plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        if plugin_id not in plugins_to_load and not self.loaded_plugins_info[plugin_id].dev:
            plugins_to_load.append(plugin_id)
            self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load)

        LogRecord(f"{plugin_id:<30} : instance created successfully", level='info', sources=[self.plugin_id]).send()

        return True

    def _load_plugins_on_startup(self):
        """
        load plugins on startup
        start with plugins that have REQUIRED=True, then move
        to plugins that were loaded in the config
        """
        if self.read_all_plugin_information():
            LogRecord(
                "conflicts with plugins, see console and correct",
                level='error',
                sources=[self.plugin_id],
            ).send(actor = f"{self.plugin_id}.read_all_plugin_information")
            sys.exit(1)

        plugins_to_load_setting = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')

        required_plugins = [plugin.plugin_id for plugin in self.all_plugin_file_info.values() \
                                           if plugin.isrequired]

        ## load all required plugins first

        # load the log plugin first
        required_plugins.remove('plugins.core.log')
        required_plugins.insert(0, 'plugins.core.log')
        #print(f"loading required plugins: {required_plugins}")
        self.load_multiple_plugins(required_plugins, check_dependencies=False, run_initialize=False)
        self.initialize_multiple_plugins(required_plugins)

        # add all required plugins
        plugins_to_load = set(plugins_to_load_setting) - set(required_plugins)

        if plugins_not_found := [
            plugin
            for plugin in plugins_to_load
            if plugin not in self.all_plugin_file_info
        ]:
            for plugin in plugins_not_found:
                LogRecord(f"plugin {plugin} was marked to load at startup and no longer exists, removing from startup",
                          level='error', sources=[self.plugin_id]).send()
                plugins_to_load_setting.remove(plugin)
                plugins_to_load.remove(plugin)
            self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load_setting)

        # print('Loading the following plugins')
        # print(pprint.pformat(plugins_to_load))
        self.load_multiple_plugins(plugins_to_load)

        found = False
        # clean up plugins that were not imported, initialized, or instantiated
        for loaded_plugin_info in self.loaded_plugins_info.values():
            if not loaded_plugin_info.isinitialized or not loaded_plugin_info.isimported or not loaded_plugin_info.plugininstance:
                found = True
                LogRecord(f"Plugin {loaded_plugin_info.plugin_id} has not been correctly loaded", level='error',
                          sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()
                self.unload_single_plugin(loaded_plugin_info.plugin_id)

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
            if plugin not in self.loaded_plugins_info:
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
            success = self.initialize_plugin(self.loaded_plugins_info[tplugin], exit_on_error)
            all_plugins_initialized = all_plugins_initialized and success

        return all_plugins_initialized

    # initialize a plugin
    def initialize_plugin(self, loaded_plugin_info: LoadedPluginInfo, exit_on_error=False):
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
        if loaded_plugin_info.isinitialized:
            return True
        LogRecord(f"{loaded_plugin_info.plugin_id:<30} : attempting to initialize ({loaded_plugin_info.name})", level='info',
                  sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()

        if not loaded_plugin_info.plugininstance:
            LogRecord(f"{loaded_plugin_info.plugin_id:<30} : plugin instance is None, not initializing", level='error',
                        sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()
            return False

        # run the initialize function
        try:
            loaded_plugin_info.plugininstance.initialize()
            loaded_plugin_info.isinitialized = True

        except Exception: # pylint: disable=broad-except
            LogRecord(f"could not run the initialize function for {loaded_plugin_info.plugin_id}", level='error',
                      sources=[self.plugin_id, loaded_plugin_info.plugin_id], exc_info=True).send()
            if exit_on_error:
                LogRecord(f"{loaded_plugin_info.plugin_id:<30} : DID NOT INITIALIZE", level='error',
                          sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()
                sys.exit(1)
            return False

        LogRecord(f"{loaded_plugin_info.plugin_id:<30} : successfully initialized ({loaded_plugin_info.name})", level='info',
                    sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()

        self.api('plugins.core.events:add.event')(f"ev_{loaded_plugin_info.plugininstance.plugin_id}_initialized", self.plugin_id,
                                                    description=f"Raised when {loaded_plugin_info.plugininstance.plugin_id} is initialized",
                                                    arg_descriptions={'None': None})



        self.api('plugins.core.events:raise.event')(f"ev_{loaded_plugin_info.plugininstance.plugin_id}_initialized", {})
        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_plugin_initialized",
                                            {'plugin':loaded_plugin_info.name,
                                                'plugin_id':loaded_plugin_info.plugin_id})
        LogRecord(f"{loaded_plugin_info.plugin_id:<30} : successfully loaded", level='info',
                  sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()

        # update plugins_to_load
        plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        if loaded_plugin_info.plugin_id not in plugins_to_load:
            plugins_to_load.append(loaded_plugin_info.plugin_id)

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
        loaded_plugin_info = self.loaded_plugins_info[plugin_id]

        if not loaded_plugin_info:
            return False

        if loaded_plugin_info.plugininstance and not loaded_plugin_info.plugininstance.can_reload_f:
            LogRecord(f"{loaded_plugin_info.plugin_id:<30} : this plugin cannot be unloaded ({loaded_plugin_info.name})",
                        level='error', sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()
            return False

        try:
            # run the uninitialize function if it exists
            if loaded_plugin_info.plugininstance:
                if loaded_plugin_info.isinitialized:
                        loaded_plugin_info.plugininstance.uninitialize()
                self.api('plugins.core.events:raise.event')(f"ev_{loaded_plugin_info.plugininstance.plugin_id}_uninitialized", {})
                self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_plugin_uninitialized",
                                                    {'plugin':loaded_plugin_info.name,
                                                    'plugin_id':loaded_plugin_info.plugin_id})
                LogRecord(f"{loaded_plugin_info.plugin_id:<30} : successfully unitialized ({loaded_plugin_info.name})", level='info',
                        sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()
            else:
                LogRecord(f"{loaded_plugin_info.plugin_id:<30} : plugin instance not found ({loaded_plugin_info.name})", level='info',
                        sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()

        except Exception: # pylint: disable=broad-except
            LogRecord(f"unload: error running the uninitialize method for {loaded_plugin_info.plugin_id}", level='error',
                        sources=[self.plugin_id, loaded_plugin_info.plugin_id], exc_info=True).send()
            return False

        # remove from pluginstoload so it doesn't load at startup
        plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        if loaded_plugin_info.plugin_id in plugins_to_load:
            plugins_to_load.remove(loaded_plugin_info.plugin_id)
            self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load)

        # clean up lookup dictionaries
        # del self.plugin_lookup_by_short_name[plugin['short_name']]
        del self.plugin_lookup_by_full_import_location[loaded_plugin_info.full_import_location]
        del self.plugin_lookup_by_plugin_filepath[loaded_plugin_info.plugin_path]

        if loaded_plugin_info.plugininstance:
            # delete the instance
            del loaded_plugin_info.plugininstance

        if loaded_plugin_info.isimported:
            if imputils.deletemodule(
                loaded_plugin_info.full_import_location
            ):
                LogRecord(f"{loaded_plugin_info.plugin_id:<30} : deleting imported module was successful ({loaded_plugin_info.name})",
                            level='info', sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()
            else:
                LogRecord(f"{loaded_plugin_info.plugin_id:<30} : deleting imported module failed ({loaded_plugin_info.name})",
                            level='error', sources=[self.plugin_id, loaded_plugin_info.plugin_id]).send()

        # remove from loaded_plugins
        del self.loaded_plugins_info[plugin_id]

        return True

    # get stats for this plugin
    def get_stats(self):
        """
        return stats for events

        returns:
          a dict of statistics
        """
        stats = {'Base Sizes': {}}
        stats['Base Sizes']['showorder'] = ['Class', 'Api', 'loaded_plugins',
                                            'all_plugin_info_from_disk']
        stats['Base Sizes']['loaded_plugins'] = f"{sys.getsizeof(self.loaded_plugins_info)} bytes"
        stats['Base Sizes']['all_plugin_info_from_disk'] = f"{sys.getsizeof(self.all_plugin_file_info)} bytes"

        stats['Base Sizes']['Class'] = f"{sys.getsizeof(self)} bytes"
        stats['Base Sizes']['Api'] = f"{sys.getsizeof(self.api)} bytes"

        stats['Plugins'] = {
            'showorder': ['Total', 'Loaded'],
            'Total': len(self.all_plugin_file_info),
            'Loaded': len(self.loaded_plugins_info),
        }
        return stats

    def evc_shutdown(self, _=None):
        """
        do tasks on shutdown
        """
        self.api_save_all_plugins_state()

    # save all plugins
    def api_save_all_plugins_state(self, _=None):
        """
        save all plugins
        """
        for i in self.loaded_plugins_info:
            self.api(f"{i}:save.state")()

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
        if self.read_all_plugin_information():
            LogRecord(
                "conflicts between plugins, see errors and correct before attempting to load another plugin",
                level='error',
                sources=[self.plugin_id],
            ).send()
            tmsg.append('conflicts between plugins, see errors and correct before attempting to load another plugin')
            return True, tmsg

        plugin = args['plugin']
        plugin_found_f = False
        if plugin:
            if plugin in self.all_plugin_file_info.keys():
                plugin_found_f = True
            else:
                tmsg.append(f"plugin {plugin} not in cache, rereading plugins from disk")
                self.read_all_plugin_information()
                if plugin in self.all_plugin_file_info.keys():
                    plugin_found_f = True

        if plugin_found_f:
            if self.api(f"{self.plugin_id}:is.plugin.loaded")(plugin):
                tmsg.append(f"{plugin} is already loaded")
            elif self.load_single_plugin(plugin, exit_on_error=False):
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
        plugin_found_f = bool(plugin and plugin in self.all_plugin_file_info.keys())
        if plugin_found_f:
            if self.unload_single_plugin(plugin):
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
        plugin_found_f = bool(plugin and plugin in self.all_plugin_file_info.keys())
        if plugin_found_f:
            if self.unload_single_plugin(plugin):
                tmsg.append(f"Plugin {plugin} successfully unloaded")
            else:
                tmsg.append(f"Plugin {plugin} could not be unloaded")
                return True, tmsg

            if self.api(f"{self.plugin_id}:is.plugin.loaded")(plugin):
                tmsg.append(f"{plugin} is already loaded")
            elif self.load_single_plugin(plugin, exit_on_error=False):
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
        loaded_plugin_info = LoadedPluginInfo()
        loaded_plugin_info.plugin_id = self.plugin_id
        loaded_plugin_info.base_plugin_dir = self.base_plugin_dir
        loaded_plugin_info.module = None
        loaded_plugin_info.purpose = self.purpose
        loaded_plugin_info.plugin_path = self.plugin_path
        loaded_plugin_info.isimported = True
        loaded_plugin_info.name = self.name
        loaded_plugin_info.author = self.author
        loaded_plugin_info.isrequired = True
        loaded_plugin_info.dev = False
        loaded_plugin_info.version = self.version
        loaded_plugin_info.full_import_location = self.full_import_location
        loaded_plugin_info.isinitialized = True
        loaded_plugin_info.plugininstance = self
        loaded_plugin_info.importedtime = self.loaded_time
        loaded_plugin_info.short_name = 'pluginm'
        self.loaded_plugins_info[self.plugin_id] = loaded_plugin_info


        self.plugin_lookup_by_full_import_location[self.full_import_location] = self.plugin_id
        self.plugin_lookup_by_plugin_filepath[self.plugin_path] = self.plugin_id

        self.can_reload_f = False
        self.auto_initialize_f = False
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
        self.api('plugins.core.commands:command.add')('list',
                                              self._command_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='load a plugin')
        parser.add_argument('plugin',
                            help='the plugin to load, don\'t include the .py',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('load',
                                              self._command_load,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='unload a plugin')
        parser.add_argument('plugin',
                            help='the plugin to unload',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('unload',
                                              self._command_unload,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='reload a plugin')
        parser.add_argument('plugin',
                            help='the plugin to reload',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('reload',
                                              self._command_reload,
                                              parser=parser)

        self.api('plugins.core.timers:add.timer')('global_save', self.api_save_all_plugins_state, 60, unique=True, log=False)

        self.api('plugins.core.events:add.event')(
            f"ev_{self.plugin_id}_plugin_initialized",
            self.plugin_id,
            description="Raised when any plugin is initialized",
            arg_descriptions={
                'plugin': 'The plugin name',
                'plugin_id': 'The plugin id',
            },
        )
        self.api('plugins.core.events:add.event')(
            f"ev_{self.plugin_id}_plugin_uninitialized",
            self.plugin_id,
            description="Raised when any plugin is initialized",
            arg_descriptions={
                'plugin': 'The plugin name',
                'plugin_id': 'The plugin id',
            },
        )

        self.initializing_f = False

        self.api('plugins.core.pluginm:save.all.plugins.state')()

        for loaded_plugin_info in self.loaded_plugins_info.values():
            plugin_id = loaded_plugin_info.plugin_id
            self.api('plugins.core.events:add.event')(f"ev_{plugin_id}_initialized", self.plugin_id,
                                                        description=f"Raised when {plugin_id} is initialized",
                                                        arg_descriptions={'None': None})
            self.api('plugins.core.events:add.event')(f"ev_{plugin_id}_uninitialized", self.plugin_id,
                                                        description=f"Raised when {plugin_id} is initialized",
                                                        arg_descriptions={'None': None})
        self.api('plugins.core.events:register.to.event')('ev_plugins.core.proxy_shutdown', self.evc_shutdown)
