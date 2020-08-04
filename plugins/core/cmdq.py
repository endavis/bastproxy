"""
this plugin creates a command queue

see the aardwolf eq plugin for examples of how to use it
"""
import re
import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'Command Queue'
SNAME = 'cmdq'
PURPOSE = 'Queue commands to the mud'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to handle the base sqldb
  """
  def __init__(self, *args, **kwargs):
    BasePlugin.__init__(self, *args, **kwargs)

    self.queue = []
    self.cmds = {}
    self.currentcmd = {}

    self.reload_dependents_f = True

    # self.api('api.add')('baseclass', self.api_baseclass)
    self.api('api.add')('addtoqueue', self._api_addtoqueue)
    self.api('api.add')('cmdstart', self._api_commandstart)
    self.api('api.add')('cmdfinish', self._api_commandfinish)
    self.api('api.add')('addcmdtype', self._api_addcmdtype)
    self.api('api.add')('rmvcmdtype', self._api_rmvcmdtype)
    self.api('api.add')('removeplugin', self.api_removeplugin)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='drop the last command')
    self.api('commands.add')('fixqueue', self.cmd_fixqueue,
                             parser=parser)

    self.api('events.register')('plugin_unloaded', self.pluginunloaded)

  def pluginunloaded(self, args):
    """
    a plugin was unloaded
    """
    self.api('%s.removeplugin' % self.short_name)(args['name'])

  # remove all triggers related to a plugin
  def api_removeplugin(self, plugin):
    """  remove all commands related to a plugin
    @Yplugin@w   = The plugin name

    this function returns no values"""
    self.api('send.msg')('removing cmdq data for plugin %s' % plugin,
                         secondary=plugin)
    tkeys = self.cmds.keys()
    for i in tkeys: # iterate keys since we are deleting things
      if self.cmds[i]['plugin'] == plugin:
        self.api('%s.rmvcmdtype' % self.short_name)(i)

  def _api_rmvcmdtype(self, cmdtype):
    """
    remove a command
    """
    if cmdtype in self.cmds:
      del self.cmds[cmdtype]
    else:
      self.api('send.msg')('could not delete command type: %s' % cmdtype)

  # start a command
  def _api_commandstart(self, cmdtype):
    """
    tell the queue a command has started
    """
    if self.currentcmd and cmdtype != self.currentcmd['ctype']:
      self.api('send.msg')("got command start for %s and it's not the current cmd: %s" \
                                % (cmdtype, self.currentcmd['ctype']))
      return
    self.api('timep.start')('cmd_%s' % cmdtype)

  def _api_addcmdtype(self, cmdtype, cmd, regex, **kwargs):
    """
    add a command type
    """
    beforef = None
    afterf = None
    plugin = self.api('api.callerplugin')(skipplugin=[self.short_name])
    if 'beforef' in kwargs:
      beforef = kwargs['beforef']
    if 'afterf' in kwargs:
      afterf = kwargs['afterf']
    if 'plugin' in kwargs:
      plugin = kwargs['plugin']
    if cmdtype not in self.cmds:
      self.cmds[cmdtype] = {}
      self.cmds[cmdtype]['cmd'] = cmd
      self.cmds[cmdtype]['regex'] = regex
      self.cmds[cmdtype]['cregex'] = re.compile(regex)
      self.cmds[cmdtype]['beforef'] = beforef
      self.cmds[cmdtype]['afterf'] = afterf
      self.cmds[cmdtype]['ctype'] = cmdtype
      self.cmds[cmdtype]['plugin'] = plugin

  def sendnext(self):
    """
    send the next command
    """
    self.api('send.msg')('checking queue')
    if not self.queue or self.currentcmd:
      return

    cmdt = self.queue.pop(0)
    cmd = cmdt['cmd']
    cmdtype = cmdt['ctype']
    self.api('send.msg')('sending cmd: %s (%s)' % (cmd, cmdtype))

    if cmdtype in self.cmds and self.cmds[cmdtype]['beforef']:
      self.cmds[cmdtype]['beforef']()

    self.currentcmd = cmdt
    self.api('send.execute')(cmd)

  def checkinqueue(self, cmd):
    """
    check for a command in the queue
    """
    for i in self.queue:
      if i['cmd'] == cmd:
        return True

    return False

  def _api_commandfinish(self, cmdtype):
    """
    tell the queue that a command has finished
    """
    self.api('send.msg')('running cmddone: %s' % cmdtype)
    if not self.currentcmd:
      return
    if cmdtype == self.currentcmd['ctype']:
      if cmdtype in self.cmds and self.cmds[cmdtype]['afterf']:
        self.api('send.msg')('running afterf: %s' % cmdtype)
        self.cmds[cmdtype]['afterf']()

      self.api('timep.finish')('cmd_%s' % self.currentcmd['ctype'])
      self.api('events.eraise')('cmd_%s_finished' % self.currentcmd['ctype'])
      self.currentcmd = {}
      self.sendnext()

  def _api_addtoqueue(self, cmdtype, arguments=''):
    """
    add a command to the queue
    """
    plugin = self.api('api.callerplugin')(skipplugin=['cmdq'])
    cmd = self.cmds[cmdtype]['cmd']
    if arguments:
      cmd = cmd + ' ' + str(arguments)
    if self.checkinqueue(cmd) or \
            ('cmd' in self.currentcmd and self.currentcmd['cmd'] == cmd):
      return
    else:
      self.api('send.msg')('added %s to queue' % cmd, secondary=[plugin])
      self.queue.append({'cmd':cmd, 'ctype':cmdtype, 'plugin':plugin})
      if not self.currentcmd:
        self.sendnext()

  def resetqueue(self, _=None):
    """
    reset the queue
    """
    self.queue = []

  def cmd_fixqueue(self, args): # pylint: disable=unused-argument
    """
    finish the last command
    """
    if self.currentcmd:
      self.api('timep.finish')('cmd_%s' % self.currentcmd['ctype'])
      self.currentcmd = {}
      self.sendnext()

    return True, ['finished the currentcmd']
