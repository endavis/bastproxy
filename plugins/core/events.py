"""
This plugin handles events.
  You can register/unregister with events, raise events

## Using
### Registering an event from a plugin
 * ```self.api('events.register')(eventname, function, prio=50)```

### Unregistering an event
 * ```self.api('events.unregister')(eventname, function)```

### Raising an event
 * ```self.api('events.eraise')(eventname, eventdictionary)```
"""
from __future__ import print_function
import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'Event Handler'
SNAME = 'events'
PURPOSE = 'Handle events'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 3

REQUIRED = True

class EFunc(object): # pylint: disable=too-few-public-methods
  """
  a basic event class
  """
  def __init__(self, func, funcplugin):
    """
    init the class
    """
    self.funcplugin = funcplugin
    self.timesexecuted = 0
    self.func = func
    self.name = func.__name__

  def execute(self, args):
    """
    execute the event
    """
    self.timesexecuted = self.timesexecuted + 1
    return self.func(args)

  def __str__(self):
    """
    return a string representation of the function
    """
    return '%-10s : %-15s' % (self.name, self.funcplugin)

  def __eq__(self, other):
    """
    check equality between two event functions
    """
    if callable(other):
      if other == self.func:
        return True
    try:
      if self.func == other.func:
        return True
    except AttributeError:
      return False

    return False

class EventContainer(object):
  """
  a container of functions for an event
  """
  def __init__(self, plugin, name):
    """
    init the class
    """
    self.name = name
    self.priod = {}
    self.plugin = plugin
    self.api = self.plugin.api
    self.numraised = 0

  def isregistered(self, func):
    """
    check if a function is registered to this event
    """
    for prio in self.priod:
      if func in self.priod[prio]:
        return True

    return False

  def isempty(self):
    """
    check if an event has no functions registered
    """
    for prio in self.priod:
      if self.priod[prio]:
        return False

    return True

  def register(self, func, funcplugin, prio=50):
    """
    register a function to this event container
    """
    if not prio:
      prio = 50

    if prio not in self.priod:
      self.priod[prio] = []

    eventfunc = EFunc(func, funcplugin)

    if eventfunc not in self.priod[prio]:
      self.priod[prio].append(eventfunc)
      self.api('send.msg')('%s - register function %s with prio %s' \
              % (self.name, eventfunc, prio), secondary=eventfunc.funcplugin)
      return True

    return False

  def unregister(self, func):
    """
    unregister a function from this event container
    """
    for prio in self.priod:
      if func in self.priod[prio]:
        eventfunc = self.priod[prio][self.priod[prio].index(func)]
        self.api('send.msg')('%s - unregister function %s with prio %s' \
              % (self.name, eventfunc, prio), secondary=eventfunc.funcplugin)
        self.priod[prio].remove(eventfunc)
        return True

    self.api('send.error')('Could not find function %s in event %s' % \
                              (func.__name__, self.name))
    return False

  def removeplugin(self, plugin):
    """
    remove all functions related to a plugin
    """
    removel = []
    for prio in self.priod:
      for eventfunc in self.priod[prio]:
        if eventfunc.funcplugin == plugin:
          removel.append(eventfunc)

    for eventf in removel:
      self.api('events.unregister')(self.name, eventf.func)

  def detail(self):
    """
    format a detail of the event
    """
    tmsg = []
    tmsg.append('%-13s : %s' % ('Event', self.name))
    tmsg.append('%-13s : %s' % ('Raised', self.numraised))
    tmsg.append('@B' + self.api('utils.center')('Registrations', '-', 60))
    tmsg.append('%-4s : %-15s - %-s' % ('prio',
                                        'plugin',
                                        'function name'))
    tmsg.append('@B' + '-' * 60)
    funcmsg = []
    tkeys = self.priod.keys()
    tkeys.sort()
    for prio in tkeys:
      for eventfunc in self.priod[prio]:
        funcmsg.append('%-4s : %-15s - %-s' % (prio,
                                               eventfunc.funcplugin,
                                               eventfunc.name))

    if not funcmsg:
      tmsg.append('None')
    else:
      tmsg.extend(funcmsg)
    tmsg.append('')

    return tmsg

  def eraise(self, nargs, calledfrom):
    """
    raise this event
    """
    self.numraised = self.numraised + 1

    if self.name != 'global_timer':
      self.api('send.msg')('event %s raised by %s with args %s' % \
                             (self.name, calledfrom, nargs),
                           secondary=calledfrom)
    keys = self.priod.keys()
    if keys:
      keys.sort()
      for prio in keys:
        for eventfunc in self.priod[prio][:]:
          try:
            tnargs = eventfunc.execute(nargs)
            if tnargs and not isinstance(tnargs, dict):
              self.api('send.msg')(
                  "Event: %s with function %s returned a nondict object" % \
                    (self.name, eventfunc.name))
            if tnargs and isinstance(tnargs, dict):
              nargs = tnargs
          except Exception:  # pylint: disable=broad-except
            self.api('send.traceback')(
                "error when calling function for event %s" % self.name)

    return nargs

class Plugin(BasePlugin):
  """
  a class to manage events, events include
    events
  """
  def __init__(self, *args, **kwargs):

    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.numglobalraised = 0
    self.eventstats = {}

    self.events = {}
    self.pluginlookup = {}

    self.api('api.add')('register', self.api_register)
    self.api('api.add')('unregister', self.api_unregister)
    self.api('api.add')('eraise', self.api_eraise)
    self.api('api.add')('isregistered', self.api_isregistered)
    self.api('api.add')('removeplugin', self.api_removeplugin)
    self.api('api.add')('gete', self.api_getevent)
    self.api('api.add')('detail', self.api_detail)

    self.dependencies = ['core.errors']

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)
    self.api('events.register')('plugin_log_loaded', self.logloaded)
    #self.api('events.eraise')('event_plugin_loaded', {})

    parser = argp.ArgumentParser(add_help=False,
                                 description='get details of an event')
    parser.add_argument('event',
                        help='the event name to get details for',
                        default=[],
                        nargs='*')
    self.api('commands.add')('detail',
                             self.cmd_detail,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list events and the ' \
                                                  'plugins registered with them')
    parser.add_argument('match',
                        help='list only events that have this argument in their name',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='raise an event')
    parser.add_argument('event',
                        help='the event to raise',
                        default='',
                        nargs='?')
    self.api('commands.add')('raise',
                             self.cmd_raise,
                             parser=parser)

    self.api('events.register')('plugin_unloaded', self.pluginunloaded, prio=10)

  def pluginunloaded(self, args):
    """
    a plugin was unloaded
    """
    self.api('send.msg')('removing events for plugin %s' % args['name'],
                         secondary=args['name'])
    self.api('%s.removeplugin' % self.short_name)(args['name'])

  # return the event, will have registered functions
  def api_getevent(self, eventname):
    """  return an event
    @Yeventname@w   = the event to return

    this function returns an EventContainer object
    """
    if eventname in self.events:
      return self.events[eventname]

    return None

  def api_isregistered(self, eventname, func):
    """  check if a function is registered to an event
    @Yeventname@w   = the event to check
    @Yfunc@w        = the function to check for

    this function returns True if found, False otherwise
    """
    #print('isregistered')
    if eventname in self.events:
      return self.events[eventname].isregistered(func)

    return False

  # register a function with an event
  def api_register(self, eventname, func, **kwargs):
    """  register a function with an event
    @Yeventname@w   = The event to register with
    @Yfunc@w        = The function to register
    keyword arguments:
      prio          = the priority of the function (default: 50)

    this function returns no values"""

    if 'prio' not in kwargs:
      prio = 50
    else:
      prio = kwargs['prio']
    try:
      funcplugin = func.im_self.short_name
    except AttributeError:
      funcplugin = self.api('api.callerplugin')(skipplugin=['events'])
    if not funcplugin and 'plugin' in kwargs:
      funcplugin = kwargs['plugin']

    if eventname not in self.events:
      self.events[eventname] = EventContainer(self, eventname)

    self.events[eventname].register(func, funcplugin, prio)

  # unregister a function from an event
  def api_unregister(self, eventname, func, **kwargs):
    # pylint: disable=unused-argument
    """  unregister a function with an event
    @Yeventname@w   = The event to unregister with
    @Yfunc@w        = The function to unregister
    keyword arguments:
      plugin        = the plugin this function is a part of

    this function returns no values"""
    if eventname in self.events:
      self.events[eventname].unregister(func)
    else:
      self.api('send.error')('could not find event %s' % (eventname))

  # remove all registered functions that are specific to a plugin
  def api_removeplugin(self, plugin):
    """  remove all registered functions that are specific to a plugin
    @Yplugin@w   = The plugin to remove events for
    this function returns no values"""
    self.api('send.msg')('removing plugin %s' % plugin,
                         secondary=plugin)

    for event in self.events:
      self.events[event].removeplugin(plugin)

  # raise an event, args vary
  def api_eraise(self, eventname, args=None, calledfrom=None):
    # pylint: disable=too-many-nested-blocks
    """  raise an event with args
    @Yeventname@w   = The event to raise
    @Yargs@w        = A table of arguments

    this function returns no values"""
    if not args:
      args = {}

    if not calledfrom:
      calledfrom = self.api('api.callerplugin')(skipplugin=['events'])

    if not calledfrom:
      print('event %s raised with unknown caller' % eventname)

    nargs = args.copy()
    nargs['eventname'] = eventname
    if eventname not in self.events:
      self.events[eventname] = EventContainer(self, eventname)

    self.numglobalraised += 1
    nargs = self.events[eventname].eraise(nargs, calledfrom)

    return nargs

  # get the details of an event
  def api_detail(self, eventname):
    """  get the details of an event
    @Yeventname@w = The event name

    this function returns a list of strings for the info"""
    tmsg = []

    if eventname in self.events:
      tmsg.extend(self.events[eventname].detail())
    else:
      tmsg.append('Event %s does not exist' % eventname)
    return tmsg

  def cmd_raise(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      raise an event - only works for events with no arguments
      @CUsage@w: raise @Y<eventname>@w
        @Yeventname@w  = the eventname to raise
    """
    tmsg = []
    event = self.api('%s.gete' % self.short_name)(args['event'])
    if event:
      self.api('%s.eraise' % self.short_name)(args['event'])
      tmsg.append('raised event: %s' % args['event'])
    else:
      tmsg.append('event does not exist: %s' % args['event'])

    return True, tmsg

  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list events and the plugins registered with them
      @CUsage@w: detail show @Y<eventname>@w
        @Yeventname@w  = the eventname to get info for
    """
    tmsg = []
    if args['event']:
      for eventname in args['event']:
        tmsg.extend(self.api('events.detail')(eventname))
        tmsg.append('')
    else:
      tmsg.append('Please provide an event name')

    return True, tmsg

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list events and the plugins registered with them
      @CUsage@w: list
    """
    tmsg = []
    match = args['match']
    for name in self.events:
      if not match or match in name:
        if self.events[name]:
          tmsg.append(name)

    return True, tmsg

  def logloaded(self, args=None):
    # pylint: disable=unused-argument
    """
    initialize the event log types
    """
    self.api('log.adddtype')(self.short_name)
    #self.api('log.console')(self.short_name)

  def summarystats(self, args=None):
    # pylint: disable=unused-argument
    """
    return a one line stats summary
    """
    return self.summary_template % ("Events", "Total: %d   Raised: %d" % \
                                    (len(self.events), self.numglobalraised))

  def get_stats(self):
    """
    return stats for events
    """
    stats = BasePlugin.get_stats(self)
    stats['Events'] = {}
    stats['Events']['showorder'] = ['Total', 'Raised']
    stats['Events']['Total'] = len(self.events)
    stats['Events']['Raised'] = self.numglobalraised

    return stats
