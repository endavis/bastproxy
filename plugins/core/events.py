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
 * ```self.api('plugins.core.events:register.to.event')(event_name, function, prio=50)```

### Unregistering an event
 * ```self.api('plugins.core.events:unregister.from.event')(event_name, function)```

### Raising an event
 * ```self.api('plugins.core.events:raise.event')(event_name, eventdictionary)```
"""
# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord, EventArgsRecord
from libs.event import Event
from libs.stack import SimpleStack
from libs.commands import AddParser, AddArgument

NAME = 'Event Handler'
SNAME = 'events'
PURPOSE = 'Handle events'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class Plugin(BasePlugin):
    """
    a class to manage events
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.can_reload_f: bool = False

        self.global_raised_count: int = 0
        self.current_event: Event | None = None
        self.event_stack = SimpleStack(100)

        self.events: dict[str, Event] = {}

        # new api that's easier to read
        self.api('libs.api:add')(self.plugin_id, 'register.to.event', self._api_register_to_event)
        self.api('libs.api:add')(self.plugin_id, 'unregister.from.event', self._api_unregister_from_event)
        self.api('libs.api:add')(self.plugin_id, 'raise.event', self._api_raise_event)
        self.api('libs.api:add')(self.plugin_id, 'is.registered.to.event', self._api_is_registered_to_event)
        self.api('libs.api:add')(self.plugin_id, 'remove.events.for.owner', self._api_remove_events_for_owner)
        self.api('libs.api:add')(self.plugin_id, 'get.event', self._api_get_event)
        self.api('libs.api:add')(self.plugin_id, 'add.event', self._api_add_event)
        self.api('libs.api:add')(self.plugin_id, 'get.event.detail', self._api_get_event_detail)
        self.api('libs.api:add')(self.plugin_id, 'get.current.event.name', self._api_get_current_event_name)
        self.api('libs.api:add')(self.plugin_id, 'get.current.event.record', self._api_get_current_event_record)
        self.api('libs.api:add')(self.plugin_id, 'get.event.stack', self._api_get_event_stack)

        self.api(f"{self.plugin_id}:setting.add")('log_savestate', False, bool,
                                'flag to log savestate events, reduces log spam if False')

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.events:register.to.event')('ev_plugins.core.pluginm_plugin_uninitialized',
                                                  self._eventcb_plugin_uninitialized, priority=10)

    def _eventcb_plugin_uninitialized(self):
        """
        a plugin was uninitialized
        """
        if event_record := self.api('plugins.core.events:get.current.event.record')():
            LogRecord(f"_eventcb_plugin_uninitialized - removing events for {event_record['plugin_id']}",
                    level='debug', sources=[self.plugin_id, event_record['plugin_id']])()
            self.api(f"{self.plugin_id}:remove.events.for.owner")(event_record['plugin_id'])

    def _api_get_current_event_name(self):
        """
        return the current event name
        """
        return self.event_stack.peek()

    def _api_get_current_event_record(self):
        """
        return the current event record
        """
        if last_event := self.event_stack.peek():
            event = self.api(f"{self.plugin_id}:get.event")(last_event)
            return event.current_record
        return None

    def _api_get_event_stack(self):
        """
        return the current event stack
        """
        return self.event_stack.getstack()

    # add an event for this plugin to track
    def _api_add_event(self, event_name: str, created_by: str, description: str = '',
                       arg_descriptions: dict[str, str] | None = None):
        """
        add an event for this plugin to track
        """
        event = self.api(f"{self.plugin_id}:get.event")(event_name)
        event.created_by = created_by
        event.description = description
        event.arg_descriptions = arg_descriptions or {}

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

        priority = 50 if 'prio' not in kwargs else kwargs['prio']
        func_owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])
        if not func_owner_id:
            LogRecord(f"_api_register_to_event - could not find owner for {func}",
                      level='error', sources=[self.plugin_id])()
            return

        event = self.api(f"{self.plugin_id}:get.event")(event_name)

        event.register(func, func_owner_id, priority)

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
                      level='error', sources=[self.plugin_id])()

    # remove all registered functions that are specific to an owner_id
    def _api_remove_events_for_owner(self, owner_id):
        """  remove all registered functions that are specific to a owner_id
        @Yowner_id@w   = The owner to remove events for
        this function returns no values"""
        LogRecord(f"_api_remove_events_for_owner - removing events for {owner_id}",
                  level='debug', sources=[self.plugin_id, owner_id])()

        for event in self.events:
            self.events[event].removeowner(owner_id)

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
            calledfrom = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        if not calledfrom:
            LogRecord(f"event {event_name} raised with unknown caller",
                      level='warning', sources=[self.plugin_id])()

        if not args:
            args = {}

        event = self.api(f"{self.plugin_id}:get.event")(event_name)

        self.global_raised_count += 1

        # push the evnet onto the stack
        self.event_stack.push(event.name)

        success = event.raise_event(args, calledfrom)

        # pop it back off
        self.event_stack.pop()

        return success

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

    @AddParser(description='raise an event')
    @AddArgument('event',
                    help='the event to raise',
                    default='',
                    nargs='?')
    def _command_raise(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          raise an event - only works for events with no arguments
          @CUsage@w: raise @Y<event_name>@w
            @Yevent_name@w  = the event_name to raise
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message = []
        if self.api(f"{self.plugin_id}:get.event")(args['event']):
            self.api(f"{self.plugin_id}:raise.event")(args['event'])
            message.append(f"raised event: {args['event']}")
        else:
            message.append(f"event does not exist: {args['event']}")

        return True, message

    @AddParser(description='get details of an event')
    @AddArgument('event',
                    help='the event name to get details for',
                    default=[],
                    nargs='*')
    def _command_detail(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list events and the owner ids registered with them
          @CUsage@w: detail show @Y<event_name>@w
            @Yevent_name@w  = the event_name to get info for
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message = []
        if args['event']:
            for event_name in args['event']:
                message.extend(self.api(f"{self.plugin_id}:get.event.detail")(event_name))
                message.append('')
        else:
            message.append('Please provide an event name')

        return True, message

    @AddParser(description='list events and the ' \
                                                      'owners registered with them')
    @AddArgument('match',
                    help='list only events that have this argument in their name',
                    default='',
                    nargs='?')
    @AddArgument('-sr',
                    '--show-registered-only',
                    help="show only events that have registered functions",
                    action='store_true',
                    default=False)
    @AddArgument('-snr',
                    '--show-not-registered-only',
                    help="show only events that have not registered functions",
                    action='store_true',
                    default=False)
    @AddArgument('-snda',
                    '--show-no-description-or-args',
                    help="show events that have no description or args",
                    action='store_true',
                    default=False)
    @AddArgument('-ra',
                    '--show-raised-only',
                    help="show events that have no description or args",
                    action='store_true',
                    default=False)
    def _command_list(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list events and the owner_ids registered with them
          @CUsage@w: list
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        match = args['match']
        show_registered_only = args['show_registered_only']
        show_no_description_or_args = args['show_no_description_or_args']
        show_raised_only = args['show_raised_only']
        show_not_registered_only = args['show_not_registered_only']
        eventnames = self.events.keys()
        eventnames = sorted(eventnames)
        eventlist = []

        if show_registered_only:
            eventlist = [name for name in eventnames if self.events[name].count() > 0]
        elif show_not_registered_only:
            eventlist = [name for name in eventnames if self.events[name].count() == 0]
        elif show_no_description_or_args:
            eventlist = [name for name in eventnames if not self.events[name].description or not self.events[name].arg_descriptions]
        elif show_raised_only:
            eventlist = [name for name in eventnames if self.events[name].raised_count > 0]
        else:
            eventlist = eventnames

        message = [
            f"{self.events[name].count():<3} - {name:<30}"
            for name in eventlist
            if (not match or match in name) and self.events[name]
        ]
        if not message:
            message = ['No events found']

        return True, message

    def summarystats(self, _=None):
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
        stats['Events'] = {
                            'showorder': ['Total', 'Raised'],
                            'Total' : len(self.events),
                            'Raised' : self.global_raised_count
                          }

        return stats
