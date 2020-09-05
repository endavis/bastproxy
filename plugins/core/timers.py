"""
this plugin has a timer interface for internal timers
"""
import time
import datetime
import sys
from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.event import Event

#these 5 are required
NAME = 'timers'
SNAME = 'timers'
PURPOSE = 'handle timers'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 25

REQUIRED = True

class TimerEvent(Event):
  """
  a class for a timer event
  """
  def __init__(self, name, func, seconds, plugin, **kwargs):
    """
    init the class

    time should be military time, "1430"

    """
    Event.__init__(self, name, plugin, func)
    self.seconds = seconds

    self.onetime = False
    if 'onetime' in kwargs:
      self.onetime = kwargs['onetime']

    self.enabled = True
    if 'enabled' in kwargs:
      self.enabled = kwargs['enabled']

    self.time = None
    if 'time' in kwargs:
      self.time = kwargs['time']

    self.log = True
    if 'log' in kwargs:
      self.log = kwargs['log']

    self.nextcall = self.getnext() or -1

  def getnext(self):
    """
    get the next time to call this timer
    """
    if self.time:
      now = datetime.datetime(2012, 1, 1)
      now = now.now()
      ttime = time.strptime(self.time, '%H%M')
      tnext = now.replace(hour=ttime.tm_hour, minute=ttime.tm_min, second=0)
      diff = tnext - now
      while diff.days < 0:
        tstuff = self.plugin.api('utils.secondstodhms')(self.seconds)
        tnext = tnext + datetime.timedelta(days=tstuff['days'],
                                           hours=tstuff['hours'],
                                           minutes=tstuff['mins'],
                                           seconds=tstuff['secs'])
        diff = tnext - now

      nextt = time.mktime(tnext.timetuple())

    else:
      nextt = int(time.time()) + self.seconds

    return nextt

  def __str__(self):
    """
    return a string representation of the timer
    """
    return 'Timer - %-10s : %-15s : %05d : %-6s : %s' % \
      (self.name,
       self.plugin,
       self.seconds, self.enabled,
       time.strftime('%a %b %d %Y %H:%M:%S',
                     time.localtime(self.nextcall)))

class Plugin(BasePlugin):
  """
  a plugin to handle timers
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.timerevents = {}
    self.timerlookup = {}
    self.overallfire = 0
    self.lasttime = int(time.time())

    self.api('api.add')('add', self.api_addtimer)
    self.api('api.add')('remove', self.api_remove)
    self.api('api.add')('toggle', self.api_toggle)
    self.api('api.add')('removeplugin', self.api_removeplugin)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('events.register')('global_timer', self.checktimerevents,
                                prio=1)
    self.api('send.msg')('lasttime:  %s' % self.lasttime)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list timers')
    parser.add_argument('match',
                        help='list only events that have this argument in their name',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='toggle log flag for a timer')
    parser.add_argument('timername',
                        help='the timer name',
                        default='',
                        nargs='?')
    self.api('commands.add')('log',
                             self.cmd_log,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get details for timers')
    parser.add_argument('timers',
                        help='a list of timers to get details',
                        default=[],
                        nargs='*')
    self.api('commands.add')('detail',
                             self.cmd_detail,
                             parser=parser)

    self.api('events.register')('plugin_uninitialized', self.pluginuninitialized)

  def pluginuninitialized(self, args):
    """
    a plugin was uninitialized
    """
    self.api('send.msg')('removing timers for plugin %s' % args['name'],
                         secondary=args['name'])
    self.api('%s.removeplugin' % self.short_name)(args['name'])

  def cmd_log(self, args=None):
    """
    change the log flag for a timer
    """
    msg = []
    if args['timername'] in self.timerlookup:
      self.timerlookup[args['timername']].log = \
          not self.timerlookup[args['timername']].log
      msg.append('changed log flag to %s for timer %s' % \
        (self.timerlookup[args['timername']].log,
         args['timername']))
    else:
      msg.append('timer %s does not exist' % args['timername'])

    return True, msg

  def get_stats(self):
    """
    return stats for this plugin
    """
    stats = BasePlugin.get_stats(self)

    disabled = 0
    enabled = 0

    for i in self.timerlookup:
      if self.timerlookup[i].enabled:
        enabled = enabled + 1
      else:
        disabled = disabled + 1

    stats['Timers'] = {}
    stats['Timers']['showorder'] = ['Total', 'Enabled', 'Disabled',
                                    'Fired', 'Memory Usage']
    stats['Timers']['Total'] = len(self.timerlookup)
    stats['Timers']['Enabled'] = enabled
    stats['Timers']['Disabled'] = disabled
    stats['Timers']['Fired'] = self.overallfire
    stats['Timers']['Memory Usage'] = sys.getsizeof(self.timerevents)
    return stats

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list timers and the plugins they are defined in
      @CUsage@w: list
    """
    tmsg = []

    match = args['match']

    tmsg.append('Local time is: %s' % time.strftime('%a %b %d %Y %H:%M:%S',
                                                    time.localtime()))

    tmsg.append('%-20s : %-13s %-9s %-8s %s' % ('Name', 'Defined in',
                                                'Enabled', 'Fired', 'Next Fire'))
    for i in self.timerlookup:
      if not match or match in i:
        timerc = self.timerlookup[i]
        tmsg.append('%-20s : %-13s %-9s %-8s %s' % (
            timerc.name, timerc.plugin.short_name,
            timerc.enabled, timerc.timesfired,
            time.strftime('%a %b %d %Y %H:%M:%S',
                          time.localtime(timerc.nextcall))))

    return True, tmsg

  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list the details of a timer
      @CUsage@w: detail
    """
    tmsg = []
    if args['timers']:
      for timer in args['timers']:
        if timer in self.timerlookup:
          timerc = self.timerlookup[timer]
          tmsg.append('%-13s : %s' % ('Name', timer))
          tmsg.append('%-13s : %s' % ('Enabled', timerc.enabled))
          tmsg.append('%-13s : %s' % ('Plugin', timerc.plugin.short_name))
          tmsg.append('%-13s : %s' % ('Onetime', timerc.onetime))
          tmsg.append('%-13s : %s' % ('Time', timerc.time))
          tmsg.append('%-13s : %s' % ('Seconds', timerc.seconds))
          tmsg.append('%-13s : %s' % ('Times Fired', timerc.timesfired))
          tmsg.append('%-13s : %s' % ('Log', timerc.log))
          tmsg.append('%-13s : %s' % ('Next Fire',
                                      time.strftime('%a %b %d %Y %H:%M:%S',
                                                    time.localtime(timerc.nextcall))))
          tmsg.append('')

    else:
      tmsg.append('Please specify a timer name')

    return True, tmsg

  # add a timer
  def api_addtimer(self, name, func, seconds, **kwargs):
    """  add a timer
    @Yname@w   = The timer name
    @Yfunc@w  = the function to call when firing the timer
    @Yseconds@w   = the interval (in seconds) to fire the timer
    @Yargs@w arguments:
      @Yunique@w    = True if no duplicates of this timer are allowed,
                                    False otherwise
      @Yonetime@w   = True for a onetime timer, False otherwise
      @Yenabled@w   = True if enabled, False otherwise
      @Ytime@w      = The time to start this timer, e.g. 1300 for 1PM

    returns an Event instance"""
    plugin = None
    try:
      plugin = func.im_self
    except AttributeError:
      plugin = None

    if 'plugin' in kwargs:
      plugin = self.api('core.plugins:get:plugin:instance')(kwargs['plugin'])

    if not plugin:
      self.api('send.msg')('timer %s has no plugin, not adding' % name)
      return
    if seconds <= 0:
      self.api('send.msg')('timer %s has seconds <= 0, not adding' % name,
                           secondary=plugin)
      return
    if not func:
      self.api('send.msg')('timer %s has no function, not adding' % name,
                           secondary=plugin)
      return

    if 'unique' in kwargs and kwargs['unique']:
      if name in self.timerlookup:
        self.api('send.msg')('trying to add duplicate timer: %s' % name,
                             secondary=plugin)
        return

    tevent = TimerEvent(name, func, seconds, plugin, **kwargs)
    self.api('send.msg')('adding %s from plugin %s' % (tevent, plugin),
                         secondary=plugin.short_name)  # pylint: disable=no-member
    self._addtimer(tevent)
    return tevent

  # remove all the timers associated with a plugin
  def api_removeplugin(self, name):
    """  remove all timers associated with a plugin
    @Yname@w   = the name of the plugin

    this function returns no values"""
    plugin = self.api('core.plugins:get:plugin:instance')(name)
    timerstoremove = []
    self.api('send.msg')('removing timers for %s' % name, secondary=name)
    for i in self.timerlookup:
      if plugin == self.timerlookup[i].plugin:
        timerstoremove.append(i)

    for i in timerstoremove:
      self.api('timers.remove')(i)


  # remove a timer
  def api_remove(self, name):
    """  remove a timer
    @Yname@w   = the name of the timer to remove

    this function returns no values"""
    try:
      tevent = self.timerlookup[name]
      if tevent:
        self.api('send.msg')('removing %s' % tevent,
                             secondary=tevent.plugin)
        ttime = tevent.nextcall
        if tevent in self.timerevents[ttime]:
          self.timerevents[ttime].remove(tevent)
        del self.timerlookup[name]
    except KeyError:
      self.api('send.msg')('timer %s does not exist' % name)

  # toggle a timer
  def api_toggle(self, name, flag):
    """  toggle a timer to be enabled/disabled
    @Yname@w   = the name of the timer to toggle
    @Yflag@w   = True to enable, False to disable

    this function returns no values"""
    if name in self.timerlookup:
      self.timerlookup[name].enabled = flag

  def _addtimer(self, timer):
    """
    internally add a timer
    """
    nexttime = timer.nextcall
    if nexttime != -1:
      if nexttime not in self.timerevents:
        self.timerevents[nexttime] = []
      self.timerevents[nexttime].append(timer)
    self.timerlookup[timer.name] = timer

  def checktimerevents(self, args):
    # this is a callback, so disable unused-argument
    # pylint: disable=unused-argument,too-many-nested-blocks
    """
    check all timers
    """
    ntime = int(time.time())
    if ntime - self.lasttime > 1:
      self.api('send.msg')('timer had to check multiple seconds')
    for i in range(self.lasttime, ntime + 1):
      if i in self.timerevents and self.timerevents[i]:
        for timer in self.timerevents[i][:]:
          if timer.enabled:
            try:
              timer.execute()
              timer.timesfired = timer.timesfired + 1
              self.overallfire = self.overallfire + 1
              if timer.log:
                self.api('send.msg')('Timer fired: %s' % timer,
                                     secondary=timer.plugin.short_name)
            except Exception:  # pylint: disable=broad-except
              self.api('send.traceback')('A timer had an error')
          try:
            self.timerevents[i].remove(timer)
          except ValueError:
            self.api('send.msg')('timer %s did not exist in timerevents' % timer.name)
          if not timer.onetime:
            timer.nextcall = timer.nextcall + timer.seconds
            if timer.log:
              self.api('send.msg')('Re adding timer %s for %s' % \
                                    (timer.name,
                                     time.strftime('%a %b %d %Y %H:%M:%S',
                                                   time.localtime(timer.nextcall))),
                                   secondary=timer.plugin.plugin_id)
            self._addtimer(timer)
          else:
            self.api('timers.remove')(timer.name)
          if not self.timerevents[i]:
            del self.timerevents[i]

    self.lasttime = ntime
