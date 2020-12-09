"""
This plugin autokeeps item types
"""
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Item autokeep'
SNAME = 'itemkeep'
PURPOSE = 'keep an item type automatically'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    itemtypes = self.api('aardwolf.itemu:objecttypes')()

    for i in itemtypes:
      self.api('setting:add')(i, False, bool,
                              'autokeep %s' % i)

    self.api('core.events:register:to:event')('eq_inventory_added', self.inventory_added)

  def inventory_added(self, args):
    """
    check an item added to inventory to autokeep
    """
    item = args['item']
    itemtypesrev = self.api('aardwolf.itemu:objecttypes')()
    ntype = itemtypesrev[item.itype]

    if self.api('setting:get')(ntype):
      if 'K' not in item.shortflags:
        self.api('libs.io:send:execute')('keep %s' % item.serial)
