"""
This module holds the class BasePlugin, which all plugins should have as
their base class.
"""
import os
import sys
import textwrap
import pprint
import inspect
import time
import libs.argp as argp
from libs.persistentdict import PersistentDictEvent
from libs.api import API

class BasePlugin(object): # pylint: disable=too-many-instance-attributes
  """
  a base class for plugins
  """
  def __init__(self, name, short_name, plugin_path, base_plugin_dir,
               full_import_location, plugin_id): # pylint: disable=too-many-arguments
    """
    initialize the instance
    The only things that should be done are:
          initializing class variables and initializing the class
          only use api:add, api:overload, dependency:add
          anything that needs to be done so another plugin can interact with this plugin

    Arguments and examples:
      name : 'Actions' - from plugin file variable NAME (long name)
      short_name : 'actions' - file name without extension - not guaranteed to be unique
      plugin_path : '/client/actions.py' - path relative to the plugins directory
      base_plugin_dir : '/home/src/games/bastproxy/bp/plugins' - the full path to the
                                                                  plugins directory
      full_import_location : 'plugins.client.actions' - import location
      plugin_id : 'client.actions' - guaranteed to be unique
    """
    self.author = ''
    self.purpose = ''
    self.version = 0
    self.priority = 100
    self.name = name
    self.short_name = short_name
    self.plugin_path = plugin_path
    self.base_plugin_dir = base_plugin_dir
    self.full_plugin_path = os.path.join(base_plugin_dir, plugin_path)
    self.full_import_location = full_import_location
    self.plugin_id = plugin_id
    self.dependencies = ['core.commands', 'core.errors', 'core.log', 'core.utils',
                         'core.colors', 'core.events']
    self.version_functions = {}
    self.reload_dependents_f = False
    self.summary_template = "%20s : %s"
    self.can_reload_f = True
    self.can_reset_f = True
    self.reset_f = True
    self.api = API()
    self.first_active_priority = None
    self.loaded_time = time.time()
    self.save_directory = os.path.join(self.api.BASEPATH, 'data',
                                       'plugins', self.plugin_id)

    old_save_directory = os.path.join(self.api.BASEPATH, 'data',
                                      'plugins', self.short_name or 'dfsdsfd')
    if os.path.exists(old_save_directory):
      os.rename(old_save_directory, self.save_directory)

    try:
      os.makedirs(self.save_directory)
    except OSError:
      pass

    self.settings_file = os.path.join(self.save_directory, 'settingvalues.txt')

    self.plugin_directory = os.path.normpath(self.base_plugin_dir + \
          os.sep + os.path.dirname(self.plugin_path))

    self.plugin_file = os.path.join(self.plugin_directory,
                                    os.path.split(self.plugin_path)[-1])

    # print 'plugin_path: %s'  % self.plugin_path
    # print 'base_plugin_dir: %s ' % self.base_plugin_dir
    # print 'plugin_file: %s ' % self.plugin_file
    # print 'plugin_directory: %s ' % self.plugin_directory

    self.package = self.plugin_id.split('.')[0]

    self.settings = {}
    self.data = {}
    self.setting_values = PersistentDictEvent(self, self.settings_file, 'c')

    self._dump_shallow_attrs = ['api']

    # added as a toplevel API based on first argument and are overloaded since this
    # is a class that is used as a base
    self.api('api:add')('dependency', 'add', self._api_dependency_add, overload=True)
    self.api('api:add')('setting', 'add', self._api_setting_add, overload=True)
    self.api('api:add')('setting', 'get', self._api_setting_gets, overload=True)
    self.api('api:add')('setting', 'change', self._api_setting_change, overload=True)
    self.api('api:add')('data', 'get', self._api_get_data, overload=True)
    self.api('api:add')('data', 'update', self._api_update_data, overload=True)
    self.api('api:add')('api', 'add', self._api_add, overload=True, force=True)
    # anything added after this will have the plugin name as the toplevel api

  # add a function to the api
  def _api_add(self, name, func, overload=False, force=False):
    """  add a command to the api
    @Yname@w = the name of the api
    @Yfunc@w = the function tied to the api
    """
    # we call the non overloaded versions
    self.api.add(self.plugin_id, name, func, overload, force)

  # get the value of a setting
  def _api_setting_gets(self, setting, plugin=None):
    """  get the value of a setting
    @Ysetting@w = the setting value to get
    @Yplugin@w = the plugin to get the setting from (optional)

    returns:
      the value of the setting, None if not found"""
    if not plugin:
      try:
        if self.api('api:has')('core.utils:verify:value'):
          return self.api('core.utils:verify:value')(self.setting_values[setting],
                                                     self.settings[setting]['stype'])

        return self.setting_values[setting]

      except KeyError:
        pass

    else:
      plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)
      if plugin_instance:
        return plugin_instance.api('setting:get')(setting)

    return None

  # get the data for a specific datatype
  def _api_get_data(self, datatype, plugin=None):
    """  get the data of a specific type from this plugin
    @Ydatatype@w = the datatype to get
    @Yplugin@w   = the plugin to get the data from (optional)

    returns:
      the data for the specified datatype, None if not found"""
    if not plugin:
      if datatype in self.data:
        return self.data[datatype]

    else:
      plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)
      if plugin_instance:
        return plugin_instance.api('data:get')(datatype)

    return None

  # update the data for a specific datatype
  def _api_update_data(self, datatype, newdata, plugin=None):
    """  get the data of a specific type from this plugin
    @Ydatatype@w = the datatype to get
    @Yplugin@w   = the plugin to get the data from (optional)

    returns:
      True if updated, False if not"""
    if not plugin:
      self.data[datatype] = newdata
      return True

    else:
      plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)
      if plugin_instance:
        return plugin_instance.api('data:update')(datatype, newdata)

    return False

  # add a plugin dependency
  def _api_dependency_add(self, dependency):
    """  add a depencency
    @Ydependency@w    = the name of the plugin that will be a dependency"""
    if dependency not in self.dependencies:
      self.dependencies.append(dependency)

  # change the value of a setting
  def _api_setting_change(self, setting, value):
    """  change a setting
    @Ysetting@w    = the name of the setting to change
    @Yvalue@w      = the value to set it as

    returns:
      True if the value was changed, False otherwise"""
    if value == 'default':
      value = self.settings[setting]['default']
    if setting in self.settings:
      if self.api('core.plugins:is:plugin:loaded')('utils'):
        value = self.api('core.utils:verify:value')(
            value,
            self.settings[setting]['stype'])

      self.setting_values[setting] = value
      self.setting_values.sync()
      return True

    return False

  # add a setting to the plugin
  def _api_setting_add(self, name, default, stype, shelp, **kwargs):
    """  remove a command
    @Yname@w     = the name of the setting
    @Ydefault@w  = the default value of the setting
    @Ystype@w    = the type of the setting
    @Yshelp@w    = the help associated with the setting
    Keyword Arguments
      @Ynocolor@w    = if True, don't parse colors when showing value
      @Yreadonly@w   = if True, can't be changed by a client"""

    if 'nocolor' in kwargs:
      nocolor_f = kwargs['nocolor']
    else:
      nocolor_f = False
    if 'readonly' in kwargs:
      readonly_f = kwargs['readonly']
    else:
      readonly_f = False
    if name not in self.setting_values:
      self.setting_values[name] = default
    self.settings[name] = {
        'default':default,
        'help':shelp,
        'stype':stype,
        'nocolor':nocolor_f,
        'readonly':readonly_f
    }

  def _cmd_inspect(self, args): # pylint: disable=too-many-branches
    """
    show the plugin as it currently is in memory

    args dictionary:
      method - inspect specified method
      object - inspect specified object
                  to get to nested objects or dictionary keys use .
                  Ex. data.commands.stats.parser.description

      simple - only dump topllevel attributes
    """
    from libs.objectdump import dumps as dumper

    message = []
    found_list = []
    if args['method']:
      try:
        found_method = getattr(self, args['method'])
        message.append(inspect.getsource(found_method))
      except AttributeError:
        message.append('There is no method named %s' % args['method'])

    elif args['object']:
      found_full_item = True
      object_string = args['object']
      next_item = None

      if '.' not in object_string:
        items_to_get = [object_string]
      else:
        items_to_get = object_string.split('.')

      obj = self
      while True:
        next_item = items_to_get.pop(0)
        # check to see if next_item is an attribute
        try:
          obj = getattr(obj, next_item)
          found_list.append(':'.join(['attr', next_item]))
          if items_to_get:
            continue
          else:
            break
        except AttributeError:
          # check if obj is a dict and then check both the string next_item and integer next_item
          if isinstance(obj, dict):
            if next_item not in obj:
              try:
                next_item = int(next_item)
              except ValueError:
                pass
            if next_item in obj:
              obj = obj[next_item]
              found_list.append(':'.join(['key', next_item]))
              if items_to_get:
                continue
              else:
                break
        found_full_item = False
        break

      if found_list:
        if not found_full_item:
          message.append("There is no item named %s" % object_string)
          message.append('found up to : %s' % '.'.join(found_list))
        else:
          if args['simple']:
            tvars = pprint.pformat(obj)
          else:
            tvars = dumper(obj)
          message.append('found: %s' % '.'.join(found_list))
          message.append(tvars)
      else:
        message.append('There is no item named %s' % args['object'])

    else:
      if args['simple']:
        tvars = pprint.pformat(vars(self))
      else:
        tvars = dumper(self)

      message.append('@M' + '-' * 60 + '@x')
      message.append('Variables')
      message.append('@M' + '-' * 60 + '@x')
      message.append(tvars)
      message.append('@M' + '-' * 60 + '@x')
      message.append('Methods')
      message.append('@M' + '-' * 60 + '@x')
      message.append(pprint.pformat(inspect.getmembers(self, inspect.ismethod)))

    return True, message

  def _cmd_stats(self, _=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    show stats, memory, profile, etc.. for this plugin
    @CUsage@w: stats
    """
    stats = self.get_stats()
    tmsg = []
    for header in stats:
      tmsg.append(self.api('core.utils:center:colored:string')(header, '=', 60))
      for subtype in stats[header]['showorder']:
        tmsg.append('%-20s : %s' % (subtype, stats[header][subtype]))

    return True, tmsg

  def _cmd_api(self, args):
    """
    list functions in the api for a plugin
    """
    tmsg = []
    if args['api']:
      tmsg.extend(self.api('api:detail')("%s.%s" % (self.plugin_id,
                                                    args['api'])))
    else:
      api_list = self.api('api:list')(self.plugin_id)
      if not api_list:
        tmsg.append('nothing in the api')
      else:
        tmsg.extend(api_list)

    return True, tmsg

  def _cmd_set(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    List or set vars
    @CUsage@w: var @Y<varname>@w @Y<varvalue>@w
      @Ysettingname@w    = The setting to set
      @Ysettingvalue@w   = The value to set it to
      if there are no arguments or 'list' is the first argument then
      it will list the settings for the plugin
    """
    msg = []
    if args['name'] == 'list':
      return True, self._list_vars()
    elif args['name'] and args['value']:
      var = args['name']
      val = args['value']
      if var in self.settings:
        if 'readonly' in self.settings[var] \
              and self.settings[var]['readonly']:
          return True, ['%s is a readonly setting' % var]
        else:
          try:
            self.api('setting:change')(var, val)
            tvar = self.setting_values[var]
            if self.settings[var]['nocolor']:
              tvar = tvar.replace('@', '@@')
            elif self.settings[var]['stype'] == 'color':
              tvar = '%s%s@w' % (val, val.replace('@', '@@'))
            elif self.settings[var]['stype'] == 'timelength':
              tvar = self.api('core.utils:format:time')(
                  self.api('core.utils:verify:value')(val, 'timelength'))
            return True, ['%s is now set to %s' % (var, tvar)]
          except ValueError:
            msg = ['Cannot convert %s to %s' % \
                              (val, self.settings[var]['stype'])]
            return True, msg
        return True, self._list_vars()
      else:
        msg = ['plugin setting %s does not exist' % var]
    return False, msg

  def _cmd_reset(self, _=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      reset the plugin
      @CUsage@w: reset
    """
    if self.can_reset_f:
      self.reset()
      return True, ['Plugin reset']

    return True, ['This plugin cannot be reset']

  def _cmd_save(self, _=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    save plugin state
    @CUsage@w: save
    """
    self.savestate()
    return True, ['Plugin settings saved']

  def _cmd_help(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    show the help for this plugin
    @CUsage@w: help
    """
    msg = []
    msg.append('%-25s : %s' % ('Plugin ID', self.plugin_id))
    msg.append('%-25s : %s' % ('Plugin Command Prefix', self.plugin_id))
    msg.append('%-25s : %s' % ('Purpose', self.purpose))
    msg.append('%-25s : %s' % ('Author', self.author))
    msg.append('%-25s : %s' % ('Version', self.version))
    msg.append('%-25s : %s' % ('Plugin Path', self.plugin_path))
    msg.append('%-25s : %s' % ('Time Loaded', self.loaded_time))
    if '.__init__' in self.full_import_location:
      import_location = self.full_import_location.replace('.__init__', '')
    else:
      import_location = self.full_import_location

    msg.extend(sys.modules[import_location].__doc__.split('\n'))
    if args['commands']:
      cmd_list = self.api('core.commands:get:commands:for:plugin:formatted')(self.plugin_id)
      if cmd_list:
        msg.extend(cmd_list)
        msg.append('@G' + '-' * 60 + '@w')
        msg.append('')
    if args['api']:
      api_list = self.api('api:list')(self.plugin_id)
      if api_list:
        msg.append('API functions in %s' % self.plugin_id)
        msg.append('@G' + '-' * 60 + '@w')
        msg.extend(self.api('api:list')(self.plugin_id))
    return True, msg

  def _add_commands(self):
    """
    add commands commands
    """
    parser = argp.ArgumentParser(
        add_help=False,
        formatter_class=argp.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""
          change a setting in the plugin

          if there are no arguments or 'list' is the first argument then
          it will list the settings for the plugin"""))
    parser.add_argument('name',
                        help='the setting name',
                        default='list',
                        nargs='?')
    parser.add_argument('value',
                        help='the new value of the setting',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('set',
                                          self._cmd_set,
                                          parser=parser,
                                          group='Base',
                                          showinhistory=False)

    if self.can_reset_f:
      parser = argp.ArgumentParser(add_help=False,
                                   description='reset the plugin')
      self.api('core.commands:command:add')('reset',
                                            self._cmd_reset,
                                            parser=parser,
                                            group='Base')

    parser = argp.ArgumentParser(add_help=False,
                                 description='save the plugin state')
    self.api('core.commands:command:add')('save',
                                          self._cmd_save,
                                          parser=parser,
                                          group='Base')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show plugin stats')
    self.api('core.commands:command:add')('stats',
                                          self._cmd_stats,
                                          parser=parser,
                                          group='Base')

    parser = argp.ArgumentParser(add_help=False,
                                 description='inspect a plugin')
    parser.add_argument('-m',
                        "--method",
                        help="get code for a method",
                        default='')
    parser.add_argument('-o',
                        "--object",
                        help="show an object of the plugin, can be method or variable",
                        default='')
    parser.add_argument('-s',
                        "--simple",
                        help="show a simple output",
                        action="store_true")
    self.api('core.commands:command:add')('inspect',
                                          self._cmd_inspect,
                                          parser=parser,
                                          group='Base')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show help info for this plugin')
    parser.add_argument('-a',
                        "--api",
                        help="show functions this plugin has in the api",
                        action="store_true")
    parser.add_argument('-c',
                        "--commands",
                        help="show commands in this plugin",
                        action="store_true")
    self.api('core.commands:command:add')('help',
                                          self._cmd_help,
                                          parser=parser,
                                          group='Base')

    parser = argp.ArgumentParser(add_help=False,
                                 description='list functions in the api')
    parser.add_argument('api',
                        help='api to get details of',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('api',
                                          self._cmd_api,
                                          parser=parser,
                                          group='Base')

  def _list_vars(self):
    """
    returns:
     a list of strings that list all settings
    """
    tmsg = []
    if not self.setting_values:
      tmsg.append('There are no settings defined')
    else:
      tform = '%-20s : %-15s - %s'
      for i in self.settings:
        val = self.setting_values[i]
        if 'nocolor' in self.settings[i] and self.settings[i]['nocolor']:
          val = val.replace('@', '@@')
        elif self.settings[i]['stype'] == 'color':
          val = '%s%s@w' % (val, val.replace('@', '@@'))
        elif self.settings[i]['stype'] == 'timelength':
          val = self.api('core.utils:format:time')(
              self.api('core.utils:verify:value')(val, 'timelength'))
        tmsg.append(tform % (i, val, self.settings[i]['help']))
    return tmsg

  def _update_version(self, old_plugin_version, new_plugin_version):
    """
    update plugin data

    arguments:
      required:
        old_plugin_version - the version in the savestate file
        new_plugin_version - the latest version from the module
    """
    if old_plugin_version != new_plugin_version and new_plugin_version > old_plugin_version:
      for version in range(old_plugin_version + 1, new_plugin_version + 1):
        self.api('send:msg')(
            '%s: upgrading to version %s' % (self.plugin_id, version),
            secondary='upgrade')
        if version in self.version_functions:
          self.version_functions[version]()
        else:
          self.api('send:msg')(
              '%s: no function to upgrade to version %s' % (self.plugin_id, version),
              secondary='upgrade')

    self.setting_values['_version'] = self.version

    self.setting_values.sync()

  def __save_state(self, _=None):
    """
    save the settings state
    """
    self.setting_values.sync()

  def __after_initialize(self, _=None):
    """
    do something after the initialize function is run
    """
    # go through each variable and raise var_%s_changed
    self.setting_values.raiseall()

    mud = self.api('managers:get')('mud')

    if mud and mud.connected:
      if self.api('api:has')('connect:firstactive'):
        if self.api('connect:firstactive')():
          self.after_first_active()
      else:
        self.api('core.events:register:to:event')('firstactive', self.after_first_active,
                                                  prio=self.first_active_priority)
    else:
      self.api('core.events:register:to:event')('firstactive', self.after_first_active,
                                                prio=self.first_active_priority)

  def __disconnect(self, _=None):
    """
    re-register to firstactive on disconnect
    """
    self.api('send:msg')('baseplugin, disconnect')
    self.api('core.events:register:to:event')('firstactive', self.after_first_active)

  def after_first_active(self, _=None):
    """
    if we are connected do
    """
    self.api('send:msg')('baseplugin, firstactive')
    if self.api('core.events:is:registered:to:event')('firstactive', self.after_first_active):
      self.api('core.events:unregister:from:event')('firstactive', self.after_first_active)

  def get_stats(self):
    """
    get the stats for the plugin

    returns:
      a dict of statistics
    """
    stats = {}
    stats['Base Sizes'] = {}
    stats['Base Sizes']['showorder'] = ['Class', 'Variables', 'Api']
    stats['Base Sizes']['Variables'] = '%s bytes' % \
                                      sys.getsizeof(self.setting_values)
    stats['Base Sizes']['Class'] = '%s bytes' % sys.getsizeof(self)
    stats['Base Sizes']['Api'] = '%s bytes' % sys.getsizeof(self.api)

    return stats

  def uninitialize(self, _=None):
    """
    uninitialize stuff
    """
    # remove anything out of the api
    self.api('api:remove')(self.plugin_id)

    #save the state
    self.savestate()

  def savestate(self, _=None):
    """
    save all settings for the plugin
    do not overload!

    attach to the <plugin_id>_savestate event
    """
    self.api('core.events:raise:event')('{0.plugin_id}_savestate'.format(self))

  def is_changed_on_disk(self):
    """
    check to see if the file this plugin is based on has changed on disk

    return:
      True if the plugin is changed on disk, False otherwise
    """
    file_modified_time = os.path.getmtime(self.plugin_file)
    if int(file_modified_time) > int(self.loaded_time):
      return True

    return False

  def reset(self):
    """
    internal function to reset data
    """
    if self.can_reset_f:
      self.reset_f = True
      self.setting_values.clear()
      for i in self.settings:
        self.setting_values[i] = self.settings[i]['default']
      self.setting_values.sync()
      self.reset_f = False

  def initialize(self):
    """
    initialize the plugin, do most things here
    """
    self.setting_values.pload()

    if '_version' in self.setting_values and \
        self.setting_values['_version'] != self.version:
      self._update_version(self.setting_values['_version'], self.version)

    if self.plugin_id != 'core.plugins': # don't initialize the plugins plugin
      self.api('core.log:add:datatype')(self.plugin_id)

      self._add_commands()

      self.api('core.events:register:to:event')('{0.plugin_id}_initialized'.format(self),
                                                self.__after_initialize)
      self.api('core.events:register:to:event')('{0.plugin_id}_savestate'.format(self),
                                                self.__save_state)

      self.api('core.events:register:to:event')('muddisconnect', self.__disconnect)

      self.reset_f = False
