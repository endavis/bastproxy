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

    self.api('dependency:add')('core.cmdq')
    self.api('dependency:add')('aardwolf.aconf')

    self.api('libs.api:add')('oncp', self.api_oncp)
    self.api('libs.api:add')('mobsleft', self.api_cpmobsleft)

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('core.cmdq:commandtype:add')('cpcheck', 'campaign check', "^campaign check$",
                                          beforef=self.cpcheckbefore, afterf=self.cpcheckafter)

    self.api('setting:add')('campaignxp', -1, int,
                            "set noexp if a campaign hasn't been taken and tnl is less " \
                            "than this variable, use '-1' (no quotes) disable")

    parser = argp.ArgumentParser(add_help=False,
                                 description='show cp info')
    self.api('core.commands:command:add')('show', self.cmd_show,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='refresh cp info')
    self.api('core.commands:command:add')('refresh', self.cmd_refresh,
                                          parser=parser)

    self.api('core.watch:watch:add')('cp_check',
                                     '^(cp|campa|campai|campaig|campaign) (c|ch|che|chec|check)$')

    self.api('core.triggers:trigger:add')('cpnew',
                                          "^Commander Barcett tells you " \
                                            "'Type 'campaign info' to see what you must kill.'$")
    self.api('core.triggers:trigger:add')('cpnone',
                                          "^You are not currently on a campaign.$",
                                          enabled=False, group='cpcheck', omit=True)
    self.api('core.triggers:trigger:add')('cptime',
                                          "^You have (?P<time>.*) to finish this campaign.$",
                                          enabled=False, group='cpcheck', omit=True)
    self.api('core.triggers:trigger:add')('cpmob',
                                          r"^You still have to kill \* (?P<mob>.*) " \
                                            r"\((?P<location>.*?)(?P<dead> - Dead|)\)$",
                                          enabled=False, group='cpcheck', omit=True)
    self.api('core.triggers:trigger:add')('cpscramble',
                                          "Note: One or more target names in this " \
                                            "campaign might be slightly scrambled.$",
                                          enabled=False, group='cpcheck', omit=True)
    self.api('core.triggers:trigger:add')('cpneedtolevel',
                                          "^You will have to level before you" \
                                            " can go on another campaign.$",
                                          enabled=False,
                                          group='cpin')
    self.api('core.triggers:trigger:add')('cpcantake',
                                          "^You may take a campaign at this level.$",
                                          enabled=False,
                                          group='cpin')
    self.api('core.triggers:trigger:add')('cpshnext',
                                          "^You cannot take another campaign for (?P<time>.*).$",
                                          enabled=False,
                                          group='cpin')
    self.api('core.triggers:trigger:add')('cpmobdead',
                                          "^Congratulations, that was one of your CAMPAIGN mobs!$",
                                          enabled=False,
                                          group='cpin')
    self.api('core.triggers:trigger:add')('cpcomplete',
                                          "^CONGRATULATIONS! You have completed your campaign.$",
                                          enabled=False,
                                          group='cpin')
    self.api('core.triggers:trigger:add')('cpclear',
                                          "^Campaign cleared.$",
                                          enabled=False,
                                          group='cpin')
    self.api('core.triggers:trigger:add')('cpreward',
                                          r"^\s*Reward of (?P<amount>\d+) (?P<type>.+) .+ added.$",
                                          enabled=False,
                                          group='cprew',
                                          argtypes={'amount':int})
    self.api('core.triggers:trigger:add')('cpcompdone',
                                          "^--------------------------" \
                                            "------------------------------------$",
                                          enabled=False,
                                          group='cpdone')

    self.api('core.events:register:to:event')('trigger_cpnew', self._cpnew)
    self.api('core.events:register:to:event')('trigger_cpnone', self._cpnone)
    self.api('core.events:register:to:event')('trigger_cptime', self._cptime)
    #self.api('core.events:register:to:event')('watch_cp_check', self._cpcheckcmd)
    self.api('core.events:register:to:event')('trigger_cpmob', self._cpmob)
    self.api('core.events:register:to:event')('trigger_cpneedtolevel',
                                              self._cpneedtolevel)
    self.api('core.events:register:to:event')('trigger_cpcantake', self._cpcantake)
    self.api('core.events:register:to:event')('trigger_cpshnext', self._cpshnext)
    self.api('core.events:register:to:event')('trigger_cpmobdead', self._cpmobdead)
    self.api('core.events:register:to:event')('trigger_cpcomplete', self._cpcomplete)
    self.api('core.events:register:to:event')('trigger_cpclear', self._cpclear)
    self.api('core.events:register:to:event')('trigger_cpreward', self._cpreward)
    self.api('core.events:register:to:event')('trigger_cpcompdone', self._cpcompdone)

#    self.api('core.events:register:to:event')('GMCP:config', self.ongmcpconfig)
#    self.api('core.events:register:to:event')('GMCP:char.status', self.ongmcpcharstatus)

    self.api('core.events:register:to:event')('ev_{0.plugin_id}_savestate'.format(self), self._savestate)

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
      self.api('core.cmdq:queue:add:command')('cpcheck', '')
    else:
      msg.append('You are not on a cp')

    return True, msg

  def cpcheckbefore(self):
    """
    function to run before send the command
    """
    self.mobsleft = []
    self.cpinfotimer = {}
    self.api('core.triggers:group:toggle:enable')('cpcheck', True)
    self.api('core.cmdq:command:start')('cpcheck')

  def cpcheckafter(self):
    """
    function to run after the command is finished
    """
    self.api('core.triggers:group:toggle:enable')("cpin", True)
    self.api('core.triggers:group:toggle:enable')('cpcheck', False)

  def after_first_active(self, _=None):
    """
    do something on connect
    """
    AardwolfBasePlugin.after_first_active(self)
    self.api('core.cmdq:queue:add:command')('cpcheck', '')
    self.api('net.GMCP:mud:send')('config noexp')

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
        self.api('net.GMCP:value:get')('char.status.level'))
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
    self.api('libs.io:send:msg')('cpnew: %s' % args)
    self._cpreset()
    self.api('core.cmdq:queue:add:command')('cpcheck', '')

  def _cpnone(self, _=None):
    """
    handle a none cp
    """
    self.api('libs.io:send:msg')('cpnone')
    self.cpinfo['oncp'] = False
    self.savestate()
    self.api('core.triggers:group:toggle:enable')('cpcheck', False)
    self.api('core.triggers:group:toggle:enable')('cpin', False)
    self.api('core.triggers:group:toggle:enable')('cprew', False)
    self.api('core.triggers:group:toggle:enable')('cpdone', False)
    self.cpinfotimer = {}
    self.api('core.cmdq:command:finish')('cpcheck')

  def _cptime(self, _=None):
    """
    handle cp time
    """
    self.api('libs.io:send:msg')('handling cp time')
    self.api('libs.io:send:msg')('%s' % self.cpinfo)
    if not self.cpinfo['mobs']:
      self.api('libs.io:send:msg')('copying mobsleft')
      self.cpinfo['mobs'] = self.mobsleft[:]
      self.api('core.events:raise:event')('aard_cp_mobsorig',
                                          copy.deepcopy({'mobsleft':self.mobsleft}))
      self.savestate()

    self.api('libs.io:send:msg')('raising aard_cp_mobsleft %s' % self.mobsleft)
    self.api('core.events:raise:event')('aard_cp_mobsleft',
                                        copy.deepcopy({'mobsleft':self.mobsleft}))

    self.api('core.cmdq:command:finish')('cpcheck')

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
    mobdead = self.api('core.utils:verify:value')(args['dead'], bool)
    location = args['location']

    if not name or not location:
      self.api('libs.io:send:msg')("error parsing line: %s" % args['line'])
    else:
      self.mobsleft.append({'name':name,
                            'nocolorname':self.api('core.colors:ansicode:strip')(name),
                            'location':location, 'mobdead':mobdead})

  def _cpmobdead(self, _=None):
    """
    handle cpmobdead
    """
    self.api('core.events:register:to:event')('aard_mobkill', self._mobkillevent)
    #self.api('libs.io:send:execute')("cp check")

  def _cpcomplete(self, _=None):
    """
    handle cpcomplete
    """
    self.api('core.triggers:group:toggle:enable')('cprew', True)
    self.cpinfo['finishtime'] = time.time()
    self.cpinfo['oncp'] = False
    self.savestate()

  def _cpreward(self, args=None):
    """
    handle cpreward
    """
    rtype = args['type']
    ramount = int(args['amount'])
    rewardt = self.api('aardwolf.aardu:rewardtable')()
    self.cpinfo[rewardt[rtype]] = ramount
    self.savestate()
    self.api('core.triggers:group:toggle:enable')('cpdone', True)

  def _cpcompdone(self, _=None):
    """
    handle cpcompdone
    """
    self.api('core.events:register:to:event')('trigger_all', self._triggerall)

  def _triggerall(self, args=None):
    """
    check to see if we have the bonus qp message
    """
    if 'first campaign completed today' in args['line']:
      mat = re.match(r'^You receive (?P<bonus>\d*) quest points bonus ' \
                        r'for your first campaign completed today.$',
                     args['line'])
      self.cpinfo['bonusqp'] = int(mat.groupdict()['bonus'])
      self.api('core.events:unregister:from:event')('trigger_all', self._triggerall)
      self.api('core.events:raise:event')('aard_cp_comp', copy.deepcopy(self.cpinfo))
    elif re.match(r"^You have completed (\d*) campaigns today.$", args['line']):
      self.api('core.events:unregister:from:event')('trigger_all', self._triggerall)
      self.api('core.events:raise:event')('aard_cp_comp', copy.deepcopy(self.cpinfo))

  def _cpclear(self, _=None):
    """
    handle cpclear
    """
    self.cpinfo['failed'] = 1
    self.api('core.events:raise:event')('aard_cp_failed', copy.deepcopy(self.cpinfo))
    self._cpnone()

  def _cpcheckcmd(self, args=None):
    """
    handle when we get a cp check
    """
    self.mobsleft = []
    self.cpinfotimer = {}
    self.api('core.triggers:group:toggle:enable')('cpcheck', True)
    return args

  def _mobkillevent(self, args):
    """
    this will be registered to the mobkill hook
    """
    self.api('libs.io:send:msg')('checking kill %s' % args['name'])
    self.api('core.events:unregister:from:event')('aard_mobkill', self._mobkillevent)

    found = False
    removeitem = None
    for i in range(len(self.mobsleft)):
      tmob = self.mobsleft[i]
      if tmob['name'] == args['name']:
        self.api('libs.io:send:msg')('found %s' % tmob['name'])
        found = True
        removeitem = i

    if removeitem:
      del self.mobsleft[removeitem]

    if found:
      self.api('core.events:raise:event')('aard_cp_mobsleft',
                                          copy.deepcopy({'mobsleft':self.mobsleft}))
    else:
      self.api('libs.io:send:msg')("BP CP: could not find mob: %s" % args['name'])
      self.api('core.cmdq:queue:add:command')('cpcheck', '')

  def _savestate(self, _=None):
    """
    save states
    """
    self.cpinfo.sync()
