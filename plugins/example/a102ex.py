# pylint: disable=line-too-long
"""
This plugin is an example plugin to show how to use the aardwolf 102
telnet options

## Using A102

 * register to the A102 event and check which option it was
 * register to the "A102:#" event

 see the [Aardwolf Blog](http://www.aardwolf.com/blog/2008/07/10/telnet-negotiation-control-mud-client-interaction/)
"""
# pylint: enable=line-too-long
from plugins._baseplugin import BasePlugin

NAME = 'Aard102 Example'
SNAME = 'a102ex'
PURPOSE = 'examples for using the a102 plugin'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(BasePlugin):
  """
  a plugin to show how to use aard102 options
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency:add')('aardwolf.A102')

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('core.events:register:to:event')('A102', self.test)
    self.api('core.events:register:to:event')('A102:101', self.test101)

  def test(self, args):
    """
    show we got an a102 event
    """
    self.api('libs.io:send:client')('@RGot A102: %s' % args)

  def test101(self, args):
    """
    show we got an a102:101 event
    """
    self.api('libs.io:send:client')('@RGot A102:101: %s' % args)
