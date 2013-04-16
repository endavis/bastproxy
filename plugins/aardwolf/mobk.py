"""
$Id$
#TODO: get weapon for vorpals
"""
import time
import copy
from libs import exported
from libs.color import strip_ansi
from plugins import BasePlugin

NAME = 'Aardwolf Mobkill events'
SNAME = 'mobk'
PURPOSE = 'Events for Aardwolf Mobkills'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

def damagedefault():
  """
  return a default damage dictionary
  """
  tdamage = {}
  tdamage['hits'] = 0
  tdamage['misses'] = 0
  tdamage['damage'] = 0
  return tdamage


def addtodamage(tdam, damtable):
  """
  add damage to a damage table
  """
  damtype = tdam['damtype']
  if not damtype:
    damtype = 'Unknown'

  if not (damtype in damtable):
    damtable[damtype] = damagedefault()

  if tdam['damverb'] == 'misses':
    damtable[damtype]['misses'] = damtable[damtype]['misses'] + tdam['hits']
  else:
    damtable[damtype]['hits'] = damtable[damtype]['hits'] + tdam['hits']
    damtable[damtype]['damage'] = damtable[damtype]['damage'] + tdam['damage']

  return damtable


class Plugin(BasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.kill_info = {}
    self.reset_kill()
    self.mobdamcache = {}
    self.addsetting('instatext', '@x0', 'color',
                      'the text color for an instakill')
    self.addsetting('instaback', '@z10', 'color',
                      'the background color for an instakill')
    self.dependencies.append('aardu')
    self.triggers['mobxp'] = {
      'regex':"^You receive (?P<xp>\d+(?:\+\d+)*) experience points?\.$"}
    self.triggers['mobxpptless'] = {
      'regex':"^That was a pointless no experience kill!$"}
    self.triggers['mobswitch'] = {
      'regex':"^You switch targets and " \
              "direct your attacks at (?P<name>.*).\.$"}
    self.triggers['mobflee'] = {
      'regex':"^You flee from combat!$"}
    self.triggers['mobretreat'] = {
      'regex':"^You retreat from the combat!$"}
    self.triggers['mobblessxp'] = {
      'regex':"^You receive (?P<blessxp>\d+) bonus " \
                          "experience points from your daily blessing.*$"}
    self.triggers['mobbonusxp'] = {
      'regex':"^You receive (?P<bonxp>\d+) bonus experience points.*$"}
    self.triggers['mobgold'] = {
      'regex':"^You get (?P<gold>.+) gold coins " \
              "from .+ corpse of (?P<name>.+)\.$"}
    self.triggers['mobname'] = {
      'regex':"^You get .+ corpse of (?P<name>.+)\.$"}
    self.triggers['mobsac'] = {
      'regex':"^.* gives you (?P<sacgold>.+) gold coins? for " \
                              "the .* ?corpse of (?P<name>.+)\.$"}
    self.triggers['mobconsume'] = {
      'regex':"^You bury your fangs deep into the " \
              ".* ?corpse of (?P<name>.+), drinking thirstily.$"}
    self.triggers['mobsplitgold'] = {
      'regex':"^\w+ splits? \d+ gold coins?. " \
                                "Your share is (?P<gold>\d+) gold\.$"}
    self.triggers['mobtrivia'] = {
      'regex':"^You killed a Triv bonus mob!! Triv point added\.$"}
    self.triggers['mobvorpal'] = {
      'regex':"^Deep magic stirs within your weapon. " \
                    "It seems to have a life of its own.$"}
    self.triggers['mobassassin'] = {
      'regex':"^You assassinate (?P<name>.*) with cold efficiency.$"}
    self.triggers['mobdeathblow'] = {
      'regex':"^Your death blow CLEAVES (P<name>.*) in two!$"}
    self.triggers['mobslit'] = {
      'regex':"^You sneak behind (?P<name>.*) and slit .* throat.$"}
    self.triggers['mobdisintegrate'] = {
      'regex':"^You have disintegrated (?P<name>.*)!$"}
    self.triggers['mobbanish'] = {
      'regex':"^You look at (?P<name>.*) very strangely.$"}
    self.triggers['mobdamage'] = {
      'regex':"^\[(.*)\] Your (.*) \[(.*)\]$"}
    self.triggers['mobdamage2'] = {
      'regex':"^Your (.*) \[(.*)\]$"}

    self.events['trigger_mobxp'] = {'func':self.mobxp}
    self.events['trigger_mobxpptless'] = {'func':self.mobxpptless}
    self.events['trigger_mobswitch'] = {'func':self.mobswitch}
    self.events['trigger_mobflee'] = {'func':self.mobnone}
    self.events['trigger_mobretreat'] = {'func':self.mobnone}
    self.events['trigger_mobblessxp'] = {'func':self.mobblessxp}
    self.events['trigger_mobbonusxp'] = {'func':self.mobbonusxp}
    self.events['trigger_mobgold'] = {'func':self.mobgold}
    self.events['trigger_mobsplitgold'] = {'func':self.mobgold}
    self.events['trigger_mobname'] = {'func':self.mobname}
    self.events['trigger_mobsac'] = {'func':self.mobname}
    self.events['trigger_mobconsume'] = {'func':self.mobname}
    self.events['trigger_mobtrivia'] = {'func':self.mobtrivia}
    self.events['trigger_mobvorpal'] = {'func':self.mobvorpal}
    self.events['trigger_mobassassin'] = {'func':self.mobassassin}
    self.events['trigger_mobdeathblow'] = {'func':self.mobdeathblow}
    self.events['trigger_mobslit'] = {'func':self.mobslit}
    self.events['trigger_mobdisintegrate'] = {'func':self.mobdisintegrate}
    self.events['trigger_mobbanish'] = {'func':self.mobbanish}
    self.events['trigger_mobdamage'] = {'func':self.mobdamage}
    self.events['trigger_mobdamage2'] = {'func':self.mobdamage}

    self.events['GMCP:char.status'] = {'func':self.gmcpcharstatus}

  def gmcpcharstatus(self, args):
    """
    do stuff when we see a gmcp char.status
    """
    status = args['data']
    if status['enemy'] != "" and self.kill_info['name'] == "":
      self.kill_info['name'] = strip_ansi(status['enemy'])
      self.reset_damage()

  def reset_kill(self):
    """
    reset a kill
    """
    self.kill_info.clear()
    self.kill_info['name'] = ''
    self.kill_info['tp'] = 0
    self.kill_info['vorpal'] = 0
    self.kill_info['assassinate'] = 0
    self.kill_info['deathblow'] = 0
    self.kill_info['slit'] = 0
    self.kill_info['disintegrate'] = 0
    self.kill_info['banishment'] = 0
    self.kill_info['xp'] = 0
    self.kill_info['bonusxp'] = 0
    self.kill_info['blessingxp'] = 0
    self.kill_info['totalxp'] = 0
    self.kill_info['gold'] = 0
    self.kill_info['tp'] = 0
    self.kill_info['name'] = ""
    self.kill_info['wielded_weapon'] = ''
    self.kill_info['second_weapon'] = ''
    self.kill_info['raised'] = True
    self.kill_info['room_id'] = -1
    self.kill_info['damage'] = {}
    self.kill_info['immunities'] = {}
    self.kill_info['starttime'] = None
    self.kill_info['finishtime'] = None

  def reset_damage(self):
    """
    reset damage
    """
    self.kill_info['damage'] = {}
    self.kill_info['immunities'] = {}
    self.kill_info['starttime'] = None
    self.kill_info['finishtime'] = None


  def mobnone(self, _=None):
    """
    reset the mob name
    """
    self.kill_info['name'] = ""
    self.reset_damage()

  def mobname(self, args):
    """
    got a mob name
    """
    if args['triggername'] in ['mobsac', 'mobconsume'] \
        and self.kill_info['name']:
      #exported.sendtoclient('got mobsac/mobconsume with name')
      self.raise_kill()

  def mobxpptless(self, _=None):
    """
    set xp to 0 when a pointless kill is seen
    """
    self.kill_info['xp'] = 0
    self.kill_info['raised'] = False

  def mobblessxp(self, args):
    """
    add blessing xp
    """
    self.kill_info['blessingxp'] = int(args['blessxp'])

  def mobbonusxp(self, args):
    """
    add bonus xp
    """
    self.kill_info['bonusxp'] = int(args['bonxp'])

  def mobxp(self, args):
    """
    add regular xp
    """
    #exported.sendtoclient('mobxp')
    mxp = args['xp']
    if '+' in mxp:
      newxp = 0
      tlist = mxp.split('+')
      for i in tlist:
        newxp = newxp + int(i)
    else:
      newxp = int(mxp)

    self.kill_info['xp'] = newxp
    self.kill_info['raised'] = False

  def mobswitch(self, args):
    """
    switch mobs
    """
    self.kill_info['name'] = strip_ansi(args['name'])
    self.reset_damage()

  def mobvorpal(self, _=None):
    """
    vopaled a mob
    """
    self.kill_info['vorpal'] = 1
    #TODO: set primary and secondary weapons

  def mobassassin(self, args):
    """
    assassinated mob
    """
    self.kill_info['name'] = strip_ansi(args['name'])
    self.kill_info['assassinate'] = 1

  def mobslit(self, args):
    """
    slitted a mob
    """
    self.kill_info['name'] = strip_ansi(args['name'])
    self.kill_info['slit'] = 1
    self.kill_info['raised'] = False
    self.kill_info['time'] = time.time()
    self.raise_kill()

  def mobdisintegrate(self, args):
    """
    disintegrated a mob
    """
    self.kill_info['name'] = strip_ansi(args['name'])
    self.kill_info['disintegrate'] = 1
    self.kill_info['raised'] = False
    self.kill_info['time'] = time.time()
    self.raise_kill()

  def mobbanish(self, args):
    """
    banished a mob
    """
    self.kill_info['name'] = strip_ansi(args['name'])
    self.kill_info['banishment'] = 1
    self.kill_info['raised'] = False
    self.kill_info['time'] = time.time()
    self.raise_kill()

  def mobdeathblow(self, args):
    """
    deathblowed a mob
    """
    self.kill_info['name'] = strip_ansi(args['name'])
    self.kill_info['deathblow'] = 1

  def mobgold(self, args):
    """
    get gold from the mobkill
    """
    gold = args['gold'].replace(',', '')
    self.kill_info['gold'] = int(gold)
    if not self.kill_info['name']:
      self.kill_info['name'] = strip_ansi(args['name'])

  def mobtrivia(self, _=None):
    """
    a trivia mob
    """
    self.kill_info['tp'] = 1

  def raise_kill(self):
    """
    raise a kill
    """
    #exported.sendtoclient('raising a kill')
    self.kill_info['finishtime'] = time.time()
    self.kill_info['room_id'] = exported.GMCP.getv('room.info.num')
    self.kill_info['level'] = exported.aardu.getactuallevel()
    self.kill_info['time'] = time.time()
    if not self.kill_info['raised']:
      if not self.kill_info['name']:
        self.kill_info['name'] = 'Unknown'
      self.kill_info['totalxp'] = self.kill_info['xp'] + \
                                  self.kill_info['bonusxp'] + \
                                  self.kill_info['blessingxp']

      exported.event.eraise('aard_mobkill', copy.deepcopy(self.kill_info))

    self.reset_kill()

  def incombat(self):
    """
    just saw an incombat backstab
    """
    if not ('backstab' in self.kill_info['damage']):
      self.kill_info['damage']['backstab'] = damagedefault()

    self.kill_info.damage['backstab']['incombat'] = True

  def immunity(self, args):
    """
    saw an immunity for the current mob
    """
    mobname = args['name']
    immunity = args['immunity']
    if not (immunity in self.kill_info['immunities']) \
          and self.kill_info['name'] == mobname:
      self.kill_info['immunities'][immunity] = True

  def mobdamage(self, args):
    """
    saw a damage line
    """
    tdam = exported.aardu.parsedamageline(args['line'])

    if not self.kill_info['starttime']:
      self.kill_info['starttime'] = time.time()
    if tdam['enemy'] \
        and self.kill_info['name'] != '' \
        and tdam['enemy'] != self.kill_info['name']:
      if not (tdam['enemy'] in  self.mobdamcache):
        self.mobdamcache[tdam['enemy']] = {}
      addtodamage(tdam, self.mobdamcache[tdam['enemy']])
      return

    if tdam['enemy'] in self.mobdamcache:
      self.kill_info['damage'] = self.mobdamcache[tdam['enemy']]
      del(self.mobdamcache[tdam['enemy']])
    addtodamage(tdam, self.kill_info['damage'])
