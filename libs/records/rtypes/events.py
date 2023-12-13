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

# 3rd Party

# Project
from libs.records.rtypes.base import BaseDictRecord, BaseRecord


class EventArgsRecord(BaseDictRecord):
    def __init__(self, owner_id: str = '', event_name: str = 'unknown', data: dict | None = None):
        """
        initialize the class
        """
        BaseDictRecord.__init__(self, owner_id, data)
        self.event_name = event_name

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.event_name}"

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].append(('Event Name', 'event_name'))
        return attributes

class RaisedEventRecord(BaseRecord):
    def __init__(self, event_name: str, called_from):
        BaseRecord.__init__(self)
        self.event_name = event_name
        self.called_from = called_from
        self.arg_data : EventArgsRecord | None = None
        self.id = f"{__name__}:{self.event_name}:{self.created}"
        self.addupdate('Info', 'Init', f"{self.id}:init")

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.event_name}"

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

