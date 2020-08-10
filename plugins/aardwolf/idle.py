"""
This plugin keeps you from disconnecting from Aardwolf
"""
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Idle'
SNAME = 'idle'
PURPOSE = 'anti idle'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to show how to use triggers
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('triggers.add')('glaze',
                             "^Your eyes glaze over.$")
    self.api('events.register')('trigger_glaze', self.glaze)

  def glaze(self, _=None):
    """
    show that the trigger fired
    """
    self.api('send.execute')('look')
