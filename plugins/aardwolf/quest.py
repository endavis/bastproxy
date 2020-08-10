"""
This plugin handles quest events on Aardwolf
"""
import time
import copy
import os
from libs.persistentdict import PersistentDict
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Quest Events'
SNAME = 'quest'
PURPOSE = 'Events for Aardwolf Quests'
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
    self.savequestfile = os.path.join(self.save_directory, 'quest.txt')
    self.queststuff = PersistentDict(self.savequestfile, 'c')

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('events.register')('GMCP:comm.quest', self.quest)

    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)


  def resetquest(self):
    """
    reset the quest info
    """
    self.queststuff.clear()
    self.queststuff['finishtime'] = -1
    self.queststuff['starttime'] = time.time()
    self.queststuff['killedtime'] = -1
    self.queststuff['mobname'] = ''
    self.queststuff['mobarea'] = ''
    self.queststuff['mobroom'] = ''
    self.queststuff['level'] = self.api('aardu.getactuallevel')(
        self.api('GMCP.getv')('char.status.level'))
    self.queststuff['failed'] = 0

  def quest(self, args):
    """
    process the quest event
    """
    questi = args['data']
    self.api('send.msg')('quest: %s' % questi)
    if questi['action'] == 'ready':
      self.api('events.eraise')('aard_quest_ready', {})
    elif questi['action'] == 'start':
      self.resetquest()
      self.queststuff['mobname'] = questi['targ']
      self.queststuff['mobarea'] = questi['area']
      self.queststuff['mobroom'] = questi['room']
      self.queststuff['stimer'] = questi['timer']
      self.api('events.eraise')('aard_quest_start', self.queststuff)
    elif questi['action'] == 'killed':
      self.queststuff['killedtime'] = time.time()
      self.api('events.eraise')('aard_quest_killed', self.queststuff)
    elif questi['action'] == 'comp':
      self.queststuff['finishtime'] = time.time()
      self.queststuff.update(questi)
      self.api('events.eraise')('aard_quest_comp',
                                copy.deepcopy(self.queststuff))
    elif questi['action'] == 'fail' or questi['action'] == 'timeout':
      self.queststuff['finishtime'] = time.time()
      self.queststuff['failed'] = 1
      self.api('events.eraise')('aard_quest_failed',
                                copy.deepcopy(self.queststuff))
    elif questi['action'] == 'status':
      self.api('events.eraise')('aard_quest_status', questi)
    elif questi['action'] == 'reset':
      #reset the timer to 60 seconds
      #when_required = os.time() + (stuff.timer * 60)
      #update_timer()
      self.api('events.eraise')('aard_quest_reset', {})
    self.queststuff.sync()

  def _savestate(self, _=None):
    """
    save states
    """
    self.queststuff.sync()
