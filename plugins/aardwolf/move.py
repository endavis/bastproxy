"""
This plugin sends events when moving between rooms
"""
import copy
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'movement'
SNAME = 'move'
PURPOSE = 'movement plugin'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

class Plugin(AardwolfBasePlugin):
  """
  a plugin to monitor aardwolf events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    super().__init__(*args, **kwargs)

    self.lastroom = {}

  def load(self):
    """
    load the plugins
    """
    super().load()

    self.api('events.register')('GMCP:room.info', self._roominfo)

  def _roominfo(self, _=None):
    """
    figure out if we moved or not
    """
    room = self.api('GMCP.getv')('room.info')
    if not self.lastroom:
      self.lastroom = copy.deepcopy(dict(room))
    else:
      if room['num'] != self.lastroom['num']:
        direction = 'unknown'
        for i in self.lastroom['exits']:
          if self.lastroom['exits'][i] == room['num']:
            direction = i
        newdict = {'from':self.lastroom,
                   'to': room, 'direction':direction,
                   'roominfo':copy.deepcopy(dict(room))}
        self.api('send.msg')('raising moved_room, %s' % (newdict))
        self.api('events.eraise')('moved_room', newdict)
        self.lastroom = copy.deepcopy(dict(room))

  def afterfirstactive(self, _=None):
    """
    do something on connect
    """
    super().afterfirstactive()

    self.api('send.msg')('requesting room')
    self.api('GMCP.sendmud')('request room')
