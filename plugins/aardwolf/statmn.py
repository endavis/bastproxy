"""
This plugin shows stats for events on Aardwolf

### Example Output

    @x033--------------  Stats for @W01@x033h:@W00@x033m  ---------------
    @x033Type       |  Total     XP    QP    TP       Gold
    @x033--------------------------------------------------
    @WQuests     @x033| @W     1      0    12     0       2899
    @WCPs        @x033| @W     0      0     0     0          0
    @WGQs        @x033| @W     0      0     0     0          0
    @WMobs       @x033| @W     4     72     0     0       1104
    @x033--------------------------------------------------
    @WTotal      @x033| @W           72    12     0       4003@w
"""
import time
import copy
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'StatMonitor'
SNAME = 'statmn'
PURPOSE = 'Monitor for Aardwolf Events'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to monitor aardwolf events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)
    self.msgs = []

    self.api('dependency.add')('core.timers')

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('events.register')('aard_quest_comp', self.compquest)
    self.api('events.register')('aard_cp_comp', self.compcp)
    self.api('events.register')('aard_level_gain', self.levelgain)
    self.api('events.register')('aard_gq_won', self.compgq)
    self.api('events.register')('aard_gq_done', self.compgq)
    self.api('events.register')('aard_gq_completed', self.compgq)
    self.api('events.register')('var_statmn_show', self.showchange)

    self.api('setting.add')('statcolor', '@W', 'color', 'the stat color')
    self.api('setting.add')('infocolor', '@x33', 'color', 'the info color')
    self.api('setting.add')('show', '5m', 'timelength',
                            'show the report every x time')
    self.api('setting.add')('reportminutes', '60m', 'timelength',
                            'the # of minutes for the report to show')
    self.api('setting.add')('exppermin', 20, int,
                            'the threshhold for showing exp per minute')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show report')
    parser.add_argument('minutes', help='the number of minutes in the report',
                        default='60m', nargs='?')
    self.api('commands.add')('rep', self.cmd_rep,
                             parser=parser, format=False, preamble=False)

  def showchange(self, args):
    """
    do something when show changes
    """
    newtime = args['newvalue']
    if newtime > 0:
      self.api('timers.remove')('statrep')
      self.api('timers.add')('statrep', self.timershow,
                             newtime,
                             nodupe=True)
    else:
      self.api('timers.remove')('statrep')
      self.api('send.client')('Turning off the statmon report')

  def timershow(self):
    """
    show the report
    """
    self.api('send.execute')('%s.%s.rep' % (self.api('commands.prefix')(), self.short_name))

  def compquest(self, args):
    """
    handle a quest completion
    """
    msg = []
    infocolor = self.api('setting.gets')('infocolor')
    statcolor = self.api('setting.gets')('statcolor')
    msg.append('%sStatMonitor: Quest finished for ' % \
                      infocolor)
    msg.append('%s%s' % (statcolor, args['qp']))
    if args['lucky'] > 0:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, args['lucky']))
    if args['mccp'] > 0:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, args['mccp']))
    if args['tierqp'] > 0:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, args['tierqp']))
    if args['opk'] > 0:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, args['opk']))
    if args['hardcore'] > 0:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, args['hardcore']))
    if args['daily'] == 1:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, 'E'))
    if args['double'] == 1:
      msg.append('%s+%s%s' % (infocolor,
                              statcolor, 'D'))
    msg.append(' %s= ' % infocolor)
    msg.append('%s%s%sqp' % (statcolor,
                             args['totqp'], infocolor))
    if args['tp'] > 0:
      msg.append(' %s%s%sTP' % (statcolor,
                                args['tp'], infocolor))
    if args['trains'] > 0:
      msg.append(' %s%s%str' % (statcolor,
                                args['trains'], infocolor))
    if args['pracs'] > 0:
      msg.append(' %s%s%spr' % (statcolor,
                                args['pracs'], infocolor))
    msg.append('. It took %s%s%s.' % \
        (statcolor,
         self.api('utils.timedeltatostring')(args['starttime'],
                                             args['finishtime'],
                                             fmin=True, colorn=statcolor,
                                             colors=infocolor),
         infocolor))

    if self.api('core.plugins:is:plugin:loaded')('statdb'):
      stmt = "SELECT COUNT(*) as COUNT, AVG(totqp) as AVEQP " \
              "FROM quests where failed = 0"
      tst = self.api('statdb.select')(stmt)
      quest_total = tst[0]['COUNT']
      quest_avg = tst[0]['AVEQP']
      if quest_total > 1:
        msg.append(" %sAvg: %s%02.02f %sqp/quest over %s%s%s quests." % \
          (infocolor, statcolor,
           quest_avg, infocolor,
           statcolor, quest_total,
           infocolor))

    self.addmessage(''.join(msg))

  def compcp(self, args):
    """
    handle a cp completion
    """
    self.api('send.msg')('compcp: %s' % args)
    infocolor = self.api('setting.gets')('infocolor')
    statcolor = self.api('setting.gets')('statcolor')
    msg = []
    msg.append('%sStatMonitor: CP finished for ' % \
                  infocolor)
    if args['bonusqp'] > 0:
      totalqp = args['bonusqp'] + args['qp']
      msg.append('%s%s%s+%s%sB%s=%s%sqp' % \
        (statcolor,
         args['qp'], infocolor,
         statcolor, args['bonusqp'],
         infocolor, statcolor,
         totalqp))
    else:
      msg.append('%s%s%sqp' % (statcolor, args['qp'],
                               infocolor))
    if args['tp'] > 0:
      msg.append(' %s%s%sTP' % (statcolor,
                                args['tp'], infocolor))
    if args['trains'] > 0:
      msg.append(' %s%s%str' % (statcolor,
                                args['trains'], infocolor))
    if args['pracs'] > 0:
      msg.append(' %s%s%spr' % (statcolor,
                                args['pracs'], infocolor))
    msg.append('. %sIt took %s.' % \
        (infocolor,
         self.api('utils.timedeltatostring')(args['starttime'],
                                             args['finishtime'],
                                             fmin=True, colorn=statcolor,
                                             colors=infocolor)))

    self.addmessage(''.join(msg))

  def compgq(self, args):
    """
    handle a gq completion
    """
    self.api('send.msg')('compgq: %s' % args)
    infocolor = self.api('setting.gets')('infocolor')
    statcolor = self.api('setting.gets')('statcolor')
    msg = []
    msg.append('%sStatMonitor: GQ finished for ' % \
                           infocolor)
    msg.append('%s%s%s' % (statcolor, args['qp'],
                           infocolor))
    msg.append('+%s%s%sqp' % (statcolor, args['qpmobs'],
                              infocolor))
    if args['tp'] > 0:
      msg.append(' %s%s%sTP' % (statcolor,
                                args['tp'], infocolor))
    if args['trains'] > 0:
      msg.append(' %s%s%str' % (statcolor,
                                args['trains'], infocolor))
    if args['pracs'] > 0:
      msg.append(' %s%s%spr' % (statcolor,
                                args['pracs'], infocolor))
    msg.append('.')
    msg.append(' %sIt took %s.' % \
        (infocolor,
         self.api('utils.timedeltatostring')(args['starttime'],
                                             args['finishtime'],
                                             fmin=True, colorn=statcolor,
                                             colors=infocolor)))

    self.addmessage(''.join(msg))

  def levelgain(self, args): # pylint: disable=too-many-branches,too-many-statements
    """
    handle a level or pup gain
    """
    self.api('send.msg')('levelgain: %s' % args)
    infocolor = self.api('setting.gets')('infocolor')
    statcolor = self.api('setting.gets')('statcolor')
    exppermin = self.api('setting.gets')('exppermin')
    msg = []
    msg.append('%sStatMonitor: Gained a %s:' % (infocolor,
                                                args['type']))
    if args['type'] == 'level':
      msg.append(' %s%s%shp' % (statcolor,
                                args['hp'], infocolor))
    if args['type'] == 'level':
      msg.append(' %s%s%smn' % (statcolor,
                                args['mp'], infocolor))
    if args['type'] == 'level':
      msg.append(' %s%s%smv' % (statcolor,
                                args['mv'], infocolor))
    if 'trains' in args:
      trains = args['trains']
      msg.append(' %s%d' % (statcolor, args['trains']))
      if args['blessingtrains'] > 0:
        trains = trains + args['blessingtrains']
        msg.append('%s+%s%dE' % (infocolor,
                                 statcolor, args['blessingtrains']))
      if args['bonustrains'] > 0:
        trains = trains + args['bonustrains']
        msg.append('%s+%s%dB' % (infocolor,
                                 statcolor, args['bonustrains']))
      if args['battlelearntrains'] > 0:
        msg.append('%s+%s%dL' % (infocolor,
                                 statcolor, args['battlelearntrains']))
      if trains != args['trains']:
        msg.append('%s=%s%d' % (infocolor,
                                statcolor, trains))
      msg.append(' %strains ' % infocolor)
    if args['type'] == 'level':
      msg.append('%s%d %spracs ' % (statcolor,
                                    args['pracs'], infocolor))
    stats = False
    for i in ['str', 'dex', 'con', 'luc', 'int', 'wis']:
      if args[i] > 0:
        if not stats:
          stats = True
          msg.append('%s%s' % (statcolor, i))
        else:
          msg.append('%s+%s%s' % (infocolor,
                                  statcolor, i))
    if stats:
      msg.append(' %sbonus ' % infocolor)

    if args['starttime'] > 0 and args['finishtime'] > 0:
      msg.append(self.api('utils.timedeltatostring')(args['starttime'],
                                                     args['finishtime'],
                                                     fmin=True,
                                                     colorn=statcolor,
                                                     colors=infocolor))

    if self.api('core.plugins:is:plugin:loaded')('statdb'):
      stmt = "SELECT count(*) as count, AVG(totalxp) as average FROM " \
            "mobkills where time > %d and time < %d and xp > 0" % \
             (args['starttime'], args['finishtime'])
      tst = self.api('statdb.select')(stmt)
      count = tst[0]['count']
      ave = tst[0]['average']
      if count > 0 and ave > 0:
        length = args['finishtime'] - args['starttime']
        msg.append(' %s%s %smobs killed' % (statcolor,
                                            count, infocolor))
        msg.append(' (%s%02.02f%sxp/mob' % (statcolor,
                                            ave, infocolor))
        if length:
          expmin = self.api('GMCP.getv')('char.base.perlevel')/(length/60)
          if int(expmin) > exppermin:
            msg.append(' %s%02d%sxp/min' % (statcolor,
                                            expmin, infocolor))
        msg.append(')')

    self.addmessage(''.join(msg))

  def addmessage(self, msg):
    """
    add a message to the out queue
    """
    self.msgs.append(msg)

    self.api('events.register')('trigger_emptyline', self.showmessages)

    #self.api('timer.add')('msgtimer',
                #{'func':self.showmessages, 'seconds':1, 'onetime':True,
                 #'nodupe':True})

  def showmessages(self, _=None):
    """
    show a message
    """
    self.api('events.unregister')('trigger_emptyline', self.showmessages)
    for i in self.msgs:
      self.api('send.client')(i, preamble=False)

    self.msgs = []

  def statreport(self, tminutes=None): # pylint: disable=too-many-locals,too-many-statements
    """
    return a report of stats for a # of minutes
    """
    if not self.api('core.plugins:is:plugin:loaded')('statdb'):
      return []

    infocolor = self.api('setting.gets')('infocolor')
    statcolor = self.api('setting.gets')('statcolor')
    reportminutes = self.api('setting.gets')('reportminutes')
    linelen = 50
    msg = ['']
    finishtime = time.time()

    emptystats = {'infocolor':infocolor,
                  'statcolor':statcolor,
                  'xp':0,
                  'qp':0,
                  'total':0,
                  'gold':0,
                  'tp':0}

    queststats = copy.deepcopy(emptystats)
    queststats['type'] = 'Quests'
    cpstats = copy.deepcopy(emptystats)
    cpstats['type'] = 'CPs'
    gqstats = copy.deepcopy(emptystats)
    gqstats['type'] = 'GQs'
    mobstats = copy.deepcopy(emptystats)
    mobstats['type'] = 'Mobs'
    hourtotals = copy.deepcopy(emptystats)
    hourtotals['type'] = 'Total'

    minutes = tminutes or reportminutes
    starttime = finishtime - minutes

    timestr = '%s' % self.api('utils.timedeltatostring')(starttime,
                                                         finishtime,
                                                         colorn=statcolor,
                                                         colors=infocolor,
                                                         nosec=True)

    stmt = """SELECT COUNT(*) as total,
                     SUM(totqp) as qp,
                     SUM(gold) as gold,
                     SUM(tp) as tp
                     FROM quests where finishtime > %d""" % starttime
    tst = self.api('statdb.select')(stmt)
    if tst[0]['total'] > 0:
      queststats.update(tst[0])

    stmt = """SELECT COUNT(*) as total,
                     SUM(qp + bonusqp) as qp,
                     SUM(gold) as gold,
                     SUM(tp) as tp
                     FROM campaigns
                     where finishtime > %d and failed = 0""" % starttime
    tst = self.api('statdb.select')(stmt)
    if tst[0]['total'] > 0:
      cpstats.update(tst[0])

    stmt = """SELECT COUNT(*) as total,
                     SUM(qp + qpmobs) as qp,
                     SUM(gold) as gold,
                     SUM(tp) as tp
                     FROM gquests where finishtime > %d""" % starttime
    tst = self.api('statdb.select')(stmt)
    if tst[0]['total'] > 0:
      gqstats.update(tst[0])

    stmt = """SELECT COUNT(*) as total,
                     SUM(totalxp) as xp,
                     SUM(gold) as gold,
                     SUM(tp) as tp
                     FROM mobkills where time > %d""" % starttime
    tst = self.api('statdb.select')(stmt)
    if tst[0]['total'] > 0:
      mobstats.update(tst[0])

    hourtotals['total'] = ""
    hourtotals['xp'] = mobstats['xp'] + gqstats['xp'] + \
                        cpstats['xp'] + queststats['xp']

    hourtotals['qp'] = mobstats['qp'] + gqstats['qp'] + \
                        cpstats['qp'] + queststats['qp']

    hourtotals['tp'] = mobstats['tp'] + gqstats['tp'] + \
                        cpstats['tp'] + queststats['tp']

    hourtotals['gold'] = mobstats['gold'] + gqstats['gold'] + \
                        cpstats['gold'] + queststats['gold']

    namestr = "Stats for {timestr}".format(timestr=timestr)

    msg.append(infocolor + \
                  self.api('utils.center')(namestr, '-', linelen))
    fstring = "{infocolor}{type:<10} | {total:>6} " \
              "{xp:>6} {qp:>5} {tp:>5} {gold:>10}"
    msg.append(fstring.format(type='Type',
                              total='Total',
                              xp='XP',
                              qp='QP',
                              tp='TP',
                              gold='Gold',
                              infocolor=infocolor))
    msg.append(infocolor + '-' * linelen)

    fstring = "{statcolor}{type:<10} {infocolor}| {statcolor}" \
              "{total:>6} {xp:>6} {qp:>5} {tp:>5} {gold:>10}"

    msg.append(fstring.format(**queststats))

    msg.append(fstring.format(**cpstats))

    msg.append(fstring.format(**gqstats))

    msg.append(fstring.format(**mobstats))

    msg.append(infocolor + '-' * linelen)

    msg.append(fstring.format(**hourtotals))

    msg.append('')
    return msg

  def cmd_rep(self, args=None):
    """
    do a cmd report
    """
    minutes = self.api('setting.gets')('reportminutes')
    if args and args['minutes']:
      minutes = self.api('utils.verify')(args['minutes'], 'timelength')

    msg = self.statreport(minutes)

    return True, msg
