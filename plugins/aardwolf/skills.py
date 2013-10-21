"""
$Id$

This plugin handles slist from Aardwolf
"""
import time
import os
import copy
from plugins import BasePlugin
from libs.persistentdict import PersistentDict
from libs import utils
from libs.timing import timeit
import fnmatch

NAME = 'Aardwolf Skills'
SNAME = 'skills'
PURPOSE = 'keep up with skills using slist'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

FAILREASON = {}
FAILREASON[1] = 'lostconc' # Regular fail, lost concentration.
FAILREASON[2] = 'alreadyaff' # Already affected.
FAILREASON[3] = 'recblock' # Cast blocked by a recovery, see below.
FAILREASON[4] = 'nomana' # Not enough mana.
FAILREASON[5] = 'nocastroom' # You are in a nocast room.
FAILREASON[6] = 'fighting' # Fighting or other 'cant concentrate'.
FAILREASON[8] = 'dontknow' # You don't know the spell.
FAILREASON[9] = 'wrongtarget' # Tried to cast self only on other.
FAILREASON[10] = 'notactive' # - You are resting / sitting.
FAILREASON[11] = 'disabled' # Skill/spell has been disabled.
FAILREASON[12] = 'nomoves' # Not enough moves.

TARGET = {}
TARGET[0] = 'special' # Target decided in spell (gate etc)
TARGET[1] = 'attack'
TARGET[2] = 'spellup'
TARGET[3] = 'selfonly'
TARGET[4] = 'object'
TARGET[5] = 'other' # Spell has extended / unique syntax.

STYPE = {}
STYPE[1] = 'spell'
STYPE[2] = 'skill'

FAILTARG = {0:'self', 1:'other'}


class Plugin(BasePlugin):
  """
  a plugin manage info about spells and skills
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.saveskillfile = os.path.join(self.savedir, 'skills.txt')
    self.skills = PersistentDict(self.saveskillfile, 'c', format='json')
    self.skillsnamelookup = {}
    for i in self.skills:
      self.skillsnamelookup[self.skills[i]['name']] = i

    self.saverecovfile = os.path.join(self.savedir, 'recoveries.txt')
    self.recoveries = PersistentDict(self.saverecovfile, 'c', format='json')
    self.recoveriesnamelookup = {}
    for i in self.recoveries:
      self.recoveriesnamelookup[self.recoveries[i]['name']] = i

    self.current = ''
    self.isuptodatef = False

    self.triggers['spellh_noprompt'] = \
            {'regex':"^\{spellheaders noprompt\}$"}
    self.triggers['spellh_spellup_noprompt'] = \
            {'regex':"^\{spellheaders spellup noprompt\}$"}
    self.triggers['spellh_affected_noprompt'] = \
            {'regex':"^\{spellheaders affected noprompt\}$"}
    self.triggers['spellh_spellline'] = \
            {'regex':"^(?P<sn>\d+),(?P<name>.+),(?P<target>\d+)," \
              "(?P<duration>\d+),(?P<pct>\d+),(?P<rcvy>-?\d+),(?P<type>\d+)$",
              'enabled':False, 'group':'spellhead'}
    self.triggers['spellh_end_noprompt'] = \
            {'regex':"^\{/spellheaders\}$",
              'enabled':False, 'group':'spellhead'}
    self.triggers['affoff'] = \
            {'regex':"^\{affoff\}(?P<sn>\d+)$"}
    self.triggers['affon'] = \
            {'regex':"^\{affon\}(?P<sn>\d+),(?P<duration>\d+)$"}
    self.triggers['recov_noprompt'] = \
            {'regex':"^\{recoveries noprompt\}$"}
    self.triggers['recov_affected_noprompt'] = \
            {'regex':"^\{recoveries affected noprompt\}$"}
    self.triggers['spellh_recovline'] = \
            {'regex':"^(?P<sn>\d+),(?P<name>.+),(?P<duration>\d+)$",
              'enabled':False, 'group':'recoveries'}
    self.triggers['recov_end_noprompt'] = \
            {'regex':"^\{/recoveries\}$",
              'enabled':False, 'group':'recoveries'}
    self.triggers['recoff'] = \
            {'regex':"^\{recoff\}(?P<sn>\d+)$"}
    self.triggers['recon'] = \
            {'regex':"^\{recon\}(?P<sn>\d+),(?P<duration>\d+)$"}
    self.triggers['skillgain'] = \
            {'regex':"^\{skillgain\}(?P<sn>\d+),(?P<percent>\d+)$"}
    self.triggers['skillfail'] = \
            {'regex':"^\{sfail\}(?P<sn>\d+),(?P<target>\d+)," \
                      "(?P<reason>\d+),(?P<recovery>-?\d+)$"}

    self.api.get('events.register')('trigger_spellh_noprompt', self.skillstart)
    self.api.get('events.register')('trigger_spellh_spellup_noprompt', self.skillstart)
    self.api.get('events.register')('trigger_spellh_affected_noprompt', self.skillstart)
    self.api.get('events.register')('trigger_spellh_spellline', self.skillline)
    self.api.get('events.register')('trigger_spellh_end_noprompt', self.skillend)
    self.api.get('events.register')('trigger_affoff', self.affoff)
    self.api.get('events.register')('trigger_affon', self.affon)
    self.api.get('events.register')('trigger_recov_noprompt', self.recovstart)
    self.api.get('events.register')('trigger_recov_affected_noprompt', self.recovstart)
    self.api.get('events.register')('trigger_spellh_recovline', self.recovline)
    self.api.get('events.register')('trigger_recov_end_noprompt', self.recovend)
    self.api.get('events.register')('trigger_recoff', self.recoff)
    self.api.get('events.register')('trigger_recon', self.recon)

    self.api.get('events.register')('trigger_skillgain', self.skillgain)
    self.api.get('events.register')('trigger_skillfail', self.skillfail)

    self.api.get('events.register')('GMCP:char.status', self.checkskills)

    self.cmds['refresh'] = {'func':self.cmd_refresh,
              'shelp':'refresh skills and spells'}
    self.cmds['lu'] = {'func':self.cmd_lu,
              'shelp':'lookup skill by name or sn'}

    self.exported['gets'] = {'func':self.getskill}
    self.exported['isspellup'] = {'func':self.isspellup}
    self.exported['getspellups'] = {'func':self.getspellups}
    self.exported['sendcmd'] = {'func':self.sendcmd}
    self.exported['isaffected'] = {'func':self.isaffected}
    self.exported['isblockedbyrecovery'] = {'func':self.isblockedbyrecovery}
    self.exported['ispracticed'] = {'func':self.ispracticed}
    self.exported['canuse'] = {'func':self.canuse}
    self.exported['isuptodate'] = {'func':self.isuptodate}

  def firstactive(self):
    """
    do something on connect
    """
    BasePlugin.firstactive(self)
    self.checkskills()

  def isuptodate(self):
    """
    return True if we have seen affected or all spells refresh
    """
    return self.isuptodatef

  def cmd_lu(self, args):
    """
    cmd to lookup a spell
    """
    msg = []
    skill = self.getskill(args[0])
    if skill:
      msg.append('%-8s : %s' % ('SN', skill['sn']))
      msg.append('%-8s : %s' % ('Name', skill['name']))
      msg.append('%-8s : %s' % ('Percent', skill['percent']))
      if skill['duration'] > 0:
        msg.append('%-8s : %s' % ('Duration',
            utils.timedeltatostring(time.time(),
              skill['duration'])))
      msg.append('%-8s : %s' % ('Target', skill['target']))
      msg.append('%-8s : %s' % ('Spellup', skill['spellup']))
      msg.append('%-8s : %s' % ('Type', skill['type']))
      if skill['recovery']:
        recov = skill['recovery']
        if recov['duration'] > 0:
          duration =  utils.timedeltatostring(time.time(),
              recov['duration'])
          msg.append('%-8s : %s (%s)' % ('Recovery',
                                      recov['name'], duration))
        else:
          msg.append('%-8s : %s' % ('Recovery', recov['name']))
    else:
      msg.append('Could not find: %s' % args[0])

    return True, msg

  def cmd_refresh(self, args):
    """
    refresh spells and skills
    """
    self.skills.clear()
    self.recoveries.clear()
    self.api.get('input.execute')('slist noprompt')
    self.api.get('input.execute')('slist spellup noprompt')
    msg = ['Refreshing spells and skills']
    return True, msg

  def checkskills(self, _=None):
    """
    check to see if we have spells
    """
    state = self.api.get('GMCP.getv')('char.status.state')
    if state == 3:
      self.api.get('output.msg')('refreshing skills')
      self.api.get('events.unregister')('GMCP:char.status', self.checkskills)
      self.api.get('A102.toggle')('SPELLUPTAGS', True)
      self.api.get('A102.toggle')('SKILLGAINTAGS', True)
      self.api.get('A102.toggle')('QUIETTAGS', False)
      if len(self.skills) == 0:
        self.cmd_refresh({})
      else:
        self.resetskills()
        self.api.get('input.execute')('slist affected noprompt')

  def resetskills(self):
    """
    reset the skills
    """
    for i in self.skills:
      self.skills[i]['duration'] = 0
    for i in self.recoveries:
      self.recoveries[i]['duration'] = 0

  def skillgain(self, args):
    """
    handle a skillgain tag
    """
    sn = int(args['sn'])
    pct = int(args['percent'])
    if sn in self.skills:
      self.skills[sn]['percent'] = pct
      self.api.get('events.eraise')('aard_skill_gain', {'sn':sn, 'percent':pct})

  def skillfail(self, args):
    """
    raise an event when we fail a skill/spell
    """
    ndict = {'sn': int(args['sn']), 'reason':FAILREASON[int(args['reason'])],
            'target':FAILTARG[int(args['target'])],
            'recovery':int(args['recovery'])}
    self.api.get('output.msg')('raising skillfail: %s' % ndict)
    self.api.get('events.eraise')('skill_fail_%s' % args['sn'], ndict)
    self.api.get('events.eraise')('skill_fail', ndict)

  def affoff(self, args):
    """
    set the affect to off for spell that wears off
    """
    sn = int(args['sn'])
    if sn in self.skills:
      self.skills[sn]['duration'] = 0
      self.savestate()
      self.api.get('events.eraise')('aard_skill_affoff_%s' % sn, {'sn':sn})
      self.api.get('events.eraise')('aard_skill_affoff', {'sn':sn})

  def affon(self, args):
    """
    set the spell's duration when we see an affon
    """
    sn = int(args['sn'])
    duration = int(args['duration'])
    if sn in self.skills:
      self.skills[sn]['duration'] = time.mktime(time.localtime()) + duration
      self.savestate()
      self.api.get('events.eraise')('aard_skill_affon_%s' % sn, {'sn':sn,
                              'duration':self.skills[sn]['duration']})
      self.api.get('events.eraise')('aard_skill_affon', {'sn':sn,
                              'duration':self.skills[sn]['duration']})

  def recovstart(self, args):
    """
    show that the trigger fired
    """
    if 'triggername' in args \
        and args['triggername'] == 'trigger_recov_affected_noprompt':
      self.current = 'affected'
    else:
      self.current = ''
    self.api.get('trigger.togglegroup')('recoveries', True)

  def recovline(self, args):
    """
    parse a recovery line
    """
    sn = int(args['sn'])
    name = args['name']
    if int(args['duration']) != 0:
      duration = time.mktime(time.localtime()) + int(args['duration'])
    else:
      duration = 0

    if not (sn in self.recoveries):
      self.recoveries[sn] = {}

    self.recoveries[sn]['name'] = name
    self.recoveries[sn]['duration'] = duration
    self.recoveries[sn]['sn'] = sn

    self.recoveriesnamelookup[name] = sn

  def recovend(self, args):
    """
    reset current when seeing a spellheaders ending
    """
    self.api.get('trigger.togglegroup')('recoveries', False)
    if self.current == '' or self.current == 'affected':
      self.isuptodatef = True
      self.api.get('output.msg')('sending skills_affected_update')
      self.api.get('events.eraise')('skills_affected_update', {})
    self.savestate()

  def recoff(self, args):
    """
    set the affect to off for spell that wears off
    """
    sn = int(args['sn'])
    if sn in self.recoveries:
      self.recoveries[sn]['duration'] = 0
      self.savestate()
      self.api.get('events.eraise')('aard_skill_recoff', {'sn':sn})

  def recon(self, args):
    """
    set the spell's duration when we see an affon
    """
    sn = int(args['sn'])
    duration = int(args['duration'])
    if sn in self.recoveries:
      self.recoveries[sn]['duration'] = \
                        time.mktime(time.localtime()) + duration
      self.savestate()
      self.api.get('events.eraise')('aard_skill_recon', {'sn':sn,
                                  'duration':self.recoveries[sn]['duration']})

  def skillstart(self, args):
    """
    show that the trigger fired
    """
    if 'triggername' in args \
        and args['triggername'] == 'spellh_spellup_noprompt':
      self.current = 'spellup'
    elif 'triggername' in args \
        and args['triggername'] == 'spellh_affected_noprompt':
      self.current = 'affected'
    else:
      self.current = ''
    self.api.get('trigger.togglegroup')('spellhead', True)

  def skillline(self, args):
    """
    parse spell lines
    """
    sn = int(args['sn'])
    name = args['name']
    target = int(args['target'])
    if int(args['duration']) != 0:
      duration = time.mktime(time.localtime()) + int(args['duration'])
    else:
      duration = 0
    percent = int(args['pct'])
    recovery = int(args['rcvy'])
    stype = int(args['type'])

    if not (sn in self.skills):
      self.skills[sn] = {}

    self.skills[sn]['name'] = name
    self.skills[sn]['target'] = TARGET[target]
    self.skills[sn]['duration'] = duration
    self.skills[sn]['percent'] = percent
    self.skills[sn]['recovery'] = recovery
    self.skills[sn]['type'] = STYPE[stype]
    self.skills[sn]['sn'] = sn
    if not ('spellup' in self.skills[sn]):
      self.skills[sn]['spellup'] = False
    if self.current == 'spellup':
      self.skills[sn]['spellup'] = True

    self.skillsnamelookup[name] = sn

  def skillend(self, args):
    """
    reset current when seeing a spellheaders ending
    """
    self.api.get('trigger.togglegroup')('spellhead', False)
    self.savestate()
    if self.current:
      evname = 'aard_skill_ref_%s' % self.current
    else:
      evname = 'aard_skill_ref'
    self.api.get('events.eraise')(evname, {})
    self.current = ''

  @timeit
  def getskill(self, tsn):
    """
    get a skill
    """
    self.api.get('output.msg')('looking for %s' % tsn, 'skills')
    sn = -1
    name = tsn
    try:
      sn = int(tsn)
    except ValueError:
      pass

    tskill = None
    if sn >= 1:
      self.api.get('output.msg')('%s >= 0' % sn, 'skills')
      if sn in self.skills:
        self.api.get('output.msg')('found sn', 'skills')
        tskill = copy.deepcopy(self.skills[sn])
        #tskill = self.skills[sn]
      else:
        self.api.get('output.msg')('did not find skill for int', 'skill')

    if not tskill and name:
      self.api.get('output.msg')('trying name', 'skills')
      tlist = utils.checklistformatch(name, self.skillsnamelookup.keys())
      if len(tlist) == 1:
        tskill = copy.deepcopy(self.skills[self.skillsnamelookup[tlist[0]]])

    if tskill:
      if tskill['recovery'] and tskill['recovery'] != -1:
        tskill['recovery'] = copy.deepcopy(self.recoveries[tskill['recovery']])
      else:
        tskill['recovery'] = None

    return tskill

  def sendcmd(self, sn):
    """
    send the command to activate a skill/spell
    """
    skill = self.getskill(sn)
    if skill:
      if skill['type'] == 'spell':
        self.api.get('output.msg')('casting %s' % skill['name'])
        self.api.get('input.execute')('cast %s' % skill['sn'])
      else:
        name = skill['name'].split()[0]
        self.api.get('output.msg')('sending skill %s' % skill['name'])
        self.api.get('input.execute')(name)

  def canuse(self, sn):
    """
    return True if the spell can be used
    """
    if self.isaffected(sn) or self.isblockedbyrecovery(sn) \
        or not self.ispracticed(sn):
      return False

    return True

  def isspellup(self, sn):
    """
    return True for a spellup, else return False
    """
    sn = int(sn)
    if sn in self.skills:
      return self.skills[sn]['spellup']

    return False

  def isaffected(self, sn):
    """
    return True for a spellup, else return False
    """
    skill = self.getskill(sn)
    if skill:
      return skill['duration'] > 0

    return False

  def isblockedbyrecovery(self, sn):
    """
    check to see if a spell/skill is blocked by a recovery
    """
    skill = self.getskill(sn)
    if skill:
      if 'recovery' in skill and skill['recovery'] and \
          skill['recovery']['duration'] > 0:
        return True

    return False

  def ispracticed(self, sn):
    """
    is the spell learned
    """
    skill = self.getskill(sn)
    if skill:
      if skill['percent'] > 1:
        return True

    return False

  def getspellups(self):
    """
    return a list of spellup spells
    """
    sus = [x for x in self.skills.values() if x['spellup']]
    return sus

  def savestate(self):
    """
    save states
    """
    BasePlugin.savestate(self)
    self.skills.sync()
    self.recoveries.sync()

