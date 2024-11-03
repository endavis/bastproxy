# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/eventargs.py
#
# File Description: Holds the record type for event arguments
#
# By: Bast
"""
Holds the log record type
"""
# Standard Library
import typing

# 3rd Party

# Project
from libs.records import BaseRecord, LogRecord, EventArgsRecord

if typing.TYPE_CHECKING:
    from _event import Event

class ProcessRaisedEvent(BaseRecord):
    def __init__(self, event: 'Event', args=None, called_from=''):
        BaseRecord.__init__(self)
        self.event = event
        self.called_from = called_from
        self.event_name = event.name
        self.arg_data = args
        self.current_arg_data = None
        self.id = f"{__name__}:{self.event.name}:{self.created}"
        self.addupdate('Info', 'Init', f"{self.id}:init")

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.__class__.__name__:<20} {self.uuid} {self.execute_time_taken:.2f}ms {self.event_name} "

    def _exec_(self, actor, **kwargs):
        """
        process the event
        """
        if 'data_list' in kwargs and kwargs['data_list'] and 'key_name' in kwargs:
            self._exec_multi(actor, **kwargs)
        else:
            self._exec_once(actor, **kwargs)

    def _exec_multi(self, *args, **kwargs):
        """
        process the event
        """
        for item in kwargs['data_list']:
            self.arg_data = {kwargs['key_name']: item}
            self._exec_once(*args, **kwargs)

    def _exec_once(self, actor, **kwargs):
        """
        exec it with self.arg_data
        """
        # Any standard dictionary will be converted to a EventArgsRecord object
        if not self.arg_data:
            self.arg_data = {}

        # If data is not a dict or EventArgsRecord object, log an error and the event will not be processed
        if not isinstance(self.arg_data, EventArgsRecord) and not isinstance(self.arg_data, dict):
            LogRecord(f"raise_event - event {self.event_name} raised by {self.called_from} did not pass a dict or EventArgsRecord object",
                        level='error', sources=[self.called_from, self.event.created_by, 'plugins.core.events'])()
            LogRecord(
                "The event will not be processed",
                level='error',
                sources=[self.called_from, self.event.created_by, 'plugins.core.events'],
            )()
            return None

        if not isinstance(self.arg_data, EventArgsRecord):
            data = EventArgsRecord(owner_id=self.called_from, event_name=self.event_name, data=self.arg_data)
        else:
            data = self.arg_data
        self.current_arg_data = data
        data.parent = self

        # log the event if the log_savestate setting is True or if the event is not a _savestate event
        log_savestate = self.api('plugins.core.settings:get')('plugins.core.events', 'log_savestate')
        log: bool = True if log_savestate else not self.event_name.endswith('_savestate')

        if log:
            LogRecord(f"raise_event - event {self.event_name} raised by {self.called_from} with data {data}",
                      level='debug', sources=[self.called_from, self.event.created_by])()

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
                    found_callbacks = self.event.raise_priority(priority, priority in priorities_done)
                    priorities_done.append(priority)

        if count > 2: # the minimum number of times through the loop is 2
            LogRecord(f"raise_event - event {self.event_name} raised by {self.called_from} was processed {count} times",
                        level='warning', sources=[self.event.created_by])()

        self.current_record = None
        self.current_callback = None
        self.event.reset_event()

        return data

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].extend([('Event Name', 'event_name'), ('Called From', 'called_from'),
                              ('Event Data', 'arg_data')])
        return attributes

    def format_simple(self):
        subheader_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_subheader_color')
        message = [
                self.api('plugins.core.utils:center.colored.string')(
                    f'{subheader_color}Stack: {self.created}@w',
                    '-',
                    50,
                    filler_color=subheader_color,
                ),
                f"Called from : {self.called_from:<13}@w",
                f"Timestamp   : {self.created}@w",
                f"Data        : {self.arg_data}@w"
            ]

        message.append(self.api('plugins.core.utils:center.colored.string')(f'{subheader_color}Event Stack@w', '-', 40, filler_color=subheader_color))
        message.extend([f"  {event}" for event in self.event_stack])
        message.append(self.api('plugins.core.utils:center.colored.string')(f'{subheader_color}Function Stack@w', '-', 40, filler_color=subheader_color))
        message.extend([f"{call}" for call in self.stack_at_creation])

        return message

