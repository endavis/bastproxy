"""
manages all plugins

#TODO: make all functions that add things use kwargs instead of a table
"""
import glob
import os
import sys
import inspect
import operator
import fnmatch

import libs.argp as argp
from libs.persistentdict import PersistentDict
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin

class PluginMgr(BasePlugin):
  """
  a class to manage plugins
  """
  def __init__(self):
    """
    initialize the instance
    """
    # Examples:
    #  name : 'Actions' - from plugin file variable NAME (long name)
    #  sname : 'actions' - from plugin file variable SNAME (short name)
    #  modpath : '/client/actions.py' - path relative to the plugins directory
    #  basepath : '/home/src/games/bastproxy/bp/plugins' - the full path to the
    #                                                       plugins directory
    #  fullimploc : 'plugins.client.actions' - import location


    #name, sname, modpath, basepath, fullimploc
    BasePlugin.__init__(self,
                        'Plugin Manager', #name,
                        'plugins', #sname,
                        "/__init__.py", #modpath
                        "$basepath$", # basepath
                        "plugins.__init__", # fullimploc
                       )

    self.canreload = False

    #key:   modpath
    #value: {'plugin', 'module'}
    self.loadedpluginsd = {}

    self.pluginlookupbysname = {}
    self.pluginlookupbyname = {}
    self.pluginlookupbyfullimploc = {}

    # key:   modpath
    # value: {'sname', 'name', 'purpose', 'author',
    #        'version', 'modpath', 'fullimploc'
    self.allplugininfo = {}

    index = __file__.rfind(os.sep)
    if index == -1:
      self.basepath = "." + os.sep
    else:
      self.basepath = __file__[:index]

    self.savefile = os.path.join(self.api.BASEPATH, 'data',
                                 'plugins', 'loadedplugins.txt')
    self.loadedplugins = PersistentDict(self.savefile, 'c')

    self.api('api.add')('isloaded', self._api_isloaded)
    self.api('api.add')('getp', self._api_getp)
    self.api('api.add')('module', self._api_getmodule)
    self.api('api.add')('allplugininfo', self._api_allplugininfo)
    self.api('api.add')('savestate', self.savestate)

  # return the dictionary of all plugins
  def _api_allplugininfo(self):
    """
    return the plugininfo dictionary
    """
    return self.allplugininfo

  def findloadedplugin(self, plugin):
    """
    find a plugin
    """
    return self.api('plugins.getp')(plugin)

  # get a plugin instance
  def _api_getmodule(self, pluginname):
    """  returns the module of a plugin
    @Ypluginname@w  = the plugin to check for"""
    plugin = self.api('plugins.getp')(pluginname)

    if plugin:
      return self.loadedpluginsd[plugin.modpath]['module']

    return None

  # get a plugin instance
  def _api_getp(self, pluginname):
    """  get a loaded plugin instance
    @Ypluginname@w  = the plugin to get"""

    if isinstance(pluginname, basestring):
      if pluginname in self.loadedpluginsd:
        return self.loadedpluginsd[pluginname]['plugin']
      if pluginname in self.pluginlookupbysname:
        return self.loadedpluginsd[self.pluginlookupbysname[pluginname]]['plugin']
      if pluginname in self.pluginlookupbyname:
        return self.loadedpluginsd[self.pluginlookupbyname[pluginname]]['plugin']
      if pluginname in self.pluginlookupbyfullimploc:
        return self.loadedpluginsd[self.pluginlookupbyfullimploc[pluginname]]['plugin']
    elif isinstance(pluginname, BasePlugin):
      return pluginname

    return None

  # check if a plugin is loaded
  def _api_isloaded(self, pluginname):
    """  check if a plugin is loaded
    @Ypluginname@w  = the plugin to check for"""
    plugin = self.api('plugins.getp')(pluginname)

    if plugin:
      return True

    return False

  # load plugin dependencies
  def _loaddependencies(self, pluginname, dependencies):
    """
    load a list of modules
    """
    for i in dependencies:
      plugin = self.api('plugins.getp')(i)
      if plugin:
        continue

      self.api('send.msg')('%s: loading dependency %s' % (pluginname, i),
                           pluginname)

      name, path = imputils.findmodule(self.basepath, i)
      if name:
        modpath = name.replace(path, '')
        self._loadplugin(modpath, path, force=True)

  # get all not loaded plugins
  def _getnotloadedplugins(self):
    """
    create a message of all not loaded plugins
    """
    msg = []
    badplugins = self._updateallplugininfo()
    pdiff = set(self.allplugininfo) - set(self.loadedpluginsd)
    for modpath in sorted(pdiff):
      msg.append("%-20s : %-25s %-10s %-5s %s@w" % \
                  (self.allplugininfo[modpath]['fullimploc'].replace('plugins.', ''),
                   self.allplugininfo[modpath]['name'],
                   self.allplugininfo[modpath]['author'],
                   self.allplugininfo[modpath]['version'],
                   self.allplugininfo[modpath]['purpose']))
    if msg:
      msg.insert(0, '-' * 75)
      msg.insert(0, "%-20s : %-25s %-10s %-5s %s@w" % \
                          ('Location', 'Name', 'Author', 'Vers', 'Purpose'))
      msg.insert(0, 'The following plugins are not loaded')

    if badplugins:
      msg.append('')
      msg.append('The following files would not import')
      for bad in badplugins:
        msg.append(bad.replace('plugins.', ''))

    return msg

  # get plugins that are change on disk
  def _getchangedplugins(self):
    """
    create a message of plugins that are changed on disk
    """
    msg = []

    plugins = sorted([i['plugin'] for i in self.loadedpluginsd.values()],
                     key=operator.attrgetter('package'))
    packageheader = []

    msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                        ('Short Name', 'Name', 'Author', 'Vers', 'Purpose'))
    msg.append('-' * 75)

    found = False
    for tpl in plugins:
      if tpl.ischangedondisk():
        found = True
        if tpl.package not in packageheader:
          if packageheader:
            msg.append('')
          packageheader.append(tpl.package)
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
                  (tpl.sname, tpl.name,
                   tpl.author, tpl.version, tpl.purpose))

    if found:
      return msg

    return ['No plugins are changed on disk.']

  # get a message of plugins in a package
  def _getpackageplugins(self, package):
    """
    create a message of plugins in a package
    """
    msg = []

    plist = []
    for plugin in [i['plugin'] for i in self.loadedpluginsd.values()]:
      if plugin.package == package:
        plist.append(plugin)

    if plist:
      plugins = sorted(plist, key=operator.attrgetter('sname'))
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
                  (tpl.sname, tpl.name,
                   tpl.author, tpl.version, tpl.purpose))
    else:
      msg.append('That is not a valid package')

    return msg

  # create a message of all plugins
  def _getallplugins(self):
    """
    create a message of all plugins
    """
    msg = []

    plugins = sorted([i['plugin'] for i in self.loadedpluginsd.values()],
                     key=operator.attrgetter('package'))
    packageheader = []
    msg.append("%-10s : %-25s %-10s %-5s %s@w" % \
                        ('Short Name', 'Name', 'Author', 'Vers', 'Purpose'))
    msg.append('-' * 75)
    for tpl in plugins:
      if tpl.package not in packageheader:
        if packageheader:
          msg.append('')
        packageheader.append(tpl.package)
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
                  (tpl.sname, tpl.name,
                   tpl.author, tpl.version, tpl.purpose))
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
      msg.extend(self._getpackageplugins(args['package']))
    else:
      msg.extend(self._getallplugins())
    return True, msg

  # command to load plugins
  def _cmd_load(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Load a plugin
      @CUsage@w: load @Yplugin@w
        @Yplugin@w    = the name of the plugin to load
               use the name without the .py
    """
    tmsg = []
    plugin = args['plugin']
    if plugin:

      fname = plugin.replace('.', os.sep)
      _module_list = imputils.find_files(self.basepath, fname + ".py")

      if len(_module_list) > 1:
        tmsg.append('There is more than one module that matches: %s' % \
                                                              plugin)
      elif not _module_list:
        tmsg.append('There are no modules that match: %s' % plugin)
      else:
        modpath = _module_list[0].replace(self.basepath, '')
        sname, reason = self._loadplugin(modpath, self.basepath, True)
        plugin = self.api('plugins.getp')(sname)
        if sname:
          if reason == 'already':
            tmsg.append('Plugin %s is already loaded' % sname)
          else:
            tmsg.append('Load complete: %s - %s' % \
                                          (sname, plugin.name))
        else:
          tmsg.append('Could not load: %s' % plugin)
      return True, tmsg
    else:
      return False, ['@Rplease specify a plugin@w']

  # command to unload a plugin
  def _cmd_unload(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      unload a plugin
      @CUsage@w: unload @Yplugin@w
        @Yplugin@w    = the shortname of the plugin to load
    """
    tmsg = []
    plugina = args['plugin']

    if not plugina:
      return False, ['@Rplease specify a plugin@w']

    plugin = self.findloadedplugin(plugina)

    if plugin:
      if plugin.canreload:
        if self._unloadplugin(plugin.fullimploc):
          tmsg.append("Unloaded: %s" % plugin.fullimploc)
        else:
          tmsg.append("Could not unload:: %s" % plugin.fullimploc)
      else:
        tmsg.append("That plugin can not be unloaded")
      return True, tmsg
    elif plugin:
      tmsg.append('plugin %s does not exist' % plugin)
      return True, tmsg

    return False, ['@Rplease specify a plugin@w']

  # command to reload a plugin
  def _cmd_reload(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      reload a plugin
      @CUsage@w: reload @Yplugin@w
        @Yplugin@w    = the shortname of the plugin to reload
    """
    tmsg = []
    plugina = args['plugin']

    if not plugina:
      return False, ['@Rplease specify a plugin@w']

    plugin = self.findloadedplugin(plugina)

    if plugin:
      if plugin.canreload:
        tret, _ = self._reloadplugin(plugin.modpath, True)
        if tret and tret != True:
          plugin = self.findloadedplugin(plugina)
          tmsg.append("Reload complete: %s" % plugin.fullimploc)
          return True, tmsg
      else:
        tmsg.append("That plugin cannot be reloaded")
        return True, tmsg
    else:
      tmsg.append('plugin %s does not exist' % plugina)
      return True, tmsg

    return False, tmsg

  # load all plugins
  def _loadplugins(self, tfilter):
    """
    load plugins in all directories under the plugin directory
    """
    _module_list = imputils.find_files(self.basepath, tfilter)
    _module_list.sort()

    load = False

    for fullpath in _module_list:
      modpath = fullpath.replace(self.basepath, '')
      force = False
      if modpath in self.loadedplugins:
        force = True
      modname, dummy = self._loadplugin(modpath, self.basepath,
                                        force=force, runload=load)

      if modname == 'log':
        self.api('log.adddtype')(self.sname)
        self.api('log.console')(self.sname)
        self.api('log.adddtype')('upgrade')
        self.api('log.console')('upgrade')

    if not load:
      testsort = sorted([i['plugin'] for i in self.loadedpluginsd.values()],
                        key=operator.attrgetter('priority'))
      for i in testsort:
        try:
          #check dependencies here
          self.loadplugin(i)
        except Exception: # pylint: disable=broad-except
          self.api('send.traceback')(
              "load: had problems running the load method for %s." \
                          % i.fullimploc)
          imputils.deletemodule(i.fullimploc)

  # update all plugin info
  def _updateallplugininfo(self):
    """
    find plugins that are not in self.allplugininfo
    """
    _plugin_list = imputils.find_files(self.basepath, '*.py')
    _plugin_list.sort()

    self.allplugininfo = {}
    badplugins = []

    for fullpath in _plugin_list:
      modpath = fullpath.replace(self.basepath, '')

      imploc, modname = imputils.get_module_name(modpath)

      if not modname.startswith("_"):
        fullimploc = "plugins" + '.' + imploc
        if fullimploc in sys.modules:
          plugin = self.api('plugins.getp')(modpath)
          self.allplugininfo[modpath] = {}
          self.allplugininfo[modpath]['sname'] = plugin.sname
          self.allplugininfo[modpath]['name'] = plugin.name
          self.allplugininfo[modpath]['purpose'] = plugin.purpose
          self.allplugininfo[modpath]['author'] = plugin.author
          self.allplugininfo[modpath]['version'] = plugin.version
          self.allplugininfo[modpath]['modpath'] = modpath
          self.allplugininfo[modpath]['fullimploc'] = fullimploc

        else:
          try:
            _module = __import__(fullimploc)
            _module = sys.modules[fullimploc]

            self.allplugininfo[modpath] = {}
            self.allplugininfo[modpath]['sname'] = _module.SNAME
            self.allplugininfo[modpath]['name'] = _module.NAME
            self.allplugininfo[modpath]['purpose'] = _module.PURPOSE
            self.allplugininfo[modpath]['author'] = _module.AUTHOR
            self.allplugininfo[modpath]['version'] = _module.VERSION
            self.allplugininfo[modpath]['modpath'] = modpath
            self.allplugininfo[modpath]['fullimploc'] = fullimploc

            imputils.deletemodule(fullimploc)

          except Exception: # pylint: disable=broad-except
            badplugins.append(fullimploc)

    return badplugins

  # load a plugin
  def _loadplugin(self, modpath, basepath, force=False, runload=True):
    """
    load a single plugin
    """
    success, msg, module, fullimploc = imputils.importmodule(modpath, basepath,
                                                             self, 'plugins')

    if success and msg == 'import':

      load = True

      if 'AUTOLOAD' in module.__dict__ and not force:
        if not module.AUTOLOAD:
          load = False
      elif 'AUTOLOAD' not in module.__dict__:
        load = False

      if modpath not in self.allplugininfo:
        self.allplugininfo[modpath] = {}
        self.allplugininfo[modpath]['sname'] = module.SNAME
        self.allplugininfo[modpath]['name'] = module.NAME
        self.allplugininfo[modpath]['purpose'] = module.PURPOSE
        self.allplugininfo[modpath]['author'] = module.AUTHOR
        self.allplugininfo[modpath]['version'] = module.VERSION
        self.allplugininfo[modpath]['modpath'] = modpath
        self.allplugininfo[modpath]['fullimploc'] = fullimploc

      if load:
        if "Plugin" in module.__dict__:
          self._addplugin(module, modpath, basepath, fullimploc, runload)

        else:
          self.api('send.msg')('Module %s has no Plugin class' % \
                                              module.NAME)

        module.__dict__["proxy_import"] = 1

        return module.SNAME, 'Loaded'
      else:
        imputils.deletemodule(fullimploc)
        self.api('send.msg')(
            'Not loading %s (%s) because autoload is False' % \
                                    (module.NAME, fullimploc), primary='plugins')
      return True, 'not autoloaded'

    return success, msg

  # unload a plugin
  def _unloadplugin(self, fullimploc):
    """
    unload a module
    """
    if fullimploc in sys.modules:

      _module = sys.modules[fullimploc]
      success = True
      try:
        if "proxy_import" in _module.__dict__:
          self.api('send.client')(
              'unload: unloading %s' % fullimploc)
          if "unload" in _module.__dict__:
            try:
              _module.unload()
            except Exception: # pylint: disable=broad-except
              success = False
              self.api('send.traceback')(
                  "unload: module %s didn't unload properly." % fullimploc)

          if not self._removeplugin(_module.SNAME):
            self.api('send.client')(
                'could not remove plugin %s' % fullimploc)
            success = False

      except Exception: # pylint: disable=broad-except
        self.api('send.traceback')(
            "unload: had problems unloading %s." % fullimploc)
        success = False

      if success:
        imputils.deletemodule(fullimploc)
        self.api('send.client')("unload: unloaded %s." % fullimploc)

    return success

  # reload a plugin
  def _reloadplugin(self, modpath, force=False):
    """
    reload a plugin
    """
    if modpath in self.loadedpluginsd:
      plugin = self.api.get('plugins.getp')(modpath)
      fullimploc = plugin.fullimploc
      basepath = plugin.basepath
      modpath = plugin.modpath
      sname = plugin.sname
      try:
        reloaddependents = plugin.reloaddependents
      except Exception: # pylint: disable=broad-except
        reloaddependents = False
      plugin = None
      if not self._unloadplugin(fullimploc):
        return False, ''

      if modpath and basepath:
        retval = self._loadplugin(modpath, basepath, force)
        if retval and reloaddependents:
          self._reloadalldependents(sname)
        return retval

    else:
      return False, ''

  # reload all dependents
  def _reloadalldependents(self, reloadedplugin):
    """
    reload all dependents
    """
    testsort = sorted([i['plugin'] for i in self.loadedpluginsd.values()],
                      key=operator.attrgetter('priority'))
    for plugin in testsort:
      if plugin.sname != reloadedplugin:
        if reloadedplugin in plugin.dependencies:
          self.api('send.msg')('reloading dependent %s of %s' % \
                      (plugin.sname, reloadedplugin), plugin.sname)
          plugin.savestate()
          self._reloadplugin(plugin.modpath, True)

  # load a plugin
  def loadplugin(self, plugin):
    """
    check dependencies and run the load function
    """
    self.api('send.msg')('loading dependencies for %s' % \
                                  plugin.fullimploc, plugin.sname)
    self._loaddependencies(plugin.sname, plugin.dependencies)
    self.api('send.client')("load: loading %s with priority %s" % \
			    (plugin.fullimploc, plugin.priority))
    self.api('send.msg')('loading %s (%s: %s)' % \
              (plugin.fullimploc, plugin.sname, plugin.name), plugin.sname)
    plugin.load()
    self.api('send.client')("load: loaded %s" % plugin.fullimploc)
    self.api('send.msg')('loaded %s (%s: %s)' % \
              (plugin.fullimploc, plugin.sname, plugin.name), plugin.sname)

    self.api('events.eraise')('%s_plugin_loaded' % plugin.sname, {})
    self.api('events.eraise')('plugin_loaded', {'plugin':plugin.sname})

  # add a plugin
  def _addplugin(self, module, modpath, basepath, fullimploc, load=True):
    # pylint: disable=too-many-arguments
    """
    add a plugin to be managed
    """
    pluginn = self.api('plugins.getp')(module.NAME)
    plugins = self.api('plugins.getp')(module.SNAME)
    if plugins or pluginn:
      self.api('send.msg')('Plugin %s already exists' % module.NAME,
                           secondary=module.SNAME)
      return False

    plugin = module.Plugin(module.NAME, module.SNAME,
                           modpath, basepath, fullimploc)
    plugin.author = module.AUTHOR
    plugin.purpose = module.PURPOSE
    plugin.version = module.VERSION
    try:
      plugin.priority = module.PRIORITY
    except AttributeError:
      pass

    if load:
      try:
        #check dependencies here
        self.loadplugin(plugin)
      except Exception: # pylint: disable=broad-except
        self.api('send.traceback')(
            "load: had problems running the load method for %s." \
                                                % fullimploc)
        imputils.deletemodule(fullimploc)
        return False

    self.loadedpluginsd[modpath] = {}
    self.loadedpluginsd[modpath]['plugin'] = plugin
    self.loadedpluginsd[modpath]['module'] = module

    self.pluginlookupbysname[plugin.sname] = modpath
    self.pluginlookupbyname[plugin.name] = modpath
    self.pluginlookupbyfullimploc[fullimploc] = modpath

    self.loadedplugins[modpath] = True
    self.loadedplugins.sync()

    return True

  # remove a plugin
  def _removeplugin(self, pluginname):
    """
    remove a plugin
    """
    plugin = self.api('plugins.getp')(pluginname)
    if plugin:
      try:
        plugin.unload()
        self.api('events.eraise')('%s_plugin_unload' % plugin.sname, {})
        self.api('events.eraise')('plugin_unloaded', {'name':plugin.sname})
        self.api('send.msg')('Plugin %s unloaded' % plugin.sname, secondary=plugin.sname)
      except Exception: # pylint: disable=broad-except
        self.api('send.traceback')(
            "unload: had problems running the unload method for %s." \
                                  % plugin.sname)
        return False

      del self.loadedpluginsd[plugin.modpath]

      del self.pluginlookupbyfullimploc[plugin.fullimploc]
      del self.pluginlookupbyname[plugin.name]
      del self.pluginlookupbysname[plugin.sname]

      del self.loadedplugins[plugin.modpath]
      self.loadedplugins.sync()

      plugin = None

      return True

    return False

  # get stats for this plugin
  def getstats(self):
    """
    return stats for events
    """
    stats = {}
    stats['Base Sizes'] = {}

    stats['Base Sizes']['showorder'] = ['Class', 'Api', 'loadedpluginsd',
                                        'plugininfo']
    stats['Base Sizes']['loadedpluginsd'] = '%s bytes' % \
                                      sys.getsizeof(self.loadedpluginsd)
    stats['Base Sizes']['plugininfo'] = '%s bytes' % \
                                      sys.getsizeof(self.allplugininfo)

    stats['Base Sizes']['Class'] = '%s bytes' % sys.getsizeof(self)
    stats['Base Sizes']['Api'] = '%s bytes' % sys.getsizeof(self.api)

    stats['Plugins'] = {}
    stats['Plugins']['showorder'] = ['Total', 'Loaded', 'Bad']
    stats['Plugins']['Total'] = len(self.allplugininfo)
    stats['Plugins']['Loaded'] = len(self.loadedpluginsd)

    badplugins = self._updateallplugininfo()

    stats['Plugins']['Bad'] = len(badplugins)

    return stats

  def shutdown(self, args=None): # pylint: disable=unused-argument
    """
    do tasks on shutdown
    """
    self.savestate()

  # save all plugins
  def savestate(self, args=None): # pylint: disable=unused-argument
    """
    save all plugins
    """
    for i in self.loadedpluginsd.values():
      i['plugin'].savestate()

  # load this plugin
  def load(self):
    """
    load various things
    """
    self._loadplugins("*.py")

    BasePlugin._loadcommands(self)

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

    self.api('commands.default')('list', self.sname)

    self.api('timers.add')('save', self.savestate, 60, nodupe=True, log=False)

    self.api('events.register')('proxy_shutdown', self.shutdown)
