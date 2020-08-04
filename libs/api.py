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

  def __init__(self):
    """
    initialize the class
    """
    # apis that have been overloaded will be put here
    self.overloaded_api = {}

    # the format for the time
    self.time_format = '%a %b %d %Y %H:%M:%S'

    # The command seperator is |
    self.split_regex = r'(?<=[^\|])\|(?=[^\|])'

    # added functions
    if not self.api_has('api.has'):
      self.add('api', 'has', self.api_has)
    if not self('api.has')('api.add'):
      self.add('api', 'add', self.add)
    if not self('api.has')('api.overload'):
      self('api.add')('api', 'overload', self.overload)

    if not self('api.has')('managers.add'):
      self('api.add')('managers', 'add', self.add_manager)
    if not self('api.has')('managers.getm'):
      self('api.add')('managers', 'getm', self.get_manager)
    if not self('api.has')('api.remove'):
      self('api.add')('api', 'remove', self.remove)
    if not self('api.has')('api.getchildren'):
      self('api.add')('api', 'getchildren', self.api_getchildren)
    if not self('api.has')('api.detail'):
      self('api.add')('api', 'detail', self.api_detail)
    if not self('api.has')('api.list'):
      self('api.add')('api', 'list', self.api_list)
    if not self('api.has')('api.callerplugin'):
      self('api.add')('api', 'callerplugin', self.api_caller_plugin)
    if not self('api.has')('api.pluginstack'):
      self('api.add')('api', 'pluginstack', self.api_plugin_stack)
    if not self('api.has')('api.callstack'):
      self('api.add')('api', 'callstack', self.api_call_stack)
    if not self('api.has')('api.simplecallstack'):
      self('api.add')('api', 'simplecallstack', self.api_simple_call_stack)
    if not self('api.has')('api.addeventdesc'):
      self('api.add')('api', 'addeventdesc', self._api_add_event_description)

  def _api_add_event_description(self, raisedevent):
    """
    add an event description
    """
    self.event_descriptions[raisedevent.name] = raisedevent

  @staticmethod
  def api_simple_call_stack():
    """
    build a simple callstack of level, module, funcion name

    Example:
    6 :          libs.io           : _api_execute
    5 :    plugins.core.events     : api_eraise
    4 :    plugins.core.events     : eraise
    3 :    plugins.core.events     : execute
    2 :       libs.net.proxy       : addtooutbuffer
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

  def api_call_stack(self, ignores=None):
    # pylint: disable=line-too-long
    """
    return a list of function calls that form the stack
    Example:
    ['  File "bastproxy.py", line 280, in <module>',
     '    main()',
     '  File "bastproxy.py", line 253, in main',
     '    start(listen_port)',
     '  File "/home/endavis/src/games/bastproxy/bp/libs/event.py", line 60, in new_func',
     '    return func(*args, **kwargs)',
     '  File "/home/endavis/src/games/bastproxy/bp/libs/net/proxy.py", line 63, in handle_read',
     "    'convertansi':tconvertansi})", '
    """
    # pylint: enable=line-too-long
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

  def api_plugin_stack(self, ignore_plugin_list=None):
    """
    return a list of all plugins in the call stack
    """
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

  def api_caller_plugin(self, ignore_plugin_list=None):
    """
    check to see if the caller is a plugin, if so return the plugin object

    this is so plugins can figure out who gave them data and keep up with it.

    it will return the first plugin found when going through the stack
       it checks for a BasePlugin instance of self
       if it doesn't find that, it checks for an attribute of plugin
    """
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
        if tcs != self and isinstance(tcs, BasePlugin) and tcs.short_name not in ignore_plugin_list:
          return tcs.short_name
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.short_name not in ignore_plugin_list:
          return tcs.plugin.short_name

    del stack
    return None

  # add a function to the api
  def add(self, top_level_api, name, tfunction):
    """  add a function to the api
    @Yptoplevel@w  = the toplevel that the api should be under
    @Yname@w  = the name of the api
    @Yfunction@w  = the function

    the function is added as toplevel.name into the api

    this function returns no values"""

    ## do some magic to get plugin this was added from
    full_api_name = top_level_api + '.' + name
    if full_api_name in self.__class__.api:
      self.get('send.error')('api.add - %s already exists' % full_api_name)

    self.__class__.api[full_api_name] = tfunction

  # overload a function in the api
  def overload(self, top_level_api, name, tfunction):
    """  overload a function in the api
    @Ytop_level_api@w  = the toplevel that the api should be under
    @Yname@w  = the name of the api
    @Yfunction@w  = the function

    the function is added as toplevel.name into the overloaded api

    this function returns no values"""
    full_api_name = top_level_api + '.' + name
    try:
      ofunc = self.get(full_api_name)
      tfunction.__doc__ = ofunc.__doc__
    except AttributeError:
      pass

    if full_api_name in self.overloaded_api:
      self.get('send.error')('api.overload - %s already exists' % full_api_name)

    self.overloaded_api[full_api_name] = tfunction

  # get a manager
  def get_manager(self, name):
    """  get a manager
    @Yname@w  = the name of the manager to get

    this function returns the manager instance"""
    if name in self.MANAGERS:
      return self.MANAGERS[name]

    return None

  # add a manager
  def add_manager(self, name, manager):
    """  add a manager
    @Yname@w  = the name of the manager
    @Ymanager@w  = the manager instance

    this function returns no values"""
    self.MANAGERS[name] = manager

  # remove a toplevel api
  def remove(self, top_level_api):
    """  remove a toplevel api
    @Ytop_level_api@w  = the toplevel of the api to remove

    this function returns no values"""
    api_toplevel = top_level_api + "."

    tkeys = sorted(self.__class__.api.keys())
    for i in tkeys:
      if api_toplevel in i:
        del self.__class__.api[i]

    tkeys = sorted(self.overloaded_api.keys())
    for i in tkeys:
      if api_toplevel in i:
        del self.overloaded_api[i]

  def get(self, api_location, do_not_overload=False):
    """
    get an api function
    """
    if not do_not_overload:
      try:
        return self.overloaded_api[api_location]
      except KeyError:
        pass

    try:
      return self.api[api_location]
    except KeyError:
      pass

    raise AttributeError('%s is not in the api' % api_location)

  __call__ = get

  # return a list of api functions in a toplevel api
  def api_getchildren(self, top_level_api):
    """
    return a list of apis in a toplevel api
    """
    api_list = []
    api_toplevel = top_level_api + "."

    tkeys = sorted(self.__class__.api.keys())
    for full_api_name in tkeys:
      if api_toplevel in full_api_name:
        api_list.append(".".join(full_api_name.split('.')[1:]))

    tkeys = sorted(self.overloaded_api.keys())
    for full_api_name in tkeys:
      if api_toplevel in full_api_name:
        api_list.append(".".join(full_api_name.split('.')[1:]))

    return list(set(api_list))

  # check to see if something exists in the api
  def api_has(self, api_location):
    """
    see if something exists in the api
    """
    try:
      self.get(api_location)
      return True
    except AttributeError:
      return False

  # get the details for an api function
  def api_detail(self, api_location):
    # parsing a function declaration and figuring out where the function
    # resides is intensive, so disabling pylint warning
    # pylint: disable=too-many-locals,too-many-branches
    """
    return the detail of an api function
    """
    tmsg = []
    api_original = None
    api_overloaded = None
    api_original_path = None
    api_overloaded_path = None
    if api_location:
      name, command_name = api_location.split('.')
      tdict = {'name':name, 'cmdname':command_name, 'api_location':api_location}
      try:
        api_original = self.get(api_location, do_not_overload=True)
      except AttributeError:
        pass

      try:
        api_overloaded = self.get(api_location)
      except AttributeError:
        pass

      if not api_original and not api_overloaded:
        tmsg.append('%s is not in the api' % api_location)
        return tmsg

      else:
        if api_original and not api_overloaded:
          api_function = api_original
          api_original_path = inspect.getsourcefile(api_original)
          api_original_path = api_original_path.replace(self.BASEPATH, '')

        elif api_overloaded and not api_original:
          api_function = api_overloaded
          api_overloaded_path = inspect.getsourcefile(api_overloaded)
          api_overloaded_path = api_overloaded_path.replace(self.BASEPATH, '')

        elif not (api_overloaded == api_original) and api_original and api_overloaded:
          api_function = api_original
          api_original_path = inspect.getsourcefile(api_original)
          api_overloaded_path = inspect.getsourcefile(api_overloaded)
          api_original_path = api_original_path.replace(self.BASEPATH, '')
          api_overloaded_path = api_overloaded_path.replace(self.BASEPATH, '')

        else:
          api_function = api_original
          api_original_path = inspect.getsourcefile(api_original)
          api_original_path = api_original_path.replace(self.BASEPATH, '')

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

    return tmsg

  def get_top_level_api_list(self, top_level_api):
    """
    build a dictionary of apis in toplevel
    """
    api_list = {}

    for i in self.api:
      if top_level_api in i:
        api_list[i] = True

    for i in self.overloaded_api:
      if top_level_api in i:
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
  def api_list(self, top_level_api=None):
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
      toplevel, therest = i.split('.', 1)
      if toplevel not in top_levels:
        top_levels.append(toplevel)
        tmsg.append('@G%-10s@w' % toplevel)
      api_function = self.get(i)
      comments = inspect.getcomments(api_function)
      if comments:
        comments = comments.strip()
      tmsg.append('  @G%-15s@w : %s' % (therest, comments))

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
    return msg

  api = API()
  api.add('test', 'api', testapi)
  api.add('test', 'over', testapi)
  api.add('test', 'some.api', testapi)
  print('test.api', api('test.api')('called test.api'))
  print('test.over', api('test.over')('called test.over'))
  print('test.some.api', api('test.some.api')('called test.some.api'))
  print('dict api.api', api.api)
  api.overload('over', 'api', testapi)
  print('dict api.overloaded_api', api.overloaded_api)
  print('over.api', api('over.api')('called over.api'))
  api.overload('test', 'over', testapi)
  print('test.over', api('test.over')('called test.over'))
  print('test.api', api('test.api')('called test.api'))
  print('api.has test.over', api('api.has')('test.over'))
  print('api.has test.over2', api('api.has')('test.over2'))
  print('api.has test.some.api', api('api.has')('test.some.api'))
  print('dict api.api', api.api)
  print('dict api.overloadapi', api.overloaded_api)
  print('dict api.api', api.api)
  print('dict api.overloadapi', api.overloaded_api)

  print('\n'.join(api.api_list(top_level_api="test")))
  print('--------------------')
  print('\n'.join(api.api_list()))
  print('--------------------')
  print('\n'.join(api.api_detail('api.add')))
  print('--------------------')

  api2 = API()
  print('api2 test.api', api2('test.api')('called test.api'))
  print('api2 test.over', api2('test.over')('called test.api'))
  print('api2 dict api.api', api2.api)
  api2.overload('over', 'api', testapi)
  print('api2 dict api.overloaded_api', api2.overloaded_api)
  print('api2 over.api', api2('over.api')('called over.api'))
  api2.overload('test', 'over', testapi)
  print('api2 dict api.api', api2.api)
  print('api2 dict api.overloadapi', api2.overloaded_api)
  print('api2 test.over', api2('test.over')('called test.over'))
  print('api2 test.api', api2('test.api')('called est.api'))
  print('api2 api_has test.three', api2.api_has('test.three'))
  try:
    print('test.three', api2('test.three')('called test.three'))
  except AttributeError:
    print('test.three was not in the api')
  try:
    print("doesn't exist", api2('test.four')('called test.four'))
  except AttributeError:
    print('test.four was not in the api')

if __name__ == '__main__':
  test()
