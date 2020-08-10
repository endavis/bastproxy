"""
This plugin handles cp events for Aardwolf
"""
import time
import os
import copy
import re
import libs.argp as argp
from libs.persistentdict import PersistentDict
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf CP Events'
SNAME = 'cp'
PURPOSE = 'Events for Aardwolf CPs'
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
    self.savecpfile = os.path.join(self.save_directory, 'cp.txt')
    self.cpinfo = PersistentDict(self.savecpfile, 'c')
    self.mobsleft = []
    self.cpinfotimer = {}
    self.nextdeath = False

    self.api('dependency.add')('core.cmdq')
    self.api('dependency.add')('aardwolf.aconf')

    self.api('api.add')('oncp', self.api_oncp)
    self.api('api.add')('mobsleft', self.api_cpmobsleft)

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('cmdq.addcmdtype')('cpcheck', 'campaign check', "^campaign check$",
                                beforef=self.cpcheckbefore, afterf=self.cpcheckafter)

    parser = argp.ArgumentParser(add_help=False,
                                 description='show cp info')
    self.api('commands.add')('show', self.cmd_show,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='refresh cp info')
    self.api('commands.add')('refresh', self.cmd_refresh,
                             parser=parser)

    self.api('watch.add')('cp_check',
                          '^(cp|campa|campai|campaig|campaign) (c|ch|che|chec|check)$')

    self.api('triggers.add')('cpnew',
                             "^Commander Barcett tells you " \
                               "'Type 'campaign info' to see what you must kill.'$")
    self.api('triggers.add')('cpnone',
                             "^You are not currently on a campaign.$",
                             enabled=False, group='cpcheck', omit=True)
    self.api('triggers.add')('cptime',
                             "^You have (?P<time>.*) to finish this campaign.$",
                             enabled=False, group='cpcheck', omit=True)
    self.api('triggers.add')('cpmob',
                             r"^You still have to kill \* (?P<mob>.*) " \
                               r"\((?P<location>.*?)(?P<dead> - Dead|)\)$",
                             enabled=False, group='cpcheck', omit=True)
    self.api('triggers.add')('cpscramble',
                             "Note: One or more target names in this " \
                               "campaign might be slightly scrambled.$",
                             enabled=False, group='cpcheck', omit=True)
    self.api('triggers.add')('cpneedtolevel',
                             "^You will have to level before you" \
                               " can go on another campaign.$",
                             enabled=False,
                             group='cpin')
    self.api('triggers.add')('cpcantake',
                             "^You may take a campaign at this level.$",
                             enabled=False,
                             group='cpin')
    self.api('triggers.add')('cpshnext',
                             "^You cannot take another campaign for (?P<time>.*).$",
                             enabled=False,
                             group='cpin')
    self.api('triggers.add')('cpmobdead',
                             "^Congratulations, that was one of your CAMPAIGN mobs!$",
                             enabled=False,
                             group='cpin')
    self.api('triggers.add')('cpcomplete',
                             "^CONGRATULATIONS! You have completed your campaign.$",
                             enabled=False,
                             group='cpin')
    self.api('triggers.add')('cpclear',
                             "^Campaign cleared.$",
                             enabled=False,
                             group='cpin')
    self.api('triggers.add')('cpreward',
                             r"^\s*Reward of (?P<amount>\d+) (?P<type>.+) .+ added.$",
                             enabled=False,
                             group='cprew',
                             argtypes={'amount':int})
    self.api('triggers.add')('cpcompdone',
                             "^--------------------------" \
                               "------------------------------------$",
                             enabled=False,
                             group='cpdone')

    self.api('events.register')('trigger_cpnew', self._cpnew)
    self.api('events.register')('trigger_cpnone', self._cpnone)
    self.api('events.register')('trigger_cptime', self._cptime)
    #self.api('events.register')('watch_cp_check', self._cpcheckcmd)
    self.api('events.register')('trigger_cpmob', self._cpmob)
    self.api('events.register')('trigger_cpneedtolevel',
                                self._cpneedtolevel)
    self.api('events.register')('trigger_cpcantake', self._cpcantake)
    self.api('events.register')('trigger_cpshnext', self._cpshnext)
    self.api('events.register')('trigger_cpmobdead', self._cpmobdead)
    self.api('events.register')('trigger_cpcomplete', self._cpcomplete)
    self.api('events.register')('trigger_cpclear', self._cpclear)
    self.api('events.register')('trigger_cpreward', self._cpreward)
    self.api('events.register')('trigger_cpcompdone', self._cpcompdone)

#    self.api('events.register')('GMCP:config', self.ongmcpconfig)
#    self.api('events.register')('GMCP:char.status', self.ongmcpcharstatus)

    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

  def api_oncp(self):
    """
    return if we are on a cp
    """
    return self.cpinfo['oncp']

  def api_cpmobsleft(self):
    """
    return the list of cp mobs left
    """
    return copy.copy(self.mobsleft)

  def cmd_show(self, _=None):
    """
    show the cp mobs
    """
    msg = []
    if self.cpinfo['oncp']:
      msg.append('Mobs left:')
      msg.append('%-40s %s' % ('Mob Name', 'Area/Room'))
      msg.append('@G' + '-' * 60)
      for i in self.mobsleft:
        color = '@w'
        if i['mobdead']:
          color = '@R'
        msg.append('%s%-40s %s' % (color, i['name'], i['location']))
    else:
      msg.append('You are not on a cp')

    return True, msg

  def cmd_refresh(self, _=None):
    """
    cmd to refresh cp info
    """
    msg = []
    if self.cpinfo['oncp']:
      msg.append('Refreshing cp mobs')
      self.api('cmdq.addtoqueue')('cpcheck', '')
    else:
      msg.append('You are not on a cp')

    return True, msg

  def cpcheckbefore(self):
    """
    function to run before send the command
    """
    self.mobsleft = []
    self.cpinfotimer = {}
    self.api('triggers.togglegroup')('cpcheck', True)
    self.api('cmdq.cmdstart')('cpcheck')

  def cpcheckafter(self):
    """
    function to run after the command is finished
    """
    self.api('triggers.togglegroup')("cpin", True)
    self.api('triggers.togglegroup')('cpcheck', False)

  def after_first_active(self, _=None):
    """
    do something on connect
    """
    AardwolfBasePlugin.after_first_active(self)
    self.api('cmdq.addtoqueue')('cpcheck', '')

  def _cpreset(self):
    """
    reset the cp
    """
    self.cpinfo.clear()
    self.cpinfo['mobs'] = {}
    self.cpinfo['trains'] = 0
    self.cpinfo['pracs'] = 0
    self.cpinfo['gold'] = 0
    self.cpinfo['tp'] = 0
    self.cpinfo['qp'] = 0
    self.cpinfo['bonusqp'] = 0
    self.cpinfo['failed'] = 0
    self.cpinfo['level'] = self.api('aardu.getactuallevel')(
        self.api('GMCP.getv')('char.status.level'))
    self.cpinfo['starttime'] = time.time()
    self.cpinfo['finishtime'] = 0
    self.cpinfo['oncp'] = True
    self.cpinfo['cantake'] = False
    self.cpinfo['shtime'] = None
    self.savestate()

  def _cpnew(self, args=None):
    """
    handle a new cp
    """
    self.api('send.msg')('cpnew: %s' % args)
    self._cpreset()
    self.api('cmdq.addtoqueue')('cpcheck', '')

  def _cpnone(self, _=None):
    """
    handle a none cp
    """
    self.api('send.msg')('cpnone')
    self.cpinfo['oncp'] = False
    self.savestate()
    self.api('triggers.togglegroup')('cpcheck', False)
    self.api('triggers.togglegroup')('cpin', False)
    self.api('triggers.togglegroup')('cprew', False)
    self.api('triggers.togglegroup')('cpdone', False)
    self.cpinfotimer = {}
    self.api('cmdq.cmdfinish')('cpcheck')

  def _cptime(self, _=None):
    """
    handle cp time
    """
    self.api('send.msg')('handling cp time')
    self.api('send.msg')('%s' % self.cpinfo)
    if not self.cpinfo['mobs']:
      self.api('send.msg')('copying mobsleft')
      self.cpinfo['mobs'] = self.mobsleft[:]
      self.api('events.eraise')('aard_cp_mobsorig',
                                copy.deepcopy({'mobsleft':self.mobsleft}))
      self.savestate()

    self.api('send.msg')('raising aard_cp_mobsleft %s' % self.mobsleft)
    self.api('events.eraise')('aard_cp_mobsleft',
                              copy.deepcopy({'mobsleft':self.mobsleft}))

    self.api('cmdq.cmdfinish')('cpcheck')

  def _cpneedtolevel(self, _=None):
    """
    handle cpneedtolevel
    """
    self.cpinfo['cantake'] = False
    self.savestate()

  def _cpcantake(self, _=None):
    """
    handle cpcantake
    """
    self.cpinfo['cantake'] = True
    self.savestate()

  def _cpshnext(self, args=None):
    """
    handle cpshnext
    """
    self.cpinfo['shtime'] = args['time']
    self.savestate()

  def _cpmob(self, args=None):
    """
    handle cpmob
    """
    name = args['mob']
    mobdead = self.api('utils.verify')(args['dead'], bool)
    location = args['location']

    if not name or not location:
      self.api('send.msg')("error parsing line: %s" % args['line'])
    else:
      self.mobsleft.append({'name':name,
                            'nocolorname':self.api('colors.stripansi')(name),
                            'location':location, 'mobdead':mobdead})

  def _cpmobdead(self, _=None):
    """
    handle cpmobdead
    """
    self.api('events.register')('aard_mobkill', self._mobkillevent)
    #self.api('send.execute')("cp check")

  def _cpcomplete(self, _=None):
    """
    handle cpcomplete
    """
    self.api('triggers.togglegroup')('cprew', True)
    self.cpinfo['finishtime'] = time.time()
    self.cpinfo['oncp'] = False
    self.savestate()

  def _cpreward(self, args=None):
    """
    handle cpreward
    """
    rtype = args['type']
    ramount = int(args['amount'])
    rewardt = self.api('aardu.rewardtable')()
    self.cpinfo[rewardt[rtype]] = ramount
    self.savestate()
    self.api('triggers.togglegroup')('cpdone', True)

  def _cpcompdone(self, _=None):
    """
    handle cpcompdone
    """
    self.api('events.register')('trigger_all', self._triggerall)

  def _triggerall(self, args=None):
    """
    check to see if we have the bonus qp message
    """
    if 'first campaign completed today' in args['line']:
      mat = re.match(r'^You receive (?P<bonus>\d*) quest points bonus ' \
                        r'for your first campaign completed today.$',
                     args['line'])
      self.cpinfo['bonusqp'] = int(mat.groupdict()['bonus'])
      self.api('events.unregister')('trigger_all', self._triggerall)
      self.api('events.eraise')('aard_cp_comp', copy.deepcopy(self.cpinfo))
    elif re.match(r"^You have completed (\d*) campaigns today.$", args['line']):
      self.api('events.unregister')('trigger_all', self._triggerall)
      self.api('events.eraise')('aard_cp_comp', copy.deepcopy(self.cpinfo))

  def _cpclear(self, _=None):
    """
    handle cpclear
    """
    self.cpinfo['failed'] = 1
    self.api('events.eraise')('aard_cp_failed', copy.deepcopy(self.cpinfo))
    self._cpnone()

  def _cpcheckcmd(self, args=None):
    """
    handle when we get a cp check
    """
    self.mobsleft = []
    self.cpinfotimer = {}
    self.api('triggers.togglegroup')('cpcheck', True)
    return args

  def _mobkillevent(self, args):
    """
    this will be registered to the mobkill hook
    """
    self.api('send.msg')('checking kill %s' % args['name'])
    self.api('events.unregister')('aard_mobkill', self._mobkillevent)

    found = False
    removeitem = None
    for i in range(len(self.mobsleft)):
      tmob = self.mobsleft[i]
      if tmob['name'] == args['name']:
        self.api('send.msg')('found %s' % tmob['name'])
        found = True
        removeitem = i

    if removeitem:
      del self.mobsleft[removeitem]

    if found:
      self.api('events.eraise')('aard_cp_mobsleft',
                                copy.deepcopy({'mobsleft':self.mobsleft}))
    else:
      self.api('send.msg')("BP CP: could not find mob: %s" % args['name'])
      self.api('cmdq.addtoqueue')('cpcheck', '')

  def _savestate(self, _=None):
    """
    save states
    """
    self.cpinfo.sync()
