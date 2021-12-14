"""
This plugin is a utility plugin for aardwolf functions

It adds functions to the api as well as takes care of the is_character_active flag
"""
from __future__ import print_function
from plugins._baseplugin import BasePlugin

NAME = 'Aardwolf Connect'
SNAME = 'connect'
PURPOSE = 'setup aardwolf when first connecting'
AUTHOR = 'Bast'
VERSION = 1


class Plugin(BasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    BasePlugin.__init__(self, *args, **kwargs)

    self.connected = False

    self.sentchar = False
    self.sentquest = False
    self.sentroom = False

    self.api('dependency:add')('net.GMCP')

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('core.triggers:trigger:add')('return_to_continue',
                                          r"(\[ Press Return to continue \])|(\[Press Return\])")

    self.api('core.events:register:to:event')('ev_libs.net.mud_muddisconnect', self._disconnect)
    self.api('core.events:register:to:event')('ev_net.GMCP_MOD_char', self._check)
    self.api('core.events:register:to:event')('ev_net.GMCP_MOD_room.info', self._check)
    self.api('core.events:register:to:event')('ev_net.GMCP_MOD_comm.quest', self._check)
    self.api('core.events:register:to:event')('ev_core.triggers_t_aardwolf.connect_return_to_continue',
                                              self._connect_return)
    self.api('core.events:register:to:event')('ev_libs.net.client_client_connected', self.clientconnected)

    self.api('core.events:register:to:event')('ev_net.GMCP_server_enabled', self.enablemods)

    #state = self.api('net.GMCP:value:get')('char.status.state')
    mud = self.api('core.managers:get')('mud')
#    if state == 3 and mud and mud.connected:
    if mud and mud.connected:
      print('mud connected')
      self.enablemods()
      self.clientconnected()

  def _connect_return(self, _=None):
    """
    send enter on connect when seeing the "Press return to continue" message
    """
    print('sending cr to mud')
    self.api('libs.io:send:mud')('\n\r')

  def clientconnected(self, _=None):
    """
    do stuff when a client connects
    """
    mud = self.api('core.managers:get')('mud')
    if mud.connected:
      self.api('net.GMCP:mud:send')("request room")
      self.api('net.GMCP:mud:send')("request quest")
      self.api('net.GMCP:mud:send')("request char")

  def enablemods(self, _=None):
    """
    enable modules for aardwolf
    """
    mud = self.api('core.managers:get')('mud')
    if mud.connected:
      self.api('net.GMCP:mud:send')("rawcolor on")
      self.api('net.GMCP:mud:send')("group on")
      self.api('net.GMCP:mud:module:toggle')('Char', True)
      self.api('net.GMCP:mud:module:toggle')('Room', True)
      self.api('net.GMCP:mud:module:toggle')('Comm', True)
      self.api('net.GMCP:mud:module:toggle')('Group', True)
      self.api('net.GMCP:mud:module:toggle')('Core', True)

  def _disconnect(self, _=None):
    """
    reattach to GMCP:char.status
    """
    self.connected = False
    self.sentchar = False
    self.sentquest = False
    self.sentroom = False
    self.api('core.events:register:to:event')('ev_net.GMCP_MOD_char', self._check)
    self.api('core.events:register:to:event')('ev_net.GMCP_MOD_room.info', self._check)
    self.api('core.events:register:to:event')('ev_net.GMCP_MOD_comm.quest', self._check)
    self.api('core.events:register:to:event')('ev_core.triggers_t_aardwolf.connect_return_to_continue',
                                              self._connect_return)
    self.api('libs.api:is_character_active:set')(False)


  def set_character_to_active(self):
    """
    set the character_is_active flag
    """
    mud = self.api('core.managers:get')('mud')
    if mud and mud.connected:
      state = self.api('net.GMCP:value:get')('char.status.state')
      if state == 3:
        self.api('core.events:unregister:from:event')('ev_net.GMCP_MOD_char', self._check)
        self.api('core.events:unregister:from:event')('ev_net.GMCP_MOD_room.info', self._check)
        self.api('core.events:unregister:from:event')('ev_net.GMCP_MOD_comm.quest', self._check)
        self.api('core.events:unregister:from:event')('ev_core.triggers_t_aardwolf.connect_return_to_continue',
                                                      self._connect_return)
        self.api('libs.io:send:mud')('look')
        self.api('libs.io:send:mud')('map')
        self.api('libs.io:send:mud')('')
        self.connected = True
        self.sentquest = False
        self.sentchar = False
        self.sentroom = False
        self.api('libs.api:is_character_active:set')(True)

  def checkall(self):
    """
    check for char, room, and quest
    """
    if self.checkchar() and self.checkroom() and self.checkquest():
      return True

    return False

  def checkchar(self):
    """
    check for all of char in GMCP
    """
    if self.api('net.GMCP:value:get')('char.base.redos') is None \
       or self.api('net.GMCP:value:get')('char.vitals.hp') is None \
       or self.api('net.GMCP:value:get')('char.stats.str') is None \
       or self.api('net.GMCP:value:get')('char.maxstats.maxhp') is None \
       or self.api('net.GMCP:value:get')('char.worth.gold') is None:

      if not self.sentchar:
        self.api('net.GMCP:mud:send')("request char")
        self.sentchar = True

      return False

    return True

  def checkroom(self):
    """
    check for room in GMCP
    """
    if self.api('net.GMCP:value:get')('room.info.num') is None:
      if not self.sentroom:
        self.sentroom = True
        self.api('net.GMCP:mud:send')("request room")

      return False

    return True

  def checkquest(self):
    """
    check for quest in GMCP
    """
    if self.api('net.GMCP:value:get')('comm.quest.action') is None:
      if not self.sentquest:
        self.sentquest = True
        self.api('net.GMCP:mud:send')("request quest")

      return False

    return True

  def _check(self, _=None):
    """
    check to see if we have seen quest gmcp data
    """
    if self.checkall():
      self.set_character_to_active()
