"""
This plugin handles gquest events on Aardwolf
"""
import os
import time
import copy
from libs.persistentdict import PersistentDict
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf GQ Events'
SNAME = 'gq'
PURPOSE = 'Events for Aardwolf GQuests'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf quest events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)
    self.savegqfile = os.path.join(self.save_directory, 'gq.txt')
    self.gqinfo = PersistentDict(self.savegqfile, 'c')
    self._gqsdeclared = {}
    self._gqsstarted = {}
    self.mobsleft = []
    self.linecount = 0

  def initialize(self):
    """
    initialize the plugin
    """
    self.api('setting:add')('joined', -1, int, 'the gq number joined')
    self.api('setting:add')('maxkills', False, bool, 'no qp because of maxkills')

    AardwolfBasePlugin.initialize(self)
    self.api('core.watch:watch:add')('gq_check',
                                     r'^(gq|gqu|gque|gques|gquest) (c|ch|che|chec|check)$')

    self.api('core.triggers:trigger:add')(
        'gqdeclared',
        r"^Global Quest: Global quest \# *(?P<gqnum>\d*) has been " \
          r"declared for levels (?P<lowlev>\d*) to (?P<highlev>\d*)( - .*)*\.$",
        argtypes={'gqnum':int})
    self.api('core.triggers:trigger:add')(
        'gqjoined',
        r"^You have now joined Global Quest \# *(?P<gqnum>\d*)\. .*$",
        argtypes={'gqnum':int})
    self.api('core.triggers:trigger:add')(
        'gqstarted',
        r"^Global Quest: Global quest \# *(?P<gqnum>\d*) for levels .* "\
          r"to .* has now started\.$",
        argtypes={'gqnum':int})
    self.api('core.triggers:trigger:add')(
        'gqcancelled',
        r"^Global Quest: Global quest \# *(?P<gqnum>\d*) has been " \
          r"cancelled due to lack of (activity|participants)\.$",
        argtypes={'gqnum':int})
    self.api('core.triggers:trigger:add')(
        'gqquit',
        r"^You are no longer part of Global Quest \# *(?P<gqnum>\d*) " \
          r"and will be unable to rejoin.$",
        argtypes={'gqnum':int})

    # GQ Check triggers
    self.api('core.triggers:trigger:add')(
        'gqnone',
        r"^You are not in a global quest\.$",
        enabled=False, group='gqcheck')
    self.api('core.triggers:trigger:add')(
        'gqitem',
        r"^You still have to kill (?P<num>[\d]*) \* " \
          r"(?P<mob>.*?) \((?P<location>.*?)\)(|\.)$",
        enabled=False, group='gqcheck',
        argtypes={'num':int})
    self.api('core.triggers:trigger:add')(
        'gqnotstarted',
        r"^Global Quest \# *(?P<gqnum>\d*) has not yet started.",
        enabled=False, group='gqcheck',
        argtypes={'gqnum':int})
    self.api('core.triggers:trigger:add')(
        'gqwins',
        r"^You may win .* more gquests* at this level\.$",
        enabled=False, group='gqcheck')

    self.api('core.triggers:trigger:add')(
        'gqreward',
        r"^\s*Reward of (?P<amount>\d+) (?P<type>.+) .+ added\.$",
        enabled=False, group='gqrew',
        argtypes={'amount':int})

    self.api('core.triggers:trigger:add')(
        'gqmobdead',
        r"^Congratulations, that was one of the GLOBAL QUEST mobs!$",
        enabled=False, group='gqin')

    self.api('core.triggers:trigger:add')(
        'gqextended',
        r"^Global Quest: Global Quest \# *(?P<gqnum>\d*) will go " \
          r"into extended time for 3 more minutes.$",
        enabled=False, group='gqin',
        argtypes={'gqnum':int})

    self.api('core.triggers:trigger:add')(
        'gqwon',
        r"^You were the first to complete this quest!$",
        enabled=False, group='gqin')
    self.api('core.triggers:trigger:add')(
        'gqextfin',
        r"^You have finished this global quest.$",
        enabled=False, group='gqin')
    self.api('core.triggers:trigger:add')(
        'gqwonannounce',
        r"Global Quest: Global Quest \#(?P<gqnum>.*) has been won " \
          r"by (?P<winner>.*) - (.*) win.$",
        enabled=False, group='gqin',
        argtypes={'gqnum':int})

    self.api('core.triggers:trigger:add')(
        'gqnote',
        r"^INFO: New post \#(?P<bdnum>.*) in forum Gquest from " \
          r"Aardwolf Subj: Lvl (?P<low>.*) to (?P<high>.*) - " \
          r"Global quest \# *(?P<gqnum>\d*)$",
        argtypes={'gqnum':int})

    self.api('core.triggers:trigger:add')(
        'gqmaxkills',
        r"^You have reached the " \
          r"maximum (.*) kills for which you can earn quest points this level\.$")

    self.api('core.events:register:to:event')('trigger_gqdeclared', self._gqdeclared)
    self.api('core.events:register:to:event')('trigger_gqjoined', self._gqjoined)
    self.api('core.events:register:to:event')('trigger_gqstarted', self._gqstarted)
    self.api('core.events:register:to:event')('trigger_gqcancelled', self._gqcancelled)
    self.api('core.events:register:to:event')('trigger_gqquit', self._gqquit)

    self.api('core.events:register:to:event')('trigger_gqnone', self._notstarted)
    self.api('core.events:register:to:event')('trigger_gqitem', self._gqitem)
    self.api('core.events:register:to:event')('trigger_gqnotstarted', self._notstarted)
    self.api('core.events:register:to:event')('trigger_gqwins', self._gqwins)

    self.api('core.events:register:to:event')('trigger_gqreward', self._gqreward)

    self.api('core.events:register:to:event')('trigger_gqmobdead', self._gqmobdead)

    self.api('core.events:register:to:event')('trigger_gqextended', self._gqextended)

    self.api('core.events:register:to:event')('trigger_gqwon', self._gqwon)
    self.api('core.events:register:to:event')('trigger_gqextfin', self._gqextfin)
    self.api('core.events:register:to:event')('trigger_gqwonannounce', self._gqwonannounce)

    self.api('core.events:register:to:event')('trigger_gqnote', self._gqnote)
    self.api('core.events:register:to:event')('trigger_gqmaxkills', self._gqmaxkills)

    self.api('core.events:register:to:event')('watch_gq_check', self._gqcheckcmd)

    self.api('core.events:register:to:event')('ev_{0.plugin_id}_savestate'.format(self), self._savestate)

  def _gqnew(self):
    """
    reset the gq info
    """
    self.mobsleft = {}
    self.gqinfo.clear()
    self.gqinfo['mobs'] = {}
    self.gqinfo['trains'] = 0
    self.gqinfo['pracs'] = 0
    self.gqinfo['gold'] = 0
    self.gqinfo['tp'] = 0
    self.gqinfo['qp'] = 0
    self.gqinfo['qpmobs'] = 0
    self.gqinfo['level'] = self.api('aardu.getactuallevel')(
        self.api('net.GMCP:value:get')('char.status.level'))
    self.gqinfo['starttime'] = 0
    self.gqinfo['finishtime'] = 0
    self.gqinfo['length'] = 0
    self.gqinfo['won'] = 0
    self.gqinfo['completed'] = 0
    self.gqinfo['extended'] = 0
    self.api('setting:change')('maxkills', False)
    self.savestate()

  def _gqdeclared(self, args):
    """
    do something when a gq is declared
    """
    self._gqsdeclared[args['gqnum']] = True
    self._checkgqavailable()
    self._raisegq('aard_gq_declared', args)

  def _gqjoined(self, args):
    """
    do something when a gq is joined
    """
    self._gqnew()
    self.api('setting:change')('joined', args['gqnum'])

    self.mobsleft = []

    if args['gqnum'] in self._gqsstarted:
      self._gqstarted(args)
    elif args['gqnum'] not in self._gqsdeclared:
      self._gqsdeclared[args['gqnum']] = True
      self._gqstarted(args)
    self._raisegq('aard_gq_joined', args)

  def _gqstarted(self, args):
    """
    do something when a gq starts
    """
    if args['gqnum'] not in self._gqsstarted:
      self._gqsstarted[args['gqnum']] = True
      self._raisegq('aard_gq_started', args)
      self._checkgqavailable()
    if self.api('setting:get')('joined') == args['gqnum']:
      self.gqinfo['starttime'] = time.time()
      self.api('core.triggers:group:toggle:enable')("gqin", True)
      self.api('libs.io:send:execute')("gq check")

  def _gqcancelled(self, args):
    """
    the gq has been cancelled
    """
    self._raisegq('aard_gq_cancelled', {'gqnum':args['gqnum']})
    if args['gqnum'] == self.api('setting:get')('joined'):
      if self.gqinfo['qpmobs'] > 0:
        self.gqinfo['finishtime'] = time.time()
        self._raisegq('aard_gq_done', self.gqinfo)
      self._gqreset({'gqnum':args['gqnum']})

    else:
      if args['gqnum'] in self._gqsdeclared:
        del self._gqsdeclared[args['gqnum']]
      if args['gqnum'] in self._gqsstarted:
        del self._gqsstarted[args['gqnum']]
      self._checkgqavailable()

  def _gqitem(self, args):
    """
    do something with a gq item
    """
    name = args['mob']
    num = args['num']
    location = args['location']
    if not name or not location or not num:
      self.api('libs.io:send:client')("error parsing line: %s" % args['line'])
    else:
      self.mobsleft.append({'name':name,
                            'nocolorname':self.api('core.colors:ansicode:strip')(name),
                            'location':location, 'num':num})

  def _notstarted(self, _=None):
    """
    this will be called when a gq check returns the not started message
    """
    self.api('core.triggers:group:toggle:enable')('gqcheck', False)
    self.api('core.triggers:group:toggle:enable')('gqin', False)

  def _gqwins(self, _=None):
    """
    this will be enabled when gq check is enabled
    """
    if not self.gqinfo['mobs']:
      self.gqinfo['mobs'] = self.mobsleft[:]
      self.savestate()

    self.api('core.triggers:group:toggle:enable')('gqcheck', False)
    self._raisegq('aard_gq_mobsleft',
                  {'mobsleft':copy.deepcopy(self.mobsleft)})

  def _gqmobdead(self, _=None):
    """
    called when a gq mob is killed
    """
    if not self.api('setting:get')('maxkills'):
      self.gqinfo['qpmobs'] = self.gqinfo['qpmobs'] + 3
    self.api('core.events:register:to:event')('aard_mobkill', self._mobkillevent)

  def _gqextended(self, args):
    """
    gquest went into extended time
    """
    if args['gqnum'] == self.api('setting:get')('joined'):
      self.gqinfo['extended'] = 1

  def _gqmaxkills(self, _=None):
    """
    didn't get xp for that last kill
    """
    self.api('setting:change')('maxkills', True)

  def _mobkillevent(self, args):
    """
    this will be registered to the mobkill hook
    """
    self.api('libs.io:send:msg')('checking kill %s' % args['name'])
    self.api('core.events:register:to:event')('aard_mobkill', self._mobkillevent)

    found = False
    removeitem = None
    for i in range(len(self.mobsleft)):
      tmob = self.mobsleft[i]
      if tmob['name'] == args['name']:
        self.api('libs.io:send:msg')('found %s' % tmob['name'])
        found = True
        if tmob['num'] == 1:
          removeitem = i
        else:
          tmob['num'] = tmob['num'] - 1

    if removeitem:
      del self.mobsleft[removeitem]

    if found:
      self._raisegq('aard_gq_mobsleft',
                    {'mobsleft':self.mobsleft})
    else:
      self.api('libs.io:send:msg')("BP GQ: could not find mob: %s" % args['name'])
      self.api('libs.io:send:execute')("gq check")

  def _gqwon(self, _=None):
    """
    the gquest was won
    """
    self.gqinfo['won'] = 1
    self.gqinfo['finishtime'] = time.time()
    self.api('core.triggers:group:toggle:enable')("gqrew", True)

  def _gqwonannounce(self, args):
    """
    the mud announced that someone won the gquest
    """
    if self.api('net.GMCP:value:get')('char.base.name') == args['winner']:
      # we won
      self._raisegq('aard_gq_won', self.gqinfo)
      self._gqreset(args)

  def _gqreward(self, args=None):
    """
    handle cpreward
    """
    rtype = args['type']
    ramount = args['amount']
    rewardt = self.api('aardwolf.aardu:rewardtable')()
    self.gqinfo[rewardt[rtype]] = ramount
    self.savestate()

  def _gqcheckcmd(self, args=None):
    """
    do something after we see a gq check
    """
    self.mobsleft = []
    self.api('core.triggers:group:toggle:enable')('gqcheck', True)
    return args

  def _gqquit(self, args):
    """
    quit the gq
    """
    if self.gqinfo['qpmobs'] > 0:
      self.gqinfo['finishtime'] = time.time()
      self._raisegq('aard_gq_done', self.gqinfo)
    self._gqreset(args)

  def _gqextfin(self, _=None):
    """
    the character finished the extended gq
    """
    if self.gqinfo['qpmobs'] > 0:
      self.gqinfo['completed'] = 1
      self.gqinfo['finishtime'] = time.time()
      self._raisegq('aard_gq_completed', self.gqinfo)
      self._gqreset({'gqnum':self.api('setting:get')('joined')})

  def _raisegq(self, event, data=None):
    """
    raise a gq event
    """
    self.api('libs.io:send:msg')('raising %s with %s' % (event, data))
    self.savestate()
    if data:
      self.api('core.events:raise:event')(event, copy.deepcopy(data))
    else:
      self.api('core.events:raise:event')(event)

  def _gqnote(self, args):
    """
    do something on the gquest note
    """
    if args['gqnum'] == self.api('setting:get')('joined'):
      if self.gqinfo['qpmobs'] > 0:
        self.gqinfo['finishtime'] = time.time()
        self._raisegq('aard_gq_done', self.gqinfo)
      self._gqreset(args)
    if args['gqnum'] in self._gqsdeclared:
      del self._gqsdeclared[args['gqnum']]
    if args['gqnum'] in self._gqsstarted:
      del self._gqsstarted[args['gqnum']]
    self._checkgqavailable()

  def _gqreset(self, args=None):
    """
    reset gq settings
    """
    self._gqnew()
    if args:
      if args['gqnum'] in self._gqsdeclared:
        del self._gqsdeclared[args['gqnum']]
      if args['gqnum'] in self._gqsstarted:
        del self._gqsstarted[args['gqnum']]
      self._checkgqavailable()
    self.api('core.triggers:group:toggle:enable')("gqcheck", False)
    self.api('core.triggers:group:toggle:enable')("gqin", False)
    self.api('core.triggers:group:toggle:enable')("gqrew", False)
    self.api('core.events:unregister:from:event')('aard_mobkill', self._mobkillevent)
    self.api('setting:change')('joined', 'default')
    self.api('setting:change')('maxkills', False)
    self.savestate()

  def _checkgqavailable(self):
    if self._gqsdeclared:
      self._raisegq('aard_gq_available')
    else:
      self._raisegq('aard_gq_notavailable')

  def _savestate(self, _=None):
    """
    save states
    """
    self.gqinfo.sync()
