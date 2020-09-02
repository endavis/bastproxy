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
from __future__ import print_function
import inspect
import sys
import traceback
import pprint

def getargs(api_function):
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

  # the basepath that the proxy was run from, will be dynamically set in
  # bastproxy.py
  BASEPATH = ''

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

  def __init__(self):
    """
    initialize the class
    """
    # apis that have been overloaded will be put here
    self.overloaded_api = {}

    # the format for the time
    self.time_format = '%a %b %d %Y %H:%M:%S'

    # added functions
    self.add('api', 'add', self.add, overload=True)
    self.add('api', 'has', self._api_has, overload=True)
    if not self('api.has')('managers.add'):
      self.add('managers', 'add', self._api_add_manager, overload=True)
    if not self('api.has')('managers:add'):
      self.add('managers', 'add', self._api_add_manager, overload=True)
    if not self('api.has')('managers.getm'):
      self.add('managers', 'getm', self._api_get_manager, overload=True)
    if not self('api.has')('managers:get'):
      self.add('managers', 'get', self._api_get_manager, overload=True)
    if not self('api.has')('api.remove'):
      self.add('api', 'remove', self._api_remove, overload=True)
    if not self('api.has')('api:remove'):
      self.add('api', 'remove', self._api_remove, overload=True)
    if not self('api.has')('api.getchildren'):
      self.add('api', 'getchildren', self._api_get_children, overload=True)
    if not self('api.has')('api:get:children'):
      self.add('api', 'get:children', self._api_get_children, overload=True)
    if not self('api.has')('api.detail'):
      self.add('api', 'detail', self._api_detail, overload=True)
    if not self('api.has')('api:detail'):
      self.add('api', 'detail', self._api_detail, overload=True)
    if not self('api.has')('api.list'):
      self.add('api', 'list', self._api_list, overload=True)
    if not self('api.has')('api:list'):
      self.add('api', 'list', self._api_list, overload=True)
    if not self('api.has')('api.callerplugin'):
      self.add('api', 'callerplugin', self._api_caller_plugin, overload=True)
    if not self('api.has')('api:get:caller:plugin'):
      self.add('api', 'get:caller:plugin', self._api_caller_plugin, overload=True)
    if not self('api.has')('api.pluginstack'):
      self.add('api', 'pluginstack', self._api_plugin_stack, overload=True)
    if not self('api.has')('api:get:plugins:from:stack:list'):
      self.add('api', 'get:plugins:from:stack:list', self._api_plugin_stack, overload=True)
    if not self('api.has')('api.callstack'):
      self.add('api', 'callstack', self._api_call_stack, overload=True)
    if not self('api.has')('api:get:call:stack'):
      self.add('api', 'get:call:stack', self._api_call_stack, overload=True)
    if not self('api.has')('api.simplecallstack'):
      self.add('api', 'simplecallstack', self._api_simple_call_stack, overload=True)
    if not self('api.has')('api:get:call:stack:simple'):
      self.add('api', 'get:call:stack:simple', self._api_simple_call_stack, overload=True)
    if not self('api.has')('api.addeventdesc'):
      self.add('api', 'addeventdesc', self._api_add_event_description, overload=True)
    if not self('api.has')('api:add:event:description'):
      self.add('api', 'add:event:description', self._api_add_event_description, overload=True)

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
    full_api_name = top_level_api + '.' + name
    new_full_api_name = top_level_api + ':' + name
    ## do some magic to get plugin this was added from

    plugin_id = self._api_caller_plugin()

    api_data = {}
    api_data['full_api_name'] = full_api_name
    api_data['new_full_api_name'] = new_full_api_name
    api_data['plugin'] = plugin_id
    api_data['function'] = tfunction

    if not overload:
      if (full_api_name in self.__class__.api or new_full_api_name in self.__class__.api) and not force:
        try:
          self.get('send.error')('api.add - %s (%s) already exists' % (full_api_name, new_full_api_name))
        except AttributeError:
          print('api.add - %s (%s) already exists' % (full_api_name, new_full_api_name))
      else:
        self.__class__.api[full_api_name] = api_data
        self.__class__.api[new_full_api_name] = api_data

    else:
      self._api_overload(api_data, force)

  # overload a function in the api
  def _api_overload(self, api_data, force=False):
    """  overload a function in the api
    @Yapi_data@w  = the api data dictionary

    the function is added as api_data['full_api_name'] into the overloaded api

    this function returns True if added, False otherwise"""
    try:
      ofunc = self.get(api_data['full_api_name'])
      api_data['function'].__doc__ = ofunc.__doc__
    except AttributeError:
      pass

    if not force and \
          (api_data['full_api_name'] in self.overloaded_api \
           or api_data['new_full_api_name'] in self.overloaded_api):
      try:
        self.get('send.error')('api.overload - %s (%s) already exists' % \
                                 (api_data['full_api_name'], api_data['new_full_api_name']))
      except AttributeError:
        print('api.overload - %s (%s) already exists' % (api_data['full_api_name'], api_data['new_full_api_name']))

      return False

    self.overloaded_api[api_data['full_api_name']] = api_data
    self.overloaded_api[api_data['new_full_api_name']] = api_data
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
    @Yignore_plugin_list@w  = ignore the plugins in this list if they are on the stack

    this function returns a list of plugins on the stack, each element will be the plugin short name"""
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
        # TODO: there seems to be no way to detect static method call - it will
        #      be just a function call
        tcs = parent_frame.f_locals['self']
        if tcs != self and isinstance(tcs, BasePlugin) and tcs.short_name not in ignore_plugin_list:
          if tcs.short_name not in plugins:
            plugins.append(tcs.short_name)
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.short_name not in ignore_plugin_list:
          if tcs.plugin.short_name not in plugins:
            plugins.append(tcs.plugin.short_name)

    del stack

    if 'plugins' in plugins:
      del plugins[plugins.index('plugins')]

    return plugins

  # find the caller of this api
  def _api_caller_plugin(self, ignore_plugin_list=None):
    """  get the plugin on the top of the stack
    @Yignore_plugin_list@w  = ignore the plugins in this list if they are on the stack

    check to see if the caller is a plugin, if so return the plugin short name

    this is so plugins can figure out who gave them data and keep up with it.

    it will return the first plugin found when going through the stack
       it checks for a BasePlugin instance of self
       if it doesn't find that, it checks for an attribute of plugin

    returns the short name of the plugin on the stack"""
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
        # TODO: there seems to be no way to detect static method call - it will
        #      be just a function call
        tcs = parent_frame.f_locals['self']
        if tcs != self and isinstance(tcs, BasePlugin) \
                       and tcs.short_name not in ignore_plugin_list \
                       and tcs.plugin_id not in ignore_plugin_list:
          return tcs.plugin_id
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.short_name not in ignore_plugin_list \
                and tcs.plugin.plugin_id not in ignore_plugin_list:
          return tcs.plugin.plugin_id

    del stack
    return None

  # get a manager
  def _api_get_manager(self, name):
    """  get a manager
    @Yname@w  = the name of the manager to get

    this function returns the manager instance"""
    if name in self.MANAGERS:
      return self.MANAGERS[name]

    return None

  # add a manager
  def _api_add_manager(self, name, manager):
    """  add a manager
    @Yname@w  = the name of the manager
    @Ymanager@w  = the manager instance

    this function returns no values"""
    self.MANAGERS[name] = manager

  # remove a toplevel api
  def _api_remove(self, top_level_api):
    """  remove a toplevel api
    @Ytop_level_api@w  = the toplevel of the api to remove

    this function returns no values"""
    api_toplevel = top_level_api + "."

    tkeys = sorted(self.__class__.api.keys())
    for i in tkeys:
      if i.startswith(api_toplevel):
        del self.__class__.api[i]

    tkeys = sorted(self.overloaded_api.keys())
    for i in tkeys:
      if i.startswith(api_toplevel):
        del self.overloaded_api[i]

  def get(self, api_location, do_not_overload=False):
    """
    get an api function
    """
    if not do_not_overload:
      try:
        return self.overloaded_api[api_location]['function']
      except KeyError:
        pass

    try:
      return self.api[api_location]['function']
    except KeyError:
      pass

    raise AttributeError('%s is not in the api' % api_location)

  __call__ = get

  # return a list of api functions in a toplevel api
  def _api_get_children(self, top_level_api):
    """
    return a list of apis in a toplevel api
    """
    api_list = []
    api_toplevel = top_level_api + "."

    tkeys = sorted(self.__class__.api.keys())
    for full_api_name in tkeys:
      if full_api_name.startswith(api_toplevel):
        api_list.append(".".join(full_api_name.split('.')[1:]))

    tkeys = sorted(self.overloaded_api.keys())
    for full_api_name in tkeys:
      if full_api_name.startswith(api_toplevel):
        api_list.append(".".join(full_api_name.split('.')[1:]))

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
  def _api_detail(self, api_location):     # pylint: disable=too-many-locals,too-many-branches
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

    if '.' not in api_location:
      tmsg.append('%s is not a . api format' % api_location)
      return tmsg

    if api_location:
      name, command_name = api_location.split('.')
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
        print('api_original == api_overloaded')
        api_overloaded = None

      if api_original:
        api_function = api_original
        api_original_path = inspect.getsourcefile(api_original).replace(self.BASEPATH, '')

      if api_overloaded:
        if not api_original:
          api_function = api_overloaded
        api_overloaded_path = inspect.getsourcefile(api_overloaded).replace(self.BASEPATH, '')

      args = getargs(api_function)

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

    else:
      tmsg.append('%s is not in the api' % api_location)

    return tmsg

  def get_top_level_api_list(self, top_level_api):
    """
    build a dictionary of apis in toplevel
    """
    api_list = {}

    for i in self.api:
      if i.startswith(top_level_api):
        api_list[i] = True

    for i in self.overloaded_api:
      if i.startswith(top_level_api):
        api_list[i] = True

    return api_list

  def get_full_api_list(self):
    """
    build a dictionary of all apis
    """
    api_list = {}
    for i in self.api:
      if i not in api_list:
        api_list[i] = True

    for i in self.overloaded_api:
      if i not in api_list:
        api_list[i] = True

    return api_list

  # return a formatted list of functions in a toplevel api
  def _api_list(self, top_level_api=None):
    """
    return a formatted list of functions in an api
    """
    api_list = {}
    tmsg = []
    if top_level_api:
      api_list = self.get_top_level_api_list(top_level_api)
    else:
      api_list = self.get_full_api_list()

    tkeys = api_list.keys()
    tkeys.sort()
    top_levels = []
    for i in tkeys:
      if ':' in i:
        toplevel, therest = i.split(':', 1)
      else:
        toplevel, therest = i.split('.', 1)
      if toplevel not in top_levels:
        top_levels.append(toplevel)
        tmsg.append('@G%-10s@w' % toplevel)
      api_function = self.get(i)
      comments = inspect.getcomments(api_function)
      if comments:
        comments = comments.strip()
      tmsg.append('  @G%-30s@w\n    %s' % (therest, comments))

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
  print('adding test.api')
  api('api.add')('test', 'api', testapi)
  print('adding test.over')
  api('api.add')('test', 'over', testapi)
  print('adding test.some.api')
  api('api.add')('test', 'some.api', testapi)
  print('called api test.api', api('test.api')('success'))
  print('called api test.over', api('test.over')('success'))
  print('called api test.some.api', api('test.some.api')('success'))
  print('dict api.api:\n', pprint.pformat(api.api))
  print('dict api.overloaded_api:\n', pprint.pformat(api.overloaded_api))
  print('overloading over.api')
  api('api.add')('over', 'api', overloadtestapi, overload=True)
  print('overloading test.over')
  api('api.add')('test', 'over', overloadtestapi, overload=True)
  print('dict api.overloaded_api:\n', pprint.pformat(api.overloaded_api))
  print('called api over.api', api('over.api')('success'))
  print('called api test.over', api('test.over')('success'))
  print('called api test.api', api('test.api')('success'))
  print('api.has test.over', api('api.has')('test.over'))
  print('api.has test.over2', api('api.has')('test.over2'))
  print('api.has over.api', api('api.has')('over.api'))
  print('api.has test.some.api', api('api.has')('test.some.api'))
  print('dict api.api:\n', pprint.pformat(api.api))
  print('dict api.overloadapi:\n', pprint.pformat(api.overloaded_api))
  print('\n'.join(api('api.list')(top_level_api="test")))
  print('--------------------')
  print('\n'.join(api('api.list')()))
  print('--------------------')
  print('\n'.join(api('api.detail')('test.over')))
  print('--------------------')


  print('-' * 80)
  api2 = API()
  print('api: ', api)
  print('api2: ', api2)
  print('dict api.api:\n', pprint.pformat(api.api))
  print('dict api.overloaded_api:\n', pprint.pformat(api.overloaded_api))
  print('api2 dict api2.api:\n', pprint.pformat(api2.api))
  print('api2 dict api2.overloaded_api:\n', pprint.pformat(api2.overloaded_api))
  print('api2 api_has over.api', api2('api.has')('over.api'))
  print('api2 api_has over.api', api2('api.has')('test.over'))
  print('api2 called test.api', api2('test.api')('success'))
  print('api2 called test.over', api2('test.over')('success'))
  print('api2 overloading over.api')
  api2('api.add')('over', 'api', overloadtestapi2, overload=True)
  print('api2 dict api.overloaded_api:\n', pprint.pformat(api2.overloaded_api))
  print('api2 called over.api', api2('over.api')('success'))
  print('api2 overloading test.over')
  api2('api.add')('test', 'over', overloadtestapi2, overload=True)
  print('api2 dict api2.api:\n', pprint.pformat(api2.api))
  print('api2 dict api2.overloadapi:\n', pprint.pformat(api2.overloaded_api))
  print('api2 called test.over', api2('test.over')('success'))
  print('api2 called test.api', api2('test.api')('success'))
  print('api2 api_has test.three', api2('api.has')('test.three'))
  try:
    print('api2 called test.three', api2('test.three')('success'))
  except AttributeError:
    print('test.three was not in the api')
  try:
    print("doesn't exist", api2('test.four')('success'))
  except AttributeError:
    print('test.four was not in the api')

if __name__ == '__main__':
  test()
