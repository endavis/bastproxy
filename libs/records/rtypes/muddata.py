# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/muddata.py
#
# File Description: Holds the tomuddata record type
#
# By: Bast
"""
Holds the tomud record type
"""
# Standard Library
import re
import typing

# 3rd Party

# Project
from libs.records.rtypes.base import BaseRecord
from libs.records.rtypes.log import LogRecord
from libs.records.rtypes.networkdata import NetworkDataLine, NetworkData

SETUPEVENTS = False

class ToMudData(BaseRecord):
    """
    a record to the mud, all client data will start as this type of record.
    data from a client will be immediately transformed into this type of record
    this record will go through execute first
    it may not end up going to the mud depending on if it is a proxy command

    The message format is NetworkData instance

    line endings will be added to each line before sending to the mud

    Valid message_types:
        'IO' - a regular string to send to the client
        'TELNET-COMMAND' - a telnet command to the client
    when it goes on the client queue, it will be converted to a NetworkDataLine object
    """
    def __init__(self,  message: 'NetworkData',
                 show_in_history: bool = True, client_id = None):
        """
        initialize the class
        """
        super().__init__()
        self.message = message
        self.show_in_history = show_in_history
        self.client_id = client_id
        self.modify_data_event_name = 'ev_to_mud_data_modify'
        self.read_data_event_name = 'ev_to_mud_data_read'
        self.sending = False
        self.setup_events()

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].extend([('Show in History', 'show_in_history'),
                              ('Client ID', 'client_id')])
        return attributes

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f'{self.__class__.__name__:<20} {self.uuid} {len(self.message)} {self.execute_time_taken:.2f}ms {repr(self.message.get_first_line())}'

    def setup_events(self):
        global SETUPEVENTS
        if not SETUPEVENTS:
            SETUPEVENTS = True
            self.api('plugins.core.events:add.event')(self.modify_data_event_name, __name__,
                                                description=['An event to modify data before it is sent to the mud'],
                                                arg_descriptions={'line': 'The line to modify, a NetworkDataLine instance',
                                                                  'showinhistory': 'If the data should be shown in the history',
                                                                  'client_id': 'The client id it came from'})
            self.api('plugins.core.events:add.event')(self.read_data_event_name, __name__,
                                                description=['An event to see data that was sent to the mud'],
                                                arg_descriptions={'line': 'The line to modify, a NetworkDataLine instance'})

    def seperate_commands(self):
        new_message = NetworkData([])
        for line in self.message:
            if line.is_io and isinstance(line.line, str):
                split_data = []
                if self.api.command_split_regex:
                    split_data = re.split(self.api.command_split_regex, line.line)
                if len(split_data) > 1:
                    self.addupdate('Info', "split (Split_Char)", f"ToMudData:{self.uuid}:prepare",
                                    extra={'line':line, 'newlines':split_data,
                                            'msg': 'split the data along the command seperator'})
                    line.line = split_data.pop(0)
                    new_message.append(line)
                    new_message.extend(
                        NetworkDataLine(newline, line_type=line.line_type, originated=line.originated)
                        for newline in split_data # type: ignore
                    )
                else:
                    new_message.append(line)
            else:
                new_message.append(line)
        self.message = new_message

    def _exec_(self, actor):
        """
        send the record to the mud
        """
        if self.sending:
            LogRecord(f"LogRecord: {self.uuid} is already sending",
                                level='debug', stack_info=True, sources=[__name__])()
            return

        self.sending = True
        self.addupdate('Info', f"{'Start':<8}: send", actor)

        self.seperate_commands()

        line: 'NetworkDataLine'
        for line in self.message:
            # If it came from a client and it is not a telnet command,
            # pass each line through the event system to allow plugins to modify it

            if not line.internal and line.is_io:
                self.api('plugins.core.events:raise.event')(self.modify_data_event_name,
                                                             {'line':line,
                                                             'showinhistory':self.show_in_history,
                                                             'client_id':self.client_id,})

            # If it came from the proxy and it is not a telnet command,
            # pass each line through the event system to allow plugins to see what
            # data is being sent to the mud

            if line.send:
                line.format()
                if mud_connection := self.api('plugins.core.proxy:get.mud.connection')():
                    mud_connection.send_to(line)

                if line.is_io:
                    self.api('plugins.core.events:raise.event')(self.read_data_event_name, args={'line': line.line})

        self.addupdate('Info', f"{'Complete':<8}: send", f"{actor}:send")
        self.sending = False
