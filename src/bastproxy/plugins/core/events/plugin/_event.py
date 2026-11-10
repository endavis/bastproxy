# Project: bastproxy
# Filename: plugins/core/events/_event.py
#
# File Description: Holds base classes for event items
#
# By: Bast
"""Holds base classes for an event to raise.

The created_by attribute is the name of the plugin or module that created the event
It can be updated in two ways, by using the api plugins.core.events:add:event
    or when the event is raised and a calledfrom argument is passed and created_by is not already been set
"""

# Standard Library
import inspect
import logging
from collections import OrderedDict
from collections.abc import Callable

# 3rd Party
# Project
from bastproxy.libs.api import API
from bastproxy.libs.callback import Callback
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.libs.records.tracking import tracking_actor
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord
from bastproxy.plugins.core.events.libs.process._raisedevent import ProcessRaisedEvent


class Event:
    """Base class for an event."""

    # Number of recent raises each event keeps in raised_events. EventsPlugin sets
    # this from its raised_history_size setting; RMANAGER keeps the long history.
    MAX_RAISED_EVENTS: int = 10

    def __init__(
        self,
        name: str,
        created_by: str = "",
        description: list | None = None,
        arg_descriptions: dict[str, str] | None = None,
    ):
        """name: the name of the event.

        created_by: it should be the __name__ of the module or the plugin id for easy identification
        description: a list of strings that describe the event
        arg_descriptions: a dictionary of argument names and descriptions.
        """
        self.name: str = name
        # it should be the __name__ of the module or the plugin id for easy identification
        self.created_by: str = created_by
        self.description = description or []
        self.arg_descriptions = arg_descriptions or {}

        self.owner_id: str = f"plugins.core.events:{self.name}"
        self.api = API(owner_id=self.owner_id)
        self.priority_dictionary = {}
        self.raised_count = 0
        # bounded to the newest MAX_RAISED_EVENTS raises (Event System Findings Bug #3, #153)
        #           it holds no callbacks, so it does not keep unloaded plugins alive
        self.raised_events: OrderedDict[str, ProcessRaisedEvent] = OrderedDict()
        self.current_callback = None
        self.active_event = None

    def get_active_event(self):
        """Get the active event."""
        return self.active_event

    def count(self) -> int:
        """Return the number of functions registered to this event."""
        return sum(len(v) for v in self.priority_dictionary.values())

    def isregistered(self, func) -> bool:
        """Check if a function is registered to this event."""
        return any(
            any(call_back.func == func for call_back in self.priority_dictionary[priority])
            for priority in self.priority_dictionary
        )

    def isempty(self) -> bool:
        """Check if an event has no functions registered."""
        return not any(self.priority_dictionary[priority] for priority in self.priority_dictionary)

    def register(self, func: Callable, func_owner_id: str, prio: int | None = 50) -> bool:
        """Register a function to this event container.

        ``prio`` orders callbacks, lower runs first. ``None`` means 50; ``0`` and
        every other value are honoured as given.

        An ``async def`` callback is rejected: raising an event calls callbacks
        synchronously, so a coroutine would be created and never awaited.
        """
        if inspect.iscoroutinefunction(func):
            get_logger(self.created_by).error(
                "%s - cannot register async function %s: event callbacks must be synchronous",
                self.name,
                getattr(func, "__name__", func),
            )
            return False

        priority = 50 if prio is None else prio
        if priority not in self.priority_dictionary:
            self.priority_dictionary[priority] = {}

        call_back = Callback(func.__name__, func_owner_id, func)

        if call_back not in self.priority_dictionary[priority]:
            # This is a list of functions that are registered to this event at this priority
            # It is used to ensure that a function is not registered twice
            # The value is not read: which callbacks have run is tracked per raise
            # by ProcessRaisedEvent (a set passed to raise_priority)
            self.priority_dictionary[priority][call_back] = False
            log_to(
                [call_back.owner_id, self.created_by],
                logging.DEBUG,
                "%s - register function %s with priority %s",
                self.name,
                call_back,
                priority,
            )
            return True

        return False

    def unregister(self, func) -> bool:
        """Unregister a function from this event container."""
        for priority in self.priority_dictionary:
            for call_back in self.priority_dictionary[priority]:
                if call_back == func:
                    log_to(
                        [call_back.owner_id, self.created_by],
                        logging.DEBUG,
                        "unregister - %s - unregister function %s with priority %s",
                        self.name,
                        func,
                        priority,
                    )
                    del self.priority_dictionary[priority][call_back]
                    return True

        get_logger(self.created_by).error(
            "unregister - %s - could not find function %s", self.name, func.__name__
        )
        return False

    def getownerregistrations(self, owner_id):
        registrations = []
        for priority in self.priority_dictionary:
            registrations.extend(
                {"function_name": call_back.name, "priority": priority}
                for call_back in self.priority_dictionary[priority]
                if call_back.owner_id == owner_id
            )
        return registrations

    def removeowner(self, owner_id):
        """Remove all functions related to a owner."""
        plugins_to_unregister = []
        for priority in self.priority_dictionary:
            plugins_to_unregister.extend(
                call_back
                for call_back in self.priority_dictionary[priority]
                if call_back.owner_id == owner_id
            )
        for event_function in plugins_to_unregister:
            self.api("plugins.core.events:event.unregister")(self.name, event_function.func)
        # an unload during a raise must not leave the callback (and its owner) referenced
        if self.current_callback is not None and self.current_callback.owner_id == owner_id:
            self.current_callback = None

    def detail(self) -> list[str]:
        """Format a detail of the event."""
        header_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )
        subheader_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_subheader_color"
        )

        description = []
        for i, line in enumerate(self.description):
            if not line:
                continue
            if i == 0:
                description.append(f"{'Description':<13} : {line}")
            else:
                description.append(f"{'':<13}   {line}")

        message: list[str] = [
            f"{'Event':<13} : {self.name}",
            *description,
            f"{'Created by':<13} : {self.created_by}",
            f"{'Raised':<13} : {self.raised_count}",
            "",
            self.api("plugins.core.utils:string.center.colored")(
                "@x86Registrations@w", "-", 60, filler_color=header_color
            ),
            f"{'priority':<13} : {'owner':<25} - function name",
            subheader_color + "-" * 60 + "@w",
        ]
        function_message: list[str] = []
        key_list = self.priority_dictionary.keys()
        key_list = sorted(key_list)
        for priority in key_list:
            function_message.extend(
                f"{priority:<13} : {call_back.owner_id:<25} - {call_back.name}"
                for call_back in self.priority_dictionary[priority]
            )
        if not function_message:
            message.append("None")
        else:
            message.extend(function_message)
        message.extend((header_color + "-" * 60 + "@w", ""))
        message.append(
            self.api("plugins.core.utils:string.center.colored")(
                "@x86Data Keys@w", "-", 60, filler_color=header_color
            )
        )
        if self.arg_descriptions and "None" not in self.arg_descriptions:
            message.extend(
                f"@C{arg:<13}@w : {self.arg_descriptions[arg]}" for arg in self.arg_descriptions
            )
        elif "None" in self.arg_descriptions:
            message.append("None")
        else:
            message.append("Unknown")
        message.append(header_color + "-" * 60 + "@w")

        return message

    def raise_priority(
        self, priority, already_done: bool, done: "set[Callback] | None" = None
    ) -> bool:
        """Raise the event at a specific priority.

        done holds the callbacks already run by the current raise (one item of
        a data_list raise); it is per raise so a nested raise of the same event
        neither resets nor is skipped by the outer one (#281).
        """
        if done is None:
            done = set()
        found = False
        for call_back in list(self.priority_dictionary[priority].keys()):
            try:
                # A callback should call the api 'plugins.core.events:event.current.record.get'
                # which returns the current EventDataRecord
                # If the registered event changes the data, it should snapshot it with addupdate
                if call_back in self.priority_dictionary[priority] and call_back not in done:
                    self.current_callback = call_back
                    done.add(call_back)
                    with tracking_actor(f"{call_back.owner_id}:{call_back.name}"):
                        call_back.execute()
                    found = True
                    if already_done:
                        log_to(
                            [call_back.owner_id, self.created_by],
                            logging.WARNING,
                            "raise_event - event %s with function %s:%s was called out of order at priority %s",
                            self.name,
                            call_back.owner_id,
                            call_back.name,
                            priority,
                        )
                        log_to(
                            [call_back.owner_id, self.created_by],
                            logging.WARNING,
                            "    this is likely due to a function being registered at priority %s during the execution of the event",
                            priority,
                        )

            except Exception:  # pylint: disable=broad-except
                log_to(
                    [call_back.owner_id, self.created_by],
                    logging.ERROR,
                    "raise_event - event %s with function %s raised an exception",
                    self.name,
                    call_back.name,
                    exc_info=True,
                )

        return found

    def raise_event(
        self, data: dict | EventDataRecord, actor: str, data_list=None, key_name=None
    ) -> ProcessRaisedEvent | None:
        """Raise this event."""
        self.raised_count = self.raised_count + 1

        # If data is not a dict or EventDataRecord object, log an error and the event will not be processed
        if not isinstance(data, EventDataRecord) and not isinstance(data, dict):
            log_to(
                [self.created_by, "plugins.core.events"],
                logging.ERROR,
                "raise_event - event %s raised by %s did not pass a dict or EventDataRecord object",
                self.name,
                actor,
            )
            log_to(
                [self.created_by, "plugins.core.events"],
                logging.ERROR,
                "The event will not be processed",
            )
            return None

        if not isinstance(data, EventDataRecord):
            data = EventDataRecord(owner_id=actor, event_name=self.name, data=data)

        # if the created_by is not set, set it to the calledfrom argument
        if actor and not self.created_by:
            self.created_by = actor

        raised = ProcessRaisedEvent(self, data, actor)  # type: ignore
        # a nested raise of this event must hand the outer raise's state back
        previous_active_event = self.active_event
        previous_callback = self.current_callback
        self.active_event = raised
        self.raised_events[raised.uuid] = raised
        # evict the oldest before the callbacks run; a lowered cap shrinks here
        while len(self.raised_events) > max(0, self.MAX_RAISED_EVENTS):
            self.raised_events.popitem(last=False)
        try:
            raised(actor, data_list=data_list, key_name=key_name)
        finally:
            # the outermost raise restores None, so the last callback (and its
            # owner instance) is not kept alive after the raise
            self.active_event = previous_active_event
            self.current_callback = previous_callback
        return raised
