"""
$Id$

This plugin sends emails when certain events happen in aardwolf
"""
from plugins import BasePlugin

NAME = 'Aardwolf Alerts'
SNAME = 'alerts'
PURPOSE = 'Alert for Aardwolf Events'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

class Plugin(BasePlugin):
  """
  a plugin to handle aardwolf quest events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.dependencies.append('aardu')
    self.dependencies.append('gq')
    self.addsetting('email', '', str, 'the email to send the alerts',
              nocolor=True)
    self.api.get('events.register')('aard_gq_declared', self._gqdeclared)
    self.api.get('events.register')('aard_quest_ready', self._quest)

  def _gqdeclared(self, args):
    """
    do something when a gq is declared
    """
    proxy = self.api.get('managers.getm')('proxy')
    msg = '%s:%s - A GQuest has been declared for levels %s to %s.' % (
              proxy.host, proxy.port,
              args['lowlev'], args['highlev'])
    if self.variables['email']:
      self.api.get('mail.send')('New GQuest', msg,
              self.variables['email'])
    else:
      self.api.get('mail.send')('New GQuest', msg)

  def _quest(self, _=None):
    """
    do something when you can quest
    """
    proxy = self.api.get('managers.getm')('proxy')
    msg = '%s:%s - Time to quest!' % (
              proxy.host, proxy.port)
    if self.variables['email']:
      self.api.get('mail.send')('Quest Time', msg,
              self.variables['email'])
    else:
      self.api.get('mail.send')('Quest Time', msg)
