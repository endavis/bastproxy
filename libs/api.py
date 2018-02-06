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

def getargs(apif):
  """
  get arguments from the function declaration
  """
  src = inspect.getsource(apif)
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

  # a flag to show that bastproxy is loading
  loading = False

  # a flag to show that bastproxy is shutting down
  shutdown = False

  # a dictionary of managers that could not be made into plugins
  MANAGERS = {}

  starttime = ''

  def __init__(self):
    """
    initialize the class
    """
    # apis that have been overloaded will be put here
    self.overloadedapi = {}

    # the format for the time
    self.timestring = '%a %b %d %Y %H:%M:%S'

    # The command seperator is |
    self.splitre = r'(?<=[^\|])\|(?=[^\|])'

    # overloaded functions
    self.overload('managers', 'add', self.addmanager)
    self.overload('managers', 'getm', self.getmanager)
    self.overload('api', 'add', self.add)
    self.overload('api', 'overload', self.overload)
    self.overload('api', 'remove', self.remove)
    self.overload('api', 'getchildren', self.api_getchildren)
    self.overload('api', 'has', self.api_has)
    self.overload('api', 'detail', self.api_detail)
    self.overload('api', 'list', self.api_list)
    self.overload('api', 'callerplugin', self.api_callerplugin)
    self.overload('api', 'pluginstack', self.api_pluginstack)
    self.overload('api', 'callstack', self.api_callstack)

  def api_callstack(self, ignores=None):
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
    callstack = []

    for _, frame in sys._current_frames().items(): # pylint: disable=protected-access
      for i in traceback.format_stack(frame)[:-1]:
        if True in [tstr in i for tstr in ignores]:
          continue
        tlist = i.split('\n')
        for tline in tlist:
          if tline:
            if self.BASEPATH:
              tline = tline.replace(self.BASEPATH + "/", "")
            callstack.append(tline.rstrip())

    return callstack

  def api_pluginstack(self, skipplugin=None):
    """
    return a list of all plugins in the call stack
    """
    from plugins._baseplugin import BasePlugin

    if not skipplugin:
      skipplugin = []

    try:
      stack = inspect.stack()
    except IndexError:
      return None

    plugins = []

    for ifr in stack[1:]:
      parentframe = ifr[0]

      if 'self' in parentframe.f_locals:
        # I don't know any way to detect call from the object method
        # TODO: there seems to be no way to detect static method call - it will
        #      be just a function call
        tcs = parentframe.f_locals['self']
        if tcs != self and isinstance(tcs, BasePlugin) and tcs.sname not in skipplugin:
          if tcs.sname not in plugins:
            plugins.append(tcs.sname)
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.sname not in skipplugin:
          if tcs.plugin.sname not in plugins:
            plugins.append(tcs.plugin.sname)

    del stack

    if 'plugins' in plugins:
      del plugins[plugins.index('plugins')]

    return plugins

  def api_callerplugin(self, skipplugin=None):
    """
    check to see if the caller is a plugin, if so return the plugin object

    this is so plugins can figure out who gave them data and keep up with it.

    it will return the first plugin found when going through the stack
       it checks for a BasePlugin instance of self
       if it doesn't find that, it checks for an attribute of plugin
    """
    from plugins._baseplugin import BasePlugin

    if not skipplugin:
      skipplugin = []

    try:
      stack = inspect.stack()
    except IndexError:
      return None

    for ifr in stack[1:]:
      parentframe = ifr[0]

      if 'self' in parentframe.f_locals:
        # I don't know any way to detect call from the object method
        # TODO: there seems to be no way to detect static method call - it will
        #      be just a function call
        tcs = parentframe.f_locals['self']
        if tcs != self and isinstance(tcs, BasePlugin) and tcs.sname not in skipplugin:
          return tcs.sname
        if hasattr(tcs, 'plugin') and isinstance(tcs.plugin, BasePlugin) \
                and tcs.plugin.sname not in skipplugin:
          return tcs.plugin.sname

    del stack
    return None

  # add a function to the api
  def add(self, toplevel, name, function):
    """  add a function to the api
    @Yptoplevel@w  = the toplevel that the api should be under
    @Yname@w  = the name of the api
    @Yfunction@w  = the function

    the function is added as toplevel.name into the api

    this function returns no values"""

    ## do some magic to get plugin this was added from

    if toplevel not in self.__class__.api:
      self.__class__.api[toplevel] = {}

    if name not in self.__class__.api[toplevel]:
      self.__class__.api[toplevel][name] = function

  # overload a function in the api
  def overload(self, toplevel, name, function):
    """  overload a function in the api
    @Ytoplevel@w  = the toplevel that the api should be under
    @Yname@w  = the name of the api
    @Yfunction@w  = the function

    the function is added as toplevel.name into the overloaded api

    this function returns no values"""
    try:
      ofunc = self.get(toplevel + '.' + name)
      function.__doc__ = ofunc.__doc__
    except AttributeError:
      pass

    if toplevel not in self.overloadedapi:
      self.overloadedapi[toplevel] = {}

    self.overloadedapi[toplevel][name] = function

  # get a manager
  def getmanager(self, name):
    """  get a manager
    @Yname@w  = the name of the manager to get

    this function returns the manager instance"""
    if name in self.MANAGERS:
      return self.MANAGERS[name]

    return None

  # add a manager
  def addmanager(self, name, manager):
    """  add a manager
    @Yname@w  = the name of the manager
    @Ymanager@w  = the manager instance

    this function returns no values"""
    self.MANAGERS[name] = manager

  # remove a toplevel api
  def remove(self, toplevel):
    """  remove a toplevel api
    @Ytoplevel@w  = the toplevel of the api to remove

    this function returns no values"""
    if toplevel in self.__class__.api:
      del self.__class__.api[toplevel]

  def get(self, apiname, toplevelapi=False):
    """
    get an api function
    """
    toplevel, name = apiname.split('.')
    if not toplevelapi:
      try:
        return self.overloadedapi[toplevel][name]
      except KeyError:
        pass

    try:
      return self.api[toplevel][name]
    except KeyError:
      pass

    raise AttributeError('%s is not in the api' % apiname)

  __call__ = get

  # return a list of api functions in a toplevel api
  def api_getchildren(self, toplevel):
    """
    return a list of apis in a toplevel api
    """
    apilist = []
    if toplevel in self.api:
      apilist.extend(self.api[toplevel].keys())

    if toplevel in self.overloadedapi:
      apilist.extend(self.overloadedapi[toplevel].keys())

    return list(set(apilist))

  # check to see if something exists in the api
  def api_has(self, apiname):
    """
    see if something exists in the api
    """
    try:
      self.get(apiname)
      return True
    except AttributeError:
      return False

  # get the details for an api function
  def api_detail(self, apiname):
    # parsing a function declaration and figuring out where the function
    # resides is intensive, so disabling pylint warning
    # pylint: disable=too-many-locals,too-many-branches
    """
    return the detail of an api function
    """
    tmsg = []
    apia = None
    apio = None
    apiapath = None
    apiopath = None
    if apiname:
      name, cmdname = apiname.split('.')
      tdict = {'name':name, 'cmdname':cmdname, 'apiname':apiname}
      try:
        apia = self.get(apiname, True)
      except AttributeError:
        pass

      try:
        apio = self.get(apiname)
      except AttributeError:
        pass

      if not apia and not apio:
        tmsg.append('%s is not in the api' % apiname)
        return tmsg

      else:
        if apia and not apio:
          apif = apia
          apiapath = inspect.getsourcefile(apia)
          apiapath = apiapath[len(self.BASEPATH)+1:]

        elif apio and not apia:
          apif = apio
          apiopath = inspect.getsourcefile(apio)
          apiopath = apiopath[len(self.BASEPATH)+1:]

        elif not (apio == apia) and apia and apio:
          apif = apia
          apiapath = inspect.getsourcefile(apia)
          apiopath = inspect.getsourcefile(apio)
          apiapath = apiapath[len(self.BASEPATH)+1:]
          apiopath = apiopath[len(self.BASEPATH)+1:]

        else:
          apif = apia
          apiapath = inspect.getsourcefile(apia)
          apiapath = apiapath[len(self.BASEPATH)+1:]

        args = getargs(apif)

        tmsg.append('@G%s@w(%s)' % (apiname, args))
        if apif.__doc__:
          tmsg.append(apif.__doc__ % tdict)

        tmsg.append('')
        if apiapath:
          tmsg.append('original defined in %s' % apiapath)
        if apiopath and apiapath:
          tmsg.append('overloaded in %s' % apiopath)
        elif apiopath:
          tmsg.append('original defined in %s' % apiopath)

    return tmsg

  def gettoplevelapilist(self, toplevel):
    """
    build a dictionary of apis in toplevel
    """
    apilist = {}

    if toplevel in self.api:
      apilist[toplevel] = {}
      for k in self.api[toplevel]:
        apilist[toplevel][k] = True
    if toplevel in self.overloadedapi:
      if toplevel not in apilist:
        apilist[toplevel] = {}
      for k in self.overloadedapi[toplevel]:
        apilist[toplevel][k] = True

    return apilist

  def getapilist(self):
    """
    build a dictionary of all apis
    """
    apilist = {}
    for i in self.api:
      if i not in apilist:
        apilist[i] = {}
      for k in self.api[i]:
        apilist[i][k] = True

    for i in self.overloadedapi:
      if i not in apilist:
        apilist[i] = {}
      for k in self.overloadedapi[i]:
        apilist[i][k] = True

    return apilist

  # return a formatted list of functions in a toplevel api
  def api_list(self, toplevel=None):
    """
    return a formatted list of functions in an api
    """
    apilist = {}
    tmsg = []
    if toplevel:
      apilist = self.gettoplevelapilist(toplevel)
    else:
      apilist = self.getapilist()

    tkeys = apilist.keys()
    tkeys.sort()
    for i in tkeys:
      tmsg.append('@G%-10s@w' % i)
      tkeys2 = apilist[i].keys()
      tkeys2.sort()
      for k in tkeys2:
        apif = self.get('%s.%s' % (i, k))
        comments = inspect.getcomments(apif)
        if comments:
          comments = comments.strip()
        tmsg.append('  @G%-15s@w : %s' % (k, comments))

    return tmsg

def test():
  """
  do some testing for the api
  """
  def testapi():
    """
    a test api
    """
    print('testapi')

  def testover():
    """
    a test overloaded api
    """
    print('testover')

  api = API()
  api.add('test', 'api', testapi)
  api.add('test', 'over', testapi)
  print('test.api', api('test.api')())
  print('test.over', api('test.over')())
  print('dict api.api', api.api)
  api.overload('over', 'api', testover)
  print('dict api.overloadedapi', api.overloadedapi)
  print('over.api', api('over.api')())
  api.overload('test', 'over', testover)
  print('test.over', api('test.over')())
  print('test.api', api('test.api')())
  print('api.has', api('api.has')('test.over'))
  print('api.has', api('api.has')('test.over2'))
  print('dict api.api', api.api)
  print('dict api.overloadapi', api.overloadedapi)
  #print('test.three', api.test.three()

  api2 = API()
  print('api2 test.api', api2('test.api')())
  print('api2 test.over', api2('test.over')())
  print('api2 dict api.api', api2.api)
  api2.overload('over', 'api', testover)
  print('api2 dict api.overloadedapi', api2.overloadedapi)
  print('api2 over.api', api2('over.api')())
  api2.overload('test', 'over', testover)
  print('api2 dict api.api', api2.api)
  print('api2 dict api.overloadapi', api2.overloadedapi)
  print('api2 test.over', api2('test.over')())
  print('api2 test.api', api2('test.api')())
  print('api_has', api2.api_has('test.three'))
  print('test.three', api2('test.three')())
  print("doesn't exist", api2('test.four')())

if __name__ == '__main__':
  test()
