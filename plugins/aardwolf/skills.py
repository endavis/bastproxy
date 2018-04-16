"""
This plugin handles slist from Aardwolf
"""
import time
import copy
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin
import libs.argp as argp

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

class Skills(object):
  """
  a class to hold skills and recoveries
  """
  def __init__(self, plugin):
    """
    init the class
    """
    self.plugin = plugin
    self.api = self.plugin.api
    self.skills = {}
    self.recoveries = {}
    self.skillsnamelookup = {}
    self.recoveriesnamelookup = {}
    self.isuptodatef = False

  def setuptodate(self, flag=True):
    """
    set the up to date flag
    """
    self.isuptodatef = flag
    self.api('events.eraise')('skills_uptodate')

  def count(self):
    """
    return the count of skills
    """
    return len(self.skills)

  def reset(self):
    """
    reset skills and recoveries
    """
    self.api('send.msg')('resetting skills')
    self.skills = {}
    self.recoveries = {}
    self.skillsnamelookup = {}
    self.recoveriesnamelookup = {}
    self.isuptodatef = False

  def refresh(self):
    """
    refresh all data
    """
    self.api('send.msg')(
        "refreshing skills with 'slist noprompt' and 'slist leanred noprompt'")
    self.api('cmdq.addtoqueue')('slist', 'noprompt')
    self.api('cmdq.addtoqueue')('slist', 'spellup noprompt')

  def resetaffected(self):
    """
    reset affected data
    """
    for i in self.skills:
      self.skills[i]['duration'] = 0
    for i in self.recoveries:
      self.recoveries[i]['duration'] = 0

  def refreshaffected(self):
    """
    refresh affected data
    """
    self.api('send.msg')("refreshing affected with 'slist affected noprompt'")
    self.api('cmdq.addtoqueue')('slist', 'affected noprompt')

  def refreshlearned(self):
    """
    refresh learned data
    """
    self.api('send.msg')("refreshing learned with 'slist learned noprompt'")
    self.api('cmdq.addtoqueue')('slist', 'learned noprompt')

  def getitem(self, ttype, idnum):
    """
    get an item
    """
    tidnum = -1
    if ttype == 'skill':
      maint = self.skills
      lookupt = self.skillsnamelookup
    elif ttype == 'recovery':
      maint = self.recoveries
      lookupt = self.recoveriesnamelookup
    else:
      return None

    name = idnum

    try:
      tidnum = int(idnum)
    except ValueError:
      pass

    item = None
    if tidnum >= 1:
      if tidnum in maint:
        item = copy.deepcopy(maint[tidnum])
      else:
        self.api('send.msg')('did not find %s %s' % (ttype, tidnum))

    if not item and name:
      tlist = self.api('utils.checklistformatch')(name,
                                                  lookupt)
      if len(tlist) == 1:
        item = copy.deepcopy(maint[lookupt[tlist[0]]])

    return item

  def getskill(self, tsn):
    """
    get a skill by sn or name
    """
    item = self.getitem('skill', tsn)

    if item:
      item['recovery'] = self.getitem('recovery', item['recovery'])

    return item

  def addskill(self, args):
    """
    add a skill
    """
    self.api('send.msg')('adding skill : %s' % args)
    skillnum = args['sn']
    name = args['name']
    target = args['target']
    if args['duration'] != 0:
      duration = time.mktime(time.localtime()) + args['duration']
    else:
      duration = 0
    percent = args['pct']
    recovery = args['rcvy']
    stype = args['type']

    if skillnum not in self.skills:
      self.skills[skillnum] = {}

    self.skills[skillnum]['name'] = name
    self.skills[skillnum]['target'] = TARGET[target]
    self.skills[skillnum]['duration'] = duration
    self.skills[skillnum]['percent'] = percent
    self.skills[skillnum]['recovery'] = recovery
    self.skills[skillnum]['type'] = STYPE[stype]
    self.skills[skillnum]['sn'] = skillnum
    self.skills[skillnum]['spellup'] = False

    self.skillsnamelookup[name] = skillnum

  def flagspellup(self, skillnum):
    """
    flag a spell as a spellup
    """
    self.skills[skillnum]['spellup'] = True

  def updateduration(self, skillnum, duration):
    """
    update the duration on a spell
    """
    if duration > 0:
      self.skills[skillnum]['duration'] = time.mktime(time.localtime()) + duration
    else:
      self.skills[skillnum]['duration'] = 0

  def updatepercent(self, skillnum, percent):
    """
    update the percent on a spell
    """
    self.skills[skillnum]['percent'] = percent

  def getspellups(self):
    """
    return a list of spellup spells
    """
    sus = [x for x in self.skills.values() if x['spellup']]
    return sus

  def getrecovery(self, tsn):
    """
    get a skill by sn or name
    """
    return self.getitem('recovery', tsn)

  def addrecovery(self, args):
    """
    add a recovery
    """
    recnum = args['sn']
    name = args['name']
    if args['duration'] != 0:
      duration = time.mktime(time.localtime()) + args['duration']
    else:
      duration = 0

    if recnum not in self.recoveries:
      self.recoveries[recnum] = {}

    self.recoveries[recnum]['name'] = name
    self.recoveries[recnum]['duration'] = duration
    self.recoveries[recnum]['sn'] = recnum

    self.recoveriesnamelookup[name] = recnum

  def updaterecoveryduration(self, recnum, duration):
    """
    update a duration on a recovery
    """
    if duration > 0:
      self.recoveries[recnum]['duration'] = time.mktime(time.localtime()) + duration
    else:
      self.recoveries[recnum]['duration'] = 0

class SListCmd(object):
  """
  a class to manipulate containers
  """
  def __init__(self, plugin):
    """
    init the class
    """
    ## cmd = command to send to get data
    ## cmdregex = regex that matches command
    ## startregex = the line to match to start collecting data
    ## endregex = the line to match to end collecting data
    self.cid = "slist"
    self.cmd = "slist"
    self.cmdregex = r"^slist\s((?P<type>.*)\s)?noprompt$"
    self.startregex = r"\{spellheaders\s((?P<type>.*)\s)?noprompt\}"
    self.endregex = r"\{/recoveries\}"
    self.plugin = plugin
    self.api = self.plugin.api
    self.current = None

    self._dump_shallow_attrs = ['plugin', 'api']

    self.api('cmdq.addcmdtype')(self.cid, self.cmd, self.cmdregex,
                                beforef=self.databefore, afterf=self.dataafter)

    self.api('triggers.add')('cmd_%s_start' % self.cid,
                             self.startregex,
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

    self.api('triggers.add')('cmd_%s_end' % self.cid,
                             self.endregex,
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

    self.api('triggers.add')('cmd_%s_spellh_spellline' % self.cid,
                             r"^(?P<sn>\d+),(?P<name>.+),(?P<target>\d+)," \
                               r"(?P<duration>\d+),(?P<pct>\d+)," \
                               r"(?P<rcvy>-?\d+),(?P<type>\d+)$",
                             group='cmd_%s_spells' % self.cid, enabled=False, omit=True,
                             argtypes={'sn':int, 'target':int, 'duration':int,
                                       'pct':int, 'rcvy':int, 'type':int})

    self.api('triggers.add')('cmd_%s_recov_noprompt' % self.cid,
                             r"^\{recoveries\s((?P<type>.*)\s)?noprompt\}$",
                             group='cmd_%s' % self.cid, enabled=False, omit=True)

    self.api('triggers.add')('cmd_%s_spellh_recovline' % self.cid,
                             r"^(?P<sn>\d+),(?P<name>.+),(?P<duration>\d+)$",
                             group='cmd_%s_recoveries' % self.cid,
                             enabled=False, omit=True,
                             argtypes={'sn':int, 'duration':int})

  def databefore(self):
    """
    this will be called before the command
    """
    self.api('events.register')('trigger_cmd_%s_start' % self.cid, self.datastart)

    self.api('events.register')('trigger_cmd_%s_spellh_spellline' % self.cid,
                                self.spellline)
    self.api('events.register')('trigger_cmd_%s_recov_noprompt' % self.cid,
                                self.recovnoprompt)

    self.api('triggers.togglegroup')('cmd_%s' % self.cid, True)
    self.api('triggers.togglegroup')('cmd_%s_spells' % self.cid, True)

  def datastart(self, args):
    """
    found beginning of data for slist
    """
    self.api('send.msg')('CMD - %s: found start %s' % (self.cid, self.startregex))
    self.api('send.msg')('current type = %s' % args['type'])
    self.api('cmdq.cmdstart')(self.cid)
    self.current = args['type']
    # change the endregex to handle specific subcommands
    if self.current is None:
      # got "slist noprompt"
      # reset skills
      self.plugin.skills.reset()
      self.api('triggers.update')('cmd_%s_end' % self.cid, {'regex':r"\{/recoveries\}"})
    elif self.current == 'affected':
      # affected
      self.plugin.skills.resetaffected()
      self.api('triggers.update')('cmd_%s_end' % self.cid, {'regex':r"\{/recoveries\}"})
    else:
      # learned, spellup
      self.api('triggers.update')('cmd_%s_end' % self.cid, {'regex':r"\{/spellheaders\}"})

    self.api('events.register')('trigger_cmd_%s_end' % self.cid, self.dataend)

  def spellline(self, args):
    """
    parse a spell line
    """
    if self.current == 'affected':
      self.plugin.skills.updateduration(args['sn'], args['duration'])
    elif self.current == 'learned':
      self.plugin.skills.updatepercent(args['sn'], args['pct'])
    elif self.current == 'spellup':
      self.plugin.skills.flagspellup(args['sn'])
    else:
      self.plugin.skills.addskill(args)

  def recovnoprompt(self, args): # pylint: disable=unused-argument
    """
    change triggers when {recoveries noprompt} seen
    """
    self.api('triggers.togglegroup')('cmd_%s_spells' % self.cid, False)
    self.api('triggers.togglegroup')('cmd_%s_recoveries' % self.cid, True)

    self.api('events.unregister')('trigger_cmd_%s_spellh_spellline' % self.cid,
                                  self.spellline)
    self.api('events.unregister')('trigger_cmd_%s_recov_noprompt' % self.cid,
                                  self.recovnoprompt)

    self.api('events.register')('trigger_cmd_%s_spellh_recovline' % self.cid,
                                self.recovline)

  def recovline(self, args):
    """
    parse a recovery line
    """
    if self.current == 'affected':
      self.plugin.skills.updaterecoveryduration(args['sn'], args['duration'])
    elif self.current == 'learned':
      # should never get this
      self.api('send.error')('got learned in recoveries, should never happen')
    elif self.current == 'spellup':
      # should never get this
      self.api('send.error')('got spellup in recoveries, should never happen')
    else:
      self.plugin.skills.addrecovery(args)

  def dataend(self, args): #pylint: disable=unused-argument
    """
    found end of data for the slist command, clean up events and triggers
    """
    self.api('send.msg')('CMD - %s: found end %s' % (self.cid, self.endregex))

    self.api('events.unregister')('trigger_cmd_%s_start' % self.cid, self.datastart)
    self.api('events.unregister')('trigger_cmd_%s_end' % self.cid, self.dataend)

    if self.api('events.isregistered')('trigger_cmd_%s_spellh_spellline' % self.cid,
                                       self.spellline):
      self.api('events.unregister')('trigger_cmd_%s_spellh_spellline' % self.cid,
                                    self.spellline)
    if self.api('events.isregistered')('trigger_cmd_%s_recov_noprompt' % self.cid,
                                       self.recovnoprompt):
      self.api('events.unregister')('trigger_cmd_%s_recov_noprompt' % self.cid,
                                    self.recovnoprompt)
    if self.api('events.isregistered')('trigger_cmd_%s_spellh_recovline' % self.cid,
                                       self.recovline):
      self.api('events.unregister')('trigger_cmd_%s_spellh_recovline' % self.cid,
                                    self.recovline)

    self.api('triggers.togglegroup')('cmd_%s' % self.cid, False)
    self.api('triggers.togglegroup')('cmd_%s_spells' % self.cid, False)
    self.api('triggers.togglegroup')('cmd_%s_recoveries' % self.cid, False)

    self.api('cmdq.cmdfinish')(self.cid)

  def dataafter(self):
    """
    this will be called after the command has completed
    """
    if self.current == 'spellup' and not self.plugin.skills.isuptodatef:
      self.plugin.skills.setuptodate()
    self.current = None

class Plugin(AardwolfBasePlugin):
  """
  a plugin manage info about spells and skills
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.skills = None
    self.slistcmd = None

    self.api('dependency.add')('cmdq')

    self.api('api.add')('gets', self._api_getskill)
    self.api('api.add')('getr', self._api_getrecovery)
    self.api('api.add')('isspellup', self._api_isspellup)
    self.api('api.add')('getspellups', self._api_getspellups)
    self.api('api.add')('sendcmd', self._api_sendcmd)
    self.api('api.add')('isaffected', self._api_isaffected)
    self.api('api.add')('isblockedbyrecovery',
                        self._api_isblockedbyrecovery)
    self.api('api.add')('ispracticed', self._api_ispracticed)
    self.api('api.add')('canuse', self._api_canuse)
    self.api('api.add')('isuptodate', self._api_isuptodate)
    self.api('api.add')('isbad', self._api_isbad)

  def load(self):
    """
    load the plugins
    """
    AardwolfBasePlugin.load(self)

    self.skills = Skills(self)
    self.slistcmd = SListCmd(self)

    self.api('send.msg')('running load function of skills')

    parser = argp.ArgumentParser(add_help=False,
                                 description='refresh skills and spells')
    self.api('commands.add')('refresh', self.cmd_refresh,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='lookup skill or spell by name or sn')
    parser.add_argument('skill', help='the skill to lookup',
                        default='', nargs='?')
    self.api('commands.add')('lu', self.cmd_lu,
                             parser=parser)

    self.api('triggers.add')('affoff',
                             r"^\{affoff\}(?P<sn>\d+)$",
                             argtypes={'sn':int})
    self.api('triggers.add')('affon',
                             r"^\{affon\}(?P<sn>\d+),(?P<duration>\d+)$",
                             argtypes={'sn':int, 'duration':int})
    self.api('triggers.add')('recoff',
                             r"^\{recoff\}(?P<sn>\d+)$",
                             argtypes={'sn':int})
    self.api('triggers.add')('recon',
                             r"^\{recon\}(?P<sn>\d+),(?P<duration>\d+)$",
                             argtypes={'sn':int, 'duration':int})
    self.api('triggers.add')('skillgain',
                             r"^\{skillgain\}(?P<sn>\d+),(?P<percent>\d+)$",
                             argtypes={'sn':int, 'percent':int})
    self.api('triggers.add')('skillfail',
                             r"^\{sfail\}(?P<sn>\d+),(?P<target>\d+)," \
                               r"(?P<reason>\d+),(?P<recovery>-?\d+)$",
                             argtypes={'sn':int, 'target':int,
                                       'reason':int, 'recovery':int})

    self.api('events.register')('trigger_affoff', self.affoff)
    self.api('events.register')('trigger_affon', self.affon)
    self.api('events.register')('trigger_recoff', self.recoff)
    self.api('events.register')('trigger_recon', self.recon)
    self.api('events.register')('trigger_skillgain', self.skillgain)
    self.api('events.register')('trigger_skillfail', self.skillfail)

    self.api('events.register')('GMCP:char.status', self.checkskills)

    self.api('events.register')('aard_level_tier', self.cmd_refresh)
    self.api('events.register')('aard_level_remort', self.cmd_refresh)

    self.api('events.register')('muddisconnect', self.skillsdisconnect)

  def skillsdisconnect(self, args=None):
    """
    set the isuptodate flag to False and clear skills
    """
    self.skills.reset()

  def afterfirstactive(self, _=None):
    """
    do something on connect
    """
    AardwolfBasePlugin.afterfirstactive(self)
    self.checkskills()

  # check if the spells/skills list is up to date
  def _api_isuptodate(self):
    """
    return True if we have seen affected or all spells refresh
    """
    return self.skills.isuptodatef

  def cmd_lu(self, args):
    """
    cmd to lookup a spell
    """
    msg = []
    skill = self.api('skills.gets')(args['skill'])
    if skill:
      msg.append('%-8s : %s' % ('SN', skill['sn']))
      msg.append('%-8s : %s' % ('Name', skill['name']))
      msg.append('%-8s : %s' % ('Percent', skill['percent']))
      if skill['duration'] > 0:
        msg.append('%-8s : %s' % ('Duration',
                                  self.api('utils.timedeltatostring')(
                                      time.time(),
                                      skill['duration'])))
      msg.append('%-8s : %s' % ('Target', skill['target']))
      msg.append('%-8s : %s' % ('Spellup', skill['spellup']))
      msg.append('%-8s : %s' % ('Type', skill['type']))
      if skill['recovery']:
        recov = skill['recovery']
        if recov['duration'] > 0:
          duration = self.api('utils.timedeltatostring')(
              time.time(),
              recov['duration'])
          msg.append('%-8s : %s (%s)' % ('Recovery',
                                         recov['name'], duration))
        else:
          msg.append('%-8s : %s' % ('Recovery', recov['name']))
    else:
      msg.append('Could not find: %s' % args['skill'])

    return True, msg

  def cmd_refresh(self, args=None): # pylint: disable=unused-argument
    """
    refresh spells and skills
    """
    self.skills.refresh()
    msg = ['Refreshing spells and skills']
    return True, msg

  def checkskills(self, args=None): # pylint: disable=unused-argument
    """
    check to see if we have spells
    """
    state = self.api('GMCP.getv')('char.status.state')
    if state == 3 and self.api('connect.firstactive')():
      self.api('send.msg')('refreshing skills')
      if self.api('events.isregistered')('GMCP:char.status', self.checkskills):
        self.api('events.unregister')('GMCP:char.status', self.checkskills)
      self.api('A102.toggle')('SPELLUPTAGS', True)
      self.api('A102.toggle')('SKILLGAINTAGS', True)
      self.api('A102.toggle')('QUIETTAGS', False)
      if self.skills.count() == 0 or not self.api('skills.isuptodate'):
        self.cmd_refresh()

  def resetskills(self):
    """
    reset the skills
    """
    self.skills.reset()

  def skillgain(self, args):
    """
    handle a skillgain tag
    """
    self.skills.updatepercent(args['sn'], args['percent'])
    self.api('events.eraise')('aard_skill_gain',
                              {'sn':args['sn'], 'percent':args['percent']})

  def skillfail(self, args):
    """
    raise an event when we fail a skill/spell
    """
    skillnum = args['sn']
    skill = self.api('skills.gets')(skillnum)
    reason = FAILREASON[args['reason']]
    ndict = {'sn':skillnum, 'reason':reason,
             'target':FAILTARG[args['target']],
             'recovery':args['recovery']}
    if reason == 'dontknow' and skill['percent'] > 0:
      self.api('send.msg')('refreshing spells because of an unlearned spell')
      self.cmd_refresh()
    self.api('send.msg')('raising skillfail: %s' % ndict)
    self.api('events.eraise')('skill_fail_%s' % skillnum, ndict)
    self.api('events.eraise')('skill_fail', ndict)

  def affoff(self, args):
    """
    set the affect to off for spell that wears off
    """
    skillnum = args['sn']
    self.skills.updateduration(skillnum, 0)
    skill = self.api('skills.gets')(skillnum)
    if skill:
      self.api('events.eraise')('aard_skill_affoff_%s' % skillnum,
                                {'sn':skillnum})
      self.api('events.eraise')('aard_skill_affoff', {'sn':skillnum})

  def affon(self, args):
    """
    set the spell's duration when we see an affon
    """
    skillnum = args['sn']
    duration = args['duration']
    self.skills.updateduration(skillnum, duration)
    skill = self.api('skills.gets')(skillnum)
    if skill:
      self.api('events.eraise')('aard_skill_affon_%s' % skillnum,
                                {'sn':skillnum,
                                 'duration':skill['duration']})
      self.api('events.eraise')('aard_skill_affon',
                                {'sn':skillnum,
                                 'duration':skill['duration']})

  def recoff(self, args):
    """
    set the affect to off for spell that wears off
    """
    skillnum = args['sn']
    self.skills.updaterecoveryduration(skillnum, 0)
    recovery = self.api('skills.getr')(skillnum)
    if recovery:
      self.api('events.eraise')('aard_skill_recoff_%s' % skillnum,
                                {'sn':skillnum})
      self.api('events.eraise')('aard_skill_recoff', {'sn':skillnum})

  def recon(self, args):
    """
    set the spell's duration when we see an affon
    """
    skillnum = args['sn']
    duration = args['duration']
    self.skills.updaterecoveryduration(skillnum, duration)
    recovery = self.api('skills.getr')(skillnum)
    if recovery:
      self.api('events.eraise')('aard_skill_recon_%s' % skillnum,
                                {'sn':skillnum,
                                 'duration':recovery['duration']})
      self.api('events.eraise')('aard_skill_recon',
                                {'sn':skillnum,
                                 'duration':recovery['duration']})

  # get a spell/skill by number or name
  def _api_getskill(self, tsn):
    """
    get a skill
    """
    #self.api('send.msg')('looking for %s' % tsn)
    return self.skills.getskill(tsn)

  # get a recovery by number or name
  def _api_getrecovery(self, tsn):
    """
    get a skill
    """
    #self.api('send.msg')('looking for %s' % tsn)
    return self.skills.getrecovery(tsn)

  # send the command to active a skill/spell
  def _api_sendcmd(self, skillnum):
    """
    send the command to activate a skill/spell
    """
    skill = self.api('skills.gets')(skillnum)
    if skill:
      if skill['type'] == 'spell':
        self.api('send.msg')('casting %s' % skill['name'])
        self.api('send.execute')('cast %s' % skill['sn'])
      else:
        name = skill['name'].split()[0]
        self.api('send.msg')('sending skill %s' % skill['name'])
        self.api('send.execute')(name)

  # check if a skill/spell can be used
  def _api_canuse(self, skillnum):
    """
    return True if the spell can be used
    """
    if self.api('skills.isaffected')(skillnum) \
        or self.api('skills.isblockedbyrecovery')(skillnum) \
        or not self.api('skills.ispracticed')(skillnum):
      return False

    return True

  # check if a skill/spell is a spellup
  def _api_isspellup(self, skillnum):
    """
    return True for a spellup, else return False
    """
    skill = self.api('skills.gets')(skillnum)
    if skill:
      return skill['spellup']

    return False

  # check if a skill/spell is bad
  def _api_isbad(self, skillnum):
    """
    return True for a bad spell, False for a good spell
    """
    skill = self.api('skill.gets')(skillnum)
    if (skill['target'] == 'attack' or skill['target'] == 'special') and \
          not skill['spellup']:
      return True

    return False

  # check if a skill/spell is active
  def _api_isaffected(self, skillnum):
    """
    return True for a spellup, else return False
    """
    skill = self.api('skills.gets')(skillnum)
    if skill:
      return skill['duration'] > 0

    return False

  # check if a skill/spell is blocked by a recovery
  def _api_isblockedbyrecovery(self, skillnum):
    """
    check to see if a spell/skill is blocked by a recovery
    """
    skill = self.api('skills.gets')(skillnum)
    if skill:
      if 'recovery' in skill and skill['recovery'] and \
          skill['recovery']['duration'] > 0:
        return True

    return False

  # check if a skill/spell is practiced
  def _api_ispracticed(self, skillnum):
    """
    is the spell learned
    """
    skill = self.api('skills.gets')(skillnum)
    if skill:
      if skill['percent'] > 10:
        return True

    return False

  # get the list of spellup spells/skills
  def _api_getspellups(self):
    """
    return a list of spellup spells
    """
    return self.skills.getspellups()
