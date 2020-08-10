"""
This is the base plugin for aardwolf plugins
it adds some dependencies
"""
from plugins._baseplugin import BasePlugin

NAME = 'Aardwolf Base Plugin'
SNAME = 'abase'
PURPOSE = 'The Aardwolf BasePlugin'
AUTHOR = 'Bast'
VERSION = 1



class AardwolfBasePlugin(BasePlugin):
  """
  base plugin for aardwolf
  """
  def __init__(self, *args, **kwargs):
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency.add')('aardwolf.connect')
    self.api('dependency.add')('aardwolf.aardu')
