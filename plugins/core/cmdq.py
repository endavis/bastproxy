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
    self.current_command = {}

    self.reload_dependents_f = True

    # new api methods
    # self.api('libs.api:add')('baseclass', self.api_baseclass)
    self.api('libs.api:add')('queue:add:command', self._api_queue_add_command)
    self.api('libs.api:add')('command:start', self._api_command_start)
    self.api('libs.api:add')('command:finish', self._api_command_finish)
    self.api('libs.api:add')('commandtype:add', self._api_command_type_add)
    self.api('libs.api:add')('commandtype:remove', self._api_command_type_remove)
    self.api('libs.api:add')('remove:commands:for:plugin', self._api_remove_commands_for_plugin)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='drop the last command')
    self.api('core.commands:command:add')('fixqueue', self.cmd_fixqueue,
                                          parser=parser)

    self.api('core.events:register:to:event')('core.plugins_plugin_uninitialized', self._event_plugin_uninitialized)

  def _event_plugin_uninitialized(self, args):
    """
    a plugin was uninitialized
    """
    self.api('%s:remove:commands:for:plugin' % self.plugin_id)(args['plugin_id'])

  # remove all triggers related to a plugin
  def _api_remove_commands_for_plugin(self, plugin):
    """  remove all commands related to a plugin
    @Yplugin@w   = The plugin name

    this function returns no values"""
    self.api('libs.io:send:msg')('removing cmdq data for plugin %s' % plugin,
                                 secondary=plugin)
    tkeys = self.cmds.keys()
    for i in tkeys: # iterate keys since we are deleting things
      if self.cmds[i]['plugin'] == plugin:
        self.api('%s:remove:command:type' % self.plugin_id)(i)

  def _api_command_type_remove(self, cmdtype):
    """
    remove a command
    """
    if cmdtype in self.cmds:
      del self.cmds[cmdtype]
    else:
      self.api('libs.io:send:msg')('could not delete command type: %s' % cmdtype)

  # start a command
  def _api_command_start(self, cmdtype):
    """
    tell the queue a command has started
    """
    if self.current_command and cmdtype != self.current_command['ctype']:
      self.api('libs.io:send:msg')("got command start for %s and it's not the current cmd: %s" \
                                % (cmdtype, self.current_command['ctype']))
      return
    self.api('libs.timing:timing:start')('cmd_%s' % cmdtype)

  def _api_command_type_add(self, cmdtype, cmd, regex, **kwargs):
    """
    add a command type
    """
    beforef = None
    afterf = None
    plugin = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
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
    self.api('libs.io:send:msg')('checking queue')
    if not self.queue or self.current_command:
      return

    cmdt = self.queue.pop(0)
    cmd = cmdt['cmd']
    cmdtype = cmdt['ctype']
    self.api('libs.io:send:msg')('sending cmd: %s (%s)' % (cmd, cmdtype))

    if cmdtype in self.cmds and self.cmds[cmdtype]['beforef']:
      self.cmds[cmdtype]['beforef']()

    self.current_command = cmdt
    self.api('libs.io:send:execute')(cmd)

  def checkinqueue(self, cmd):
    """
    check for a command in the queue
    """
    for i in self.queue:
      if i['cmd'] == cmd:
        return True

    return False

  def _api_command_finish(self, cmdtype):
    """
    tell the queue that a command has finished
    """
    self.api('libs.io:msg')('running cmddone: %s' % cmdtype)
    if not self.current_command:
      return
    if cmdtype == self.current_command['ctype']:
      if cmdtype in self.cmds and self.cmds[cmdtype]['afterf']:
        self.api('libs.io:send:msg')('running afterf: %s' % cmdtype)
        self.cmds[cmdtype]['afterf']()

      self.api('libs.timing:timing:finish')('cmd_%s' % self.current_command['ctype'])
      self.api('core.events:raise:event')('cmd_%s_finished' % self.current_command['ctype'])
      self.current_command = {}
      self.sendnext()

  def _api_queue_add_command(self, cmdtype, arguments=''):
    """
    add a command to the queue
    """
    plugin = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
    cmd = self.cmds[cmdtype]['cmd']
    if arguments:
      cmd = cmd + ' ' + str(arguments)
    if self.checkinqueue(cmd) or \
            ('cmd' in self.current_command and self.current_command['cmd'] == cmd):
      return
    else:
      self.api('libs.io:send:msg')('added %s to queue' % cmd, secondary=[plugin])
      self.queue.append({'cmd':cmd, 'ctype':cmdtype, 'plugin':plugin})
      if not self.current_command:
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
    if self.current_command:
      self.api('libs.timing:timing:finish')('cmd_%s' % self.current_command['ctype'])
      self.current_command = {}
      self.sendnext()

    return True, ['finished the currentcmd']
