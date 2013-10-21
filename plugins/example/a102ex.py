"""
$Id$

This plugin is an example plugin to show how to use the aardwolf 102
telnet options
"""
from plugins import BasePlugin

NAME = 'Aard102 Example'
SNAME = 'a102ex'
PURPOSE = 'examples for using the a102 plugin'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

class Plugin(BasePlugin):
  """
  a plugin to show how to use aard102 options
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.api.get('events.register')('A102', self.test)
    self.api.get('events.register')('A102:101',self.test101)

  def test(self, args):
    """
    show we got an a102 event
    """
    self.api.get('output.client')('@RGot A102: %s' % args)

  def test101(self, args):
    """
    show we got an a102:101 event
    """
    self.api.get('output.client')('@RGot A102:101: %s' % args)

