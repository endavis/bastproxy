"""
This plugin highlights cp/gq/quest mobs in scan

#TODO: intelligently figure out which spells add which flags
"""
import copy
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Affect Flags'
SNAME = 'aflags'
PURPOSE = 'keep up with affect flags'
AUTHOR = 'Bast'
VERSION = 1



class AFlags(object):
  """
  class for aflags
  """
  def __init__(self, plugin):
    """
    initialize the class
    """
    self.plugin = plugin
    self.currentflags = {}
    self.snapshots = {}
    self._dump_shallow_attrs = ['plugin', 'api']

  def checkflag(self, flag):
    """
    check to see if affected by a flag
    """
    flag = flag.lower()
    if flag and flag in self.currentflags:
      return True

    return False

  def count(self):
    """
    return # of flags
    """
    return len(self.currentflags)

  def getaffects(self):
    """
    return a list of affects
    """
    return self.currentflags.keys()

  def addflag(self, flag):
    """
    add a flag
    """
    self.currentflags[flag] = True

  def removeflag(self, flag):
    """
    remove a flag
    """
    self.currentflags[flag] = False

  def snapshot(self, name):
    """
    create a snapshot of the current affects
    """
    self.snapshots[name] = copy.deepcopy(self.currentflags)


class AFlagsCmd(object):
  """
  Class for command aflags
  """
  def __init__(self, plugin):
    """
    init the class
    """
    ## cmd = command to send to get data
    ## cmdregex = regex that matches command
    ## startregex = the line to match to start collecting data
    ## endregex = the line to match to end collecting data
    self.cid = "aflags"
    self.cmd = "aflags"
    self.cmdregex = "^aflags$"
    self.startregex = "^Affect Flags: (?P<flags>.*)$"
    self.plugin = plugin
    self.api = self.plugin.api

    self._dump_shallow_attrs = ['plugin', 'api']

    self.api('cmdq.addcmdtype')(self.cid, self.cmd, self.cmdregex,
                                beforef=self.aflagsbefore, afterf=self.aflagsafter)

    self.api('triggers.add')('aflagsstart',
                             self.startregex,
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

  def affoff(self, args=None):
    """
    modify flags based on what affect wore off
    """
    pass

  def affon(self, args=None):
    """
    modify flags based on what affect was added
    """
    pass

  def recoff(self, args=None):
    """
    modfiy flags based on what recovery wore off
    """
    pass

  def recon(self, args=None):
    """
    modify flags based on what recovery was added
    """
    pass

  def aflagsbefore(self):
    """
    stuff to do before doing aflags command
    """
    self.api('triggers.togglegroup')('cmd_%s' % self.cmd, True)
    self.api('events.register')('trigger_aflagsstart', self.aflagsfirstline)
    self.plugin.aflags.snapshot('Before')

  def aflagsfirstline(self, args):
    """
    process the first aflags line
    """
    self.api('cmdq.cmdstart')(self.cid)
    allflags = args['flags'].split(',')
    for i in allflags:
      i = i.lower().strip()
      if i:
        self.plugin.aflags.addflag(i)
    self.api('events.register')('trigger_beall', self.aflagsotherline)
    self.api('events.register')('trigger_emptyline', self.aflagsend)
    args['omit'] = True
    return args

  def aflagsotherline(self, args):
    """
    process other aflags lines
    """
    line = args['line']
    line = line.lstrip()
    allflags = line.split(',')
    for i in allflags:
      i = i.lower().strip()
      if i:
        self.plugin.aflags.addflag(i)

    args['omit'] = True

    return args

  def aflagsend(self, _=None):
    """
    finished aflags when seeing an emptyline, mainly clean up triggers
    and events
    """
    self.api('events.unregister')('trigger_beall', self.aflagsotherline)
    self.api('events.unregister')('trigger_emptyline', self.aflagsend)

    self.api('triggers.togglegroup')('cmd_%s' % self.cmd, False)

    self.api('cmdq.cmdfinish')('aflags')

  def aflagsafter(self):
    """
    stuff to do after doing aflags command
    """
    self.plugin.aflags.snapshot('Before')
    removed = set(self.plugin.aflags.snapshots['Before']) - \
                set(self.plugin.aflags.currentflags)
    added = set(self.plugin.aflags.currentflags) - \
               set(self.plugin.aflags.snapshots['Before'])
    self.plugin.api('events.eraise')('affect_diff',
                                     args={'added':added,
                                           'removed':removed})

class Plugin(AardwolfBasePlugin):
  """
  a plugin to highlight mobs in the scan output
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency.add')('aardwolf.skills')
    self.api('dependency.add')('core.cmdq')

    self.api('api.add')('check', self.api_checkflag)

    self.first_active_priority = 1
    self.cmdaflags = None
    self.aflags = None
    self.currentflag = None
    self.flagstable = {}

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.cmdaflags = AFlagsCmd(self)
    self.aflags = AFlags(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='refresh affect flags')
    self.api('commands.add')('refresh', self.cmd_refresh,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='check to see if affected by a flag')
    parser.add_argument('flag', help='the flag to check',
                        default='', nargs='?')
    self.api('commands.add')('check', self.cmd_check,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list affect flags')
    self.api('commands.add')('list', self.cmd_list,
                             parser=parser)

    self.api('events.register')('aard_skill_affoff',
                                self.flagschanged, prio=10)
    self.api('events.register')('aard_skill_affon',
                                self.flagschanged, prio=10)
    self.api('events.register')('aard_skill_recoff',
                                self.refreshflags, prio=99)
    self.api('events.register')('aard_skill_recon',
                                self.refreshflags, prio=99)
    self.api('events.register')('skills_affected_update',
                                self.refreshflags, prio=99)
    self.api('events.register')('skills_uptodate',
                                self.refreshflags, prio=99)
    self.api('events.register')('affect_diff',
                                self.flagsdiff)

  def after_first_active(self, _=None):
    """
    do something on connect
    """
    AardwolfBasePlugin.after_first_active(self)
    self.refreshflags()

  # check if affected by a flag
  def api_checkflag(self, flag):
    """
    check if affected by a flag
    """
    return self.aflags.checkflag(flag)

  def flagschanged(self, args=None):
    """
    do something when a flag changes
    """
    flag = args['sn']
    if flag not in self.flagstable and not self.currentflag:
      self.currentflag = flag
    elif self.currentflag:
      self.api('send.msg')('got multiple affects change before getting flags')
      self.currentflag = None
    else:
      self.api('send.msg')('%s : flags are %s' % (flag, self.flagstable[flag]))

    self.refreshflags()

  def flagsdiff(self, args):
    """
    find out which flags were changed and associate them with an sn
    """
    if self.currentflag:
      if args['added']:
        self.api('send.msg')('diff : flags %s were associated with sn %s' % \
                    (args['added'], self.currentflag))
        self.flagstable[self.currentflag] = args['added']
      if args['removed']:
        self.api('send.msg')('diff : flags %s were associated with sn %s' % \
                    (args['removed'], self.currentflag))
        self.flagstable[self.currentflag] = args['removed']

      self.currentflag = None

  def refreshflags(self, _=None):
    """
    start to refresh flags
    """
    self.api('cmdq.addtoqueue')('aflags')

  def cmd_refresh(self, _=None):
    """
    refresh aflags
    """
    self.refreshflags()

    return True, ['Refreshing Affect Flags']

  def cmd_check(self, args):
    """
    check for an affect
    """
    if not args['flag']:
      return True, ['Please specifiy a flag']

    if self.api_checkflag(args['flag']):
      return True, ['Affect %s is active' % args['flag']]

    return True, ['Affect %s is inactive' % args['flag']]

  def cmd_list(self, _=None):
    """
    list all affects
    """
    if self.aflags.count() == 0:
      return True, ["There are no affects active"]

    msg = ["The following %s affects are active" % self.aflags.count()]
    for i in sorted(self.aflags.getaffects()):
      msg.append('  ' + i)

    return True, msg
