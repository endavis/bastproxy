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
    self.api('setting.add')('joined', -1, int, 'the gq number joined')
    self.api('setting.add')('maxkills', False, bool, 'no qp because of maxkills')
    self.mobsleft = []
    self.linecount = 0

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)
    self.api('watch.add')('gq_check',
                          r'^(gq|gqu|gque|gques|gquest) (c|ch|che|chec|check)$')

    self.api('triggers.add')(
        'gqdeclared',
        r"^Global Quest: Global quest \# *(?P<gqnum>\d*) has been " \
          r"declared for levels (?P<lowlev>\d*) to (?P<highlev>\d*)( - .*)*\.$",
        argtypes={'gqnum':int})
    self.api('triggers.add')(
        'gqjoined',
        r"^You have now joined Global Quest \# *(?P<gqnum>\d*)\. .*$",
        argtypes={'gqnum':int})
    self.api('triggers.add')(
        'gqstarted',
        r"^Global Quest: Global quest \# *(?P<gqnum>\d*) for levels .* "\
          r"to .* has now started\.$",
        argtypes={'gqnum':int})
    self.api('triggers.add')(
        'gqcancelled',
        r"^Global Quest: Global quest \# *(?P<gqnum>\d*) has been " \
          r"cancelled due to lack of (activity|participants)\.$",
        argtypes={'gqnum':int})
    self.api('triggers.add')(
        'gqquit',
        r"^You are no longer part of Global Quest \# *(?P<gqnum>\d*) " \
          r"and will be unable to rejoin.$",
        argtypes={'gqnum':int})

    # GQ Check triggers
    self.api('triggers.add')(
        'gqnone',
        r"^You are not in a global quest\.$",
        enabled=False, group='gqcheck')
    self.api('triggers.add')(
        'gqitem',
        r"^You still have to kill (?P<num>[\d]*) \* " \
          r"(?P<mob>.*?) \((?P<location>.*?)\)(|\.)$",
        enabled=False, group='gqcheck',
        argtypes={'num':int})
    self.api('triggers.add')(
        'gqnotstarted',
        r"^Global Quest \# *(?P<gqnum>\d*) has not yet started.",
        enabled=False, group='gqcheck',
        argtypes={'gqnum':int})
    self.api('triggers.add')(
        'gqwins',
        r"^You may win .* more gquests* at this level\.$",
        enabled=False, group='gqcheck')

    self.api('triggers.add')(
        'gqreward',
        r"^\s*Reward of (?P<amount>\d+) (?P<type>.+) .+ added\.$",
        enabled=False, group='gqrew',
        argtypes={'amount':int})

    self.api('triggers.add')(
        'gqmobdead',
        r"^Congratulations, that was one of the GLOBAL QUEST mobs!$",
        enabled=False, group='gqin')

    self.api('triggers.add')(
        'gqextended',
        r"^Global Quest: Global Quest \# *(?P<gqnum>\d*) will go " \
          r"into extended time for 3 more minutes.$",
        enabled=False, group='gqin',
        argtypes={'gqnum':int})

    self.api('triggers.add')(
        'gqwon',
        r"^You were the first to complete this quest!$",
        enabled=False, group='gqin')
    self.api('triggers.add')(
        'gqextfin',
        r"^You have finished this global quest.$",
        enabled=False, group='gqin')
    self.api('triggers.add')(
        'gqwonannounce',
        r"Global Quest: Global Quest \#(?P<gqnum>.*) has been won " \
          r"by (?P<winner>.*) - (.*) win.$",
        enabled=False, group='gqin',
        argtypes={'gqnum':int})

    self.api('triggers.add')(
        'gqnote',
        r"^INFO: New post \#(?P<bdnum>.*) in forum Gquest from " \
          r"Aardwolf Subj: Lvl (?P<low>.*) to (?P<high>.*) - " \
          r"Global quest \# *(?P<gqnum>\d*)$",
        argtypes={'gqnum':int})

    self.api('triggers.add')(
        'gqmaxkills',
        r"^You have reached the " \
          r"maximum (.*) kills for which you can earn quest points this level\.$")

    self.api('events.register')('trigger_gqdeclared', self._gqdeclared)
    self.api('events.register')('trigger_gqjoined', self._gqjoined)
    self.api('events.register')('trigger_gqstarted', self._gqstarted)
    self.api('events.register')('trigger_gqcancelled', self._gqcancelled)
    self.api('events.register')('trigger_gqquit', self._gqquit)

    self.api('events.register')('trigger_gqnone', self._notstarted)
    self.api('events.register')('trigger_gqitem', self._gqitem)
    self.api('events.register')('trigger_gqnotstarted', self._notstarted)
    self.api('events.register')('trigger_gqwins', self._gqwins)

    self.api('events.register')('trigger_gqreward', self._gqreward)

    self.api('events.register')('trigger_gqmobdead', self._gqmobdead)

    self.api('events.register')('trigger_gqextended', self._gqextended)

    self.api('events.register')('trigger_gqwon', self._gqwon)
    self.api('events.register')('trigger_gqextfin', self._gqextfin)
    self.api('events.register')('trigger_gqwonannounce',
                                self._gqwonannounce)

    self.api('events.register')('trigger_gqnote', self._gqnote)
    self.api('events.register')('trigger_gqmaxkills', self._gqmaxkills)

    self.api('events.register')('watch_gq_check', self._gqcheckcmd)

    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

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
        self.api('GMCP.getv')('char.status.level'))
    self.gqinfo['starttime'] = 0
    self.gqinfo['finishtime'] = 0
    self.gqinfo['length'] = 0
    self.gqinfo['won'] = 0
    self.gqinfo['completed'] = 0
    self.gqinfo['extended'] = 0
    self.api('setting.change')('maxkills', False)
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
    self.api('setting.change')('joined', args['gqnum'])

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
    if self.api('setting.gets')('joined') == args['gqnum']:
      self.gqinfo['starttime'] = time.time()
      self.api('triggers.togglegroup')("gqin", True)
      self.api('send.execute')("gq check")

  def _gqcancelled(self, args):
    """
    the gq has been cancelled
    """
    self._raisegq('aard_gq_cancelled', {'gqnum':args['gqnum']})
    if args['gqnum'] == self.api('setting.gets')('joined'):
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
      self.api('send.client')("error parsing line: %s" % args['line'])
    else:
      self.mobsleft.append({'name':name,
                            'nocolorname':self.api('colors.stripansi')(name),
                            'location':location, 'num':num})

  def _notstarted(self, _=None):
    """
    this will be called when a gq check returns the not started message
    """
    self.api('triggers.togglegroup')('gqcheck', False)
    self.api('triggers.togglegroup')('gqin', False)

  def _gqwins(self, _=None):
    """
    this will be enabled when gq check is enabled
    """
    if not self.gqinfo['mobs']:
      self.gqinfo['mobs'] = self.mobsleft[:]
      self.savestate()

    self.api('triggers.togglegroup')('gqcheck', False)
    self._raisegq('aard_gq_mobsleft',
                  {'mobsleft':copy.deepcopy(self.mobsleft)})

  def _gqmobdead(self, _=None):
    """
    called when a gq mob is killed
    """
    if not self.api('setting.gets')('maxkills'):
      self.gqinfo['qpmobs'] = self.gqinfo['qpmobs'] + 3
    self.api('events.register')('aard_mobkill', self._mobkillevent)

  def _gqextended(self, args):
    """
    gquest went into extended time
    """
    if args['gqnum'] == self.api('setting.gets')('joined'):
      self.gqinfo['extended'] = 1

  def _gqmaxkills(self, _=None):
    """
    didn't get xp for that last kill
    """
    self.api('setting.change')('maxkills', True)

  def _mobkillevent(self, args):
    """
    this will be registered to the mobkill hook
    """
    self.api('send.msg')('checking kill %s' % args['name'])
    self.api('events.register')('aard_mobkill', self._mobkillevent)

    found = False
    removeitem = None
    for i in range(len(self.mobsleft)):
      tmob = self.mobsleft[i]
      if tmob['name'] == args['name']:
        self.api('send.msg')('found %s' % tmob['name'])
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
      self.api('send.msg')("BP GQ: could not find mob: %s" % args['name'])
      self.api('send.execute')("gq check")

  def _gqwon(self, _=None):
    """
    the gquest was won
    """
    self.gqinfo['won'] = 1
    self.gqinfo['finishtime'] = time.time()
    self.api('triggers.togglegroup')("gqrew", True)

  def _gqwonannounce(self, args):
    """
    the mud announced that someone won the gquest
    """
    if self.api('GMCP.getv')('char.base.name') == args['winner']:
      # we won
      self._raisegq('aard_gq_won', self.gqinfo)
      self._gqreset(args)

  def _gqreward(self, args=None):
    """
    handle cpreward
    """
    rtype = args['type']
    ramount = args['amount']
    rewardt = self.api('aardu.rewardtable')()
    self.gqinfo[rewardt[rtype]] = ramount
    self.savestate()

  def _gqcheckcmd(self, args=None):
    """
    do something after we see a gq check
    """
    self.mobsleft = []
    self.api('triggers.togglegroup')('gqcheck', True)
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
      self._gqreset({'gqnum':self.api('setting.gets')('joined')})

  def _raisegq(self, event, data=None):
    """
    raise a gq event
    """
    self.api('send.msg')('raising %s with %s' % (event, data))
    self.savestate()
    if data:
      self.api('events.eraise')(event, copy.deepcopy(data))
    else:
      self.api('events.eraise')(event)

  def _gqnote(self, args):
    """
    do something on the gquest note
    """
    if args['gqnum'] == self.api('setting.gets')('joined'):
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
    self.api('triggers.togglegroup')("gqcheck", False)
    self.api('triggers.togglegroup')("gqin", False)
    self.api('triggers.togglegroup')("gqrew", False)
    self.api('events.unregister')('aard_mobkill', self._mobkillevent)
    self.api('setting.change')('joined', 'default')
    self.api('setting.change')('maxkills', False)
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
