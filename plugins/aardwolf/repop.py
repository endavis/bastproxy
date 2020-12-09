"""
This plugin sends a message to a channel when an area repops
"""
import time
from string import Template
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Repop'
SNAME = 'repop'
PURPOSE = 'Send repop messages to a channel'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to show gmcp usage
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

    self.api('setting:add')('channel', 'gt', str,
                            'the channel to send the repop message')
    self.api('setting:add')('format',
                            "@r[@RRepop@r]@w ${zone} @R@@ @w${time}", str,
                            'the format of the message')

    self.api('core.events:register:to:event')('GMCP:comm.repop', self.repop)

  def repop(self, args):
    """
    do something on repop
    """
    zone = args['data']['zone']
    ttime = time.strftime('%X', time.localtime())
    chan = self.api('setting:get')('channel')

    templ = Template(self.api('setting:get')('format'))
    datan = templ.safe_substitute({'zone':zone, 'time':ttime})

    self.api('libs.io:send:execute')(chan + ' ' + datan)
