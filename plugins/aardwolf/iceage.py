"""
This plugin adds events for Aardwolf Ice Ages.
"""
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Ice Age'
SNAME = 'iceage'
PURPOSE = 'Send ice age events'
AUTHOR = 'Bast'
VERSION = 1


class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf quest events
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

    self.api('core.triggers:trigger:add')(
        'iceage',
        r"^.* An Ice Age Approaches - (\d*) minutes?.*$")

    self.api('core.triggers:trigger:add')(
        'reboot',
        r"^.* Aardwolf will [rR]eboot (.* )?in (\d*) minutes?.*$")

    self.api('core.events:register:to:event')('trigger_iceage', self.iceage)

    self.api('core.events:register:to:event')('trigger_reboot', self.reboot)

  def iceage(self, _=None):
    """
    raise an iceage event
    """
    self.api('libs.io:send:msg')('Ice Age imminent')
    self.api('core.events:raise:event')('aard_iceage', {})

  def reboot(self, _=None):
    """
    raise a reboot event
    """
    self.api('libs.io:send:msg')('Reboot imminent')
    self.api('core.events:raise:event')('aard_reboot', {})
