"""
This plugin handles level events on Aardwolf
"""
import time
import os
import copy
import re
from libs.persistentdict import PersistentDict
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Level Events'
SNAME = 'level'
PURPOSE = 'Events for Aardwolf Level'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)
    self.savelevelfile = os.path.join(self.save_directory, 'level.txt')
    self.levelinfo = PersistentDict(self.savelevelfile, 'c')

  def initialize(self): # pylint: disable=too-many-statements
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting:add')('preremort', False, bool,
                            'flag for pre remort')
    self.api('setting:add')('remortcomp', False, bool,
                            'flag for remort completion')
    self.api('setting:add')('tiering', False, bool, 'flag for tiering')
    self.api('setting:add')('seen2', False, bool,
                            'we saw a state 2 after tiering')

    self.api('core.watch:watch:add')('shloud', '^superhero loud$')
    self.api('core.watch:watch:add')('shsilent', '^superhero silent$')
    self.api('core.watch:watch:add')('shconfirm', '^superhero confirm$')
    self.api('core.watch:watch:add')('shloudconfirm', '^superhero loud confirm$')

    self.api('core.triggers:trigger:add')('lvlpup',
                                          r"^Congratulations, hero. You have increased your powers!$")
    self.api('core.triggers:trigger:add')('lvlpupbless',
                                          r"^You gain a powerup\.$")
    self.api('core.triggers:trigger:add')('lvllevel',
                                          r"^You raise a level! You are now level (?P<level>\d*).$",
                                          argtypes={'level':int})
    self.api('core.triggers:trigger:add')('lvlshloud',
                                          r"^Congratulations! You are now a superhero!" \
                                          r" You receive (?P<trains>) trains for superhero loud.$",
                                          argtypes={'trains':int})
    self.api('core.triggers:trigger:add')('lvlsh',
                                          r"^Congratulations! You are now a superhero!")
    self.api('core.triggers:trigger:add')('lvlbless',
                                          r"^You gain a level - you are now level (?P<level>\d*).$",
                                          argtypes={'level':int})
    self.api('core.triggers:trigger:add')('lvlgains',
                                          r"^You gain (?P<hp>\d*) hit points, (?P<mp>\d*) mana, "\
                                            r"(?P<mv>\d*) moves, (?P<pr>\d*) practices and " \
                                            r"(?P<tr>\d*) trains.$",
                                          enabled=False, group='linfo',
                                          argtypes={'hp':int, 'mn':int, 'mv':int, 'pr':int, 'tr':int})
    self.api('core.triggers:trigger:add')('lvlblesstrain',
                                          r"^You gain (?P<tr>\d*) extra trains? " \
                                            r"daily blessing bonus.$",
                                          enabled=False, group='linfo',
                                          argtypes={'tr':int})
    self.api('core.triggers:trigger:add')('lvlpupgains',
                                          r"^You gain (?P<tr>\d*) trains.$",
                                          enabled=False, group='linfo',
                                          argtypes={'tr':int})
    self.api('core.triggers:trigger:add')('lvlbattlelearntrains',
                                          r"^You gain (?P<tr>\d*) additional training sessions? " \
                                            r"from your enhanced battle learning.$",
                                          enabled=False, group='linfo',
                                          argtypes={'tr':int})
    self.api('core.triggers:trigger:add')('lvlbonustrains',
                                          r"^Lucky! You gain an extra (?P<tr>\d*) " \
                                            r"training sessions?!$",
                                          enabled=False, group='linfo',
                                          argtypes={'tr':int})
    self.api('core.triggers:trigger:add')('lvlbonusstat',
                                          r"^You gain a bonus (?P<stat>.*) point!$",
                                          enabled=False, group='linfo')

    self.api('core.triggers:trigger:add')('lvlshbadstar',
                                          r"^%s$" % re.escape("*******************************" \
                                              "****************************************"),
                                          enabled=False, group='superhero')
    self.api('core.triggers:trigger:add')('lvlshbad',
                                          r"^Use either: 'superhero loud'   - (?P<mins>.*) mins of " \
                                            r"double xp, (?P<qp>.*)qp and (?P<gold>.*) gold$",
                                          enabled=False, group='superhero')
    self.api('core.triggers:trigger:add')('lvlshnogold',
                                          r"^You must be carrying at least 500,000 gold coins.$",
                                          enabled=False, group='superhero')
    self.api('core.triggers:trigger:add')('lvlshnoqp',
                                          r"^You must have at least 1000 quest points.$",
                                          enabled=False, group='superhero')
    self.api('core.triggers:trigger:add')('lvlshnodbl',
                                          r"^You cannot superhero loud until double exp is over.$",
                                          enabled=False, group='superhero')
    self.api('core.triggers:trigger:add')('lvlshnot200',
                                          r"^You have to be level 200 to superhero.$",
                                          enabled=False, group='superhero')

    self.api('core.triggers:trigger:add')('lvlpreremort',
                                          r"^You are now flagged as remorting.$",
                                          enabled=True, group='remort')
    self.api('core.triggers:trigger:add')('lvlremortcomp',
                                          r"^\* Remort transformation complete!$",
                                          enabled=True, group='remort')
    self.api('core.triggers:trigger:add')('lvltier',
                                          r"^## You have already remorted the max number of times.$",
                                          enabled=True, group='remort')


    self.api('core.events:register:to:event')('trigger_lvlpup', self._lvl)
    self.api('core.events:register:to:event')('trigger_lvlpupbless', self._lvl)
    self.api('core.events:register:to:event')('trigger_lvllevel', self._lvl)
    self.api('core.events:register:to:event')('trigger_lvlbless', self._lvl)
    #self.api('core.events:register:to:event')('trigger_lvlsh', self._lvl)
    self.api('core.events:register:to:event')('trigger_lvlgains', self._lvlgains)
    self.api('core.events:register:to:event')('trigger_lvlpupgains', self._lvlgains)
    self.api('core.events:register:to:event')('trigger_lvlblesstrain', self._lvlblesstrains)
    self.api('core.events:register:to:event')('trigger_lvlbonustrains', self._lvlbonustrains)
    self.api('core.events:register:to:event')('trigger_lvlbonusstat', self._lvlbonusstat)
    self.api('core.events:register:to:event')('trigger_lvlbattlelearntrains', self._lvlbattlelearntrains)

    self.api('core.events:register:to:event')('trigger_lvlshbadstar', self._superherobad)
    self.api('core.events:register:to:event')('trigger_lvlshbad', self._superherobad)
    self.api('core.events:register:to:event')('trigger_lvlshnogold', self._superherobad)
    self.api('core.events:register:to:event')('trigger_lvlshnoqp', self._superherobad)
    self.api('core.events:register:to:event')('trigger_lvlshnodbl', self._superherobad)
    self.api('core.events:register:to:event')('trigger_lvlshnot200', self._superherobad)

    self.api('core.events:register:to:event')('watch_shloud', self.cmd_superhero)
    self.api('core.events:register:to:event')('watch_shsilent', self.cmd_superhero)
    self.api('core.events:register:to:event')('watch_shconfirm', self.cmd_superhero)
    self.api('core.events:register:to:event')('watch_shloudconfirm', self.cmd_superhero)

    self.api('core.events:register:to:event')('trigger_lvlpreremort', self._preremort)
    self.api('core.events:register:to:event')('trigger_lvlremortcomp', self._remortcomp)
    self.api('core.events:register:to:event')('trigger_lvltier', self._tier)

    self.api('core.events:register:to:event')('{0.plugin_id}_savestate'.format(self), self._savestate)

  def _gmcpstatus(self, _=None):
    """
    check gmcp status when tiering
    """
    state = self.api('net.GMCP:value:get')('char.status.state')
    if state == 2:
      self.api('libs.io:send:client')('seen2')
      self.api('setting:change')('seen2', True)
      self.api('core.events:unregister:from:event')('GMCP:char.status', self._gmcpstatus)
      self.api('core.events:register:to:event')('GMCP:char.base', self._gmcpbase)

  def _gmcpbase(self, _=None):
    """
    look for a new base when we remort
    """
    self.api('libs.io:send:client')('called char.base')
    state = self.api('net.GMCP:value:get')('char.status.state')
    tiering = self.api('setting:get')('tiering')
    seen2 = self.api('setting:get')('seen2')
    if tiering and seen2 and state == 3:
      self.api('libs.io:send:client')('in char.base')
      self.api('core.events:unregister:from:event')('GMCP:char.base', self._gmcpstatus)
      self._lvl({'level':1})

  def _tier(self, _=None):
    """
    about to tier
    """
    self.api('setting:change')('tiering', True)
    self.api('libs.io:send:client')('tiering')
    self.api('core.events:register:to:event')('GMCP:char.status', self._gmcpstatus)

  def _remortcomp(self, _=None):
    """
    do stuff when a remort is complete
    """
    self.api('setting:change')('preremort', False)
    self.api('setting:change')('remortcomp', True)
    self._lvl({'level':1})

  def _preremort(self, _=None):
    """
    set the preremort flag
    """
    self.api('setting:change')('preremort', True)
    self.api('core.events:raise:event')('aard_level_preremort', {})

  def cmd_superhero(self, _=None):
    """
    figure out what is done when superhero is typed
    """
    self.api('libs.io:send:client')('superhero was typed')
    self.api('core.triggers:group:toggle:enable')('superhero', True)
    self._lvl({'level':201})

  def _superherobad(self, _=None):
    """
    undo things that we typed if we didn't really superhero
    """
    self.api('libs.io:send:client')('didn\'t sh though')
    self.api('core.triggers:group:toggle:enable')('superhero', False)
    self.api('core.triggers:group:toggle:enable')('linfo', False)
    self.api('core.events:unregister:from:event')('trigger_emptyline', self._finish)

  def resetlevel(self):
    """
    reset the level info, use the finishtime of the last level as
    the starttime of the next level
    """
    if 'finishtime' in self.levelinfo and self.levelinfo['finishtime'] > 0:
      starttime = self.levelinfo['finishtime']
    else:
      starttime = time.time()
    self.levelinfo.clear()
    self.levelinfo['type'] = ""
    self.levelinfo['level'] = -1
    self.levelinfo['str'] = 0
    self.levelinfo['int'] = 0
    self.levelinfo['wis'] = 0
    self.levelinfo['dex'] = 0
    self.levelinfo['con'] = 0
    self.levelinfo['luc'] = 0
    self.levelinfo['starttime'] = starttime
    self.levelinfo['hp'] = 0
    self.levelinfo['mp'] = 0
    self.levelinfo['mv'] = 0
    self.levelinfo['pracs'] = 0
    self.levelinfo['trains'] = 0
    self.levelinfo['bonustrains'] = 0
    self.levelinfo['blessingtrains'] = 0
    self.levelinfo['battlelearntrains'] = 0
    self.levelinfo['totallevels'] = 0

  def _lvl(self, args=None):
    """
    trigger for leveling
    """
    if not args:
      return

    self.resetlevel()
    if 'triggername' in args and (args['triggername'] == 'lvlpup' \
        or args['triggername'] == 'lvlpupbless'):
      self.levelinfo['level'] = self.api('net.GMCP:value:get')('char.status.level')
      self.levelinfo['totallevels'] = self.api('aardu.getactuallevel')()
      self.levelinfo['type'] = 'pup'
    else:
      self.levelinfo['level'] = args['level']
      self.levelinfo['totallevels'] = self.api('aardu.getactuallevel')(
          args['level'])
      self.levelinfo['type'] = 'level'

    self.api('core.triggers:group:toggle:enable')('linfo', True)
    self.api('core.events:register:to:event')('trigger_emptyline', self._finish)


  def _lvlblesstrains(self, args):
    """
    trigger for blessing trains
    """
    self.levelinfo['blessingtrains'] = args['tr']

  def _lvlbonustrains(self, args):
    """
    trigger for bonus trains
    """
    self.levelinfo['bonustrains'] = args['tr']

  def _lvlbattlelearntrains(self, args):
    """
    trigger for bonus trains
    """
    self.levelinfo['battlelearntrains'] = args['tr']

  def _lvlbonusstat(self, args):
    """
    trigger for bonus stats
    """
    self.levelinfo[args['stat'][:3].lower()] = 1

  def _lvlgains(self, args):
    """
    trigger for level gains
    """
    self.levelinfo['trains'] = args['tr']

    if args['triggername'] == "lvlgains":
      self.levelinfo['hp'] = args['hp']
      self.levelinfo['mp'] = args['mp']
      self.levelinfo['mv'] = args['mv']
      self.levelinfo['pracs'] = args['pr']

  def _finish(self, _):
    """
    finish up and raise the level event
    """
    remortcomp = self.api('setting:get')('remortcomp')
    tiering = self.api('setting:get')('tiering')
    if self.levelinfo['trains'] == 0 and not remortcomp or tiering:
      return
    self.levelinfo['finishtime'] = time.time()
    self.levelinfo.sync()
    self.api('core.triggers:group:toggle:enable')('linfo', False)
    self.api('core.events:unregister:from:event')('trigger_emptyline', self._finish)
    self.api('core.events:raise:event')('aard_level_gain',
                                        copy.deepcopy(self.levelinfo))
    if self.levelinfo['level'] == 200 and self.levelinfo['type'] == 'level':
      self.api('libs.io:send:msg')('raising hero event', 'level')
      self.api('core.events:raise:event')('aard_level_hero', {})
    elif self.levelinfo['level'] == 201 and self.levelinfo['type'] == 'level':
      self.api('libs.io:send:msg')('raising superhero event', 'level')
      self.api('core.events:raise:event')('aard_level_superhero', {})
    elif self.levelinfo['level'] == 1:
      if self.api('setting:get')('tiering'):
        self.api('libs.io:send:msg')('raising tier event', 'level')
        self.api('setting:change')('tiering', False)
        self.api('setting:change')('seen2', False)
        self.api('core.events:raise:event')('aard_level_tier', {})
      else:
        self.api('libs.io:send:msg')('raising remort event', 'level')
        self.api('setting:change')('remortcomp', False)
        self.api('core.events:raise:event')('aard_level_remort', {})

  def _savestate(self, _=None):
    """
    save states
    """
    self.levelinfo.sync()
