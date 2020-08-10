"""
This plugin handles mobkills on Aardwolf
"""
import copy
import time
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Mobkill events'
SNAME = 'mobk'
PURPOSE = 'Events for Aardwolf Mobkills'
AUTHOR = 'Bast'
VERSION = 1



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

  if damtype not in damtable:
    damtable[damtype] = damagedefault()

  if tdam['damverb'] == 'misses':
    damtable[damtype]['misses'] = damtable[damtype]['misses'] + tdam['hits']
  else:
    damtable[damtype]['hits'] = damtable[damtype]['hits'] + tdam['hits']
    damtable[damtype]['damage'] = damtable[damtype]['damage'] + tdam['damage']

  return damtable


class Plugin(AardwolfBasePlugin): # pylint: disable=too-many-public-methods
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)
    self.kill_info = {}
    self.reset_kill()
    self.mobdamcache = {}

  def initialize(self): # pylint: disable=too-many-statements
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting.add')('instatext', '@x0', 'color',
                            'the text color for an instakill')
    self.api('setting.add')('instaback', '@z10', 'color',
                            'the background color for an instakill')

    self.api('triggers.add')(
        'mobxp',
        r"^You (don't )?receive (?P<xp>\d+(?:\+\d+)*) experience points?\.$")
    self.api('triggers.add')(
        'mobrarexp',
        r"^You (don't )?receive (?P<xp>\d+) 'rare kill' experience bonus.$")
    self.api('triggers.add')(
        'mobblessxp',
        r"^You (don't )?receive (?P<xp>\d+) bonus " \
          r"experience points from your daily blessing.$",
        priority=99,
        stopevaluating=True)
    self.api('triggers.add')(
        'mobbonusxp',
        r"^You (don't )?receive (?P<xp>\d+) bonus experience points.+$")
    self.api('triggers.add')(
        'mobxpptless',
        r"^That was a pointless no experience kill\!$")
    self.api('triggers.add')(
        'mobswitch',
        r"^You switch targets and " \
          r"direct your attacks at (?P<name>.*).\.$")
    self.api('triggers.add')(
        'mobflee',
        r"^You flee from combat\!$")
    self.api('triggers.add')(
        'mobretreat',
        r"^You retreat from the combat\!$")
    self.api('triggers.add')(
        'mobgold',
        r"^You get (?P<gold>.+) gold coins " \
          r"from .+ corpse of (?P<name>.+)\.$")
    self.api('triggers.add')(
        'mobname',
        r"^You get .+ corpse of (?P<name>.+)\.$")
    self.api('triggers.add')(
        'mobsac',
        r"^.* gives you (?P<sacgold>.+) gold coins? for " \
          r"the .* ?corpse of (?P<name>.+)\.$")
    self.api('triggers.add')(
        'mobconsume',
        r"^You bury your fangs deep into the " \
          r".* ?corpse of (?P<name>.+), drinking thirstily.$")
    self.api('triggers.add')(
        'mobsplitgold',
        r"^\w+ splits? \d+ gold coins?. " \
          r"Your share is (?P<gold>\d+) gold\.$")
    self.api('triggers.add')(
        'mobtrivia',
        r"^You killed a Triv bonus mob!! Triv point added\.$")
    self.api('triggers.add')(
        'mobtrivia2',
        r"^You killed a Trivia Point bonus mob!! Trivia point added\.$")
    self.api('triggers.add')(
        'mobvorpal',
        r"^Deep magic stirs within your weapon. " \
          r"It seems to have a life of its own.$")
    self.api('triggers.add')(
        'mobassassin',
        r"^You assassinate (?P<name>.*) with cold efficiency.$")
    self.api('triggers.add')(
        'mobdeathblow',
        r"^Your death blow CLEAVES (?P<name>.*) in two!$")
    self.api('triggers.add')(
        'mobslit',
        r"^You sneak behind (?P<name>.*) and slit .* throat.$")
    self.api('triggers.add')(
        'mobdisintegrate',
        r"^You have disintegrated (?P<name>.*)!$")
    self.api('triggers.add')(
        'mobbanish',
        r"^You look at (?P<name>.*) very strangely.$")
    self.api('triggers.add')(
        'mobdamage',
        r"^\[(.*)\] Your (.*) \[(.*)\]$")
    self.api('triggers.add')(
        'mobdamage2',
        r"^Your (.*) \[(.*)\]$")
    self.api('triggers.add')(
        'bsincombat',
        r"^You spin around (.*), catching (.*) off guard, " \
          r"and execute a vicious double backstab.$")

    self.api('events.register')('trigger_mobxp', self.mobxp)
    self.api('events.register')('trigger_mobblessxp', self.bonusxp)
    self.api('events.register')('trigger_mobrarexp', self.bonusxp)
    self.api('events.register')('trigger_mobbonusxp', self.bonusxp)
    self.api('events.register')('trigger_mobxpptless', self.mobxpptless)
    self.api('events.register')('trigger_mobswitch', self.mobswitch)
    self.api('events.register')('trigger_mobflee', self.mobnone)
    self.api('events.register')('trigger_mobretreat', self.mobnone)
    self.api('events.register')('trigger_mobgold', self.mobgold)
    self.api('events.register')('trigger_mobsplitgold', self.mobgold)
    self.api('events.register')('trigger_mobname', self.mobname)
    self.api('events.register')('trigger_mobsac', self.mobname)
    self.api('events.register')('trigger_mobconsume', self.mobname)
    self.api('events.register')('trigger_mobtrivia', self.mobtrivia)
    self.api('events.register')('trigger_mobtrivia2', self.mobtrivia)
    self.api('events.register')('trigger_mobvorpal', self.mobvorpal)
    self.api('events.register')('trigger_mobassassin', self.mobassassin)
    self.api('events.register')('trigger_mobdeathblow', self.mobdeathblow)
    self.api('events.register')('trigger_mobslit', self.mobslit)
    self.api('events.register')('trigger_mobdisintegrate',
                                self.mobdisintegrate)
    self.api('events.register')('trigger_mobbanish', self.mobbanish)
    self.api('events.register')('trigger_mobdamage', self.mobdamage)
    self.api('events.register')('trigger_mobdamage2', self.mobdamage)
    self.api('events.register')('trigger_bsincombat', self.bsincombat)

    self.api('events.register')('GMCP:char.status', self.gmcpcharstatus)

  def gmcpcharstatus(self, args):
    """
    do stuff when we see a gmcp char.status
    """
    status = args['data']
    if status['enemy'] != "" and self.kill_info['name'] == "":
      self.kill_info['name'] = self.api('colors.stripansi')(
          status['enemy'])
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
    self.kill_info['rarexp'] = 0
    self.kill_info['totalxp'] = 0
    self.kill_info['noexp'] = 0
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

  def mobnone(self, args=None): # pylint: disable=unused-argument
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
      self.raise_kill()

  def mobxpptless(self, _=None):
    """
    set xp to 0 when a pointless kill is seen
    """
    self.kill_info['xp'] = 0
    self.kill_info['raised'] = False

  def bonusxp(self, args):
    """
    add different bonus xps
    """
    mxp = args['xp']
    newxp = int(mxp)
    if 'your daily blessing' in args['line']:
      self.kill_info['blessingxp'] = newxp
    elif 'rare' in args['line']:
      self.kill_info['rarexp'] = newxp
    else:
      self.kill_info['bonusxp'] = newxp

  def mobxp(self, args):
    """
    add regular xp
    """
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

    if "don't" in args['line']:
      self.kill_info['noexp'] = 1

  def mobswitch(self, args):
    """
    switch mobs
    """
    self.kill_info['name'] = self.api('colors.stripansi')(args['name'])
    self.reset_damage()

  def mobvorpal(self, _=None):
    """
    vopaled a mob
    """
    self.kill_info['vorpal'] = 1

  def mobassassin(self, args):
    """
    assassinated mob
    """
    self.kill_info['name'] = self.api('colors.stripansi')(args['name'])
    self.kill_info['assassinate'] = 1

  def mobslit(self, args):
    """
    slitted a mob
    """
    self.kill_info['name'] = self.api('colors.stripansi')(args['name'])
    self.kill_info['slit'] = 1
    self.kill_info['raised'] = False
    self.kill_info['time'] = time.time()
    self.raise_kill()

  def mobdisintegrate(self, args):
    """
    disintegrated a mob
    """
    self.kill_info['name'] = self.api('colors.stripansi')(args['name'])
    self.kill_info['disintegrate'] = 1
    self.kill_info['raised'] = False
    self.kill_info['time'] = time.time()
    self.raise_kill()

  def mobbanish(self, args):
    """
    banished a mob
    """
    self.kill_info['name'] = self.api('colors.stripansi')(args['name'])
    self.kill_info['banishment'] = 1
    self.kill_info['raised'] = False
    self.kill_info['time'] = time.time()
    self.raise_kill()

  def mobdeathblow(self, args):
    """
    deathblowed a mob
    """
    self.kill_info['name'] = self.api('colors.stripansi')(args['name'])
    self.kill_info['deathblow'] = 1

  def mobgold(self, args):
    """
    get gold from the mobkill
    """
    gold = args['gold'].replace(',', '')
    try:
      self.kill_info['gold'] = int(gold)
    except ValueError:
      self.api('send.msg')('got an invalid value for gold in mobgold: %s' \
                                                % args)
    if not self.kill_info['name']:
      self.kill_info['name'] = self.api('colors.stripansi')(args['name'])

  def mobtrivia(self, _=None):
    """
    a trivia mob
    """
    self.kill_info['tp'] = 1

  def raise_kill(self):
    """
    raise a kill
    """
    self.kill_info['finishtime'] = time.time()
    self.kill_info['room_id'] = self.api('GMCP.getv')('room.info.num')
    self.kill_info['level'] = self.api('aardu.getactuallevel')()
    self.kill_info['time'] = time.time()
    wielded = self.api('eq.getworn')(24)
    second = self.api('eq.getworn')(25)
    if wielded:
      self.kill_info['wielded_weapon'] = wielded.serial
    if second:
      self.kill_info['second_weapon'] = second.serial

    if not self.kill_info['raised']:
      if not self.kill_info['name']:
        self.kill_info['name'] = 'Unknown'
      self.kill_info['totalxp'] = self.kill_info['xp'] + \
                                  self.kill_info['rarexp'] + \
                                  self.kill_info['bonusxp'] + \
                                  self.kill_info['blessingxp']

      self.api('send.msg')('raising a mobkill: %s' % self.kill_info)
      self.api('events.eraise')('aard_mobkill',
                                copy.deepcopy(self.kill_info))

    self.reset_kill()

  def bsincombat(self, _=None):
    """
    just saw an incombat backstab
    """
    self.api('send.msg')('saw bs in combat')
    if 'backstab' not in self.kill_info['damage']:
      self.kill_info['damage']['backstab'] = damagedefault()

    self.kill_info['damage']['backstab']['incombat'] = True

  def immunity(self, args):
    """
    saw an immunity for the current mob
    """
    mobname = args['name']
    immunity = args['immunity']
    if immunity not in self.kill_info['immunities'] \
          and self.kill_info['name'] == mobname:
      self.kill_info['immunities'][immunity] = True

  def mobdamage(self, args):
    """
    saw a damage line
    """
    tdam = self.api('aardu.parsedamageline')(args['line'])

    if not self.kill_info['starttime']:
      self.kill_info['starttime'] = time.time()
    if tdam['enemy'] \
        and self.kill_info['name'] != '' \
        and tdam['enemy'] != self.kill_info['name']:
      if tdam['enemy'] not in  self.mobdamcache:
        self.mobdamcache[tdam['enemy']] = {}
      addtodamage(tdam, self.mobdamcache[tdam['enemy']])
      return

    if tdam['enemy'] in self.mobdamcache:
      self.kill_info['damage'] = self.mobdamcache[tdam['enemy']]
      del self.mobdamcache[tdam['enemy']]
    addtodamage(tdam, self.kill_info['damage'])

    if not self.kill_info['name']:
      self.kill_info['name'] = tdam['enemy']
