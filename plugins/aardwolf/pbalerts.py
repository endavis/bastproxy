"""
This plugin sends pushbullet alerts when certain events happen in aardwolf

It sends alerts for the following:

 * quests available
 * gq available
 * ice age & reboot
 * daily blessing
"""
import time

from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Pushbullet Alerts'
SNAME = 'pbalerts'
PURPOSE = 'Pushbullet Alert for Aardwolf Events'
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
    self.api('dependency:add')('utils.pb')
    self.api('dependency:add')('aardwolf.gq')
    self.api('dependency:add')('aardwolf.quest')
    self.api('dependency:add')('aardwolf.iceage')

    self.evmap = {}
    self.evmap['quests'] = {'event':'aard_quest_ready',
                            'function':self._quest,
                            'help':'flag for sending alerts for quests'}
    self.evmap['gqs'] = {'event':'aard_gq_declared',
                         'function':self._gqdeclared,
                         'help':'flag for sending alerts for gqs'}
    self.evmap['iceage'] = {'event':'aard_iceage',
                            'function':self._iceage,
                            'help':'flag for sending alerts for an ice age'}
    self.evmap['reboot'] = {'event':'aard_reboot',
                            'function':self._reboot,
                            'help':'flag for sending alerts for a reboot'}
    self.evmap['daily'] = {'event':'aard_daily_available',
                           'function':self._daily,
                           'help':'flag for sending alerts for daily blessing'}


  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    for tevent in self.evmap:
      self.api('setting:add')(tevent, True, bool,
                              self.evmap[tevent]['help'])

      self.api('core.events:register:to:event')('%s_var_%s_modified' % (self.plugin_id, tevent), self.varchange)

  def varchange(self, args):
    """
    unregister events
    """
    tevent = args['var']
    tbool = self.api('setting:get')(tevent)

    if tbool:
      self.api('core.events:register:to:event')(self.evmap[tevent]['event'],
                                                self.evmap[tevent]['function'])
    else:
      if self.api('core.events:is:registered:to:event')(self.evmap[tevent]['event'],
                                                        self.evmap[tevent]['function']):
        self.api('core.events:unregister:from:event')(self.evmap[tevent]['event'],
                                                      self.evmap[tevent]['function'])

  def _gqdeclared(self, args):
    """
    send a pushbullet note that a gq has been declared
    """
    mud = self.api('core.managers:get')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - A GQuest has been declared for levels %s to %s. (%s)' % \
            (mud.host, mud.port,
             args['lowlev'], args['highlev'], times)
    self.api('utils.pb:note')('New GQuest', msg)

  def _quest(self, _=None):
    """
    send an pushbullet note that it is time to quest
    """
    mud = self.api('core.managers:get')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - Time to quest! (%s)' % \
            (mud.host, mud.port, times)
    self.api('utils.pb:note')('Quest Time', msg)

  def _iceage(self, _=None):
    """
    send an pushbullet note that an iceage approaches
    """
    mud = self.api('core.managers:get')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - An ice age approaches! (%s)' % \
            (mud.host, mud.port, times)
    self.api('utils.pb:note')('Ice Age', msg)

  def _reboot(self, _=None):
    """
    send an pushbullet note that Aardwolf is rebooting
    """
    mud = self.api('core.managers:get')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - Aardwolf is rebooting (%s)' % \
            (mud.host, mud.port, times)
    self.api('utils.pb:note')('Reboot', msg)

  def _daily(self, _=None):
    """
    send a pushbullet note when daily blessing is available
    """
    self.api('libs.io:send:msg')('got daily blessing event')
    mud = self.api('core.managers:get')('mud')
    times = time.asctime(time.localtime())
    msg = '%s:%s - Daily blessing is available (%s)' % \
            (mud.host, mud.port, times)
    self.api('utils.pb:note')('Daily Blessing', msg)
