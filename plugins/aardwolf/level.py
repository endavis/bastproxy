"""
$Id$
"""
import time, os, copy
from libs import exported
from libs.persistentdict import PersistentDict
from plugins import BasePlugin

NAME = 'Aardwolf Level Events'
SNAME = 'level'
PURPOSE = 'Events for Aardwolf Level'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

class Plugin(BasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, name, sname, filename, directory, importloc):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, name, sname, filename, directory, importloc)
    self.savelevelfile = os.path.join(self.savedir, 'level.txt')
    self.levelinfo = PersistentDict(self.savelevelfile, 'c', format='json')    
    self.dependencies.append('aardu')
    self.rewardtable = {
        'quest':'qp',
        'training':'trains',
        'gold':'gold',
        'trivia':'tp',
        'practice':'pracs',
    }
    self.triggers['lvlpup'] = {
      'regex':"^Congratulations, hero. You have increased your powers!$"}
    self.triggers['lvllevel'] = {
      'regex':"^You raise a level! You are now level (?P<level>\d*).$",
      'argtypes':{'level':int}}
    self.triggers['lvlbless'] = {
      'regex':"^You gain a level - you are now level (?P<level>\d*).$",
      'argtypes':{'level':int}}
    self.triggers['lvlgains'] = {
      'regex':"^You gain (?P<hp>\d*) hit points, (?P<mn>\d*) mana, "\
          "(?P<mv>\d*) moves, (?P<pr>\d*) practices and (?P<tr>\d*) trains.$", 
            'enabled':False, 'group':'linfo',
            'argtypes':{'hp':int, 'mn':int, 'mv':int, 'pr':int, 'tr':int}}    
    self.triggers['lvlblesstrain'] = {
      'regex':"^You gain (?P<tr>\d*) extra trains? daily blessing bonus.$",
      'enabled':False, 'group':'linfo',
      'argtypes':{'tr':int}}
    self.triggers['lvlpupgains'] = {
      'regex':"^You gain (?P<tr>\d*) trains.$", 
      'enabled':False, 'group':'linfo',
      'argtypes':{'tr':int}}
    self.triggers['lvlbonustrains'] = {
      'regex':"^Lucky! You gain an extra (?P<tr>\d*) training sessions?!$", 
      'enabled':False, 'group':'linfo',
      'argtypes':{'tr':int}}      
    self.triggers['lvlbonusstat'] = {
      'regex':"^You gain a bonus (?P<stat>.*) point!$", 
      'enabled':False, 'group':'linfo'}

    self.events['trigger_lvlpup'] = {'func':self._lvl}
    self.events['trigger_lvllevel'] = {'func':self._lvl}
    self.events['trigger_lvlbless'] = {'func':self._lvl}
    self.events['trigger_lvlgains'] = {'func':self._lvlgains}
    self.events['trigger_lvlpupgains'] = {'func':self._lvlgains}
    self.events['trigger_lvlblesstrain'] = {'func':self._lvlblesstrains}
    self.events['trigger_lvlbonustrains'] = {'func':self._lvlbonustrains}
    self.events['trigger_lvlbonusstat'] = {'func':self._lvlbonusstat}
    
    
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
    self.levelinfo['totallevels'] = 0
    
  def _lvl(self, args=None):
    """
    trigger for leveling
    """   
    if not args:
      return
    
    self.resetlevel()
    if args['triggername'] == 'lvlpup':
      self.levelinfo['level'] = exported.GMCP.getv('char.status.level')
      self.levelinfo['totallevels'] = exported.aardu.getactuallevel()
      self.levelinfo['type'] = 'pup'
    else:
      self.levelinfo['level'] = args['level']
      self.levelinfo['totallevels'] = exported.aardu.getactuallevel(
                                                            args['level'])
      self.levelinfo['type'] = 'level'
      if self.levelinfo['level'] == 200:
        exported.trigger.eraise('aard_level_hero', {})
      elif self.levelinfo['level'] == 201:
        exported.trigger.eraise('aard_level_superhero', {})
        
    self.levelinfo['finishtime'] = time.time()     
   
    exported.trigger.togglegroup('linfo', True)  
    exported.event.register('trigger_emptyline', self._finish)    
    
    
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
      self.levelinfo['mn'] = args['mn']
      self.levelinfo['mv'] = args['mv']
      self.levelinfo['pracs'] = args['pr']
          
  def _finish(self, _):
    """
    finish up and raise the level event
    """
    self.levelinfo.sync()
    exported.trigger.togglegroup('linfo', False)     
    exported.event.unregister('trigger_emptyline', self._finish)    
    exported.event.eraise('aard_level_gain', copy.deepcopy(self.levelinfo))
    
  def savestate(self):
    """
    save states
    """
    BasePlugin.savestate(self)
    self.levelinfo.sync()
    
    