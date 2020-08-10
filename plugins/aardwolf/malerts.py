"""
This plugin sends emails when certain events happen in aardwolf

It sends alerts for the following:

 * quests available
 * gq available
 * ice age
"""
import time

from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Email Alerts'
SNAME = 'malerts'
PURPOSE = 'Email Alerts for Aardwolf Events'
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
    self.api('dependency.add')('aardwolf.gq')
    self.api('dependency.add')('aardwolf.quest')
    self.api('dependency.add')('aardwolf.iceage')

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting.add')('email', '', str,
                            'the email to send the alerts', nocolor=True)
    self.api('events.register')('aard_gq_declared', self._gqdeclared)
    self.api('events.register')('aard_quest_ready', self._quest)
    self.api('events.register')('aard_iceage', self._iceage)
    self.api('events.register')('aard_reboot', self._reboot)

  def _gqdeclared(self, args):
    """
    send an email that a gq has been declared
    """
    mud = self.api('managers.getm')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - A GQuest has been declared for levels %s to %s. (%s)' % (
        mud.host, mud.port,
        args['lowlev'], args['highlev'], times)
    email = self.api('setting.gets')('email')
    if email:
      self.api('mail.send')('New GQuest', msg,
                            email)
    else:
      self.api('mail.send')('New GQuest', msg)

  def _quest(self, _=None):
    """
    send an email that it is time to quest
    """
    mud = self.api('managers.getm')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - Time to quest! (%s)' % (
        mud.host, mud.port, times)
    email = self.api('setting.gets')('email')
    if email:
      self.api('mail.send')('Quest Time', msg,
                            email)
    else:
      self.api('mail.send')('Quest Time', msg)

  def _iceage(self, _=None):
    """
    send an email that an iceage approaches
    """
    mud = self.api('managers.getm')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - An ice age approaches! (%s)' % (
        mud.host, mud.port, times)
    email = self.api('setting.gets')('email')
    if email:
      self.api('mail.send')('Ice Age', msg,
                            email)
    else:
      self.api('mail.send')('Ice Age', msg)

  def _reboot(self, _=None):
    """
    send an email that Aardwolf is rebooting
    """
    mud = self.api('managers.getm')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - Aardwolf is rebooting (%s)' % (
        mud.host, mud.port, times)
    email = self.api('setting.gets')('email')
    if email:
      self.api('mail.send')('Reboot', msg,
                            email)
    else:
      self.api('mail.send')('Reboot', msg)
