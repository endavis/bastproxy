# Project: bastproxy
# Filename: plugins/core/events/plugin/_events.py
#
# File Description: a plugin to handle events
#
# By: Bast

import logging

from bastproxy.libs.api import AddAPI
from bastproxy.libs.context import event_stack, raised_event
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.libs.net.protocols import PROTOCOL_EVENTS
from bastproxy.libs.plugins import loader as plugin_loader
from bastproxy.libs.queue import SimpleQueue
from bastproxy.libs.records.events import RECORD_EVENTS
from bastproxy.libs.scan import find_methods

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

from ._event import Event


class EventsPlugin(BasePlugin):
    """a class to manage events."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.can_reload_f: bool = False

        self.global_raised_count: int = 0
        self.current_event: Event | None = None

        self.all_event_stack = SimpleQueue(300)

        self.events: dict[str, Event] = {}

    @RegisterPluginHook("after_load")
    def _phook_initialize(self):
        """Initialize the plugin."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "log_savestate",
            False,
            bool,
            "flag to log savestate events, reduces log spam if False",
        )

        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "raised_history_size",
            10,
            int,
            "number of recent raises each event keeps in its raised_events history, 0 keeps none; older raises stay in the records manager",
        )
        self._apply_raised_history_size(
            self.api("plugins.core.settings:setting.get")(self.plugin_id, "raised_history_size")
        )

        # Can't use decorator since this is the one that registers all events from decorators
        self.api("plugins.core.events:event.register")(
            plugin_loader.POST_STARTUP_EVENT,
            self._eventcb_post_startup_plugins_loaded,
        )

        # the processing records only name their events, they are registered here once
        for spec in (*RECORD_EVENTS, *PROTOCOL_EVENTS):
            self.api(f"{self.plugin_id}:event.add")(
                spec.name,
                spec.created_by,
                description=spec.description,
                arg_descriptions=spec.arg_descriptions,
            )

    def _apply_raised_history_size(self, value) -> None:
        """Write the raised_history_size setting onto Event.MAX_RAISED_EVENTS."""
        if value is None:
            return
        size = int(value)
        if size < 0:
            get_logger(self.plugin_id).warning("raised_history_size %s is negative, using 0", size)
            size = 0
        Event.MAX_RAISED_EVENTS = size

    @RegisterToEvent(event_name="ev_{plugin_id}_var_raised_history_size_modified")
    def _eventcb_raised_history_size_modified(self):
        """Apply a changed raised_history_size."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self._apply_raised_history_size(event_record["newvalue"])

    def _eventcb_post_startup_plugins_loaded(self):
        """Register all events in all plugins."""
        self._register_all_plugin_events()
        self.api("plugins.core.events:event.raise")(f"ev_{self.plugin_id}_all_events_registered")

    def _register_all_plugin_events(self):
        """Add commands on startup."""
        get_logger(self.plugin_id).debug("_register_all_plugin_events: start")
        for plugin_id in self.api("libs.plugins.loader:plugin.list.loaded")():
            get_logger(self.plugin_id).debug(
                "_register_all_plugin_events: registering events in %s", plugin_id
            )
            self._register_events_for_plugin(plugin_id)
        get_logger(self.plugin_id).debug("_register_all_plugin_events: finish")

    def _register_events_for_plugin(self, plugin_id):
        """Register all events in a plugin."""
        plugin_instance = self.api("libs.plugins.loader:plugin.instance.get")(plugin_id)
        event_functions = self.get_event_registration_functions_in_object(plugin_instance)
        log_to(
            [self.plugin_id, plugin_id],
            logging.DEBUG,
            "_register_events_for_plugin: %s has %s registrations",
            plugin_id,
            len(event_functions),
        )
        for func in self.get_ignored_event_registration_functions_in_object(plugin_instance):
            log_to(
                [self.plugin_id, plugin_id],
                logging.WARNING,
                "_register_events_for_plugin: %s.%s is decorated with RegisterToEvent for %s "
                "but is ignored because its name lacks the _eventcb_ prefix",
                plugin_id,
                func.__name__,
                [item["event_name"] for item in func.event_registration],
            )
        if event_functions:
            names = [item.__name__ for item in event_functions]
            log_to(
                [self.plugin_id, plugin_id],
                logging.DEBUG,
                "_register_events_for_plugin names = %r",
                names,
            )
            for func in event_functions:
                self.api(f"{self.plugin_id}:event.register.by.func")(func)

    @RegisterToEvent(event_name="ev_plugin_loaded", priority=1)
    def _eventcb_plugin_initialized(self):
        """A plugin was loaded, so register all events."""
        if self.api.startup or not (
            event_record := self.api("plugins.core.events:event.current.record.get")()
        ):
            return

        self._register_events_for_plugin(event_record["plugin_id"])

    def get_event_registration_functions_in_object(self, base, recurse=True):
        """Recursively search for functions that are commands in a plugin instance.

        and it's attributes.
        """
        return find_methods(
            base,
            lambda m: m.__name__.startswith("_eventcb_") and hasattr(m, "event_registration"),
            recurse=recurse,
        )

    def get_ignored_event_registration_functions_in_object(self, base, recurse=True):
        """Find decorated methods that are ignored because their name lacks `_eventcb_`."""
        return find_methods(
            base,
            lambda m: not m.__name__.startswith("_eventcb_") and hasattr(m, "event_registration"),
            recurse=recurse,
        )

    @AddAPI(
        "event.register.by.func",
        description="register a decorated function to an event",
    )
    def _api_event_register_by_func(self, func):
        """Register a decorated function as an event."""
        for item in func.event_registration:
            event_name = item["event_name"]
            event_name = event_name.format(**func.__self__.__dict__)
            prio = item["priority"]
            self.api("plugins.core.events:event.register")(event_name, func, prio=prio)

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self):
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            log_to(
                [self.plugin_id, event_record["plugin_id"]],
                logging.INFO,
                "_eventcb_plugin_unloaded - removing events for %s",
                event_record["plugin_id"],
            )
            self.api(f"{self.plugin_id}:event.unregister.for.owner")(event_record["plugin_id"])

    @AddAPI("event.current.name.get", description="return the current event name")
    def _api_event_current_name_get(self):
        """Return the current event name."""
        names = event_stack.get()
        return names[-1] if names else None

    @AddAPI("event.current.record.get", description="return the current event record")
    def _api_event_current_record_get(self):
        """Return the current event record."""
        if last_event := self._api_event_current_name_get():
            event = self.api(f"{self.plugin_id}:event.get")(last_event)
            return event.get_active_event().event_data
        return None

    @AddAPI("event.stack.get", description="return the current event stack")
    def _api_event_stack_get(self):
        """Return the current event stack."""
        return list(event_stack.get())

    @AddAPI("event.add", description="add an event for this plugin to track")
    def _api_event_add(
        self,
        event_name: str,
        created_by: str,
        description: list | None = None,
        arg_descriptions: dict[str, str] | None = None,
    ):
        """Add an event for this plugin to track."""
        event = self.api(f"{self.plugin_id}:event.get")(event_name)
        event.created_by = created_by
        event.description = description or []
        event.arg_descriptions = arg_descriptions or {}

    @AddAPI("event.get", description="return the event")
    def _api_event_get(self, event_name):
        """Return an event.

        @Yevent_name@w   = the event to return.

        this function returns an Event object
        """
        if event_name not in self.events:
            self.events[event_name] = Event(event_name)

        return self.events[event_name]

    @AddAPI("event.exists", description="return the event")
    def _api_event_exists(self, event_name):
        """Check if an event exists.

        @Yevent_name@w   = the event to check for.

        this function returns True if found, False otherwise
        """
        return event_name in self.events

    @AddAPI(
        "event.is.registered",
        description="check if a function is registered to an event",
    )
    def _api_event_is_registered(self, event_name, func):
        """Check if a function is registered to an event.

        @Yevent_name@w   = the event to check
        @Yfunc@w        = the function to check for.

        this function returns True if found, False otherwise
        """
        if event_name in self.events:
            return self.events[event_name].isregistered(func)

        return False

    @AddAPI("event.register", description="register a function to an event")
    def _api_event_register(self, event_name, func, **kwargs):
        """Register a function to an event.

        @Yevent_name@w   = The event to register with
        @Yfunc@w        = The function to register
        keyword arguments:
          prio          = the priority of the function (default: 50).

        this function returns no values
        """
        priority = kwargs.get("prio", 50)
        func_owner_id = self.api("libs.api:function.owner.get")(func)

        if not func_owner_id:
            get_logger(self.plugin_id).error(
                "_api_event_register -could not find owner for %s", func
            )
            return

        # unregister if it's already registered, it might be a new priority
        if self.api(f"{self.plugin_id}:event.is.registered")(event_name, func):
            self.api(f"{self.plugin_id}:event.unregister")(event_name, func)

        event = self.api(f"{self.plugin_id}:event.get")(event_name)

        event.register(func, func_owner_id, priority)

    @AddAPI("event.unregister", description="unregister a function from an event")
    def _api_event_unregister(self, event_name, func):
        # pylint: disable=unused-argument
        """Unregister a function from an event.

        @Yevent_name@w   = The event to unregister with
        @Yfunc@w        = The function to unregister.

        this function returns no values
        """
        if event_name in self.events:
            self.events[event_name].unregister(func)
        else:
            get_logger(self.plugin_id).error(
                "_api_event_unregister -could not find event %s", event_name
            )

    @AddAPI(
        "event.unregister.for.owner",
        description="remove all registered functions that are specific to a owner_id",
    )
    def _api_event_unregister_for_owner(self, owner_id):
        """Remove all registered functions that are specific to a owner_id.

        @Yowner_id@w   = The owner to remove events for
        this function returns no values.
        """
        log_to(
            [self.plugin_id, owner_id],
            logging.INFO,
            "_api_event_unregister_for_owner -removing events for %s",
            owner_id,
        )

        for event in self.events:
            self.events[event].removeowner(owner_id)

    @AddAPI("detail.get.for.plugin", description="get detailed data for a plugin")
    def _api_detail_get_for_plugin(self, owner_name):
        """Return all events for an owner."""
        owner_events = {}
        for event in self.events.values():
            if registrations := event.getownerregistrations(owner_name):
                owner_events[event.name] = registrations

        if not owner_events:
            return []

        columns = [
            {"name": "Event Name", "key": "event", "width": 10},
            {"name": "Priority", "key": "priority", "width": 10},
            {"name": "Function", "key": "function_name", "width": 40},
        ]

        data = []
        sorted_keys = sorted(owner_events.keys())
        for event_name in sorted_keys:
            data.extend(
                {
                    "event": event_name,
                    "function_name": item["function_name"],
                    "priority": item["priority"],
                }
                for item in owner_events[event_name]
            )

        count = len(data)

        return [
            *self.api("plugins.core.utils:table.format")(
                f"{count} Event Registrations for owner: {owner_name}", data, columns
            )
        ]

    @AddAPI("event.raise", description="raise an event")
    def _api_event_raise(
        self,
        event_name,
        event_args=None,
        calledfrom=None,
        data_list=None,
        key_name=None,
    ):
        # pylint: disable=too-many-nested-blocks
        """Raise an event with args.

        @Yevent_name@w   = The event to raise
        @Yargs@w         = A dict or EventDataRecord of arguments.
        """
        if not event_args:
            event_args = {}

        if not calledfrom:
            calledfrom = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        if not calledfrom:
            get_logger(self.plugin_id).warning("event %s raised with unknown caller", event_name)

        event = self.api(f"{self.plugin_id}:event.get")(event_name)

        self.global_raised_count += 1

        self.all_event_stack.enqueue(event.name)

        # the event is on the event stack until the raise finishes, also when it raises
        with raised_event(event.name):
            return event.raise_event(event_args, calledfrom, data_list=data_list, key_name=key_name)

    @AddAPI("event.detail.get", description="get the details of an event")
    def _api_event_detail_get(self, event_name):
        """Get the details of an event.

        @Yevent_name@w = The event name.

        this function returns a list of strings for the info
        """
        message = []

        if event_name in self.events:
            message.extend(self.events[event_name].detail())
        else:
            message.append(f"event {event_name} does not exist")
        return message

    @AddParser(description="raise an event")
    @AddArgument("event", help="the event to raise", default="", nargs="?")
    def _command_raise(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        raise an event - only works for events with no arguments
        @CUsage@w: raise @Y<event_name>@w
          @Yevent_name@w  = the event_name to raise.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        message = []
        if args["event"] and self.api(f"{self.plugin_id}:event.exists")(args["event"]):
            self.api(f"{self.plugin_id}:event.raise")(args["event"])
            message.append(f"raised event: {args['event']}")
        else:
            message.append(f"event does not exist: {args['event']}")

        return CommandResult(True, message)

    @AddParser(description="get details of an event")
    @AddArgument("event", help="the event name to get details for", default=[], nargs="*")
    def _command_detail(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        list events and the owner ids registered with them
        @CUsage@w: detail show @Y<event_name>@w
          @Yevent_name@w  = the event_name to get info for.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        message = []
        if args["event"]:
            for event_name in args["event"]:
                message.extend(self.api(f"{self.plugin_id}:event.detail.get")(event_name))
                message.append("")
        else:
            message.append("Please provide an event name")

        return CommandResult(True, message)

    @AddParser(description="list events and the owners registered with them")
    @AddArgument(
        "match",
        help="list only events that have this argument in their name",
        default="",
        nargs="?",
    )
    @AddArgument(
        "-sr",
        "--show-registered-only",
        help="show only events that have registered functions",
        action="store_true",
        default=False,
    )
    @AddArgument(
        "-snr",
        "--show-not-registered-only",
        help="show only events that have not registered functions",
        action="store_true",
        default=False,
    )
    @AddArgument(
        "-snda",
        "--show-no-description-or-args",
        help="show events that have no description or args",
        action="store_true",
        default=False,
    )
    @AddArgument(
        "-ra",
        "--show-raised-only",
        help="show events that have no description or args",
        action="store_true",
        default=False,
    )
    def _command_list(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        list events and the owner_ids registered with them
        @CUsage@w: list.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        match = args["match"]
        show_registered_only = args["show_registered_only"]
        show_no_description_or_args = args["show_no_description_or_args"]
        show_raised_only = args["show_raised_only"]
        show_not_registered_only = args["show_not_registered_only"]
        eventnames = self.events.keys()
        eventnames = sorted(eventnames)
        eventlist = []

        if show_registered_only:
            eventlist = [name for name in eventnames if self.events[name].count() > 0]
        elif show_not_registered_only:
            eventlist = [name for name in eventnames if self.events[name].count() == 0]
        elif show_no_description_or_args:
            eventlist = [
                name
                for name in eventnames
                if not self.events[name].description or not self.events[name].arg_descriptions
            ]
        elif show_raised_only:
            eventlist = [name for name in eventnames if self.events[name].raised_count > 0]
        else:
            eventlist = eventnames

        message = [
            f"{self.events[name].count():<3} - {name:<30}"
            for name in eventlist
            if (not match or match in name) and self.events[name]
        ] or ["No events found"]

        return CommandResult(True, message)

    @AddParser(description="list registrations for a specific owner")
    @AddArgument(
        "owner",
        help="list only events that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_owner(self):
        """Show all registrations for a specific owner."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["owner"]:
            return CommandResult(False, ["Please provide an owner"])

        owner_name = args["owner"]

        data = self.api(f"{self.plugin_id}:detail.get.for.plugin")(owner_name)

        return CommandResult(True, data or ["No registrations"])

    @AddAPI("summary.get.for.plugin", description="get summary data for a plugin")
    def _api_summary_get_for_plugin(self, plugin_id):
        """Return a summary of the data in this plugin for a specific plugin_id."""
        msg = []
        if plugin_id == self.plugin_id:
            msg.extend(
                (
                    self.api("plugins.core.utils:string.center.colored")(
                        "Overall Event Data", "=", 80, filler_color="@G"
                    ),
                    f"Total Events  : {len(self.events)}",
                    f"Raised Events : {self.global_raised_count}",
                    "",
                    self.api("plugins.core.utils:string.center.colored")(
                        f"{self.plugin_id} specific data", "=", 80, filler_color="@G"
                    ),
                )
            )

        registrations = {}
        for event in self.events:
            if new_registrations := self.events[event].getownerregistrations(plugin_id):
                registrations[event] = new_registrations

        all_registrations = list(registrations.keys())

        registrations_str = "".join(f"{'':<26}{item}\n" for item in all_registrations)

        count = len(all_registrations)

        msg.extend(
            [
                f"{f'{count} Event Registrations':<23} : {registrations_str.strip()}",
            ]
        )

        return msg
