"""
This plugin highlights cp/gq/quest mobs in scan
"""
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Scan Highlight'
SNAME = 'scanh'
PURPOSE = 'highlight cp, gq, quest mobs in scan'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to highlight mobs in the scan output
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency:add')('aardwolf.quest')
    self.api('dependency:add')('aardwolf.cp')
    self.api('dependency:add')('aardwolf.gq')

    self.mobs = {}

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting:add')('cpbackcolor', '@z14', 'color',
                            'the background color for cp mobs')
    self.api('setting:add')('gqbackcolor', '@z9', 'color',
                            'the background color for gq mobs')
    self.api('setting:add')('questbackcolor', '@z13', 'color',
                            'the background color for quest mobs')
    self.api('setting:add')('cptextcolor', '@x0', 'color',
                            'the background color for cp mobs')
    self.api('setting:add')('gqtextcolor', '@x0', 'color',
                            'the background color for gq mobs')
    self.api('setting:add')('questtextcolor', '@x0', 'color',
                            'the background color for quest mobs')

    self.api('core.triggers:trigger:add')('scanstart',
                                          r"^\{scan\}$")
    self.api('core.triggers:trigger:add')('scanend',
                                          r"^\{/scan\}$",
                                          enabled=False, group='scan')

    self.api('core.events:register:to:event')('trigger_scanstart', self.scanstart)
    self.api('core.events:register:to:event')('trigger_scanend', self.scanend)
    self.api('core.events:register:to:event')('aard_cp_mobsleft', self.cpmobs)
    self.api('core.events:register:to:event')('aard_cp_failed', self.cpclear)
    self.api('core.events:register:to:event')('aard_cp_comp', self.cpclear)
    self.api('core.events:register:to:event')('aard_gq_mobsleft', self.gqmobs)
    self.api('core.events:register:to:event')('aard_gq_done', self.gqclear)
    self.api('core.events:register:to:event')('aard_gq_completed', self.gqmobs)
    self.api('core.events:register:to:event')('aard_gq_won', self.gqmobs)
    self.api('core.events:register:to:event')('aard_quest_start', self.questmob)
    self.api('core.events:register:to:event')('aard_quest_failed', self.questclear)
    self.api('core.events:register:to:event')('aard_quest_comp', self.questclear)

  def scanstart(self, _=None):
    """
    toggle the "scan" trigger group when seeing {scan}
    """
    self.api('libs.io:send:msg')('found {scan}')
    self.api('core.triggers:group:toggle:enable')('scan', True)
    self.api('core.events:register:to:event')('trigger_all', self.scanline)

  def scanline(self, args):
    """
    parse a scan line
    """
    cptextcolor = self.api('setting:get')('cptextcolor')
    cpbackcolor = self.api('setting:get')('cpbackcolor')
    gqtextcolor = self.api('setting:get')('gqtextcolor')
    gqbackcolor = self.api('setting:get')('gqbackcolor')
    questtextcolor = self.api('setting:get')('questtextcolor')
    questbackcolor = self.api('setting:get')('questbackcolor')
    if not args['line'] or args['line'][0] != ' ':
      return None
    line = args['line'].lower().strip()
    self.api('libs.io:send:msg')('scanline: %s' % line)
    if self.api('aardwolf.cp:oncp')():
      mobs = self.api('aardwolf.cp:mobsleft')()
      for i in mobs:
        if line[len(line) - len(i['nocolorname']):].strip() \
                      == i['nocolorname'].lower():
          args['newline'] = cptextcolor + \
                  cpbackcolor + args['line'] + ' - (CP)@x'
          self.api('libs.io:send:msg')('cp newline: %s' % args['newline'])
          break
    if 'gq' in self.mobs:
      for i in self.mobs['gq']:
        if line[len(line) - len(i['name']):].strip() == i['name'].lower():
          args['newline'] = gqtextcolor + \
                  gqbackcolor + args['line'] + ' - (GQ)@x'
          self.api('libs.io:send:msg')('gq newline: %s' % args['newline'])
          break
    if 'quest' in self.mobs:
      if line[len(line) - len(self.mobs['quest']):].strip() \
                        == self.mobs['quest'].lower():
        args['newline'] = questtextcolor + \
              questbackcolor + args['line'] + ' - (Quest)@x'
        self.api('libs.io:send:msg')('quest newline: %s' % args['newline'])

    return args

  def scanend(self, _=None):
    """
    reset current when seeing a scan ending
    """
    self.api('libs.io:send:msg')('found {/scan}')
    self.api('core.events:unregister:from:event')('trigger_all', self.scanline)
    self.api('core.triggers:group:toggle:enable')('scan', False)

  def cpmobs(self, args):
    """
    get cp mobs left
    """
    self.api('libs.io:send:msg')('got cpmobs')
    if 'mobsleft' in args:
      self.mobs['cp'] = args['mobsleft']

  def cpclear(self, _=None):
    """
    clear the cp mobs
    """
    self.api('libs.io:send:msg')('clearing cp mobs')
    if 'cp' in self.mobs:
      del self.mobs['cp']

  def gqmobs(self, args):
    """
    get gq mobs left
    """
    self.api('libs.io:send:msg')('got gqmobs')
    if 'mobsleft' in args:
      self.mobs['gq'] = args['mobsleft']

  def gqclear(self, _=None):
    """
    clear the gq mob
    """
    self.api('libs.io:send:msg')('clearing gq mobs')
    if 'gq' in self.mobs:
      del self.mobs['gq']

  def questmob(self, args):
    """
    get quest mob
    """
    self.api('libs.io:send:msg')('got quest mob')
    self.mobs['quest'] = args['mobname']

  def questclear(self, _=None):
    """
    clear the quest mob
    """
    self.api('libs.io:send:msg')('clearing quest mob')
    if 'quest' in self.mobs:
      del self.mobs['quest']
