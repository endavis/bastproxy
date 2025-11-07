# Project: bastproxy
# Filename: libs/records/rtypes/eventargs.py
#
# File Description: Holds the record type for event arguments
#
# By: Bast
"""Holds the log record type"""

# Standard Library
from typing import TYPE_CHECKING

# 3rd Party
# Project
from libs.records import BaseRecord, LogRecord

if TYPE_CHECKING:
    from _event import Event

    from plugins.core.events.libs.data._event import EventDataRecord


class ProcessRaisedEvent(BaseRecord):
    def __init__(self, event: "Event", event_data: "EventDataRecord", called_from=""):
        BaseRecord.__init__(self)
        self.event = event
        self.called_from = called_from
        self.event_name = event.name
        self.event_data = event_data
        self.event_data.parent = self
        self.event_data.add_parent(self, reset=True)
        self.times_invoked = 0
        self.id = f"{__name__}:{self.event.name}:{self.created}"
        self.addupdate("Info", "Init")

    def one_line_summary(self):
        """Get a one line summary of the record"""
        return f"{self.__class__.__name__:<20} {self.uuid} {self.execute_time_taken:.2f}ms {self.event_name} {self.times_invoked}"

    def _exec_(self, actor, *args, **kwargs):
        """Process the event"""
        if "data_list" in kwargs and kwargs["data_list"] and "key_name" in kwargs:
            self._exec_multi(actor, *args, **kwargs)
        else:
            self._exec_once(actor, *args, **kwargs)

    def _exec_multi(self, *args, **kwargs):
        """Process the event"""
        for item in kwargs["data_list"]:
            self.event_data[kwargs["key_name"]] = item
            self._exec_once(*args, **kwargs)

    def _exec_once(self, actor, **kwargs):
        """Exec it with self.arg_data"""
        self.times_invoked += 1
        self.addupdate("Info", "Invoked", extra={"data": f"{self.event_data.data}"})

        # log the event if the log_savestate setting is True or if the event is not a _savestate event
        log_savestate = self.api("plugins.core.settings:get")(
            "plugins.core.events", "log_savestate"
        )
        log: bool = (
            True if log_savestate else not self.event_name.endswith("_savestate")
        )

        if log:
            LogRecord(
                f"raise_event - event {self.event_name} raised by {self.called_from} with data {self.event_data}",
                level="debug",
                sources=[self.called_from, self.event.created_by],
            )()

        # convert a dict to an EventArgsRecord object

        # This checks each priority seperately and executes the functions in order of priority
        # A while loop is used to ensure that if a function is added to the event during the execution of the same event
        # it will be processed in the same order as the other functions
        # This means that any registration added during the execution of the event will be processed
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
                    found_callbacks = self.event.raise_priority(
                        priority, priority in priorities_done
                    )
                    priorities_done.append(priority)

        if count > 2:  # the minimum number of times through the loop is 2
            LogRecord(
                f"raise_event - event {self.event_name} raised by {self.called_from} was processed {count} times",
                level="warning",
                sources=[self.event.created_by],
            )()

        self.current_record = None
        self.current_callback = None
        self.event.reset_event()

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
        subheader_color = self.api("plugins.core.settings:get")(
            "plugins.core.commands", "output_subheader_color"
        )
        message = [
            self.api("plugins.core.utils:center.colored.string")(
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
            self.api("plugins.core.utils:center.colored.string")(
                f"{subheader_color}Event Stack@w", "-", 40, filler_color=subheader_color
            )
        )
        message.extend([f"  {event}" for event in self.event_stack])
        message.append(
            self.api("plugins.core.utils:center.colored.string")(
                f"{subheader_color}Function Stack@w",
                "-",
                40,
                filler_color=subheader_color,
            )
        )
        message.extend([f"{call}" for call in self.stack_at_creation])

        return message
