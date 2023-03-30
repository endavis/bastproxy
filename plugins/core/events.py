# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/events.py
#
# File Description: a plugin to handle events
#
# By: Bast
"""
This plugin handles events.
  You can register/unregister with events, raise events

## Using
### Registering an event from a plugin
 * ```self.api('plugins.core.events:register:to:event')(event_name, function, prio=50)```

### Unregistering an event
 * ```self.api('plugins.core.events:unregister:from:event')(event_name, function)```

### Raising an event
 * ```self.api('plugins.core.events:raise:event')(event_name, eventdictionary)```
"""
# Standard Library

# 3rd Party

# Project
import libs.argp as argp
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord
from libs.event import Event

NAME = 'Event Handler'
SNAME = 'events'
PURPOSE = 'Handle events'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class Plugin(BasePlugin):
    """
    a class to manage events, events include
      events
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.can_reload_f = False

        self.global_raised_count = 0
        #self.event_stats = {}

        self.events = {}

        # new api that's easier to read
        self.api('libs.api:add')('register:to:event', self._api_register_to_event)
        self.api('libs.api:add')('unregister:from:event', self._api_unregister_from_event)
        self.api('libs.api:add')('raise:event', self._api_raise_event)
        self.api('libs.api:add')('is:registered:to:event', self._api_is_registered_to_event)
        self.api('libs.api:add')('remove:events:for:plugin', self._api_remove_events_from_plugin)
        self.api('libs.api:add')('get:event', self._api_get_event)
        self.api('libs.api:add')('add:event', self._api_add_event)
        self.api('libs.api:add')('get:event:detail', self._api_get_event_detail)

        self.api('setting:add')('log_savestate', False, bool,
                                'flag to log savestate events, reduces log spam if False')

        self.dependencies = ['core.errors', 'core.managers']

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        parser = argp.ArgumentParser(add_help=False,
                                     description='get details of an event')
        parser.add_argument('event',
                            help='the event name to get details for',
                            default=[],
                            nargs='*')
        self.api('plugins.core.commands:command:add')('detail',
                                              self._command_detail,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list events and the ' \
                                                      'plugins registered with them')
        parser.add_argument('match',
                            help='list only events that have this argument in their name',
                            default='',
                            nargs='?')
        parser.add_argument('-sr',
                            '--show-registered-only',
                            help="show only events that have registered functions",
                            action='store_true',
                            default=False)
        parser.add_argument('-snda',
                            '--show-no-description-or-args',
                            help="show events that have no description or args",
                            action='store_true',
                            default=False)
        self.api('plugins.core.commands:command:add')('list',
                                              self._command_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='raise an event')
        parser.add_argument('event',
                            help='the event to raise',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('raise',
                                              self._command_raise,
                                              parser=parser)

        self.api('plugins.core.events:register:to:event')('ev_plugins.core.plugins_plugin_uninitialized',
                                                  self.plugin_uninitialized, priority=10)

    def plugin_uninitialized(self, args):
        """
        a plugin was uninitialized
        """
        LogRecord(f"plugin_uninitialized - removing events for {args['plugin_id']}",
                  level='debug', sources=[self.plugin_id, args['plugin_id']]).send()
        self.api(f"{self.plugin_id}:remove:events:for:plugin")(args['plugin_id'])

    # add an event for the plugin to track
    def _api_add_event(self, event_name, created_by, description=None, arg_descriptions=None):
        """
        add an event for the plugin to track
        """
        event = self._api_get_event(event_name)
        event.created_by = created_by
        event.description = description
        event.arg_descriptions = arg_descriptions

    # return the event, will have registered functions
    def _api_get_event(self, event_name):
        """  return an event
        @Yevent_name@w   = the event to return

        this function returns an Event object
        """
        if event_name not in self.events:
            self.events[event_name] = Event(event_name)

        return self.events[event_name]

    def _api_is_registered_to_event(self, event_name, func):
        """  check if a function is registered to an event
        @Yevent_name@w   = the event to check
        @Yfunc@w        = the function to check for

        this function returns True if found, False otherwise
        """
        if event_name in self.events:
            return self.events[event_name].isregistered(func)

        return False

    # register a function with an event
    def _api_register_to_event(self, event_name, func, **kwargs):
        """  register a function with an event
        @Yevent_name@w   = The event to register with
        @Yfunc@w        = The function to register
        keyword arguments:
          prio          = the priority of the function (default: 50)

        this function returns no values"""

        if 'prio' not in kwargs:
            priority = 50
        else:
            priority = kwargs['prio']
        try:
            func_plugin_id = func.__self__.plugin_id
        except AttributeError:
            func_plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
        if not func_plugin_id and 'plugin' in kwargs:
            func_plugin_id = kwargs['plugin_id']

        event = self._api_get_event(event_name)

        event.register(func, func_plugin_id, priority)

    # unregister a function from an event
    def _api_unregister_from_event(self, event_name, func):
        # pylint: disable=unused-argument
        """  unregister a function with an event
        @Yevent_name@w   = The event to unregister with
        @Yfunc@w        = The function to unregister

        this function returns no values"""
        if event_name in self.events:
            self.events[event_name].unregister(func)
        else:
            LogRecord(f"_api_unregister_from_event - could not find event {event_name}",
                      level='error', sources=[self.plugin_id]).send()

    # remove all registered functions that are specific to a plugin
    def _api_remove_events_from_plugin(self, plugin):
        """  remove all registered functions that are specific to a plugin
        @Yplugin@w   = The plugin to remove events for
        this function returns no values"""
        LogRecord(f"_api_remove_events_from_plugin - removing events for {plugin}",
                  level='debug', sources=[self.plugin_id, plugin]).send()

        for event in self.events:
            self.events[event].removeplugin(plugin)

    # raise an event, args vary
    def _api_raise_event(self, event_name, args=None, calledfrom=None):
        # pylint: disable=too-many-nested-blocks
        """  raise an event with args
        @Yevent_name@w   = The event to raise
        @Yargs@w         = A dict or libs.records.EventArgsRecord of arguments
        """
        if not args:
            args = {}

        if not calledfrom:
            calledfrom = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

        if not calledfrom:
            LogRecord(f"event {event_name} raised with unknown caller",
                      level='error', sources=[self.plugin_id]).send()

        if not args:
            args = {}

        event = self._api_get_event(event_name)

        self.global_raised_count += 1
        new_args = event.raise_event(args, calledfrom)

        return new_args

    # get the details of an event
    def _api_get_event_detail(self, event_name):
        """  get the details of an event
        @Yevent_name@w = The event name

        this function returns a list of strings for the info"""
        message = []

        if event_name in self.events:
            message.extend(self.events[event_name].detail())
        else:
            message.append(f"event {event_name} does not exist")
        return message

    def _command_raise(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          raise an event - only works for events with no arguments
          @CUsage@w: raise @Y<event_name>@w
            @Yevent_name@w  = the event_name to raise
        """
        message = []
        event = self.api(f"{self.plugin_id}:get:event")(args['event'])
        if event:
            self.api(f"{self.plugin_id}:raise:event")(args['event'])
            message.append(f"raised event: {args['event']}")
        else:
            message.append(f"event does not exist: {args['event']}")

        return True, message

    def _command_detail(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list events and the plugins registered with them
          @CUsage@w: detail show @Y<event_name>@w
            @Yevent_name@w  = the event_name to get info for
        """
        message = []
        if args['event']:
            for event_name in args['event']:
                message.extend(self.api('plugins.core.events:get:event:detail')(event_name))
                message.append('')
        else:
            message.append('Please provide an event name')

        return True, message

    def _command_list(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list events and the plugins registered with them
          @CUsage@w: list
        """
        message = []
        match = args['match']
        show_registered_only = args['show_registered_only']
        show_no_description_or_args = args['show_no_description_or_args']
        eventnames = self.events.keys()
        eventnames = sorted(eventnames)
        eventlist = []

        if show_registered_only:
            for name in eventnames:
                if self.events[name].count() > 0:
                    eventlist.append(name)
        elif show_no_description_or_args:
            for name in eventnames:
                if not self.events[name].description or not self.events[name].arg_descriptions:
                    eventlist.append(name)
        else:
            eventlist = eventnames

        for name in eventlist:
            if not match or match in name:
                if self.events[name]:
                    message.append(f"{self.events[name].count():<3} - {name:<30}")

        if not message:
            message = ['No events found']

        return True, message

    def summarystats(self, args=None):
        # pylint: disable=unused-argument
        """
        return a one line stats summary
        """
        return self.summary_template % ('Events', f"Total: {len(self.events)}   Raised: {self.global_raised_count}")

    def get_stats(self):
        """
        return stats for events
        """
        stats = BasePlugin.get_stats(self)
        stats['Events'] = {}
        stats['Events']['showorder'] = ['Total', 'Raised']
        stats['Events']['Total'] = len(self.events)
        stats['Events']['Raised'] = self.global_raised_count

        return stats
