# Project: bastproxy
# Filename: plugins/core/events/libs/process/_raisedevent.py
#
# File Description: Holds the record for one raise of an event
#
# By: Bast
"""Holds ProcessRaisedEvent, the record for one raise of an event.

It runs the event's callbacks in priority order for each item of data the
raise carries.
"""

# Standard Library
import logging
from typing import TYPE_CHECKING

from bastproxy.libs.logger import get_logger, log_to

# 3rd Party
# Project
from bastproxy.libs.records import BaseRecord, UpdateFlag

if TYPE_CHECKING:
    from bastproxy.libs.callback import Callback
    from bastproxy.plugins.core.events.libs.data._event import EventDataRecord
    from bastproxy.plugins.core.events.plugin._event import Event


class ProcessRaisedEvent(BaseRecord):
    def __init__(self, event: "Event", event_data: "EventDataRecord", called_from=""):
        BaseRecord.__init__(self)
        self.event = event
        self.called_from = called_from
        self.event_name = event.name
        self.event_data = event_data
        self.event_data.add_receiving_event(self)
        self.times_invoked = 0
        self.done: set[Callback] = set()
        self.id = f"{__name__}:{self.event.name}:{self.created}"
        self.addupdate(UpdateFlag.INFO, "Init")

    def one_line_summary(self):
        """Get a one line summary of the record."""
        return f"{self.__class__.__name__:<20} {self.uuid} {self.execute_time_taken:.2f}ms {self.event_name} {self.times_invoked}"

    def _exec_(self, actor, *args, **kwargs):
        """Process the event."""
        if "data_list" in kwargs and kwargs["data_list"] and "key_name" in kwargs:
            self._exec_multi(actor, *args, **kwargs)
        else:
            self._exec_once(actor, *args, **kwargs)

    def _exec_multi(self, *args, **kwargs):
        """Process the event."""
        for item in kwargs["data_list"]:
            self.event_data[kwargs["key_name"]] = item
            self._exec_once(*args, **kwargs)

    def _exec_once(self, actor, **kwargs):
        """Exec it with self.arg_data."""
        self.times_invoked += 1
        # callbacks run for this item; fresh per item so every item runs every callback
        self.done = set()
        self.addupdate(UpdateFlag.INFO, "Invoked", extra={"data": f"{dict(self.event_data)}"})

        # log the event if the log_savestate setting is True or if the event is not a _savestate event
        log_savestate = self.api("plugins.core.settings:setting.get")(
            "plugins.core.events", "log_savestate"
        )
        log: bool = True if log_savestate else not self.event_name.endswith("_savestate")

        if log:
            log_to(
                [self.called_from, self.event.created_by],
                logging.DEBUG,
                "raise_event - event %s raised by %s with data %s",
                self.event_name,
                self.called_from,
                self.event_data,
            )

        # Each pass visits the priorities in ascending order and runs each callback once per
        # raise (tracked in self.done). The loop repeats while any priority in a pass ran a
        # callback (found_callbacks is OR-ed across priorities, #275), so a callback registered
        # during the raise runs in a later pass, after the higher-priority callbacks already ran
        # in the first pass. That is not priority order; raise_priority logs an out-of-order
        # warning when already_done.
        priorities_done = []

        found_callbacks = True
        count = 0
        while found_callbacks:
            count = count + 1
            found_callbacks = False
            if keys := list(self.event.priority_dictionary.keys()):
                keys = sorted(keys)
                if len(keys) < 1:
                    found_callbacks = False
                    continue
                for priority in keys:
                    # keep looping while any priority in this pass ran a callback;
                    # the last priority alone can run nothing on a later pass
                    ran = self.event.raise_priority(
                        priority, priority in priorities_done, self.done
                    )
                    found_callbacks = found_callbacks or bool(ran)
                    priorities_done.append(priority)

        if count > 2:  # the minimum number of times through the loop is 2
            get_logger(self.event.created_by).warning(
                "raise_event - event %s raised by %s was processed %s times",
                self.event_name,
                self.called_from,
                count,
            )

        self.current_record = None
        # raised_events keeps this record; do not keep callbacks (and their owners) alive
        self.done = set()

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].extend(
            [
                ("Event Name", "event_name"),
                ("Called From", "called_from"),
                ("Event Data", "arg_data"),
            ]
        )
        return attributes

    def format_simple(self):
        subheader_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_subheader_color"
        )
        message = [
            self.api("plugins.core.utils:string.center.colored")(
                f"{subheader_color}Stack: {self.created}@w",
                "-",
                50,
                filler_color=subheader_color,
            ),
            f"Called from : {self.called_from:<13}@w",
            f"Timestamp   : {self.created}@w",
            f"Data        : {self.event_data}@w",
        ]

        message.append(
            self.api("plugins.core.utils:string.center.colored")(
                f"{subheader_color}Event Stack@w", "-", 40, filler_color=subheader_color
            )
        )
        message.extend([f"  {event}" for event in self.event_stack])
        message.append(
            self.api("plugins.core.utils:string.center.colored")(
                f"{subheader_color}Function Stack@w",
                "-",
                40,
                filler_color=subheader_color,
            )
        )
        message.extend([f"{call}" for call in self.stack_at_creation])

        return message
