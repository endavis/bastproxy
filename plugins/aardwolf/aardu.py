"""
$Id$
"""
from libs import exported
from plugins import BasePlugin
import math

NAME = 'Aardwolf Utils'
SNAME = 'aardu'
PURPOSE = 'Aard related functions for exported'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

CLASSABB = {
  'mag':'mage',
  'thi':'thief',
  'pal':'paladin',
  'war':'warrior',
  'psi':'psionicist',
  'cle':'cleric',
  'ran':'ranger',
  }

CLASSABBREV = {}
for i in CLASSABB:
  CLASSABBREV[CLASSABB[i]] = i

REWARDTABLE = {
        'quest':'qp',
        'training':'trains',
        'gold':'gold',
        'trivia':'tp',
        'practice':'pracs',
    }
    
def getactuallevel(level=None, remort=None, tier=None, redos=None):
  """
  get an actual level
  all arguments are optional, if an argument is not given, it will be
    gotten from gmcp
  level, remort, tier, redos
  """  
  level = level or exported.GMCP.getv('char.status.level') or 0
  remort = remort or exported.GMCP.getv('char.base.remorts') or 0
  tier = tier or exported.GMCP.getv('char.base.tier') or 0
  redos = int(redos or exported.GMCP.getv('char.base.redos') or 0)
  if redos == 0:
    return (tier * 7 * 201) + ((remort - 1) * 201) + level
  else:
    return (tier * 7 * 201) + (redos * 7 * 201) + ((remort - 1) * 201) + level


def convertlevel(level):
  """
  convert a level to tier, redos, remort, level
  """
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
  return {'tier':tier, 'redos':redos, 'remort':remort, 'level':alevel}


def classabb(rev=False):
  """
  return the class abbreviations
  """
  if rev:
    return CLASSABB
  else:
    return CLASSABBREV

def rewardtable():
  """
  return the reward tables
  """
  return REWARDTABLE
  
class Plugin(BasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, name, sname, filename, directory, importloc):
    BasePlugin.__init__(self, name, sname, filename, directory, importloc)
    self.exported['getactuallevel'] = {'func':getactuallevel}
    self.exported['classabb'] = {'func':classabb}

