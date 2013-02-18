"""
$Id$
"""

import glob, os, sys

from libs import exported
from libs.utils import find_files
import inspect


def get_module_name(path, filename):
  filename = filename.replace(path, "")
  path, filename = os.path.split(filename)
  tpath = path.split(os.sep)
  path = '.'.join(tpath)
  return path, os.path.splitext(filename)[0]


class BasePlugin:
  def __init__(self, name, sname, fullname, basepath, fullimploc):
    self.author = ''
    self.purpose = ''
    self.version = 0
    self.name = name
    self.sname = sname
    self.canreload = True
    self.fullname = fullname
    self.basepath = basepath
    self.fullimploc = fullimploc
    
    self.cmds = {}
    self.defaultcmd = ''
    self.variables = {}
    self.events = []
    self.timers = {}
    exported.logger.adddtype(self.sname)
    
  def load(self):
    # load all commands
    for i in self.cmds:
      self.addCmd(i, self.cmds[i]['func'], self.cmds[i]['shelp'])
      
    # if there is a default command, then set it
    if self.defaultcmd:
      self.setDefaultCmd(self.defaultcmd)
      
    # register all events
    for i in self.events:
      exported.registerevent(i['event'], i['func'])
      
    # register all timers
    for i in self.timers:
      tim = self.timers[i]
      exported.addtimer(i, tim['func'], tim['seconds'], tim['onetime'])
  
  def unload(self):
    'clear all commands for this plugin from cmdMgr'
    exported.cmdMgr.resetPluginCmds(self.sname)

    # unregister all events
    for i in self.events:
      exported.unregisterevent(i['event'], i['func'])

    # delete all timers
    for i in self.timers:
      exported.deletetimer(i)


  def addCmd(self, cmd, tfunc, shelp=None):
    exported.cmdMgr.addCmd(self.sname, self.name, cmd, tfunc, shelp)
    
  def setDefaultCmd(self, name):
    exported.cmdMgr.setDefault(self.sname, name)
    
  def msg(self, msg):
    exported.msg(msg, self.sname)
  

class PluginMgr:
  def __init__(self):
    self.plugins = {}
    self.pluginl = {}
    self.pluginm = {}
    self.sname = 'plugins'
    self.lname = 'Plugins'
    exported.logger.adddtype(self.sname)
    exported.logger.cmd_console([self.sname])    

  def cmd_exported(self, args):
    """---------------------------------------------------------------
@G%(name)s@w - @B%(cmdname)s@w
  see what functions are available to the exported module
  useful for finding out what can be gotten for scripting
  @CUsage@w: exported
---------------------------------------------------------------"""
    tmsg = []
    if len(args) == 0:
      tmsg.append('Items available in exported')
      for i in dir(exported):
        if not (i in ['sys', 'traceback', '__builtins__', '__doc__', '__file__', '__name__', '__package__',]):
          if inspect.isfunction(exported.__dict__[i]):
            tmsg.append('Function: %s' % i)
          elif isinstance(exported.__dict__[i], dict):
            for t in exported.__dict__[i]:
              tmsg.append('Function: %s.%s' % (i,t))
    else:
      i = args[0]
      if i in dir(exported):
        if inspect.isfunction(exported.__dict__[i]):
          tmsg = self.printexported(i, exported.__dict__[i])
        elif isinstance(exported.__dict__[i], dict):
          for t in exported.__dict__[i]:
            tmsg = self.printexported('%s.%s' % (i,t), exported.__dict__[i][t])
    return True, tmsg
    
  def printexported(self, item, tfunction):
    tmsg = []
    tmsg.append('Function: %s' % (item))
    if tfunction.__doc__:
      tlist = tfunction.__doc__.split('\n')
      for i in tlist:
        tmsg.append('  %s' % i)    
    
  def cmd_list(self, args):
    """---------------------------------------------------------------
@G%(name)s@w - @B%(cmdname)s@w
  List plugins
  @CUsage@w: list
---------------------------------------------------------------"""
    msg = ['', 'Plugins:']
    msg.append("%-10s : %-20s %-10s %-5s %s@w" % ('Short Name', 'Name', 'Author', 'Vers', 'Purpose'))
    msg.append('-' * 75)
    for plugin in self.plugins:
      tpl = self.plugins[plugin]
      msg.append("%-10s : %-20s %-10s %-5s %s@w" % (plugin, tpl.name, tpl.author, tpl.version, tpl.purpose))
    msg.append('-' * 75)
    msg.append('')
    return True, msg
    
  def cmd_load(self, args):
    """---------------------------------------------------------------
@G%(name)s@w - @B%(cmdname)s@w
  Load a plugin
  @CUsage@w: load @Yplugin@w
    @Yplugin@w    = the name of the plugin to load
               use the name without the .py    
---------------------------------------------------------------"""
    tmsg = []
    if len(args) == 1:
      basepath = ''
      index = __file__.rfind(os.sep)
      if index == -1:
        basepath = "." + os.sep
      else:
        basepath = __file__[:index]      
        
      _module_list = find_files( basepath, args[0] + ".py")
      
      if len(_module_list) > 1:
        tmsg.append('There is more than one module that matches: %s' % args[0])
      elif len(_module_list) == 0:
        tmsg.append('There are no modules that match: %s' % args[0])        
      else:
        sname = self.load_module(_module_list[0], basepath, True)
        if sname:
          tmsg.append('Load complete: %s - %s' % (sname, self.plugins[sname].name))
        else:
          tmsg.append('Could not load: %s' % args[0])
      return True, tmsg
    else:
      return False, tmsg

  def cmd_unload(self, args):
    """---------------------------------------------------------------
@G%(name)s@w - @B%(cmdname)s@w
  unload a plugin
  @CUsage@w: unload @Yplugin@w
    @Yplugin@w    = the shortname of the plugin to load
---------------------------------------------------------------"""    
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
    """---------------------------------------------------------------
@G%(name)s@w - @B%(cmdname)s@w
  reload a plugin
  @CUsage@w: reload @Yplugin@w
    @Yplugin@w    = the shortname of the plugin to reload
---------------------------------------------------------------""" 
    tmsg = []
    if args[0] and args[0] in self.plugins:
      if self.plugins[args[0]].canreload:
        tret = self.reload_module(args[0], True)
        if tret and tret != True:
          tmsg.append("Reload complete: %s" % self.plugins[tret].fullimploc)
          return True
      else:
        tmsg.append("That plugin cannot be reloaded")
        return True
    else:
      tmsg.append("That plugin does not exist")
      return True, tmsg

  def load_modules(self, filter):
    index = __file__.rfind(os.sep)
    if index == -1:
      basepath = "." + os.sep
    else:
      basepath = __file__[:index]
    
    _module_list = find_files( basepath, filter)
    _module_list.sort()

    for fullname in _module_list:
      # we skip over all files that start with a _
      # this allows hackers to be working on a module and not have
      # it die every time.
      self.load_module(fullname, basepath)

  def load_module(self, fullname, basepath, force=False):
    imploc, modname = get_module_name(basepath, fullname)
    
    if modname.startswith("_") and not force:
      return False

    try:
      if imploc == '.':
        fullimploc = "plugins" + imploc + modname          
      else:
        fullimploc = "plugins" + imploc + '.' + modname
      exported.msg('loading %s' % fullimploc, self.sname)
      _module = __import__(fullimploc)
      _module = sys.modules[fullimploc]
      load = True

      if _module.__dict__.has_key("autoload") and not force:
        if not _module.autoload:          
          load = False
      
      if load:
        if _module.__dict__.has_key("Plugin"):
          self.add_plugin(_module, fullname, basepath, fullimploc)

        else:
          exported.msg('Module %s has no Plugin class', _module.name, self.sname)

        _module.__dict__["proxy_import"] = 1
        exported.write_message("load: loaded %s" % fullimploc)
        
        return _module.sname
      else:
        exported.msg('Not loading %s (%s) because autoload is False' % (_module.name, fullimploc), self.sname) 
      return True
    except:
      exported.write_traceback("Module '%s' refuses to load." % fullimploc)
      return False
     
  def unload_module(self, fullimploc):
    if sys.modules.has_key(fullimploc):
      
      _module = sys.modules[fullimploc]
      _oldmodule = _module
      try:
        if _module.__dict__.has_key("proxy_import"):
          
          if _module.__dict__.has_key("unload"):
            try:
              _module.unload()
            except:
              exported.write_traceback("unload: module %s didn't unload properly." % fullimploc)
          
          if not self.remove_plugin(_module.sname):
            exported.write_message('could not remove plugin %s' % fullimploc)
          
        del sys.modules[fullimploc]
        exported.write_message("unload: unloaded %s." % fullimploc)

      except:
        exported.write_traceback("unload: had problems unloading %s." % fullimploc)
        return False
    else:
      _oldmodule = None
      
    return True

  def reload_module(self, modname, force=False):
    if modname in self.plugins:
      plugin = self.plugins[modname]  
      fullimploc = plugin.fullimploc
      basepath = plugin.basepath
      fullname = plugin.fullname
      plugin = None
      if not self.unload_module(fullimploc):
        return False

      if fullname and basepath:
        return self.load_module(fullname, basepath, force)

    else:
      return False
  
  def add_plugin(self, module, fullname, basepath, fullimploc):
    module.__dict__["lyntin_import"] = 1    
    plugin = module.Plugin(module.name, module.sname, fullname, basepath, fullimploc)
    plugin.author = module.author
    plugin.purpose = module.purpose
    plugin.version = module.version    
    if plugin.name in self.pluginl:
      print('Plugin %s already exists' % plugin.name)
      return False
    if plugin.sname in self.plugins:
      print('Plugin %s already exists' % plugin.sname)
      return False
    
    plugin.load()
    self.pluginl[plugin.name] = plugin
    self.plugins[plugin.sname] = plugin
    self.pluginm[plugin.name] = module
    return True

  def remove_plugin(self, pluginname):
    plugin = None
    if pluginname in self.plugins:
      plugin = self.plugins[pluginname]
      plugin.unload()
      del self.plugins[plugin.sname]
      del self.pluginl[plugin.name]
      del self.pluginm[plugin.name]      
      plugin = None      
      return True
    else:
      return False

  def load(self):
    self.load_modules("*.py")
    exported.cmdMgr.addCmd(self.sname, 'Plugin Manager', 'list', self.cmd_list, 'List plugins')
    exported.cmdMgr.addCmd(self.sname, 'Plugin Manager', 'load', self.cmd_load, 'Load a plugin')
    exported.cmdMgr.addCmd(self.sname, 'Plugin Manager', 'unload', self.cmd_unload, 'Unload a plugin')
    exported.cmdMgr.addCmd(self.sname, 'Plugin Manager', 'reload', self.cmd_reload, 'Reload a plugin')
    exported.cmdMgr.addCmd(self.sname, 'Plugin Manager', 'exported', self.cmd_exported, 'Examine the exported module')
    exported.cmdMgr.setDefault(self.sname, 'list')
    