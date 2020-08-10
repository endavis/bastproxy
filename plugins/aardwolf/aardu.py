"""
This plugin is a utility plugin for aardwolf functions

It contains

 * a damages table
 * class abbreviation table
 * a function to convert a level to level, remort, tier, redos
 * a function to convert a level, remort, tier, redos to overall level
 * a function to parse damage lines
"""
import math
import re
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Utils'
SNAME = 'aardu'
PURPOSE = 'Aard related functions to use in the api'
AUTHOR = 'Bast'
VERSION = 1



# a table of class abbreviations
CLASSABB = {
    'mag':'mage',
    'thi':'thief',
    'pal':'paladin',
    'war':'warrior',
    'psi':'psionicist',
    'cle':'cleric',
    'ran':'ranger',
}

# the reverse of CLASSABB
CLASSABBREV = {}
for classn in CLASSABB:
  CLASSABBREV[CLASSABB[classn]] = classn

# a table of rewards
REWARDTABLE = {
    'quest':'qp',
    'training':'trains',
    'gold':'gold',
    'trivia':'tp',
    'practice':'pracs',
}

# a table of damages
DAMAGES = [
    'misses',
    'tickles',
    'bruises',
    'scratches',
    'grazes',
    'nicks',
    'scars',
    'hits',
    'injures',
    'wounds',
    'mauls',
    'maims',
    'mangles',
    'mars',
    'LACERATES',
    'DECIMATES',
    'DEVASTATES',
    'ERADICATES',
    'OBLITERATES',
    'EXTIRPATES',
    'INCINERATES',
    'MUTILATES',
    'DISEMBOWELS',
    'MASSACRES',
    'DISMEMBERS',
    'RENDS',
    '- BLASTS -',
    '-= DEMOLISHES =-',
    '** SHREDS **',
    '**** DESTROYS ****',
    '***** PULVERIZES *****',
    '-=- VAPORIZES -=-',
    '<-==-> ATOMIZES <-==->',
    '<-:-> ASPHYXIATES <-:->',
    '<-*-> RAVAGES <-*->',
    '<>*<> FISSURES <>*<>',
    '<*><*> LIQUIDATES <*><*>',
    '<*><*><*> EVAPORATES <*><*><*>',
    '<-=-> SUNDERS <-=->',
    '<=-=><=-=> TEARS INTO <=-=><=-=>',
    '<->*<=> WASTES <=>*<->',
    '<-+-><-*-> CREMATES <-*-><-+->',
    '<*><*><*><*> ANNIHILATES <*><*><*><*>',
    '<--*--><--*--> IMPLODES <--*--><--*-->',
    '<-><-=-><-> EXTERMINATES <-><-=-><->',
    '<-==-><-==-> SHATTERS <-==-><-==->',
    '<*><-:-><*> SLAUGHTERS <*><-:-><*>',
    '<-*-><-><-*-> RUPTURES <-*-><-><-*->',
    '<-*-><*><-*-> NUKES <-*-><*><-*->',
    '-<[=-+-=]<:::<>:::> GLACIATES <:::<>:::>[=-+-=]>-',
    '<-=-><-:-*-:-><*--*> METEORITES <*--*><-:-*-:-><-=->',
    '<-:-><-:-*-:-><-*-> SUPERNOVAS <-*-><-:-*-:-><-:->',
    'does UNSPEAKABLE things to',
    'does UNTHINKABLE things to',
    'does UNIMAGINABLE things to',
    'does UNBELIEVABLE things to',
    'pimpslaps'
]

# the reverse of DAMAGES
DAMAGESREV = {}
for damagen in DAMAGES:
  DAMAGESREV[damagen] = DAMAGES.index(damagen)

class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.api('api.add')('getactuallevel', self.api_getactuallevel)
    self.api('api.add')('convertlevel', self.api_convertlevel)
    self.api('api.add')('classabb', self.api_classabb)
    self.api('api.add')('rewardtable', self.api_rewardtable)
    self.api('api.add')('parsedamageline', self.api_parsedamageline)

    self.dependencies = ['aardwolf.connect']

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('triggers.add')('dead',
                             r"^You die.$",
                             enabled=True,
                             group='dead')

  # convert level, remort, tier, redos to the total levels
  def api_getactuallevel(self, level=None, remort=None,
                         tier=None, redos=None):
    """  convert level, remort, tier, redos to the total levels
    @Ylevel@w  = the level, defaults to GMCP value
    @Yremort@w  = the # of remorts, default to GMCP value
    @Ytier@w  = the # of tiers, default to GMCP value
    @Yredos@w  = the # of redos, default to GMCP value

    this function returns the total levels"""
    level = level or self.api('GMCP.getv')('char.status.level') or 0
    remort = remort or self.api('GMCP.getv')('char.base.remorts') or 0
    tier = tier or self.api('GMCP.getv')('char.base.tier') or 0
    redos = int(redos or self.api('GMCP.getv')('char.base.redos') or 0)
    if redos == 0:
      return (tier * 7 * 201) + ((remort - 1) * 201) + level

    return (tier * 7 * 201) + (redos * 7 * 201) + \
                                  ((remort - 1) * 201) + level

  @staticmethod
  # parse an Aardwolf damage line
  def api_parsedamageline(line):
    """  parse an Aardwolf damage line from combat
    @Yline@w  = the line to parse

    this function returns a dictionary with keys:
      damage  = the amount of damage
      hits    = the # of hits
      damtype = the damage type
      damverb = the verb of the damage
      enemy   = the enemy"""
    ddict = {}
    tsplit = line.split(' ')
    ddict['hits'] = 1
    thits = re.match(r'^\[(?P<hits>\d*)\]', tsplit[0])
    if thits:
      ddict['hits'] = int(thits.groupdict()['hits'])
      del tsplit[0]

    if tsplit[0] == 'Your':
      del tsplit[0]

    ddict['damage'] = 0
    tdam = re.match(r'^\[(?P<damage>\d*)\]', tsplit[-1])
    if tdam:
      ddict['damage'] = int(tdam.groupdict()['damage'])
      del tsplit[-1]

    nline = ' '.join(tsplit)
    for i in DAMAGES:
      if i in nline:
        regex = r'^(?P<damtype>.*) (%s) (?P<enemy>.*)[!|\.]$' % re.escape(i)
        mat = re.match(regex, nline)
        if mat:
          ddict['damtype'] = mat.groupdict()['damtype']
          ddict['damverb'] = i
          ddict['enemy'] = mat.groupdict()['enemy']
          break

    return ddict

  @staticmethod
  # convert a level to redos, tier, remort, level
  def api_convertlevel(level):
    """  convert a level to redos, tier, remort, level
    @Ylevel@w  = the level to convert

    this function returns a dictionary with keys:
      level   = the level
      remort  = the # of remorts
      tier    = the # of tiers
      redo    = the # of redos"""
    if not level or level < 1:
      return {'tier':-1, 'redos':-1, 'remort':-1, 'level':-1}
    tier = math.floor(level / (7 * 201))
    if level % (7 * 201) == 0:
      tier = math.floor(level / (7 * 201)) - 1
    remort = math.floor((level - (tier * 7 * 201)) / 202) + 1
    alevel = level % 201
    if alevel == 0:
      alevel = 201

    redos = 0
    if tier > 9:
      redos = tier - 9
      tier = 9
    return {'tier':int(tier), 'redos':int(redos),
            'remort':int(remort), 'level':int(alevel)}

  @staticmethod
  # get the Class abbreviations table
  def api_classabb(rev=False):
    """  get the class abbreviations
    @Yrev@w  = if True, return the reversed table

    this function returns a dictionary
      original dictionary example:
        'mag' : 'mage'

      reversed dictionary example:
        'mage' : 'mag'"""
    if rev:
      return CLASSABB

    return CLASSABBREV

  @staticmethod
  # get the reward table
  def api_rewardtable():
    """  get the reward table
    @Yrev@w  = if True, return the reversed table

    this function returns a dictionary of rewards"""
    return REWARDTABLE
