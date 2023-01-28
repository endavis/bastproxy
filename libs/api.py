# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api.py
#
# File Description: create an api for use by plugins and modules
#
# By: Bast/Jubelo
"""
this module handles the api for all other modules

Most api functions will go in as a class api.

However, some api functions will need to be overloaded.
The main reason for overloading an api is when
a class instance calls an api function and needs to access itself,
or there are multiple instances of a class that will add the
same function to the api.

See the BasePlugin class
"""
# Standard Library
import inspect
import sys
import traceback
import pprint

# Third Party

# Project

def get_args(api_function):
  """
  get arguments from the function declaration
  """
  src = inspect.getsource(api_function)
  dec = src.split('\n')[0]
  args = dec.split('(')[-1].strip()
  args = args.split(')')[0]
  argsl = args.split(',')
  argn = []
  for i in argsl:
    if i == 'self':
      continue
    argn.append('@Y%s@w' % i.strip())

  args = ', '.join(argn)

  return args

class API(object):
  """
  A class that exports an api for plugins and modules to use
  """
  # where the main api resides
  api = {}

  # stats for the api
  stats = {}

  # the basepath that the proxy was run from, will be dynamically set in
  # bastproxy.py
  BASEPATH = ''
  BASEDATAPATH = ''
  BASEDATAPLUGINPATH = ''
  BASEDATALOGPATH = ''

  TIMEZONE = ''

  # a flag to show that bastproxy is starting up
  startup = False

  # a flag to show that bastproxy is shutting down
  shutdown = False

  # a dictionary of managers that could not be made into plugins
  MANAGERS = {}

  # the proxy start time, will be dynamically set in bastproxy.py
  proxy_start_time = ''

  # this will hold event descriptions and usage
  event_descriptions = {}

  # the regex to use to split commands, the seperator is configured in
  # the proxy plugin
  command_split_regex = None

  # flag to set the character active flag for connecting.
  # set this ater the mud has been connected to and
  # is available for active commands to be sent
  is_character_active = False

  def __init__(self, parent_plugin_id=None):
    """
    initialize the class
    """
    # apis that have been overloaded will be put here
    self.overloaded_api = {}

    # the format for the time
    self.time_format = '%a %b %d %Y %H:%M:%S'

    # this is the plugin the api was created from
    self.parent_plugin_id = parent_plugin_id

    # added functions
    self.add('libs.api', 'add', self.add, overload=True)
    self.add('libs.api', 'has', self._api_has, overload=True)
    if not self('libs.api:has')('libs.api:remove'):
      self.add('libs.api', 'remove', self._api_remove, overload=True)
    if not self('libs.api:has')('libs.api:get:children'):
      self.add('libs.api', 'get:children', self._api_get_children, overload=True)
    if not self('libs.api:has')('libs.api:run:as:plugin'):
      self.add('libs.api', 'run:as:plugin', self._api_run_as_plugin, overload=True)
    if not self('libs.api:has')('libs.api:detail'):
      self.add('libs.api', 'detail', self._api_detail, overload=True)
    if not self('libs.api:has')('libs.api:list'):
      self.add('libs.api', 'list', self._api_list, overload=True)
    if not self('libs.api:has')('libs.api:data:get'):
      self.add('libs.api', 'api:data:get', self._api_data_get, overload=True)
    if not self('libs.api:has')('libs.api:get:caller:plugin'):
      self.add('libs.api', 'get:caller:plugin', self._api_caller_plugin, overload=True)
    if not self('libs.api:has')('libs.api:get:plugins:from:stack:list'):
      self.add('libs.api', 'get:plugins:from:stack:list', self._api_plugin_stack, overload=True)
    if not self('libs.api:has')('libs.api:get:call:stack'):
      self.add('libs.api', 'get:call:stack', self._api_call_stack, overload=True)
    if not self('libs.api:has')('libs.api:get:call:stack:simple'):
      self.add('libs.api', 'get:call:stack:simple', self._api_simple_call_stack, overload=True)
    if not self('libs.api:has')('libs.api:add:event:description'):
      self.add('libs.api', 'add:event:description', self._api_add_event_description, overload=True)
    if not self('libs.api:has')('libs.api:is_character_active'):
      self.add('libs.api', 'is_character_active', self._api_is_character_active_get, overload=True)
    if not self('libs.api:has')('libs.api:is_character_active:set'):
      self.add('libs.api', 'is_character_active:set', self._api_is_character_active_set, overload=True)

  # get the firstactive flag
  def _api_is_character_active_get(self):
    """
    returns the is_character_active flag
    """
    return self.is_character_active

  def _api_is_character_active_set(self, flag):
    """
    set the is_character_active flag
    """
    self.__class__.is_character_active = flag

    if flag:
      self('core.events:raise:event')('ev_libs.api_character_active',
                                      args={'is_character_active':self.is_character_active},
                                      calledfrom='libs.api')
    else:
      self('core.events:raise:event')('ev_libs.api_character_inactive',
                                      args={'is_character_active':self.is_character_active},
                                      calledfrom='libs.api')

  # return the data for an api
  def _api_data_get(self, api_name, base=True):
    """
    return the data for an api
    """
    data = None
    if api_name in self.overloaded_api:
      data = self.overloaded_api[api_name].copy()
    elif api_name in self.api and ((not data) or base):
      data = self.api[api_name].copy()

    if data:
      data['count'] = sum(self.stats[api_name].values())
      data['stats'] = self.stats[api_name]

    return data

  # add a function to the api
  def add(self, top_level_api, name, tfunction, overload=False, force=False):
    """  add a function to the api
    @Ytop_level_api@w  = the toplevel that the api should be under
    @Yname@w  = the name of the api
    @Yfunction@w  = the function
    @Yoverload@w  = bool, True to add to instance api, false to add to class api

    the function is added as toplevel.name into the api

    if the api already exists, it is added to the overloaded

    this function returns no values"""
    full_api_name = top_level_api + ':' + name

    plugin_id = self.parent_plugin_id

    api_data = {}
    api_data['full_api_name'] = full_api_name
    api_data['plugin'] = plugin_id
    api_data['function'] = tfunction

    if full_api_name not in self.stats:
      self.stats[full_api_name] = {}

    if not overload:
      if full_api_name in self.api and not force:
        try:
          self.get('libs.io:send:error')('libs.api:add - %s already exists from plugin %s' % \
                                  (full_api_name, plugin_id))
        except AttributeError:
          print('libs.api:add - %s already exists from plugin %s' % \
                                  (full_api_name, plugin_id))
      else:
        self.api[full_api_name] = api_data

    else:
      self._api_overload(api_data, force)

  # overload a function in the api
  def _api_overload(self, api_data, force=False):
    """  overload a function in the api
    @Yapi_data@w  = the api data dictionary

    the function is added as api_data['full_api_name'] into the overloaded api

    this function returns True if added, False otherwise"""
    try:
      overloaded_func = self.get(api_data['full_api_name'])
      api_data['function'].__doc__ = overloaded_func.__doc__
    except AttributeError:
      pass

    if not force and \
          (api_data['full_api_name'] in self.overloaded_api):
      try:
        self.get('libs.io:send:error')('libs.api:overload - %s already exists added by plugin: %s' % \
                                 (api_data['full_api_name'], api_data['plugin']))
      except AttributeError:
        print('libs.api:overload - %s already exists added by plugin %s ' % (api_data['full_api_name'],
                                                                             api_data['plugin']))

      return False

    self.overloaded_api[api_data['full_api_name']] = api_data
    # self.overloaded_api[api_data['new_full_api_name']] = api_data
    return True

  # add an event description
  def _api_add_event_description(self, raisedevent):
    """  add an event description
    @Yraisedevent@w - RaisesEvent from libs/event.py = the event description
    """
    self.event_descriptions[raisedevent.name] = raisedevent

  # return a simple call stack
  @staticmethod
  def _api_simple_call_stack():
    """  build a simple callstack of level, module, funcion name

    Example:
    6 :          libs.io           : _api_execute
    5 :    plugins.core.events     : api_eraise
    4 :    plugins.core.events     : eraise
    3 :    plugins.core.events     : execute
    2 :       libs.net.proxy       : addtooutbuffer

    returns a list of callers
      the caller is a dict with keys index, module, file, name
    """
    stack = inspect.stack()

    modules = [(index, inspect.getmodule(stack[index][0]))
               for index in reversed(range(1, len(stack)))]

    callers = []
    for index, module in modules:
      callers.append({'index':index,
                      'module':module.__name__,
                      'file':module.__file__,
                      'name':stack[index][3]})

    return callers

  # return the call stack
  def _api_call_stack(self, ignores=None):
    """  return a list of function calls that form the stack
    @Yignores@w - list = ignore the line in the stack that contains a string in this list

    The easiest way to ignore anything that comes from a specific plugin is to pass
    plugin.full_plugin_path in the ignores list

    Example:
    ['  File "bastproxy.py", line 280, in <module>',
     '    main()',
     '  File "bastproxy.py", line 253, in main',
     '    start(listen_port)',
     '  File "/home/endavis/src/games/bastproxy/bp/libs/event.py", line 60, in new_func',
     '    return func(*args, **kwargs)',
     '  File "/home/endavis/src/games/bastproxy/bp/libs/net/proxy.py", line 63, in handle_read',
     "    'convertansi':tconvertansi})"]

    returns a string of the stack
    """
    if ignores is None:
      ignores = []
    call_stack = []

    for _, frame in sys._current_frames().items(): # pylint: disable=protected-access
      for i in traceback.format_stack(frame)[:-1]:
        if True in [tstr in i for tstr in ignores]:
          continue
        tlist = i.split('\n')
        for tline in tlist:
          if tline:
            if self.BASEPATH:
              tline = tline.replace(self.BASEPATH + "/", "")
            call_stack.append(tline.rstrip())

    return call_stack

  # return a list of the plugins in the call stack
  def _api_plugin_stack(self, ignore_plugin_list=None):
    """  return a list of all plugins in the call stack
    @Yignore_plugin_list@w  = ignore the plugins (by plugin_id) in this list if they are on the stack

    this function returns a list of plugins on the stack, each element will be the plugin_id"""
    from plugins._baseplugin import BasePlugin

    if not ignore_plugin_list:
      ignore_plugin_list = []

    try:
      stack = inspect.stack()
    except IndexError:
      return None

    plugins = []

    for ifr in stack[1:]:
      parent_frame = ifr[0]

      if 'self' in parent_frame.f_locals:
        # I don't know any way to detect call from the object method
        # NOTE: there seems to be no way to detect static method call - it will
        #      be just a function call
        tcs = parent_frame.f_locals['self']
        if tcs != self and isinstance(tcs, BasePlugin) and tcs.plugin_id not in ignore_plugin_list:
          if tcs.plugin_id not in plugins:
            plugins.append(tcs.plugin_id)
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.plugin_id not in ignore_plugin_list:
          if tcs.plugin.plugin_id not in plugins:
            plugins.append(tcs.plugin.plugin_id)

    del stack

    if 'plugins' in plugins:
      del plugins[plugins.index('plugins')]

    return plugins

  # find the caller of this api
  def _api_caller_plugin(self, ignore_plugin_list=None):
    """  get the plugin on the top of the stack
    @Yignore_plugin_list@w  = ignore the plugins (by plugin_id) in this list if they are on the stack

    check to see if the caller is a plugin, if so return the plugin id

    this is so plugins can figure out who gave them data and keep up with it.

    it will return the first plugin found when going through the stack
       it checks for a BasePlugin instance of self
       if it doesn't find that, it checks for an attribute of plugin

    returns the plugin_id of the plugin on the stack"""
    #print("calling get:caller:plugin with ignore %s" % ignore_plugin_list)
    from plugins._baseplugin import BasePlugin

    if not ignore_plugin_list:
      ignore_plugin_list = []

    try:
      stack = inspect.stack()
    except IndexError:
      return None

    for ifr in stack[1:]:
      parent_frame = ifr[0]

      if 'self' in parent_frame.f_locals:
        # I don't know any way to detect call from the object method
        # NOTE: there seems to be no way to detect static method call - it will
        #      be just a function call
        tcs = parent_frame.f_locals['self']
        if tcs != self and isinstance(tcs, BasePlugin) \
                       and tcs.plugin_id not in ignore_plugin_list:
          # print( "found: %s" % tcs.plugin_id)
          return tcs.plugin_id
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.plugin_id not in ignore_plugin_list:
          # print("found: %s" % tcs.plugin.plugin_id)
          return tcs.plugin.plugin_id

    del stack
    return None

  # remove a toplevel api
  def _api_remove(self, top_level_api):
    """  remove a toplevel api
    @Ytop_level_api@w  = the toplevel of the api to remove

    this function returns no values"""
    api_toplevel = top_level_api + ":"

    tkeys = sorted(self.api.keys())
    for i in tkeys:
      if i.startswith(api_toplevel):
        del self.api[i]

    tkeys = sorted(self.overloaded_api.keys())
    for i in tkeys:
      if i.startswith(api_toplevel):
        del self.overloaded_api[i]

  def _api_run_as_plugin(self, plugin_id, api_location):
    """
    run an api as another plugin
    """
    plugin_instance = self('core.plugins:get:plugin:instance')(plugin_id)

    if plugin_instance:
      return plugin_instance.api(api_location)
    else:
      self('io.error')('API run_as: %s plugin does not exist' % plugin_id)

  def get(self, api_location, do_not_overload=False):
    """
    get an api function

    do_not_overload = get the non overloaded api
    """
    try:
      caller_plugin = self._api_caller_plugin()
    except:   # pylint: disable=bare-except
      caller_plugin = 'Unknown'

    api_data = None

    # all apis should have a . in the first part
    # if not, we add the parent plugin id to the api
    if '.' not in api_location:
      if self.parent_plugin_id:
        api_location = self.parent_plugin_id + ':' + api_location
      else:
        self('libs.io:send:error')('api lookup: %s : did not contain a .' % api_location)

    # check overloaded api
    if not do_not_overload:
      if api_location in self.overloaded_api:
        api_data = self.overloaded_api[api_location]

    # check api
    if not api_data:
      if api_location in self.api:
        api_data = self.api[api_location]

    if api_data:
      if caller_plugin not in self.stats[api_location]:
        self.stats[api_location][caller_plugin] = 0
      self.stats[api_location][caller_plugin] = self.stats[api_location][caller_plugin] + 1
      return api_data['function']

    raise AttributeError('%s is not in the api' % api_location)

  __call__ = get

  # return a list of api functions in a toplevel api
  def _api_get_children(self, parent_api):
    """
    return a list of apis in a toplevel api
    """
    api_list = []
    if parent_api[-1] != ':':
      parent_api = parent_api + ':'

    tkeys = sorted(self.api.keys())
    for full_api_name in tkeys:
      if full_api_name.startswith(parent_api):
        api_list.append(full_api_name[len(parent_api):])

    tkeys = sorted(self.overloaded_api.keys())
    for full_api_name in tkeys:
      if full_api_name.startswith(parent_api):
        api_list.append(full_api_name[len(parent_api):])

    return list(set(api_list))

  # check to see if something exists in the api
  def _api_has(self, api_location):
    """
    see if something exists in the api
    """
    try:
      self.get(api_location)
      return True
    except AttributeError:
      return False

  # get the details for an api function
  def _api_detail(self, api_location, stats_by_plugin=False):     # pylint: disable=too-many-locals,too-many-branches
    # parsing a function declaration and figuring out where the function
    # resides is intensive, so disabling pylint warning
    """
    return the detail of an api function
    """
    tmsg = []
    api_original = None
    api_overloaded = None
    api_original_path = None
    api_overloaded_path = None

    if ':' not in api_location:
      tmsg.append('%s is not a : api format' % api_location)
      return tmsg

    if api_location:
      location_split = api_location.split(':')
      name = location_split[0]
      command_name = ':'.join(location_split[1:])
      tdict = {'name':name, 'cmdname':command_name, 'api_location':api_location}
      try:
        api_original = self.get(api_location, do_not_overload=True)
      except AttributeError:
        print('%s not in original api' % api_location)

      try:
        api_overloaded = self.get(api_location)
      except AttributeError:
        print('%s not in any api' % api_location)

      if not api_original and not api_overloaded:
        tmsg.append('%s is not in the api' % api_location)
        return tmsg

      if api_original == api_overloaded:
        api_overloaded = None

      if api_original:
        api_function = api_original
        api_original_path = inspect.getsourcefile(api_original).replace(self.BASEPATH, '')

      if api_overloaded:
        if not api_original:
          api_function = api_overloaded
        api_overloaded_path = inspect.getsourcefile(api_overloaded).replace(self.BASEPATH, '')

      args = get_args(api_function)

      tmsg.append('@G%s@w(%s)' % (api_location, args))
      if api_function.__doc__:
        tmsg.append(api_function.__doc__ % tdict)

      tmsg.append('')
      if api_original_path:
        tmsg.append('original defined in %s' % api_original_path)
      if api_overloaded_path and api_original_path:
        tmsg.append('overloaded in %s' % api_overloaded_path)
      elif api_overloaded_path:
        tmsg.append('original defined in %s' % api_overloaded_path)

      if stats_by_plugin:
        api_data = self._api_data_get(api_location)
        if api_data:
          tmsg.append('')
          tmsg.append('Stats by plugin')
          tmsg.append('@B' + '-' * 50)
          stats_keys = api_data['stats'].keys()
          stats_keys.sort()
          for i in stats_keys:

            tmsg.append('%-20s: %s' % (i or 'Unknown', api_data['stats'][i]))

    else:
      tmsg.append('%s is not in the api' % api_location)

    return tmsg

  def get_top_level_api_list(self, top_level_api):
    """
    build a dictionary of apis in toplevel
    """
    api_list = []

    for i in self.api:
      if i.startswith(top_level_api):
        api_list.append(i)

    for i in self.overloaded_api:
      if i.startswith(top_level_api):
        api_list.append(i)

    api_list = set(api_list)
    return list(api_list)

  def get_full_api_list(self):
    """
    build a dictionary of all apis
    """
    api_list = []
    api_list.extend(self.api.keys())
    api_list.extend(self.overloaded_api.keys())

    api_list = set(api_list)
    api_list = list(api_list)
    api_list.sort()
    return api_list

  # return a formatted list of functions in a toplevel api
  def _api_list(self, top_level_api=None):
    """
    return a formatted list of functions in an api
    """
    api_list = []
    tmsg = []
    if top_level_api:
      api_list = self.get_top_level_api_list(top_level_api)
    else:
      api_list = self.get_full_api_list()

    api_list.sort()

    top_levels = []
    for i in api_list:
      toplevel, therest = i.split(':', 1)
      if toplevel not in top_levels:
        top_levels.append(toplevel)
        tmsg.append('@G%-10s@w' % toplevel)
      api_data = self._api_data_get(i)

      comments = inspect.getcomments(api_data['function'])
      if comments:
        comments = comments.strip()
      added_by = ''
      if api_data['plugin']:
        added_by = '- added by %s ' % api_data['plugin']
      tmsg.append('  @G%-30s %s- called %s times @w\n    %s' % \
         (therest, added_by, api_data['count'], comments))

    return tmsg

def test():
  """
  do some testing for the api
  """
  # some generic description
  def testapi(msg):
    """
    a test api
    """
    return msg + ' (orig)'

  def overloadtestapi(msg):
    """
    a overload test api
    """
    return msg + ' (overload)'

  def overloadtestapi2(msg):
    """
    a overload test api
    """
    return msg + ' (overload2)'


  print('-' * 80)
  api = API()
  print('adding test:api')
  api('libs.api:add')('test', 'api', testapi)
  print('adding test:over')
  api('libs.api:add')('test', 'over', testapi)
  print('adding test:some:api')
  api('libs.api:add')('test', 'some:api', testapi)
  print('called api test:api', api('test:api')('success'))
  print('called api test:over', api('test:over')('success'))
  print('called api test:some:api', api('test:some:api')('success'))
  print('dict api.api:\n', pprint.pformat(api.api))
  print('dict api.overloaded_api:\n', pprint.pformat(api.overloaded_api))
  print('overloading over.api')
  api('libs.api:add')('over', 'api', overloadtestapi, overload=True)
  print('overloading test.over')
  api('libs.api:add')('test', 'over', overloadtestapi, overload=True)
  print('dict api.overloaded_api:\n', pprint.pformat(api.overloaded_api))
  print('called api over:api', api('over:api')('success'))
  print('called api test:over', api('test:over')('success'))
  print('called api test:api', api('test:api')('success'))
  print('api.has test:over', api('libs.api:has')('test.over'))
  print('api.has test:over2', api('libs.api:has')('test.over2'))
  print('api.has over:api', api('libs.api:has')('over.api'))
  print('api.has test:some:api', api('libs.api:has')('test.some.api'))
  print('dict api.api:\n', pprint.pformat(api.api))
  print('dict api.overloadapi:\n', pprint.pformat(api.overloaded_api))
  print('\n'.join(api('libs.api:list')(top_level_api="test")))
  print('--------------------')
  print('\n'.join(api('libs.api:list')()))
  print('--------------------')
  print('\n'.join(api('libs.api:detail')('test:over')))
  print('--------------------')


  print('-' * 80)
  api2 = API()
  print('api: ', api)
  print('api2: ', api2)
  print('dict api.api:\n', pprint.pformat(api.api))
  print('dict api.overloaded_api:\n', pprint.pformat(api.overloaded_api))
  print('api2 dict api2.api:\n', pprint.pformat(api2.api))
  print('api2 dict api2.overloaded_api:\n', pprint.pformat(api2.overloaded_api))
  print('api2 api_has over:api', api2('libs.api:has')('over:api'))
  print('api2 api_has over:api', api2('libs.api:has')('test:over'))
  print('api2 called test:api', api2('test:api')('success'))
  print('api2 called test:over', api2('test:over')('success'))
  print('api2 overloading over.api')
  api2('libs.api:add')('over', 'api', overloadtestapi2, overload=True)
  print('api2 dict api.overloaded_api:\n', pprint.pformat(api2.overloaded_api))
  print('api2 called over:api', api2('over:api')('success'))
  print('api2 overloading test.over')
  api2('libs.api:add')('test', 'over', overloadtestapi2, overload=True)
  print('api2 dict api2:api:\n', pprint.pformat(api2.api))
  print('api2 dict api2:overloadapi:\n', pprint.pformat(api2.overloaded_api))
  print('api2 called test:over', api2('test:over')('success'))
  print('api2 called test:api', api2('test:api')('success'))
  print('api2 api_has test:three', api2('libs.api:has')('test.three'))
  try:
    print('api2 called test:three', api2('test:three')('success'))
  except AttributeError:
    print('test:three was not in the api')
  try:
    print("doesn't exist", api2('test:four')('success'))
  except AttributeError:
    print('test:four was not in the api')

if __name__ == '__main__':
  test()
