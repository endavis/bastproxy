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
# Standard Library
import time
import datetime
import sys
import asyncio
import math

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.callback import Callback
from libs.records import LogRecord

#these 5 are required
NAME = 'timers'
SNAME = 'timers'
PURPOSE = 'handle timers'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class Timer(Callback):
    """
    a class for a timer
    """
    def __init__(self, name, func, seconds, plugin_id, enabled=True, **kwargs):
        """
        Initialize the class. Time should be in military format, e.g.,"1430".

        Parameters:
        name (str): Name of the timer event.
        func (func): Function to execute on the timer event.
        seconds (int): Time interval in seconds.
        plugin (obj): Plugin related to the timer event.
        **kwargs (Optional): Additional keyword arguments
            onetime (bool): True if the timer is one-time only. Defaults to False.
            enabled (bool): True if the timer is enabled. Defaults to True.
            time (str): Time (in military format) when the timer should fire. If None, timer will fire according to the "seconds" value. Defaults to None.
            log (bool): True if the timer should show up in the logs. Defaults to True.
        """
        super().__init__(name, plugin_id, func, enabled)
        self.seconds = seconds

        self.onetime = False
        if 'onetime' in kwargs:
            self.onetime = kwargs['onetime']

        self.time = None
        if 'time' in kwargs:
            self.time = kwargs['time']

        self.log = True
        if 'log' in kwargs:
            self.log = kwargs['log']

        self.last_fired_datetime = None

        # this should be a datetime object
        self.next_fire_datetime = self.get_first_fire() or None

    def get_first_fire(self):
        """
        Gets the first fire time of the timer.

        Returns:
            datetime: First fire time of the timer.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.time:
            hour_minute = time.strptime(self.time, '%H%M')
            new_date = now.replace(hour=hour_minute.tm_hour, minute=hour_minute.tm_min, second=0)
            while new_date < now:
                new_date = new_date + datetime.timedelta(days=1)
            return new_date

        else:
            new_date = now + datetime.timedelta(seconds=self.seconds)

            while new_date < now:
                new_date = new_date + datetime.timedelta(seconds=self.seconds)
            return new_date

    def getnext(self):
        """
        Gets the next timestamp when the timer should fire.

        Returns:
            int: Timestamp of the next time when the timer should fire.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.last_fired_datetime:
            next_fire = self.last_fired_datetime + datetime.timedelta(seconds=self.seconds)
            while next_fire < now:
                next_fire = next_fire + datetime.timedelta(seconds=self.seconds)
            return next_fire
        else:
            return self.get_first_fire()

    def __str__(self):
        """
        return a string representation of the timer
        """
        return f"Timer {self.name:<10} : {self.plugin_id:<15} : {self.seconds:05d} : {self.enabled:<6} : {self.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}"

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
        self.time_last_checked = datetime.datetime.now(datetime.timezone.utc)

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

        LogRecord(f"initialize - lasttime:  {self.time_last_checked}",
                  'debug', sources=[self.plugin_id]).send()

        parser = argp.ArgumentParser(add_help=False,
                                     description='list timers')
        parser.add_argument('match',
                            help='list only events that have this argument in their name',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('list',
                                              self.command_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='toggle log flag for a timer')
        parser.add_argument('timername',
                            help='the timer name',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('log',
                                              self.command_log,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='get details for timers')
        parser.add_argument('timers',
                            help='a list of timers to get details',
                            default=None,
                            nargs='*')
        self.api('plugins.core.commands:command:add')('detail',
                                              self.command_detail,
                                              parser=parser)

        self.api('plugins.core.events:register:to:event')('ev_core.plugins_plugin_uninitialized', self.event_plugin_uninitialized)

        # setup the task to check for timers to fire
        self.api('libs.asynch:task:add')(self.check_for_timers_to_fire, 'Timer thread')

    def event_plugin_uninitialized(self, args):
        """
        a plugin was uninitialized
        """
        LogRecord(f"event_plugin_uninitialized - removing timers for plugin {args['plugin_id']}",
                  'debug', sources=[self.plugin_id, args['plugin_id']]).send()
        self.api(f"{self.plugin_id}:remove:all:timers:for:plugin")(args['plugin_id'])

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
            message.append(f"timer {args['timername']} does not exist")

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

        message.append(f"UTC time is: {datetime.datetime.now(datetime.timezone.utc).strftime('%a %b %d %Y %H:%M:%S %Z')}")

        message.append('@M' + '-' * 80 + '@w')
        templatestring = '%-20s : %-25s %-9s %-8s %s'
        message.append(templatestring % ('Name', 'Defined in',
                                                       'Enabled', 'Fired', 'Next Fire'))
        message.append('@M' + '-' * 80 + '@w')
        for i in self.timer_lookup:
            if not match or match in i:
                timer = self.timer_lookup[i]
                message.append(templatestring % (
                    timer.name, timer.plugin_id,
                    timer.enabled, timer.fired_count,
                    timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')))

        return True, message

    def command_detail(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list the details of a timer
          @CUsage@w: detail
        """
        message = []
        columnwidth = 13
        if args['timers']:
            for timer in args['timers']:
                if timer in self.timer_lookup:
                    timer = self.timer_lookup[timer]
                    message.append(f"{'Name':<{columnwidth}} : {timer.name}")
                    message.append(f"{'Enabled':<{columnwidth}} : {timer.enabled}")
                    message.append(f"{'Plugin':<{columnwidth}} : {timer.plugin_id}")
                    message.append(f"{'Onetime':<{columnwidth}} : {timer.onetime}")
                    message.append(f"{'Time':<{columnwidth}} : {timer.time}")
                    message.append(f"{'Seconds':<{columnwidth}} : {timer.seconds}")
                    message.append(f"{'Times Fired':<{columnwidth}} : {timer.fired_count}")
                    message.append(f"{'Log':<{columnwidth}} : {timer.log}")
                    last_fire_time = 'None'
                    if timer.last_fired_datetime:
                        last_fire_time = timer.last_fired_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')
                        message.append(f"{'Last Fire':<{columnwidth}} : {last_fire_time}")
                    message.append(f"{'Next Fire':<{columnwidth}} : {timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}")
                    message.append('')
                else:
                    message.append(f"Timer {timer} does not exist")

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
        plugin_id = None
        plugin = None
        try:
            plugin_id = func.__self__.plugin_id
        except AttributeError:
            plugin_id = None

        if 'plugin' in kwargs:
            plugin = self.api('plugins.core.plugins:get:plugin:instance')(kwargs['plugin'])
            plugin_id = plugin.plugin_id

        if not plugin_id:
            LogRecord(f"_api_add_timer: timer {name} has no plugin, not adding",
                      'error', sources=[self.plugin_id]).send()
            return
        if seconds <= 0:
            LogRecord(f"_api_add_timer: timer {name} has seconds <= 0, not adding",
                      'error', sources=[self.plugin_id, plugin_id]).send()
            return
        if not func:
            LogRecord(f"_api_add_timer: timer {name} has no function, not adding",
                      'error', sources=[self.plugin_id, plugin_id]).send()
            return

        if 'unique' in kwargs and kwargs['unique']:
            if name in self.timer_lookup:
                LogRecord(f"_api_add_timer: timer {name} already exists, not adding",
                          'error', sources=[self.plugin_id, plugin_id]).send()
                return

        timer = Timer(name, func, seconds, plugin_id, **kwargs)
        LogRecord(f"_api_add_timer: adding timer {name}",
                  'debug', sources=[self.plugin_id, plugin_id]).send()
        self._add_timer_internal(timer)
        return timer

    # remove all the timers associated with a plugin
    def _api_remove_all_timers_for_plugin(self, name):
        """  remove all timers associated with a plugin
        @Yname@w   = the name of the plugin

        this function returns no values"""
        plugin = self.api('plugins.core.plugins:get:plugin:instance')(name)
        timers_to_remove = []
        LogRecord(f"removing timers for {name}",
                  'debug', sources=[self.plugin_id, name]).send()
        for i in self.timer_lookup:
            if plugin == self.timer_lookup[i].plugin:
                timers_to_remove.append(i)

        for i in timers_to_remove:
            self.api(f"{self.plugin_id}:remove:timer")(i)

    # remove a timer
    def _api_remove_timer(self, name):
        """  remove a timer
        @Yname@w   = the name of the timer to remove

        this function returns no values"""
        try:
            timer = self.timer_lookup[name]
            if timer:
                LogRecord(f"_api_remove_timer - removing {timer}",
                          'debug', sources=[self.plugin_id, timer.plugin]).send()
                ttime = timer.next_fire
                if timer in self.timer_events[ttime]:
                    self.timer_events[ttime].remove(timer)
                del self.timer_lookup[name]
        except KeyError:
            LogRecord(f"_api_remove_timer - timer {name} does not exist",
                      'error', sources=[self.plugin_id]).send()

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
        timer_next_time_to_fire = math.floor(timer.next_fire_datetime.timestamp())
        if timer_next_time_to_fire != -1:
            if timer_next_time_to_fire not in self.timer_events:
                self.timer_events[timer_next_time_to_fire] = []
            self.timer_events[timer_next_time_to_fire].append(timer)
        self.timer_lookup[timer.name] = timer

    async def check_for_timers_to_fire(self):
        # this is a callback, so disable unused-argument
        # pylint: disable=unused-argument,too-many-nested-blocks
        """
        check all timers
        """
        asyncio.current_task().set_name(f"timers task")
        firstrun = True
        keepgoing = True
        while keepgoing:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now != self.time_last_checked:
                if not firstrun:
                    diff = now - self.time_last_checked
                    if diff.total_seconds() > 1:
                        LogRecord(f"check_for_timers_to_fire - timer had to check multiple seconds: {now - self.time_last_checked}",
                                'warning', sources=[self.plugin_id]).send()
                else:
                    LogRecord('Checking timers coroutine has started', 'debug', sources=[self.plugin_id]).send()
                firstrun = False
                for i in range(math.floor(self.time_last_checked.timestamp()), math.floor(now.timestamp()) + 1):
                    if i in self.timer_events and self.timer_events[i]:
                        for timer in self.timer_events[i][:]:
                            if timer.enabled:
                                try:
                                    timer.execute()
                                    self.overall_fire_count = self.overall_fire_count + 1
                                    if timer.log:
                                        LogRecord(f"check_for_timers_to_fire - timer fired: {timer}",
                                                'debug', sources=[self.plugin_id, timer.plugin_id]).send()
                                except Exception:  # pylint: disable=broad-except
                                    LogRecord(f"check_for_timers_to_fire - timer had an error: {timer}",
                                            'error', sources=[self.plugin_id, timer.plugin_id], exc_info=True).send()
                            try:
                                self.timer_events[i].remove(timer)
                            except ValueError:
                                LogRecord(f"check_for_timers_to_fire - timer {timer.name} did not exist in timerevents",
                                        'error', sources=[self.plugin_id, timer.plugin_id]).send()
                            if not timer.onetime:
                                timer.next_fire_datetime = timer.getnext()
                                if timer.log:
                                    LogRecord(f"check_for_timers_to_fire - re adding timer {timer.name} for {timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}",
                                            'debug', sources=[self.plugin_id, timer.plugin_id]).send()
                                self._add_timer_internal(timer)
                            else:
                                self.api(f"{self.plugin_id}:remove:timer")(timer.name)
                            if not self.timer_events[i]:
                                del self.timer_events[i]

                self.time_last_checked = now

            await asyncio.sleep(.5)


