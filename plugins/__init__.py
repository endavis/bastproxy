"""
$Id$

make all functions that add things use kwargs instead of a table
"""

import glob
import os
import sys
import inspect
import operator

from libs.utils import find_files, verify, convert
from libs.persistentdict import PersistentDict
from libs.utils import DotDict
from libs.api import API
from plugins._baseplugin import BasePlugin


def get_module_name(path, filename):
  """
  get a module name
  """
  filename = filename.replace(path, "")
  path, filename = os.path.split(filename)
  tpath = path.split(os.sep)
  path = '.'.join(tpath)
  return path, os.path.splitext(filename)[0]


def findplugin(name):
  """
  find a plugin file
  """
  basepath = ''
  index = __file__.rfind(os.sep)

  if index == -1:
    basepath = "." + os.sep
  else:
    basepath = __file__[:index]

  if '.' in name:
    tlist = name.split('.')
    name = tlist[-1]
    del tlist[-1]
    npath = os.sep.join(tlist)

  _module_list = find_files( basepath, name + ".py")

  if len(_module_list) == 1:
    return _module_list[0], basepath
  else:
    for i in _module_list:
      if npath in i:
        return i, basepath

  return False, ''

class PluginMgr(object):
  """
  a class to manage plugins
  """
  def __init__(self):
    """
    initialize the instance
    """
    self.plugins = {}
    self.pluginl = {}
    self.pluginm = {}
    self.api = API()
    self.savefile = os.path.join(self.api.BASEPATH, 'data',
                                          'plugins', 'loadedplugins.txt')
    self.loadedplugins = PersistentDict(self.savefile, 'c', format='json')
    self.sname = 'plugins'
    self.lname = 'Plugin Manager'

    self.api.add(self.sname, 'isinstalled', self.api_isinstalled)
    self.api.add(self.sname, 'getp', self.api_getp)

  # get a plugin instance
  def api_getp(self, pluginname):
    """  get a plugin instance
    @Ypluginname@w  = the plugin to check for"""

    if type(pluginname) == str:
      if pluginname in self.plugins:
        return self.plugins[pluginname]
      if pluginname in self.pluginl:
        return self.pluginl[pluginname]
    elif type(pluginname) == BasePlugin:
      return pluginname

    return None

  # check if a plugin is installed
  def api_isinstalled(self, pluginname):
    """  check if a plugin is installed
    @Ypluginname@w  = the plugin to check for"""
    if pluginname in self.plugins or pluginname in self.pluginl:
      return True
    return False

  def loaddependencies(self, pluginname, dependencies):
    """
    load a list of modules
    """
    for i in dependencies:
      if i in self.plugins or i in self.pluginl:
        continue

      self.api.get('output.msg')('%s: loading dependency %s' % (pluginname, i), pluginname)

      name, path = findplugin(i)
      if name:
        self.load_module(name, path, force=True)

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List plugins
      @CUsage@w: list
    """
    msg = []
    if len(args) > 0:
      #TODO: check for the name here
      pass
    else:
      tkeys = self.plugins.keys()
      tkeys.sort()
      msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                          ('Short Name', 'Name', 'Author', 'Vers', 'Purpose'))
      msg.append('-' * 75)
      for plugin in tkeys:
        tpl = self.plugins[plugin]
        msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                    (plugin, tpl.name, tpl.author, tpl.version, tpl.purpose))
    return True, msg

  def cmd_load(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Load a plugin
      @CUsage@w: load @Yplugin@w
        @Yplugin@w    = the name of the plugin to load
               use the name without the .py
    """
    tmsg = []
    if len(args) == 1:
      basepath = ''
      index = __file__.rfind(os.sep)
      if index == -1:
        basepath = "." + os.sep
      else:
        basepath = __file__[:index]

      fname = args[0].replace('.', os.sep)
      _module_list = find_files( basepath, fname + ".py")

      if len(_module_list) > 1:
        tmsg.append('There is more than one module that matches: %s' % \
                                                              args[0])
      elif len(_module_list) == 0:
        tmsg.append('There are no modules that match: %s' % args[0])
      else:
        sname, reason = self.load_module(_module_list[0], basepath, True)
        if sname:
          if reason == 'already':
            tmsg.append('Module %s is already loaded' % sname)
          else:
            tmsg.append('Load complete: %s - %s' % \
                                          (sname, self.plugins[sname].name))
        else:
          tmsg.append('Could not load: %s' % args[0])
      return True, tmsg
    else:
      return False, tmsg

  def cmd_unload(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      unload a plugin
      @CUsage@w: unload @Yplugin@w
        @Yplugin@w    = the shortname of the plugin to load
    """
    tmsg = []
    if len(args) == 1 and args[0] in self.plugins:
      if self.plugins[args[0]].canreload:
        if self.unload_module(self.plugins[args[0]].fullimploc):
          tmsg.append("Unloaded: %s" % args[0])
        else:
          tmsg.append("Could not unload:: %s" % args[0])
      else:
        tmsg.append("That plugin can not be unloaded")
      return True, tmsg

    return False

  def cmd_reload(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      reload a plugin
      @CUsage@w: reload @Yplugin@w
        @Yplugin@w    = the shortname of the plugin to reload
    """
    tmsg = []
    if len(args) == 0:
      return True, ['Please specify a plugin']

    if args[0] and args[0] in self.plugins:
      if self.plugins[args[0]].canreload:
        tret, _ = self.reload_module(args[0], True)
        if tret and tret != True:
          tmsg.append("Reload complete: %s" % self.plugins[tret].fullimploc)
          return True, tmsg
      else:
        tmsg.append("That plugin cannot be reloaded")
        return True, tmsg
    else:
      tmsg.append("That plugin does not exist")
      return True, tmsg

  def load_modules(self, tfilter):
    """
    load modules in all directories under plugins
    """
    index = __file__.rfind(os.sep)
    if index == -1:
      basepath = "." + os.sep
    else:
      basepath = __file__[:index]

    _module_list = find_files( basepath, tfilter)
    _module_list.sort()

    pluginlist = {}

    load = False

    for fullname in _module_list:
      force = False
      if fullname in self.loadedplugins:
        force = True
      modname, status = self.load_module(fullname, basepath, force=force, runload=load)

      if modname == 'log':
        self.api.get('log.adddtype')(self.sname)
        self.api.get('log.console')(self.sname)

    if not load:
      testsort = sorted(self.plugins.values(), key=operator.attrgetter('priority'))
      for i in testsort:
        self.loadplugin(i)

  def load_module(self, fullname, basepath, force=False, runload=True):
    """
    load a single module
    """
    imploc, modname = get_module_name(basepath, fullname)

    if modname.startswith("_"):
      return False, 'dev'

    try:
      if imploc == '.':
        fullimploc = "plugins" + imploc + modname
      else:
        fullimploc = "plugins" + imploc + '.' + modname
      if fullimploc in sys.modules:
        return sys.modules[fullimploc].SNAME, 'already'

      self.api.get('output.msg')('importing %s' % fullimploc, self.sname)
      _module = __import__(fullimploc)
      _module = sys.modules[fullimploc]
      self.api.get('output.msg')('imported %s' % fullimploc, self.sname)
      load = True

      if 'AUTOLOAD' in _module.__dict__ and not force:
        if not _module.AUTOLOAD:
          load = False
      elif not ('AUTOLOAD' in _module.__dict__):
        load = False

      if load:
        if "Plugin" in _module.__dict__:
          self.add_plugin(_module, fullname, basepath, fullimploc, runload)

        else:
          self.api.get('output.msg')('Module %s has no Plugin class' % \
                                              _module.NAME, self.sname)

        _module.__dict__["proxy_import"] = 1

        return _module.SNAME, 'Loaded'
      else:
        if fullimploc in sys.modules:
          del sys.modules[fullimploc]
        self.api.get('output.msg')('Not loading %s (%s) because autoload is False' % \
                                    (_module.NAME, fullimploc), self.sname)
      return True, 'not autoloaded'
    except:
      if fullimploc in sys.modules:
        del sys.modules[fullimploc]

      self.api.get('output.traceback')("Module '%s' refuses to import/load." % fullimploc)
      return False, 'error'

  def unload_module(self, fullimploc):
    """
    unload a module
    """
    if fullimploc in sys.modules:

      _module = sys.modules[fullimploc]
      _oldmodule = _module
      try:
        if "proxy_import" in _module.__dict__:

          if "unload" in _module.__dict__:
            try:
              _module.unload()
            except:
              self.api.get('output.traceback')(
                    "unload: module %s didn't unload properly." % fullimploc)

          if not self.remove_plugin(_module.SNAME):
            self.api.get('output.client')('could not remove plugin %s' % fullimploc)

        del sys.modules[fullimploc]
        self.api.get('output.client')("unload: unloaded %s." % fullimploc)

      except:
        self.api.get('output.traceback')(
                      "unload: had problems unloading %s." % fullimploc)
        return False
    else:
      _oldmodule = None

    return True

  def reload_module(self, modname, force=False):
    """
    reload a module
    """
    if modname in self.plugins:
      plugin = self.plugins[modname]
      fullimploc = plugin.fullimploc
      basepath = plugin.basepath
      fullname = plugin.fullname
      plugin = None
      if not self.unload_module(fullimploc):
        return False, ''

      if fullname and basepath:
        return self.load_module(fullname, basepath, force)

    else:
      return False, ''

  def loadplugin(self, plugin):
    """
    check dependencies and run the load function
    """
    self.api.get('output.msg')('loading dependencies for %s' % plugin.fullimploc, self.sname)
    self.loaddependencies(plugin.sname, plugin.dependencies)
    self.api.get('output.client')("load: loading %s" % plugin.fullimploc)
    self.api.get('output.msg')('loading %s (%s: %s)' % (plugin.fullimploc,
                                    plugin.sname, plugin.name), self.sname)
    plugin.load()
    self.api.get('output.client')("load: loaded %s" % plugin.fullimploc)
    self.api.get('output.msg')('loaded %s (%s: %s)' % (plugin.fullimploc,
                                    plugin.sname, plugin.name), self.sname)

    self.api.get('events.eraise')('%s_plugin_load' % plugin.sname, {})

  def add_plugin(self, module, fullname, basepath, fullimploc, load=True):
    """
    add a plugin to be managed
    """
    module.__dict__["lyntin_import"] = 1
    plugin = module.Plugin(module.NAME, module.SNAME,
                                    fullname, basepath, fullimploc)
    plugin.author = module.AUTHOR
    plugin.purpose = module.PURPOSE
    plugin.version = module.VERSION
    try:
      plugin.priority = module.PRIORITY
    except AttributeError:
      pass
    if plugin.name in self.pluginl:
      self.api.get('output.msg')('Plugin %s already exists' % plugin.name, self.sname)
      return False
    if plugin.sname in self.plugins:
      self.api.get('output.msg')('Plugin %s already exists' % plugin.sname, self.sname)
      return False

    if load:
      try:
        #check dependencies here
        self.loadplugin(plugin)
      except:
        self.api.get('output.traceback')(
                      "load: had problems running the load method for %s." % fullimploc)
        return False
    self.pluginl[plugin.name] = plugin
    self.plugins[plugin.sname] = plugin
    self.pluginm[plugin.name] = module
    self.loadedplugins[fullname] = True
    self.loadedplugins.sync()

    return True

  def remove_plugin(self, pluginname):
    """
    remove a plugin
    """
    plugin = None
    if pluginname in self.plugins:
      plugin = self.plugins[pluginname]
      try:
        plugin.unload()
      except:
        self.api.get('output.traceback')(
                      "unload: had problems running the unload method for %s." % plugin.sname)
        return False

      del self.plugins[plugin.sname]
      del self.pluginl[plugin.name]
      del self.pluginm[plugin.name]
      del self.loadedplugins[plugin.fullname]
      self.loadedplugins.sync()

      self.api.get('events.eraise')('%s_plugin_unload' % plugin.sname, {})

      plugin = None

      return True
    else:
      return False

  def savestate(self):
    """
    save all plugins
    """
    for i in self.plugins:
      self.plugins[i].savestate()

  def load(self):
    """
    load various things
    """
    self.api.get('managers.add')('plugin', self)

    self.load_modules("*.py")

    self.api.get('commands.add')('list', self.cmd_list,
                        lname='Plugin Manager', shelp='List plugins')
    self.api.get('commands.add')('load', self.cmd_load,
                        lname='Plugin Manager', shelp='Load a plugin')
    self.api.get('commands.add')('unload', self.cmd_unload,
                        lname='Plugin Manager', shelp='Unload a plugin')
    self.api.get('commands.add')('reload', self.cmd_reload,
                        lname='Plugin Manager', shelp='Reload a plugin')

    self.api.get('commands.default')(self.sname, 'list')
    self.api.get('events.register')('savestate', self.savestate, plugin=self.sname)

