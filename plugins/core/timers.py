# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/timers.py
#
# File Description: a plugin to handle timers
#
# By: Bast
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

        self.time_last_fired = None
        self.next_fire = self.getnext() or -1

    def getnext(self):
        """
        get the next time to call this timer
        """
        if self.time:
            now = datetime.datetime(2012, 1, 1)
            now_time_tuple = now.now()
            hour_minute = time.strptime(self.time, '%H%M')
            next_time_tuple = now.replace(hour=hour_minute.tm_hour, minute=hour_minute.tm_min, second=0)
            diff = next_time_tuple - now
            while diff.days < 0:
                tstuff = self.plugin.api('core.utils:convert:seconds:to:dhms')(self.seconds)
                next_time_tuple = next_time_tuple + datetime.timedelta(days=tstuff['days'],
                                                                       hours=tstuff['hours'],
                                                                       minutes=tstuff['mins'],
                                                                       seconds=tstuff['secs'])
                diff = next_time_tuple - now_time_tuple

            next_time_in_seconds = time.mktime(next_time_tuple.timetuple())

        else:
            next_time_in_seconds = int(time.time()) + self.seconds

        return next_time_in_seconds

    def execute(self):
        """
        execute the event
        """
        self.time_last_fired = time.localtime()
        Event.execute(self)

    def __str__(self):
        """
        return a string representation of the timer
        """
        return 'Timer - %-10s : %-15s : %05d : %-6s : %s' % \
          (self.name,
           self.plugin,
           self.seconds, self.enabled,
           time.strftime('%a %b %d %Y %H:%M:%S',
                         time.localtime(self.next_fire)))

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

        self.timer_events = {}
        self.timer_lookup = {}
        self.overall_fire_count = 0
        self.time_last_checked = int(time.time())

        # new api format
        self.api('libs.api:add')('add:timer', self._api_add_timer)
        self.api('libs.api:add')('remove:timer', self._api_remove_timer)
        self.api('libs.api:add')('toggle:timer', self._api_toggle_timer)
        self.api('libs.api:add')('remove:all:timers:for:plugin', self._api_remove_all_timers_for_plugin)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('core.events:register:to:event')('ev_bastproxy_global_timer', self.check_for_timers_to_fire,
                                                  prio=1)
        self.api('libs.io:send:msg')('lasttime:  %s' % self.time_last_checked)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list timers')
        parser.add_argument('match',
                            help='list only events that have this argument in their name',
                            default='',
                            nargs='?')
        self.api('core.commands:command:add')('list',
                                              self.command_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='toggle log flag for a timer')
        parser.add_argument('timername',
                            help='the timer name',
                            default='',
                            nargs='?')
        self.api('core.commands:command:add')('log',
                                              self.command_log,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='get details for timers')
        parser.add_argument('timers',
                            help='a list of timers to get details',
                            default=[],
                            nargs='*')
        self.api('core.commands:command:add')('detail',
                                              self.command_detail,
                                              parser=parser)

        self.api('core.events:register:to:event')('ev_core.plugins_plugin_uninitialized', self.event_plugin_uninitialized)

    def event_plugin_uninitialized(self, args):
        """
        a plugin was uninitialized
        """
        self.api('libs.io:send:msg')('removing timers for plugin %s' % args['plugin_id'],
                                     secondary=args['plugin_id'])
        self.api('%s:remove:all:timers:for:plugin' % self.plugin_id)(args['plugin_id'])

    def command_log(self, args=None):
        """
        change the log flag for a timer
        """
        message = []
        if args['timername'] in self.timer_lookup:
            self.timer_lookup[args['timername']].log = \
                not self.timer_lookup[args['timername']].log
            message.append('changed log flag to %s for timer %s' % \
              (self.timer_lookup[args['timername']].log,
               args['timername']))
        else:
            message.append('timer %s does not exist' % args['timername'])

        return True, message

    def get_stats(self):
        """
        return stats for this plugin
        """
        stats = BasePlugin.get_stats(self)

        disabled = 0
        enabled = 0

        for i in self.timer_lookup:
            if self.timer_lookup[i].enabled:
                enabled = enabled + 1
            else:
                disabled = disabled + 1

        stats['Timers'] = {}
        stats['Timers']['showorder'] = ['Total', 'Enabled', 'Disabled',
                                        'Fired', 'Memory Usage']
        stats['Timers']['Total'] = len(self.timer_lookup)
        stats['Timers']['Enabled'] = enabled
        stats['Timers']['Disabled'] = disabled
        stats['Timers']['Fired'] = self.overall_fire_count
        stats['Timers']['Memory Usage'] = sys.getsizeof(self.timer_events)
        return stats

    def command_list(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list timers and the plugins they are defined in
          @CUsage@w: list
        """
        message = []

        match = args['match']

        message.append('Local time is: %s' % time.strftime('%a %b %d %Y %H:%M:%S',
                                                           time.localtime()))

        message.append('%-20s : %-13s %-9s %-8s %s' % ('Name', 'Defined in',
                                                       'Enabled', 'Fired', 'Next Fire'))
        for i in self.timer_lookup:
            if not match or match in i:
                timer = self.timer_lookup[i]
                message.append('%-20s : %-13s %-9s %-8s %s' % (
                    timer.name, timer.plugin.plugin_id,
                    timer.enabled, timer.fired_count,
                    time.strftime('%a %b %d %Y %H:%M:%S',
                                  time.localtime(timer.next_fire))))

        return True, message

    def command_detail(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list the details of a timer
          @CUsage@w: detail
        """
        message = []
        if args['timers']:
            for timer in args['timers']:
                if timer in self.timer_lookup:
                    timer = self.timer_lookup[timer]
                    message.append('%-13s : %s' % ('Name', timer))
                    message.append('%-13s : %s' % ('Enabled', timer.enabled))
                    message.append('%-13s : %s' % ('Plugin', timer.plugin.plugin_id))
                    message.append('%-13s : %s' % ('Onetime', timer.onetime))
                    message.append('%-13s : %s' % ('Time', timer.time))
                    message.append('%-13s : %s' % ('Seconds', timer.seconds))
                    message.append('%-13s : %s' % ('Times Fired', timer.fired_count))
                    message.append('%-13s : %s' % ('Log', timer.log))
                    last_fire_time = 'None'
                    if timer.time_last_fired:
                        last_fire_time = time.strftime('%a %b %d %Y %H:%M:%S',
                                                       timer.time_last_fired)
                    message.append('%-13s : %s' % ('Last Fire', last_fire_time))
                    message.append('%-13s : %s' % ('Next Fire',
                                                   time.strftime('%a %b %d %Y %H:%M:%S',
                                                                 time.localtime(timer.next_fire))))
                    message.append('')

        else:
            message.append('Please specify a timer name')

        return True, message

    # add a timer
    def _api_add_timer(self, name, func, seconds, **kwargs):
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
            self.api('libs.io:send:msg')('timer %s has no plugin, not adding' % name)
            return
        if seconds <= 0:
            self.api('libs.io:send:msg')('timer %s has seconds <= 0, not adding' % name,
                                         secondary=plugin)
            return
        if not func:
            self.api('libs.io:send:msg')('timer %s has no function, not adding' % name,
                                         secondary=plugin)
            return

        if 'unique' in kwargs and kwargs['unique']:
            if name in self.timer_lookup:
                self.api('libs.io:send:msg')('trying to add duplicate timer: %s' % name,
                                             secondary=plugin)
                return

        timer = TimerEvent(name, func, seconds, plugin, **kwargs)
        self.api('libs.io:send:msg')('adding %s from plugin %s' % (timer, plugin.plugin_id),
                                     secondary=plugin.plugin_id)  # pylint: disable=no-member
        self._add_timer_internal(timer)
        return timer

    # remove all the timers associated with a plugin
    def _api_remove_all_timers_for_plugin(self, name):
        """  remove all timers associated with a plugin
        @Yname@w   = the name of the plugin

        this function returns no values"""
        plugin = self.api('core.plugins:get:plugin:instance')(name)
        timers_to_remove = []
        self.api('libs.io:send:msg')('removing timers for %s' % name, secondary=name)
        for i in self.timer_lookup:
            if plugin == self.timer_lookup[i].plugin:
                timers_to_remove.append(i)

        for i in timers_to_remove:
            self.api('%s:remove:all:timers:for:plugin' % self.plugin_id)(i)


    # remove a timer
    def _api_remove_timer(self, name):
        """  remove a timer
        @Yname@w   = the name of the timer to remove

        this function returns no values"""
        try:
            timer = self.timer_lookup[name]
            if timer:
                self.api('libs.io:send:msg')('removing %s' % timer,
                                             secondary=timer.plugin)
                ttime = timer.next_fire
                if timer in self.timer_events[ttime]:
                    self.timer_events[ttime].remove(timer)
                del self.timer_lookup[name]
        except KeyError:
            self.api('libs.io:send:msg')('timer %s does not exist' % name)

    # toggle a timer
    def _api_toggle_timer(self, name, flag):
        """  toggle a timer to be enabled/disabled
        @Yname@w   = the name of the timer to toggle
        @Yflag@w   = True to enable, False to disable

        this function returns no values"""
        if name in self.timer_lookup:
            self.timer_lookup[name].enabled = flag

    def _add_timer_internal(self, timer):
        """
        internally add a timer
        """
        timer_next_time_to_fire = timer.next_fire
        if timer_next_time_to_fire != -1:
            if timer_next_time_to_fire not in self.timer_events:
                self.timer_events[timer_next_time_to_fire] = []
            self.timer_events[timer_next_time_to_fire].append(timer)
        self.timer_lookup[timer.name] = timer

    def check_for_timers_to_fire(self, args):
        # this is a callback, so disable unused-argument
        # pylint: disable=unused-argument,too-many-nested-blocks
        """
        check all timers
        """
        now = int(time.time())
        if now - self.time_last_checked > 1:
            self.api('libs.io:send:msg')('timer had to check multiple seconds')
        for i in range(self.time_last_checked, now + 1):
            if i in self.timer_events and self.timer_events[i]:
                for timer in self.timer_events[i][:]:
                    if timer.enabled:
                        try:
                            timer.execute()
                            timer.fired_count = timer.fired_count + 1
                            self.overall_fire_count = self.overall_fire_count + 1
                            if timer.log:
                                self.api('libs.io:send:msg')('Timer fired: %s' % timer,
                                                             secondary=timer.plugin.plugin_id)
                        except Exception:  # pylint: disable=broad-except
                            self.api('libs.io:send:traceback')('A timer had an error')
                    try:
                        self.timer_events[i].remove(timer)
                    except ValueError:
                        self.api('libs.io:send:msg')('timer %s did not exist in timerevents' % timer.name)
                    if not timer.onetime:
                        timer.next_fire = timer.next_fire + timer.seconds
                        if timer.log:
                            self.api('libs.io:send:msg')('Re adding timer %s for %s' % \
                                                            (timer.name,
                                                             time.strftime('%a %b %d %Y %H:%M:%S',
                                                                           time.localtime(timer.next_fire))),
                                                         secondary=timer.plugin.plugin_id)
                        self._add_timer_internal(timer)
                    else:
                        self.api('%s:remove:all:timers:for:plugin' % self.plugin_id)(timer.name)
                    if not self.timer_events[i]:
                        del self.timer_events[i]

        self.time_last_checked = now
