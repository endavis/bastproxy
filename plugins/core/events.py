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

NAME = 'Event Handler'
SNAME = 'events'
PURPOSE = 'Handle events'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class EFunc(object): # pylint: disable=too-few-public-methods
    """
    a basic event class
    """
    def __init__(self, func, func_plugin_id):
        """
        init the class
        """
        self.plugin_id = func_plugin_id
        self.executed_count = 0
        self.func = func
        self.name = func.__name__

    def execute(self, args):
        """
        execute the event
        """
        self.executed_count = self.executed_count + 1
        return self.func(args)

    def __str__(self):
        """
        return a string representation of the function
        """
        return f"{self.name:<10} : {self.plugin_id:15}"

    def __eq__(self, other_function):
        """
        check equality between two event functions
        """
        if callable(other_function):
            if other_function == self.func:
                return True
        try:
            if self.func == other_function.func:
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
        self.priority_dictionary = {}
        self.plugin = plugin
        self.api = self.plugin.api
        self.raised_count = 0

    def isregistered(self, func):
        """
        check if a function is registered to this event
        """
        for priority in self.priority_dictionary:
            if func in self.priority_dictionary[priority]:
                return True

        return False

    def isempty(self):
        """
        check if an event has no functions registered
        """
        for priority in self.priority_dictionary:
            if self.priority_dictionary[priority]:
                return False

        return True

    def register(self, func, func_plugin_id, prio=50):
        """
        register a function to this event container
        """
        if not prio:
            priority = 50
        else:
            priority = prio

        if priority not in self.priority_dictionary:
            self.priority_dictionary[priority] = []

        event_function = EFunc(func, func_plugin_id)

        if event_function not in self.priority_dictionary[priority]:
            self.priority_dictionary[priority].append(event_function)
            LogRecord(f"{self.name} - register function {event_function} with priority {priority}",
                      level='debug', sources=[event_function.plugin_id, self.plugin.plugin_id]).send()
            return True

        return False

    def unregister(self, func):
        """
        unregister a function from this event container
        """
        for priority in self.priority_dictionary:
            if func in self.priority_dictionary[priority]:
                event_function = self.priority_dictionary[priority][self.priority_dictionary[priority].index(func)]
                LogRecord(f"unregister - {self.name} - unregister function {event_function} with priority {priority}",
                          level='debug', sources=[event_function.plugin_id, self.plugin_id]).send()
                self.priority_dictionary[priority].remove(event_function)
                return True

        LogRecord(f"unregister - {self.name} - could not find function {func.__name__}",
                  level='error', sources=[self.plugin_id]).send()
        return False

    def removeplugin(self, plugin):
        """
        remove all functions related to a plugin
        """
        plugins_to_unregister = []
        for priority in self.priority_dictionary:
            for event_function in self.priority_dictionary[priority]:
                if event_function.plugin_id == plugin:
                    plugins_to_unregister.append(event_function)

        for event_function in plugins_to_unregister:
            self.api('plugins.core.events:unregister:from:event')(self.name, event_function.func)

    def detail(self):
        """
        format a detail of the event
        """
        message = []
        message.append(f"{'Event':<13} : {self.name}")
        message.append(f"{'Raised':<13} : {self.raised_count}")
        message.append(self.api('plugins.core.utils:center:colored:string')('Registrations', '-', 60))
        message.append(f"{'priority':<13} : {'plugin':<15} - {'function name'}")
        message.append('@B' + '-' * 60)
        function_message = []
        key_list = self.priority_dictionary.keys()
        key_list.sort()
        for priority in key_list:
            for event_function in self.priority_dictionary[priority]:
                function_message.append(f"{priority:<13} : {event_function.plugin_id:<15} - {event_function.name}")

        if not function_message:
            message.append('None')
        else:
            message.extend(function_message)
        message.append('')

        return message

    def raise_event(self, new_args, calledfrom):
        """
        raise this event
        """
        self.raised_count = self.raised_count + 1

        if self.name != 'ev_bastproxy_global_timer' and \
            ('_savestate' in self.name and self.api('setting:get')('log_savestate')):
            LogRecord(f"raise_event - event {self.name} raised by {calledfrom} with args {new_args}",
                      level='debug', sources=[calledfrom, self.plugin_id]).send()
        keys = self.priority_dictionary.keys()
        if keys:
            keys = sorted(keys)
            for priority in keys:
                for event_function in self.priority_dictionary[priority][:]:
                    try:
                        temp_new_args = event_function.execute(new_args)
                        if temp_new_args and not isinstance(temp_new_args, dict):
                            LogRecord(f"raise_event - event {self.name} with function {event_function.name} returned a nondict object",
                                      level='error', sources=[event_function.plugin_id, self.plugin_id]).send()
                        if temp_new_args and isinstance(temp_new_args, dict):
                            new_args = temp_new_args
                    except Exception:  # pylint: disable=broad-except
                        LogRecord(f"raise_event - event {self.name} with function {event_function.name} raised an exception",
                                    level='error', sources=[event_function.plugin_id, self.plugin_id], exc_info=True).send()

        return new_args

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
        self.api('libs.api:add')('get:event:detail', self._api_get_event_detail)

        self.api('setting:add')('log_savestate', False, bool,
                                'flag to log savestate events, reduces log spam if False')

        self.dependencies = ['core.errors', 'core.managers']

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)
        self.api('plugins.core.events:register:to:event')('ev_core.msg_initialized', self.logloaded)
        #self.api('plugins.core.events:raise:event')('event_plugin_loaded', {})

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

        self.api('plugins.core.events:register:to:event')('ev_core.plugins_plugin_uninitialized',
                                                  self.plugin_uninitialized, priority=10)

    def plugin_uninitialized(self, args):
        """
        a plugin was uninitialized
        """
        LogRecord(f"plugin_uninitialized - removing events for {args['plugin_id']}",
                  level='debug', sources=[self.plugin_id, args['plugin_id']]).send()
        self.api(f"{self.plugin_id}:remove:events:for:plugin")(args['plugin_id'])

    # return the event, will have registered functions
    def _api_get_event(self, event_name):
        """  return an event
        @Yevent_name@w   = the event to return

        this function returns an EventContainer object
        """
        if event_name in self.events:
            return self.events[event_name]

        return None

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
            func_plugin_id = func.im_self.plugin_id
        except AttributeError:
            func_plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
        if not func_plugin_id and 'plugin' in kwargs:
            func_plugin_id = kwargs['plugin_id']

        if event_name not in self.events:
            self.events[event_name] = EventContainer(self, event_name)

        self.events[event_name].register(func, func_plugin_id, priority)

    # unregister a function from an event
    def _api_unregister_from_event(self, event_name, func, **kwargs):
        # pylint: disable=unused-argument
        """  unregister a function with an event
        @Yevent_name@w   = The event to unregister with
        @Yfunc@w        = The function to unregister
        keyword arguments:
          plugin        = the plugin this function is a part of

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
        @Yargs@w         = A table of arguments

        this function returns no values"""
        if not args:
            args = {}

        if not calledfrom:
            calledfrom = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

        if not calledfrom:
            LogRecord(f"event {event_name} raised with unknown caller",
                      level='error', sources=[self.plugin_id]).send()

        new_args = args.copy()
        new_args['eventname'] = event_name
        if event_name not in self.events:
            self.events[event_name] = EventContainer(self, event_name)

        self.global_raised_count += 1
        new_args = self.events[event_name].raise_event(new_args, calledfrom)

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
        eventnames = self.events.keys()
        eventnames = sorted(eventnames)
        for name in eventnames:
            if not match or match in name:
                if self.events[name]:
                    message.append(name)

        return True, message

    def logloaded(self, args=None):
        # pylint: disable=unused-argument
        """
        initialize the event log types
        """
        pass
        #self.api('plugins.core.msg:add:datatype')(self.plugin_id)
        #self.api('plugins.core.msg:toggle:to:console')(self.plugin_id)

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
