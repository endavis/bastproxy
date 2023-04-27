# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/tomud.py
#
# File Description: Holds the tomud record type
#
# By: Bast
"""
Holds the tomud record type
"""
# Standard Library
import re

# 3rd Party

# Project
from libs.records.rtypes.base import BaseListRecord
from libs.records.rtypes.log import LogRecord

SETUPEVENTS = False

class ToMudRecord(BaseListRecord):
    """
    a record to the mud, all client data will start as this type of record
    data from a client will be immediately transformed into this type of record
    this record will go through execute first
    it may not end up going to the mud depending on if it is a proxy command

    The message format is a list of strings

    line endings will be added to each line before sending to the mud

    Valid message_types:
        'IO' - a regular string to send to the client
        'TELNET-COMMAND' - a telnet command to the client
    when it goes on the client queue, it will be converted to a NetworkData object
    """
    def __init__(self, message: list[str | bytes] | list[str] | list[bytes] | str | bytes, message_type: str = 'IO', internal: bool = False,
                 show_in_history: bool = True, client_id = None):
        """
        initialize the class
        """
        super().__init__(message, message_type, internal)
        self.show_in_history = show_in_history
        self.send_to_mud = True
        self.client_id = client_id
        self.modify_data_event_name = 'ev_to_mud_data_modify'
        self.read_data_event_name = 'ev_to_mud_data_read'
        self.items_to_format_in_details.extend([('Show in History', 'show_in_history'),
                                                ('Send to Mud', 'send_to_mud'),
                                                ('Client ID', 'client_id')])
        self.setup_events()

    def setup_events(self):
        global SETUPEVENTS
        if not SETUPEVENTS:
            SETUPEVENTS = True
            self.api('plugins.core.events:add.event')(self.modify_data_event_name, __name__,
                                                description='An event to modify data before it is sent to the mud',
                                                arg_descriptions={'line': 'The line to modify',
                                                                  'sendtoclient': 'A flag to determine if this line should be sent to the mud'})
            self.api('plugins.core.events:add.event')(self.read_data_event_name, __name__,
                                                description='An event to see data that was sent to the mud',
                                                arg_descriptions={'ToClientRecord': 'A libs.records.ToClientRecord object'})

    def prepare(self, actor):
        """
        prepare the record for sending to the mud

        this will split the data along the command seperator and along newlines
        """
        self.addupdate('Info', f"{'Start':<8}: Prepare", f"{actor}:prepare", savedata=False,
                       extra={'msg': 'split the data along the command seperator and along newlines'})

        new_message = []
        for item in self:
            line = item.strip()

            # split the line along newlines
            lines = line.split('\r\n')
            if len(lines) > 1:
                self.addupdate('Info', "split (CRLF)", f"{actor}:prepare",
                               extra={'line':line, 'newlines':lines,
                                      'msg': 'split the data along newlines'},
                               savedata=False)

            for line in lines:
                # split the line if it has the command seperator in it
                if self.api.command_split_regex:
                    split_data = re.split(self.api.command_split_regex, line)
                else:
                    split_data = [line]
                if len(split_data) > 1:
                    self.addupdate('Info', "split (Split_Char)", f"{actor}:prepare",
                                   extra={'line':line, 'newlines':split_data,
                                          'msg': 'split the data along the command seperator'},
                                    savedata=False)
                    new_message.extend(split_data)
                else:
                    new_message.append(line)

        self.replace(new_message, actor=f"{actor}:prepare")

        self.addupdate('Info', f"{'Complete':<8}: Prepare", f"{actor}:prepare", savedata=False)

    def fix_double_command_seperator(self, actor):
        """
        fix double command seperators

        take out double command seperators and replaces them with a single one before
        sending the data to the mud
        """
        self.addupdate('Info', f"{'Start':<8}: Fix Double Command Seperator", f"{actor}:fix_double_command_seperator", savedata=False,
                       extra={'msg': 'take out double command seperators and replaces them with a single one'})
        new_message = []
        for line in self:
            current_line = line.replace('||', '|')
            new_message.append(current_line)

        self.replace(new_message, actor=f"{actor}:fix_double_command_seperator")

        self.addupdate('Info', f"{'Complete':<8}: Fix Double Command Seperator", f"{actor}:fix_double_command_seperator", savedata=False)

    def format(self, actor):
        """
        format the record for sending to the mud
        """
        if not self.internal and self.is_io:
            self.addupdate('Info', f"{'Start':<8}: Format", f"{actor}:format", savedata=False)
            self.add_line_endings(f"{actor}:format")
            self.color_lines('', f"{actor}:format")
            self.fix_double_command_seperator(f"{actor}:format")
            self.addupdate('Info', f"{'Complete':<8}: Format", f"{actor}:format", savedata=False)

    def send(self, actor):
        """
        send the record to the mud
        """
        if self.sending:
            LogRecord(f"LogRecord: {self.uuid} is already sending",
                                level='debug', stack_info=True, sources=[__name__]).send()
            return
        self.addupdate('Info', f"{'Start':<8}: send", actor, savedata=False)

        # non-io and anything generated internally do not go through the mud_data_modify event
        if not self.internal and self.is_io:
            self.prepare(f"{actor}:send")
            new_message = []
            for line in self:
                event_args = self.api('plugins.core.events:raise.event')(self.modify_data_event_name,
                                                            {'line':line,
                                                            'internal':self.internal,
                                                            'showinhistory':self.show_in_history,
                                                            'sendtomud':True,
                                                            'client_id':self.client_id,})

                if event_args['line'] != line:
                    self.addupdate('Modify', f"event:{self.modify_data_event_name} modified line" ,
                                    f"{actor}:send:{self.modify_data_event_name}", extra={'line':line, 'newline':event_args['data']}, savedata=False)
                    self.add_related_record(event_args)

                if event_args['sendtomud']:
                    new_message.append(event_args['line'])
                else:
                    self.addupdate('Modify', f"event:{self.modify_data_event_name}: line removed because sendtomud was set to False",
                                    f"{actor}:send:{self.modify_data_event_name}", extra={'line':line},
                                    savedata=False)
                    self.add_related_record(event_args)

            self.replace(new_message, f"{actor}:{self.modify_data_event_name}")
            self.addupdate('Info', f'Data after event {self.modify_data_event_name}', f"{actor}:send")

        if self.send_to_mud and self:
            self.format(f"{actor}:send")
            mud_connection = self.api('plugins.core.proxy:get.mud.connection')()
            mud_connection.send_to(self)

        if self.is_io:
            self.api('plugins.core.events:raise.event')(self.read_data_event_name, args={'ToMudRecord': self})

        self.addupdate('Info', f"{'Complete':<8}: send", f"{actor}:send", savedata=False)
